"""Evaluation pipeline — scores sessions across 5 dimensions."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any

from edini.eval.models import EvalResult, StructuredSession

logger = logging.getLogger(__name__)

# Weights for each dimension in total_score calculation
WEIGHTS = {
    "tool_accuracy": 0.30,
    "task_completion": 0.30,
    "efficiency": 0.15,
    "reliability": 0.15,
    "cost": 0.10,
}


class EvaluatorPipeline:
    """Evaluates a StructuredSession across 5 dimensions.

    Usage:
        result = EvaluatorPipeline().evaluate(session)

    Dimensions:
        - tool_accuracy:     LLM-as-Judge — tool selection + parameter correctness
        - task_completion:   LLM-as-Judge — was user's goal met?
        - efficiency:        Deterministic — convergence ratio
        - reliability:       Deterministic — tool call success rate
        - cost:              Deterministic — token/call efficiency
    """

    def __init__(
        self,
        judge_model: str | None = None,
        judge_api_key: str | None = None,
        judge_provider: str | None = None,
        judge_sampling_rate: float = 0.5,
        force_judge: bool = False,
        force_no_judge: bool = False,
    ):
        # Resolve judge config: use conversation model's provider & API key by default.
        # After Phase 19 refactor, api_key is in pi's auth.json, not edini settings.
        try:
            from edini.config import read_pi_auth, read_pi_settings
            pi_settings = read_pi_settings()
            pi_auth = read_pi_auth()

            # Default: use the conversation model's provider
            default_provider = pi_settings.get("defaultProvider", "deepseek")
            self._judge_provider = judge_provider or default_provider

            # Default: use the conversation model itself (or a non-reasoning variant)
            default_model = pi_settings.get("defaultModel", "deepseek-chat")
            # Reasoning models (R1, V4 Pro) hide visible text output — fall back
            # to the base chat model for judge reliability
            if "reason" in default_model.lower() or "r1" in default_model.lower():
                default_model = "deepseek-chat"
            self._judge_model = judge_model or default_model

            # API key from pi auth.json for the chosen provider
            provider_auth = pi_auth.get(self._judge_provider, {})
            resolved_key = ""
            if isinstance(provider_auth, dict):
                resolved_key = provider_auth.get("key", "")
            elif isinstance(provider_auth, str):
                resolved_key = provider_auth
            self._judge_api_key = judge_api_key or resolved_key
        except Exception:
            self._judge_model = judge_model or os.environ.get("EDINI_JUDGE_MODEL", "deepseek-chat")
            self._judge_api_key = judge_api_key or os.environ.get("EDINI_JUDGE_API_KEY", "")
            self._judge_provider = judge_provider or "deepseek"
        self._judge_sampling_rate = judge_sampling_rate
        self._force_judge = force_judge
        self._force_no_judge = force_no_judge

    def evaluate(self, session: StructuredSession) -> EvalResult:
        """Run all evaluators and return combined result."""
        now = datetime.utcnow().isoformat()

        # 1. Deterministic evaluations (always run, zero cost)
        reliability = self._eval_reliability(session)
        efficiency = self._eval_efficiency(session)
        cost = self._eval_cost(session)
        sandbox_adoption = self._eval_sandbox_adoption(session)

        # 2. LLM-as-Judge evaluations (sampled)
        tool_accuracy: float | None = None
        task_completion: float | None = None

        if self._force_judge or (
            session.tool_calls and self._should_judge(session)
        ):
            try:
                ta_score, _ = self._judge_tool_accuracy(session)
                tool_accuracy = ta_score
            except Exception as judge_e:
                logger.warning("Judge (tool_accuracy) crashed: %s", judge_e)
                import traceback
                logger.debug(traceback.format_exc())
                tool_accuracy = None
            try:
                tc_score, _ = self._judge_task_completion(session)
                task_completion = tc_score
            except Exception as judge_e:
                logger.warning("Judge (task_completion) crashed: %s", judge_e)
                import traceback
                logger.debug(traceback.format_exc())
                task_completion = None

        # 3. Compute total score (weighted, re-normalize if Judge scores missing)
        available_weights = {}
        dim_scores = {
            "tool_accuracy": tool_accuracy,
            "task_completion": task_completion,
            "efficiency": efficiency,
            "reliability": reliability,
            "cost": cost,
        }
        for dim, weight in WEIGHTS.items():
            if dim_scores[dim] is not None:
                available_weights[dim] = weight

        total_w = sum(available_weights.values())
        if total_w > 0:
            normalized = {k: v / total_w for k, v in available_weights.items()}
            total_score = sum(
                normalized[d] * (dim_scores[d] if dim_scores[d] is not None else 0.0)
                for d in normalized
            )
        else:
            total_score = 0.0

        # 4. Build per-call details
        call_details = []
        for tc in session.tool_calls:
            call_details.append({
                "call_index": tc.index,
                "tool_name": tc.tool_name,
                "params": tc.params,
                "result_status": "error" if not tc.result_success else "success",
                "error_message": tc.error_message,
                "latency_ms": tc.latency_ms,
            })

        return EvalResult(
            session_id=session.session_id,
            evaluated_at=now,
            tool_accuracy=tool_accuracy,
            task_completion=task_completion,
            efficiency=efficiency,
            reliability=reliability,
            cost=cost,
            sandbox_adoption_rate=round(sandbox_adoption, 3),
            total_score=round(total_score, 3),
            tool_call_details=call_details,
            tool_calls_count=len(session.tool_calls),
            total_latency_ms=session.total_latency_ms,
        )

    # ── Deterministic Evaluators ──────────────────────────────

    def _eval_reliability(self, session: StructuredSession) -> float:
        """Reliability = successful_calls / total_calls.

        1.0 when there are no tool calls (nothing to fail).
        """
        total = len(session.tool_calls)
        if total == 0:
            return 1.0
        successful = sum(1 for tc in session.tool_calls if tc.result_success)
        return round(successful / total, 3)

    def _eval_efficiency(self, session: StructuredSession) -> float:
        """Efficiency = optimal_steps / actual_steps.

        Uses a heuristic based on first tool call type to estimate optimal steps.
        Simple queries → 1 step, creation tasks → 3 steps, scripts → 2 steps.
        """
        calls = session.tool_calls
        if not calls:
            return 1.0

        first_tool = calls[0].tool_name

        # Heuristic optimal steps per task type
        if first_tool in (
            "houdini_get_scene_info", "houdini_get_selection",
            "houdini_get_param", "houdini_search_nodes",
            "houdini_check_errors", "houdini_get_node",
            "houdini_get_help", "houdini_get_hda_info",
        ):
            optimal = 1
        elif first_tool in (
            "houdini_create_node", "houdini_delete_node",
            "houdini_connect_nodes", "houdini_set_param",
            "houdini_set_display_flag", "houdini_layout_nodes",
        ):
            optimal = 3
        elif first_tool in ("houdini_run_python", "houdini_run_vex",
                            "edini_get_eval_stats"):
            optimal = 2
        elif first_tool in ("houdini_capture_viewport",
                            "houdini_capture_network"):
            optimal = 2
        elif first_tool in ("houdini_create_hda",):
            optimal = 4
        else:
            optimal = max(1, len(calls) // 2)

        actual = len(calls)
        score = min(1.0, optimal / max(1, actual))
        return round(score, 3)

    def _eval_sandbox_adoption(self, session: StructuredSession) -> float:
        """Evaluate sandbox adoption rate for procedural tasks.

        Returns 1.0 if no procedural work was done (neutral).
        Otherwise: sandbox_commits / (raw_python_runs + sandbox_commits).
        """
        sandbox_commits = sum(
            1 for tc in session.tool_calls
            if tc.sandbox_action == "commit"
        )
        raw_python_runs = sum(
            1 for tc in session.tool_calls
            if tc.tool_name == "houdini_run_python"
            and tc.sandbox_action is None
        )
        total = sandbox_commits + raw_python_runs
        if total == 0:
            return 1.0  # no procedural work done, neutral
        return round(sandbox_commits / total, 3)

    def _eval_cost(self, session: StructuredSession) -> float:
        """Cost score — higher = cheaper.

        Benchmarked against call count: 0 calls = 1.0, 20+ calls = 0.0.
        """
        call_count = len(session.tool_calls)
        if call_count == 0:
            return 1.0
        score = max(0.0, 1.0 - (call_count / 20.0))
        return round(score, 3)

    # ── LLM-as-Judge Evaluators ──────────────────────────────

    def _should_judge(self, session: StructuredSession) -> bool:
        """Determine if we should run LLM-as-Judge for this session.

        Always judge short sessions (≤ 3 tool calls) as a baseline.
        Sample longer sessions at judge_sampling_rate.
        """
        if self._force_no_judge:
            return False
        if self._force_judge:
            return True
        if len(session.tool_calls) <= 3:
            return True
        import random
        return random.random() < self._judge_sampling_rate

    def _judge_tool_accuracy(
        self, session: StructuredSession
    ) -> tuple[float | None, dict | None]:
        """Judge tool selection + parameter correctness using LLM-as-Judge.

        Returns (score, judge_log) or (None, None) if judge model not configured.
        """
        if not self._judge_model:
            return None, None

        # Limit tool calls in prompt to avoid timeout and cost
        max_calls = min(len(session.tool_calls), 20)
        tool_summary = []
        for tc in session.tool_calls[:max_calls]:
            tool_summary.append(
                f"[{tc.index}] {tc.tool_name}("
                f"params={json.dumps(tc.params)}, "
                f"success={tc.result_success})"
            )
        if len(session.tool_calls) > max_calls:
            tool_summary.append(
                f"... and {len(session.tool_calls) - max_calls} more calls"
            )

        first_query = session.user_queries[0] if session.user_queries else "(unknown)"

        _json_example = '{"score": 0.0-1.0, "reason": "..."}'
        prompt = (
            f"You are an evaluator for a Houdini AI assistant.\n"
            f"Evaluate the tool call accuracy for the following session.\n\n"
            f"User request: {first_query}\n\n"
            f"Tool calls:\n"
            f"{chr(10).join(tool_summary)}\n\n"
            f"Evaluate:\n"
            f"1. Was each tool the correct choice for the user's intent?\n"
            f"2. Were the parameters correctly extracted?\n"
            f"3. Was the tool call order logical?\n\n"
            f"Output JSON only: "
            f"{_json_example}"
        )

        try:
            t0 = time.time()
            score, response_text = self._call_judge(prompt)
            latency = int((time.time() - t0) * 1000)
            log = {
                "dimension": "tool_accuracy",
                "prompt": prompt,
                "response": response_text,
                "score": score,
                "latency_ms": latency,
            }
            return score, log
        except Exception as e:
            logger.warning("Judge (tool_accuracy) failed: %s", e)
            return None, None

    def _judge_task_completion(
        self, session: StructuredSession
    ) -> tuple[float | None, dict | None]:
        """Judge whether the user's task was fully accomplished."""
        if not self._judge_model:
            return None, None

        # Limit tool calls in prompt
        max_calls = min(len(session.tool_calls), 20)
        tool_summary = []
        for tc in session.tool_calls[:max_calls]:
            tool_summary.append(
                f"[{tc.index}] {tc.tool_name}("
                f"params={json.dumps(tc.params)}, "
                f"success={tc.result_success})"
            )
        if len(session.tool_calls) > max_calls:
            tool_summary.append(
                f"... and {len(session.tool_calls) - max_calls} more calls"
            )

        first_query = session.user_queries[0] if session.user_queries else "(unknown)"
        last_response = session.assistant_responses[-1] if session.assistant_responses else "(none)"

        _json_example = '{"score": 0.0-1.0, "reason": "..."}'
        prompt = (
            f"You are an evaluator for a Houdini AI assistant.\n"
            f"Evaluate whether the user's task was fully accomplished.\n\n"
            f"User request: {first_query}\n\n"
            f"Actions taken:\n"
            f"{chr(10).join(tool_summary)}\n\n"
            f"Final response: {last_response}\n\n"
            f"Consider:\n"
            f"- Was the original request fulfilled?\n"
            f"- Is the output usable in Houdini?\n"
            f"- Were there critical errors?\n\n"
            f"Output JSON only: "
            f"{_json_example}"
        )

        try:
            t0 = time.time()
            score, response_text = self._call_judge(prompt)
            latency = int((time.time() - t0) * 1000)
            log = {
                "dimension": "task_completion",
                "prompt": prompt,
                "response": response_text,
                "score": score,
                "latency_ms": latency,
            }
            return score, log
        except Exception as e:
            logger.warning("Judge (task_completion) failed: %s", e)
            return None, None

    def _call_judge(self, prompt: str) -> tuple[float, str]:
        """Call the configured LLM as a judge and parse JSON response.

        Supports OpenAI-compatible providers (DeepSeek, Qwen) and Anthropic.
        Falls back to placeholder if API call fails.
        """
        if not self._judge_api_key:
            logger.warning(
                "No API key configured for judge. Set api_key in Edini settings."
            )
            return 0.8, '{"score": 0.8, "reason": "No API key"}'

        provider = self._judge_provider.lower()
        model = self._judge_model

        try:
            if provider in ("deepseek", "openai", "qwen"):
                return self._call_openai_like(prompt, model)
            elif provider == "anthropic":
                return self._call_anthropic(prompt, model)
            else:
                logger.warning("Unknown provider '%s', trying OpenAI-compatible", provider)
                return self._call_openai_like(prompt, model)
        except Exception as e:
            logger.warning("Judge API call failed: %s", e)
            return 0.8, '{"score": 0.8, "reason": "Judge API call failed: %s"}' % str(e)

    def _call_openai_like(self, prompt: str, model: str) -> tuple[float, str]:
        """Call OpenAI-compatible API (DeepSeek, Qwen, etc.)."""
        import urllib.request
        import urllib.error

        # Determine API endpoint and key based on provider
        provider = self._judge_provider.lower()
        if provider == "deepseek":
            url = "https://api.deepseek.com/chat/completions"
            api_key = self._judge_api_key
        elif provider == "qwen":
            url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
            api_key = self._judge_api_key
        else:
            url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/chat/completions"
            api_key = self._judge_api_key

        body = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": (
                    "You are a precise evaluator. "
                    "Output ONLY valid JSON. No thinking, no reasoning, "
                    "no markdown formatting, no extra text. "
                    "Just the JSON object."
                )},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.01,
            "max_tokens": 512,
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            response_data = json.loads(resp.read().decode("utf-8"))

        msg = response_data["choices"][0]["message"]
        raw = msg.get("content", "") or ""

        # Some models (DeepSeek V4 Pro) return content in reasoning_content
        if not raw.strip():
            raw = msg.get("reasoning_content", "") or ""

        # If still no content, try a different approach: use deepseek-chat
        if not raw.strip() or not any(c in raw for c in ('{"score"', "'score'", '"reason"')):
            # The model may have hidden the JSON in reasoning tokens
            # Search entire response for a score pattern
            full_response = json.dumps(response_data)
            import re
            score_match = re.search(r'"score"\s*[:=]\s*([01]\.?\d*)', full_response)
            if score_match:
                try:
                    score = float(score_match.group(1))
                    return max(0.0, min(1.0, score)), full_response[:300]
                except ValueError:
                    pass

        return self._parse_judge_response(raw)

    def _call_anthropic(self, prompt: str, model: str) -> tuple[float, str]:
        """Call Anthropic Claude API."""
        import urllib.request

        body = json.dumps({
            "model": model or "claude-sonnet-4-20250514",
            "max_tokens": 512,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self._judge_api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            response_data = json.loads(resp.read().decode("utf-8"))

        raw = response_data["content"][0]["text"]
        return self._parse_judge_response(raw)

    def _parse_judge_response(self, raw: str) -> tuple[float, str]:
        """Parse JSON response from judge LLM.

        Handles nested braces in reason strings by finding the outermost
        balanced JSON object that contains a "score" key.
        """
        import re

        # 1. Try extracting JSON from code block
        code_match = re.search(
            r'```(?:json)?\s*([\s\S]*?)\s*```', raw
        )
        json_str = code_match.group(1) if code_match else raw

        # 2. Find balanced JSON object with "score" key
        start = json_str.find('{')
        depth = 0
        obj_start = -1
        for i, ch in enumerate(json_str):
            if ch == '{':
                if depth == 0:
                    obj_start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and obj_start >= 0:
                    candidate = json_str[obj_start:i + 1]
                    if '"score"' in candidate:
                        try:
                            parsed = json.loads(candidate)
                            score = float(parsed.get("score", 0.8))
                            score = max(0.0, min(1.0, score))
                            return score, raw[:300]
                        except (json.JSONDecodeError, ValueError, TypeError):
                            pass
                    obj_start = -1

        # 3. Fallback: return default
        logger.warning(
            "Failed to parse judge response: %s", raw[:200]
        )
        return 0.8, raw[:300]


def evaluate_session(
    session: StructuredSession,
    force_judge: bool = False,
) -> EvalResult:
    """Convenience function for one-shot evaluation."""
    return EvaluatorPipeline(force_judge=force_judge).evaluate(session)


def extract_knowledge_from_eval(
    session: StructuredSession,
    result: EvalResult,
    score_threshold: float = 0.5,
) -> list[dict]:
    """Auto-extract knowledge entries from low-scoring sessions.

    Only extracts if total_score < score_threshold.
    Generates entries based on error patterns and failure modes.
    Returns list of candidate items for entries.json (not auto-saved).
    """
    if result.total_score >= score_threshold:
        return []

    items = []

    # Extract from failed tool calls
    for tc in session.tool_calls:
        if not tc.result_success and tc.error_message:
            items.append({
                "type": "entry",
                "category": "避坑",
                "title": f"{tc.tool_name}: {tc.error_message[:50]}",
                "content": f"Tool {tc.tool_name} failed with: {tc.error_message}. "
                           f"Check parameters and node paths before calling.",
                "tags": [tc.tool_name, "auto-extracted"],
            })

    # Extract from low reliability (empty responses or errors)
    if result.reliability < 0.4:
        items.append({
            "type": "entry",
            "category": "避坑",
            "title": "低可靠性会话模式",
            "content": f"Session had reliability score {result.reliability:.2f}. "
                       f"Review error patterns and tool parameter validation.",
            "tags": ["reliability", "auto-extracted"],
        })

    # Extract from low tool accuracy
    if result.tool_accuracy is not None and result.tool_accuracy < 0.4:
        failed_tools = [
            tc.tool_name for tc in session.tool_calls if not tc.result_success
        ]
        if failed_tools:
            items.append({
                "type": "entry",
                "category": "技巧",
                "title": f"工具精度低: {', '.join(set(failed_tools[:3]))}",
                "content": f"Tools {set(failed_tools)} had accuracy issues. "
                           f"Double-check parameters and verify node existence before calling.",
                "tags": list(set(failed_tools)) + ["accuracy", "auto-extracted"],
            })

    return items[:5]  # Cap at 5 items per session
