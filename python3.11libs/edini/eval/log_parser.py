"""Parse Pi JSONL session files into StructuredSession objects."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from edini.eval.models import StructuredSession, ToolCallRecord


class LogParser:
    """Parses Pi JSONL session files into StructuredSession."""

    @classmethod
    def parse(cls, session_path: str | Path) -> Optional[StructuredSession]:
        """Parse a single JSONL file into a StructuredSession.

        Returns None if the file is missing, empty, or malformed.
        """
        path = Path(session_path)
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except (OSError, UnicodeDecodeError):
            return None

        if not lines:
            return None

        # Parse header
        try:
            header = json.loads(lines[0])
        except json.JSONDecodeError:
            return None

        htype = header.get("type", "")
        if htype not in ("header", "session"):
            return None

        session_id = path.stem
        model_id = header.get("model") or header.get("model_id")

        user_queries: list[str] = []
        tool_calls: list[ToolCallRecord] = []
        thinking_steps: list[str] = []
        assistant_responses: list[str] = []
        pending_tool: dict | None = None

        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = entry.get("type")
            if etype != "message":
                continue

            msg = entry.get("message", {})
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                if isinstance(content, list):
                    texts = [
                        b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    content = "".join(texts)
                if content:
                    user_queries.append(content)

            elif role == "assistant":
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                assistant_responses.append(
                                    block.get("text", "")
                                )
                            elif block.get("type") == "thinking":
                                thinking_steps.append(
                                    block.get("thinking", "")
                                )

            elif role == "toolResult":
                # Pi RPC format: tool results have toolName in message
                tool_name = msg.get("toolName", "")
                content = msg.get("content", "")

                # Extract result text from content blocks
                result_text = ""
                if isinstance(content, list):
                    texts = [
                        b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    result_text = "".join(texts)
                elif isinstance(content, str):
                    result_text = content

                # Parse result as JSON to check success
                result_success = True
                error_msg = None
                if result_text:
                    result_text_stripped = result_text.strip()
                    if result_text_stripped.startswith("{"):
                        try:
                            parsed = json.loads(result_text_stripped)
                            if isinstance(parsed, dict):
                                result_success = parsed.get("success", True)
                                if not result_success:
                                    error_msg = parsed.get("error", "Tool call failed")
                        except json.JSONDecodeError:
                            pass

                tool_calls.append(ToolCallRecord(
                    index=len(tool_calls),
                    tool_name=tool_name or "unknown",
                    params={},
                    result_success=bool(result_success),
                    error_message=error_msg,
                    latency_ms=0,
                ))

        return StructuredSession(
            session_id=session_id,
            jsonl_path=str(path.resolve()),
            cwd=str(
                path.parent.parent.parent
            ) if path.parent.parent else "",
            model_id=model_id,
            created_at=header.get("createdAt", header.get("timestamp", "")),
            user_queries=user_queries,
            tool_calls=tool_calls,
            thinking_steps=thinking_steps,
            assistant_responses=assistant_responses,
            total_latency_ms=0,
            message_count=len(user_queries) + len(assistant_responses),
        )
