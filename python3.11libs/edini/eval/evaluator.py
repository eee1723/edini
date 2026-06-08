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
        judge_sampling_rate: float = 0.5,
        force_judge: bool = False,
    ):
        self._judge_model = judge_model or os.environ.get("EDINI_JUDGE_MODEL", "")
        self._judge_api_key = judge_api_key or os.environ.get("EDINI_JUDGE_API_KEY", "")
        self._judge_sampling_rate = judge_sampling_rate
        self._force_judge = force_judge

    def evaluate(self, session: StructuredSession) -> EvalResult:
        """Run all evaluators and return combined result."""
        now = datetime.utcnow().isoformat()

        # 1. Deterministic evaluations (always run, zero cost)
        reliability = self._eval_reliability(session)
        efficiency = self._eval_efficiency(session)
        cost = self._eval_cost(session)

        # 2. LLM-as-Judge evaluations (sampled)
        tool_accuracy: float | None = None
        task_completion: float | None = None

        if self._force_judge or (
            session.tool_calls and self._should_judge(session)
        ):
            ta_score, _ = self._judge_tool_accuracy(session)
            tc_score, _ = self._judge_task_completion(session)
            tool_accuracy = ta_score
            task_completion = tc_score

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

        tool_summary = []
        for tc in session.tool_calls:
            tool_summary.append(
                f"[{tc.index}] {tc.tool_name}("
                f"params={json.dumps(tc.params)}, "
                f"success={tc.result_success})"
            )

        first_query = session.user_queries[0] if session.user_queries else "(unknown)"

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
            f"{'{\"score\": 0.0-1.0, \"reason\": \"...\"}'}"
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

        tool_summary = []
        for tc in session.tool_calls:
            tool_summary.append(
                f"[{tc.index}] {tc.tool_name}("
                f"params={json.dumps(tc.params)}, "
                f"success={tc.result_success})"
            )

        first_query = session.user_queries[0] if session.user_queries else "(unknown)"
        last_response = session.assistant_responses[-1] if session.assistant_responses else "(none)"

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
            f"{'{\"score\": 0.0-1.0, \"reason\": \"...\"}'}"
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
        """Call the judge LLM and parse the JSON response.

        In production, this should be wired to the configured model provider
        (DeepSeek/Anthropic/Qwen). The current implementation logs the call
        and returns a default score so the system works without a judge model.
        """
        logger.info(
            "Judge would call model=%s with %d chars",
            self._judge_model,
            len(prompt),
        )
        # Placeholder: returns default score.
        # Override by subclassing or monkey-patching _call_judge.
        return 0.8, '{"score": 0.8, "reason": "Placeholder judge"}'


def evaluate_session(
    session: StructuredSession,
    force_judge: bool = False,
) -> EvalResult:
    """Convenience function for one-shot evaluation."""
    return EvaluatorPipeline(force_judge=force_judge).evaluate(session)
