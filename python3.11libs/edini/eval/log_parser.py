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
            if etype not in ("message", "tool_call", "tool_result",
                             "vision_description"):
                continue

            msg = entry.get("message", {})

            if etype == "message":
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

            elif etype == "tool_call":
                pending_tool = {
                    "tool": msg.get("name", entry.get("name", "")),
                    "params": msg.get("params", entry.get("params", {})),
                    "call_index": len(tool_calls),
                    "timestamp": entry.get("timestamp", 0),
                }

            elif etype == "tool_result":
                tool_name = msg.get("name", entry.get("name", ""))
                if pending_tool and pending_tool["tool"] == tool_name:
                    result = msg.get("content", entry.get("result", ""))
                    result_success = True
                    error_msg = None
                    if isinstance(result, str) and "error" in result.lower():
                        result_success = False
                        error_msg = result
                    elif isinstance(result, dict):
                        result_success = result.get("success", True)
                        if not result_success:
                            error_msg = result.get("error", str(result))

                    tool_calls.append(ToolCallRecord(
                        index=pending_tool["call_index"],
                        tool_name=tool_name,
                        params=pending_tool.get("params", {}),
                        result_success=result_success,
                        error_message=error_msg,
                        latency_ms=0,
                    ))
                    pending_tool = None

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
