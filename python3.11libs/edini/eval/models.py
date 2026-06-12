"""Data classes for the evaluation system."""
from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass
class ToolCallRecord:
    """A single tool call extracted from JSONL."""
    index: int
    tool_name: str
    params: dict[str, Any]
    result_success: bool
    error_message: str | None
    latency_ms: int
    sandbox_job_id: str | None = None
    sandbox_action: str | None = None       # "create" | "discard" | "commit"
    sandbox_root_path: str | None = None


@dataclasses.dataclass
class StructuredSession:
    """Parsed representation of a Pi JSONL session."""
    session_id: str
    jsonl_path: str
    cwd: str
    model_id: str | None
    created_at: str
    user_queries: list[str]
    tool_calls: list[ToolCallRecord]
    thinking_steps: list[str]
    assistant_responses: list[str]
    total_latency_ms: int
    message_count: int


@dataclasses.dataclass
class EvalResult:
    """Evaluation result for a single session."""
    session_id: str
    evaluated_at: str

    # Dimension scores [0.0, 1.0]
    tool_accuracy: float | None
    task_completion: float | None
    total_score: float
    efficiency: float
    reliability: float
    cost: float

    # Per-call eval details
    tool_call_details: list[dict]

    # Derived stats
    tool_calls_count: int
    total_latency_ms: int

    sandbox_adoption_rate: float = 1.0
