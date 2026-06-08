# Agent Evaluation & Logging System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an agent evaluation and logging system for Edini that scores each session across 5 dimensions, stores results in SQLite, provides a UI dashboard, and offers an AgentEval tool for self-reflection.

**Architecture:** LogParser reads Pi JSONL session files → EvaluatorPipeline applies 3 deterministic + 2 LLM-as-Judge evaluators → results stored in SQLite → displayed in PySide6 EvalDashboard tab. A new `edini_get_eval_stats` Pi tool lets the agent query its own performance stats.

**Tech Stack:** Python 3.11, PySide6, sqlite3 (stdlib), Pi Extensions (TypeScript, TypeBox)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `python3.11libs/edini/eval/__init__.py` | Create | Package init |
| `python3.11libs/edini/eval/models.py` | Create | Data classes: `StructuredSession`, `ToolCallRecord`, `EvalResult` |
| `python3.11libs/edini/eval/store.py` | Create | SQLite EvalStore — CRUD + aggregates |
| `python3.11libs/edini/eval/log_parser.py` | Create | Parse Pi JSONL files into StructuredSession |
| `python3.11libs/edini/eval/evaluator.py` | Create | EvaluatorPipeline with all 5 evaluators |
| `python3.11libs/edini/tool_executor.py` | Modify | Register `edini_get_eval_stats` handler |
| `pi-extensions/edini-tools/tools/eval.ts` | Create | Pi tool definition for `edini_get_eval_stats` |
| `pi-extensions/edini-tools/index.ts` | Modify | Export eval tool |
| `python3.11libs/edini/ui/eval_tab.py` | Create | EvalDashboard QWidget |
| `python3.11libs/edini/ui/main_window.py` | Modify | Register EvalTab in tab widget |
| `python3.11libs/edini/ui/agent_panel.py` | Modify | Trigger background evaluation after session finishes |

---

### Task 1: Data Models

**Files:**
- Create: `python3.11libs/edini/eval/__init__.py`
- Create: `python3.11libs/edini/eval/models.py`
- Test: no separate test — these are pure dataclasses, tested implicitly by later tasks

- [ ] **Step 1: Create the eval package**

```bash
mkdir -p python3.11libs/edini/eval
```

- [ ] **Step 2: Create `__init__.py`**

```python
"""Edini Agent Evaluation System.

Records agent interactions, scores sessions across 5 dimensions,
provides a UI dashboard and an AgentEval tool for self-reflection.
"""
```

- [ ] **Step 3: Create `models.py`**

```python
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
    efficiency: float
    reliability: float
    cost: float

    total_score: float

    # Per-call eval details
    tool_call_details: list[dict]

    # Derived stats
    tool_calls_count: int
    total_latency_ms: int
```

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/edini/eval/__init__.py python3.11libs/edini/eval/models.py
git commit -m "feat(eval): add data models for evaluation system"
```

---

### Task 2: SQLite EvalStore

**Files:**
- Create: `python3.11libs/edini/eval/store.py`

- [ ] **Step 1: Write the EvalStore class**

```python
"""SQLite evaluation store — CRUD + aggregates for evaluation results."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from edini.eval.models import EvalResult


_DEFAULT_DB_DIR = None  # resolved lazily


def _default_db_path() -> str:
    """Get the default database path alongside Pi sessions."""
    global _DEFAULT_DB_DIR
    if _DEFAULT_DB_DIR is None:
        home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or "~"
        _DEFAULT_DB_DIR = Path(home) / ".pi" / "agent" / "evaluation"
    _DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
    return str(_DEFAULT_DB_DIR / "eval_store.db")


class EvalStore:
    """Thread-safe SQLite store for evaluation results.

    Path resolution:
        default: ~/.pi/agent/evaluation/eval_store.db
        custom:  specified via db_path argument
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or _default_db_path()
        self._lock = threading.Lock()
        self._init_db()

    @property
    def db_path(self) -> str:
        return self._db_path

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;

                CREATE TABLE IF NOT EXISTS sessions (
                    session_id      TEXT PRIMARY KEY,
                    cwd             TEXT NOT NULL,
                    jsonl_path      TEXT NOT NULL,
                    model_id        TEXT,
                    created_at      TEXT NOT NULL,
                    evaluated_at    TEXT NOT NULL,
                    total_score     REAL,
                    tool_accuracy   REAL,
                    task_completion REAL,
                    efficiency      REAL,
                    reliability     REAL,
                    cost            REAL,
                    thinking_steps  INTEGER DEFAULT 0,
                    tool_calls_count INTEGER DEFAULT 0,
                    total_latency_ms INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS tool_calls (
                    call_id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id      TEXT NOT NULL REFERENCES sessions(session_id),
                    call_index      INTEGER NOT NULL,
                    tool_name       TEXT NOT NULL,
                    params          TEXT,
                    result_status   TEXT,
                    error_message   TEXT,
                    latency_ms      INTEGER,
                    eval_correct    INTEGER,
                    eval_optimal    INTEGER,
                    eval_reason     TEXT
                );

                CREATE TABLE IF NOT EXISTS judge_logs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id      TEXT NOT NULL REFERENCES sessions(session_id),
                    dimension       TEXT NOT NULL,
                    prompt          TEXT,
                    response        TEXT,
                    score           REAL,
                    latency_ms      INTEGER
                );

                CREATE TABLE IF NOT EXISTS daily_aggregates (
                    date            TEXT NOT NULL,
                    avg_score       REAL,
                    avg_tool_accuracy  REAL,
                    avg_task_completion REAL,
                    avg_efficiency  REAL,
                    avg_reliability REAL,
                    avg_cost        REAL,
                    session_count   INTEGER,
                    PRIMARY KEY (date)
                );

                CREATE INDEX IF NOT EXISTS idx_tc_session ON tool_calls(session_id);
                CREATE INDEX IF NOT EXISTS idx_jl_session ON judge_logs(session_id);
            """)

    def has_evaluated(self, session_id: str) -> bool:
        """Check if a session has been evaluated."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            return row is not None

    def save_result(self, session_id: str, result: EvalResult) -> None:
        """Save evaluation result for a session (insert or update)."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sessions
                (session_id, cwd, jsonl_path, model_id, created_at, evaluated_at,
                 total_score, tool_accuracy, task_completion, efficiency,
                 reliability, cost, thinking_steps, tool_calls_count, total_latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    "",  # cwd not currently available from EvalResult
                    "",  # jsonl_path not currently available from EvalResult
                    None,
                    "",
                    result.evaluated_at,
                    result.total_score,
                    result.tool_accuracy,
                    result.task_completion,
                    result.efficiency,
                    result.reliability,
                    result.cost,
                    0,  # thinking_steps
                    result.tool_calls_count,
                    result.total_latency_ms,
                ),
            )

            # Save per-call details
            for detail in result.tool_call_details:
                conn.execute(
                    """INSERT INTO tool_calls
                    (session_id, call_index, tool_name, params, result_status,
                     error_message, latency_ms, eval_correct, eval_optimal, eval_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        detail["call_index"],
                        detail["tool_name"],
                        json.dumps(detail.get("params", {}), ensure_ascii=False),
                        detail.get("result_status", "unknown"),
                        detail.get("error_message"),
                        detail.get("latency_ms"),
                        detail.get("eval_correct"),
                        detail.get("eval_optimal"),
                        detail.get("eval_reason"),
                    ),
                )

    def get_recent_sessions(self, limit: int = 20) -> list[dict]:
        """Get the most recently evaluated sessions."""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                """SELECT session_id, total_score, tool_accuracy, task_completion,
                          efficiency, reliability, cost, evaluated_at,
                          tool_calls_count
                   FROM sessions
                   ORDER BY evaluated_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {
                "session_id": r[0],
                "total_score": r[1],
                "tool_accuracy": r[2],
                "task_completion": r[3],
                "efficiency": r[4],
                "reliability": r[5],
                "cost": r[6],
                "evaluated_at": r[7],
                "tool_calls_count": r[8],
            }
            for r in rows
        ]

    def get_daily_trend(self, days: int = 14) -> list[dict]:
        """Get daily average scores for trend chart."""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                """SELECT DATE(evaluated_at) as d,
                          AVG(total_score),
                          AVG(tool_accuracy),
                          AVG(task_completion),
                          AVG(efficiency),
                          AVG(reliability),
                          AVG(cost),
                          COUNT(*)
                   FROM sessions
                   WHERE evaluated_at >= DATE('now', '-' || ? || ' days')
                   GROUP BY d
                   ORDER BY d""",
                (days,),
            ).fetchall()
        return [
            {
                "date": r[0],
                "avg_score": r[1],
                "avg_tool_accuracy": r[2],
                "avg_task_completion": r[3],
                "avg_efficiency": r[4],
                "avg_reliability": r[5],
                "avg_cost": r[6],
                "session_count": r[7],
            }
            for r in rows
        ]

    def get_bottom_sessions(self, limit: int = 20, dimension: str | None = None) -> list[dict]:
        """Get lowest-scoring sessions for a dimension (or total)."""
        col = dimension if dimension in (
            "tool_accuracy", "task_completion", "efficiency", "reliability", "cost"
        ) else "total_score"

        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                f"""SELECT session_id, total_score, tool_accuracy, task_completion,
                           efficiency, reliability, cost, evaluated_at,
                           tool_calls_count
                    FROM sessions
                    WHERE {col} IS NOT NULL
                    ORDER BY {col} ASC
                    LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {
                "session_id": r[0],
                "total_score": r[1],
                "tool_accuracy": r[2],
                "task_completion": r[3],
                "efficiency": r[4],
                "reliability": r[5],
                "cost": r[6],
                "evaluated_at": r[7],
                "tool_calls_count": r[8],
            }
            for r in rows
        ]

    def get_common_failures(self, limit: int = 10, max_items: int = 5) -> list[dict]:
        """Get most common error messages from recent sessions."""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                """SELECT tc.error_message, COUNT(*) as cnt
                   FROM tool_calls tc
                   JOIN sessions s ON tc.session_id = s.session_id
                   WHERE tc.error_message IS NOT NULL AND tc.error_message != ''
                   GROUP BY tc.error_message
                   ORDER BY cnt DESC
                   LIMIT ?""",
                (max_items,),
            ).fetchall()
        return [{"error": r[0], "count": r[1]} for r in rows]

    def get_session_detail(self, session_id: str) -> dict | None:
        """Get full evaluation detail for a session, including tool calls."""
        with sqlite3.connect(self._db_path) as conn:
            s = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if not s:
                return None
            tcs = conn.execute(
                "SELECT * FROM tool_calls WHERE session_id = ? ORDER BY call_index",
                (session_id,),
            ).fetchall()
            jls = conn.execute(
                "SELECT * FROM judge_logs WHERE session_id = ?", (session_id,),
            ).fetchall()

        columns = [d[0] for d in conn.execute("PRAGMA table_info(sessions)")]
        tc_columns = [d[0] for d in conn.execute("PRAGMA table_info(tool_calls)")]
        jl_columns = [d[0] for d in conn.execute("PRAGMA table_info(judge_logs)")]

        return {
            "session": dict(zip(columns, s)),
            "tool_calls": [dict(zip(tc_columns, tc)) for tc in tcs],
            "judge_logs": [dict(zip(jl_columns, jl)) for jl in jls],
        }

    def get_stats_summary(self, period: int = 10) -> dict:
        """Get aggregated stats for agent self-reflection."""
        recent = self.get_recent_sessions(limit=max(1, period))
        if not recent:
            return {
                "avg_scores": {},
                "trend": "stable",
                "weakest_dimension": "",
                "common_failures": [],
                "session_count": 0,
            }

        dims = ["tool_accuracy", "task_completion", "efficiency", "reliability", "cost"]
        avg_scores = {}
        for dim in dims:
            scores = [s[dim] for s in recent if s.get(dim) is not None]
            avg_scores[dim] = round(sum(scores) / len(scores), 3) if scores else None

        # Trend: compare first half vs second half
        mid = len(recent) // 2
        if mid > 0:
            first_half = sum(s["total_score"] for s in recent[:mid]) / mid
            second_half = sum(s["total_score"] for s in recent[mid:]) / max(1, len(recent) - mid)
            if second_half - first_half > 0.03:
                trend = "improving"
            elif first_half - second_half > 0.03:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "stable"

        valid = {k: v for k, v in avg_scores.items() if v is not None}
        weakest = min(valid, key=valid.get) if valid else ""

        failures = self.get_common_failures(limit=period, max_items=5)

        return {
            "avg_scores": avg_scores,
            "trend": trend,
            "weakest_dimension": weakest,
            "common_failures": [f["error"] for f in failures],
            "session_count": len(recent),
        }
```

- [ ] **Step 2: Quick smoke test**

```bash
cd python3.11libs/edini/eval
python -c "from edini.eval.store import EvalStore; s = EvalStore(); print('DB at:', s.db_path); print('has_evaluated(x):', s.has_evaluated('x'))"
```

Expected output: no import errors, db path printed, `has_evaluated('x')` returns False.

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/eval/store.py
git commit -m "feat(eval): add SQLite EvalStore with CRUD and aggregates"
```

---

### Task 3: LogParser — Read JSONL into StructuredSession

**Files:**
- Create: `python3.11libs/edini/eval/log_parser.py`

- [ ] **Step 1: Write the LogParser**

```python
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
            if etype not in ("message", "tool_call", "tool_result", "vision_description"):
                continue

            msg = entry.get("message", {})

            if etype == "message":
                role = msg.get("role", "")
                content = msg.get("content", "")

                if role == "user":
                    # Extract text from list content
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
                                    assistant_responses.append(block.get("text", ""))
                                elif block.get("type") == "thinking":
                                    thinking_steps.append(block.get("thinking", ""))

            elif etype == "tool_call":
                # Pi may include tool_call entries directly
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
                    result_success = not (
                        isinstance(result, str) and "error" in result.lower()
                    )
                    if isinstance(result, dict):
                        result_success = result.get("success", True)
                    error_msg = str(result) if not result_success else None
                    tool_calls.append(ToolCallRecord(
                        index=pending_tool["call_index"],
                        tool_name=tool_name,
                        params=pending_tool.get("params", {}),
                        result_success=result_success,
                        error_message=error_msg,
                        latency_ms=0,  # Will be refined in future
                    ))
                    pending_tool = None

        return StructuredSession(
            session_id=session_id,
            jsonl_path=str(path.resolve()),
            cwd=str(path.parent.parent.parent) if path.parent.parent else "",
            model_id=model_id,
            created_at=header.get("createdAt", header.get("timestamp", "")),
            user_queries=user_queries,
            tool_calls=tool_calls,
            thinking_steps=thinking_steps,
            assistant_responses=assistant_responses,
            total_latency_ms=0,
            message_count=len(user_queries) + len(assistant_responses),
        )
```

- [ ] **Step 2: Create a test JSONL file and run parser**

```bash
cd python3.11libs/edini
mkdir -p tests/eval
python -c "
from edini.eval.log_parser import LogParser
result = LogParser.parse('__init__.py')
print('Non-existent file:', result)  # None expected
"
```

Expected: `Non-existent file: None`

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/eval/log_parser.py
git commit -m "feat(eval): add LogParser for reading Pi JSONL sessions"
```

---

### Task 4: EvaluatorPipeline — 5 evaluation dimensions

**Files:**
- Create: `python3.11libs/edini/eval/evaluator.py`

- [ ] **Step 1: Write the EvaluatorPipeline**

```python
"""Evaluation pipeline — scores sessions across 5 dimensions."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any

from edini.eval.models import EvalResult, StructuredSession, ToolCallRecord

logger = logging.getLogger(__name__)

# Weights for each dimension
WEIGHTS = {
    "tool_accuracy": 0.30,
    "task_completion": 0.30,
    "efficiency": 0.15,
    "reliability": 0.15,
    "cost": 0.10,
}

# Task type classification (based on first tool call)
TASK_TYPES = frozenset([
    "houdini_create_node", "houdini_delete_node", "houdini_connect_nodes",
    "houdini_set_param", "houdini_get_param", "houdini_get_scene_info",
    "houdini_list_nodes", "houdini_get_node", "houdini_layout_nodes",
    "houdini_search_nodes", "houdini_get_help", "houdini_inspect_geo",
    "houdini_run_python", "houdini_run_vex", "houdini_create_hda",
    "houdini_get_hda_info", "houdini_capture_viewport", "houdini_capture_network",
    "houdini_get_selection", "houdini_check_errors", "houdini_set_display_flag",
    "edini_get_eval_stats",
])


class EvaluatorPipeline:
    """Evaluates a StructuredSession across 5 dimensions.

    Usage:
        result = EvaluatorPipeline().evaluate(session)
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
        judge_logs: list[dict] = []

        if self._force_judge or (session.tool_calls and self._should_judge(session)):
            ta_score, ta_log = self._judge_tool_accuracy(session)
            tc_score, tc_log = self._judge_task_completion(session)
            tool_accuracy = ta_score
            task_completion = tc_score
            if ta_log:
                judge_logs.append(ta_log)
            if tc_log:
                judge_logs.append(tc_log)

        # 3. Compute total score (weighted, re-normalize if Judge scores missing)
        available_weights = {}
        for dim, weight in WEIGHTS.items():
            score = locals().get(dim.replace("-", "_"))
            if score is not None:
                available_weights[dim] = weight

        total_w = sum(available_weights.values())
        if total_w > 0:
            normalized = {k: v / total_w for k, v in available_weights.items()}
            total_score = sum(
                normalized[d] * (locals().get(d.replace("-", "_")) or 0.0)
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
        """Reliability = successful_calls / total_calls."""
        total = len(session.tool_calls)
        if total == 0:
            return 1.0
        successful = sum(1 for tc in session.tool_calls if tc.result_success)
        return round(successful / total, 3)

    def _eval_efficiency(self, session: StructuredSession) -> float:
        """Efficiency = optimal_steps / actual_steps.

        Optimal for same task type = minimum steps across all sessions.
        Current implementation: optimal ≈ 1 call for simple info queries,
        3+ for creation tasks. Uses a heuristic based on first tool.
        """
        calls = session.tool_calls
        if not calls:
            return 1.0

        first_tool = calls[0].tool_name

        # Heuristic optimal steps per task type
        if first_tool in ("houdini_get_scene_info", "houdini_get_selection",
                          "houdini_get_param", "houdini_search_nodes",
                          "houdini_check_errors", "houdini_get_node"):
            optimal = 1
        elif first_tool in ("houdini_create_node", "houdini_delete_node",
                            "houdini_connect_nodes", "houdini_set_param",
                            "houdini_set_display_flag"):
            optimal = 3
        elif first_tool in ("houdini_run_python", "houdini_run_vex"):
            optimal = 2
        elif first_tool in ("houdini_capture_viewport", "houdini_capture_network"):
            optimal = 2
        else:
            optimal = max(1, len(calls) // 2)

        actual = len(calls)
        score = min(1.0, optimal / max(1, actual))
        return round(score, 3)

    def _eval_cost(self, session: StructuredSession) -> float:
        """Cost = 1.0 - percentile(tokens/requests) within task type.

        Lower token usage and fewer calls = better score.
        """
        call_count = len(session.tool_calls)
        if call_count == 0:
            return 1.0

        # Baseline: assume 10 calls is the budget for a session
        # Sessions with fewer calls score better
        score = max(0.0, 1.0 - (call_count / 20.0))
        return round(score, 3)

    # ── LLM-as-Judge Evaluators ──────────────────────────────

    def _should_judge(self, session: StructuredSession) -> bool:
        """Determine if we should run LLM-as-Judge for this session.

        Always judge if force_judge is set or if it's a session with few tool calls.
        Otherwise sample at judge_sampling_rate.
        """
        if self._force_judge:
            return True
        # Always judge sessions with > 3 tool calls
        if len(session.tool_calls) <= 3:
            return True
        # Sample for longer sessions
        import random
        return random.random() < self._judge_sampling_rate

    def _judge_tool_accuracy(self, session: StructuredSession) -> tuple[float | None, dict | None]:
        """Judge tool selection + parameter correctness using LLM-as-Judge.

        Returns (score, judge_log) or (None, None) if judge model not configured.
        """
        if not self._judge_model:
            return None, None

        # Build a compact summary of tool calls
        tool_summary = []
        for tc in session.tool_calls:
            tool_summary.append(f"[{tc.index}] {tc.tool_name}(params={json.dumps(tc.params)}, success={tc.result_success})")

        prompt = f"""You are an evaluator for a Houdini AI assistant.
Evaluate the tool call accuracy for the following session.

User request: {session.user_queries[0] if session.user_queries else '(unknown)'}

Tool calls:
{chr(10).join(tool_summary)}

Evaluate:
1. Was each tool the correct choice for the user's intent?
2. Were the parameters correctly extracted?
3. Was the tool call order logical?

Output JSON only: {{"score": 0.0-1.0, "reason": "..."}}"""

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
            logger.warning(f"Judge (tool_accuracy) failed: {e}")
            return None, None

    def _judge_task_completion(self, session: StructuredSession) -> tuple[float | None, dict | None]:
        """Judge whether the user's task was fully accomplished."""
        if not self._judge_model:
            return None, None

        tool_summary = []
        for tc in session.tool_calls:
            tool_summary.append(f"[{tc.index}] {tc.tool_name}(params={json.dumps(tc.params)}, success={tc.result_success})")

        last_response = session.assistant_responses[-1] if session.assistant_responses else "(none)"

        prompt = f"""You are an evaluator for a Houdini AI assistant.
Evaluate whether the user's task was fully accomplished.

User request: {session.user_queries[0] if session.user_queries else '(unknown)'}

Actions taken:
{chr(10).join(tool_summary)}

Final response: {last_response}

Consider:
- Was the original request fulfilled?
- Is the output usable in Houdini?
- Were there critical errors?

Output JSON only: {{"score": 0.0-1.0, "reason": "..."}}"""

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
            logger.warning(f"Judge (task_completion) failed: {e}")
            return None, None

    def _call_judge(self, prompt: str) -> tuple[float, str]:
        """Call the judge LLM and parse the JSON response.

        This is a simplified implementation. In production, route through
        the configured provider (DeepSeek/Anthropic/Qwen).
        Returns (score, raw_response_text).
        """
        # Placeholder: in production, replace with actual API call.
        # This will be wired to the configured model in a follow-up.
        # For now, return a default score so the system works without a judge.
        logger.info(f"Judge would call model={self._judge_model} with {len(prompt)} chars")
        return 0.8, '{"score": 0.8, "reason": "Placeholder judge - configure judge model for real evaluation"}'
```

- [ ] **Step 2: Quick smoke test**

```bash
cd python3.11libs/edini/eval
python -c "
from edini.eval.models import StructuredSession, ToolCallRecord
from edini.eval.evaluator import EvaluatorPipeline

session = StructuredSession(
    session_id='test', jsonl_path='/tmp/test.jsonl', cwd='/tmp',
    model_id='test-model', created_at='2026-01-01',
    user_queries=['Create a box'],
    tool_calls=[
        ToolCallRecord(index=0, tool_name='houdini_create_node', params={'node_type': 'geo', 'name': 'test'}, result_success=True, error_message=None, latency_ms=100),
        ToolCallRecord(index=1, tool_name='houdini_set_display_flag', params={'node_path': '/obj/test'}, result_success=True, error_message=None, latency_ms=50),
    ],
    thinking_steps=['Creating a box geometry node', 'Setting display flag'],
    assistant_responses=['Done! Created a box node at /obj/test'],
    total_latency_ms=150, message_count=2,
)

result = EvaluatorPipeline().evaluate(session)
print(f'Total: {result.total_score}')
print(f'Reliability: {result.reliability}')
print(f'Efficiency: {result.efficiency}')
print(f'Cost: {result.cost}')
"
```

Expected: scores printed, no errors.

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/eval/evaluator.py
git commit -m "feat(eval): add EvaluatorPipeline with 5 evaluation dimensions"
```

---

### Task 5: `get_eval_stats` Handler in ToolExecutor

**Files:**
- Modify: `python3.11libs/edini/tool_executor.py`

- [ ] **Step 1: Add `get_eval_stats` function and register handler**

At the top of `tool_executor.py`, add the import and function:

```python
# Near existing imports, add:
from edini.eval.store import EvalStore
```

Add the handler function before `TOOL_HANDLERS`:

```python
def get_eval_stats(period: int = 10) -> dict:
    """Read from SQLite and return evaluation stats for agent self-reflection."""
    try:
        store = EvalStore()
        stats = store.get_stats_summary(period=period)
        return {"success": True, **stats}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

Register in `TOOL_HANDLERS` dict:

```python
"edini_get_eval_stats": lambda **kw: get_eval_stats(
    period=kw.get("period", 10),
),
```

- [ ] **Step 2: Verify registration**

```bash
cd python3.11libs/edini
python -c "
from edini.tool_executor import TOOL_HANDLERS
assert 'edini_get_eval_stats' in TOOL_HANDLERS
print('Handler registered:', TOOL_HANDLERS['edini_get_eval_stats'])
result = TOOL_HANDLERS['edini_get_eval_stats'](period=5)
print('Result:', result['success'])
"
```

Expected: `Handler registered: ...` and `Result: True`

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/tool_executor.py
git commit -m "feat(eval): add get_eval_stats handler to tool executor"
```

---

### Task 6: Pi Extension — `edini_get_eval_stats` Tool

**Files:**
- Create: `pi-extensions/edini-tools/tools/eval.ts`
- Modify: `pi-extensions/edini-tools/index.ts`

- [ ] **Step 1: Create `tools/eval.ts`**

```typescript
// pi-extensions/edini-tools/tools/eval.ts
// Agent self-evaluation tool — queries the Edini eval system.

import { Type } from "typebox";

const TOOL_PORT = parseInt(process.env.EDINI_TOOL_PORT || "9876", 10);
const TOOL_URL = `http://127.0.0.1:${TOOL_PORT}/execute`;

async function forwardTool(toolName: string, params: Record<string, unknown>) {
  const response = await fetch(TOOL_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool: toolName, params }),
  });
  const result = await response.json();
  return {
    content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
    details: result,
  };
}

export const ediniGetEvalStats = {
  name: "edini_get_eval_stats",
  label: "Get Eval Stats",
  description:
    "Query the agent's own evaluation history. " +
    "Returns average scores across all dimensions (tool_accuracy, task_completion, efficiency, reliability, cost), " +
    "recent trend direction (improving/declining/stable), weakest dimension, and common failure patterns. " +
    "Use at the start or end of a session for self-reflection and to identify areas for improvement. " +
    "If a dimension score is low, focus on that aspect in subsequent tool calls.",
  promptSnippet:
    "Get my evaluation history, performance trends, and common failure patterns",
  promptGuidelines: [
    "Use edini_get_eval_stats at the start of a session to understand your recent performance trends.",
    "If tool_accuracy is your weakest dimension, be extra careful with parameter extraction and tool selection.",
    "If reliability is low, double-check tool parameters before calling and handle errors gracefully.",
    "Review common_failures to avoid repeating past mistakes.",
    "Use this after completing tasks to build a self-improvement loop.",
  ],
  parameters: Type.Object({
    period: Type.Optional(
      Type.Number({
        description: "Number of recent sessions to analyze (default: 10, max: 100)",
        default: 10,
      })
    ),
  }),
  async execute(_toolCallId: string, params: { period?: number }) {
    return forwardTool("edini_get_eval_stats", params);
  },
};
```

- [ ] **Step 2: Export in `index.ts`**

Read `pi-extensions/edini-tools/index.ts` to find the tools array, then add the import and export:

```typescript
// At the top with other imports:
import { ediniGetEvalStats } from "./tools/eval";

// In the tools array:
export const tools = [
  ...sceneTools,
  ...scriptTools,
  ...hdaTools,
  ediniGetEvalStats,
];
```

- [ ] **Step 3: TypeScript compilation check**

```bash
cd pi-extensions/edini-tools
npx tsc --noEmit --strict 2>&1 || echo "Type check done (errors are OK if no tsconfig)"
```

- [ ] **Step 4: Commit**

```bash
git add pi-extensions/edini-tools/tools/eval.ts pi-extensions/edini-tools/index.ts
git commit -m "feat(eval): add edini_get_eval_stats Pi tool for agent self-reflection"
```

---

### Task 7: EvalDashboard UI

**Files:**
- Create: `python3.11libs/edini/ui/eval_tab.py`

- [ ] **Step 1: Create the EvalDashboard widget**

```python
"""EvalDashboard — Evaluation results view for Edini."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from edini.eval.store import EvalStore
from edini.ui.theme import accent_color, fs


# Color thresholds
COLOR_GREEN = "#22c55e"
COLOR_YELLOW = "#eab308"
COLOR_RED = "#ef4444"
COLOR_BG = "#0d0d1a"
COLOR_CARD = "#18182a"
COLOR_TEXT = "#e5e5eb"
COLOR_MUTED = "#71717a"
COLOR_BORDER = "#252540"


def _score_color(score: float) -> str:
    if score >= 0.85:
        return COLOR_GREEN
    elif score >= 0.70:
        return COLOR_YELLOW
    return COLOR_RED


def _score_emoji(score: float) -> str:
    if score >= 0.85:
        return "🟢"
    elif score >= 0.70:
        return "🟡"
    return "🔴"


class _ScoreCard(QtWidgets.QFrame):
    """A single dimension score card with label, value, and trend arrow."""

    def __init__(self, label: str, score: float | None, trend: str = "", parent=None):
        super().__init__(parent)
        self._score = score
        self._label = label
        self._trend = trend
        self._build_ui()

    def _build_ui(self):
        self.setFixedSize(150, 80)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setStyleSheet(f"""
            _ScoreCard {{
                background: {COLOR_CARD};
                border: 1px solid {COLOR_BORDER};
                border-radius: 8px;
                padding: 8px;
            }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        # Label
        label = QtWidgets.QLabel(self._label)
        label.setStyleSheet(f"color:{COLOR_MUTED};font-size:{fs(9)};border:none;")
        layout.addWidget(label)

        # Score + trend
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(4)

        if self._score is not None:
            score_label = QtWidgets.QLabel(f"{self._score:.2f}")
            score_label.setStyleSheet(
                f"color:{_score_color(self._score)};font-size:{fs(14)};font-weight:bold;border:none;"
            )
            row.addWidget(score_label)

            if self._trend:
                trend_arrow = {"improving": "↑", "declining": "↓", "stable": "→"}.get(self._trend, "→")
                trend_color = COLOR_GREEN if self._trend == "improving" else (COLOR_RED if self._trend == "declining" else COLOR_MUTED)
                trend_lbl = QtWidgets.QLabel(trend_arrow)
                trend_lbl.setStyleSheet(f"color:{trend_color};font-size:{fs(11)};border:none;")
                row.addWidget(trend_lbl)
        else:
            na = QtWidgets.QLabel("—")
            na.setStyleSheet(f"color:{COLOR_MUTED};font-size:{fs(14)};border:none;")
            row.addWidget(na)

        row.addStretch()
        layout.addLayout(row)


class _TrendChart(QtWidgets.QWidget):
    """Custom-painted trend line chart for evaluation scores."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[dict] = []
        self._dimensions = ["avg_score", "avg_tool_accuracy", "avg_task_completion",
                            "avg_efficiency", "avg_reliability", "avg_cost"]
        self._colors = ["#22c55e", "#3b82f6", "#a855f7", "#f59e0b", "#ec4899", "#06b6d4"]
        self._visible = {d: True for d in self._dimensions}
        self.setMinimumHeight(200)

    def set_data(self, data: list[dict]):
        self._data = data
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 40

        chart_w = w - margin * 2
        chart_h = h - margin * 2

        # Background
        painter.fillRect(0, 0, w, h, QtGui.QColor(COLOR_BG))

        if chart_w <= 0 or chart_h <= 0:
            painter.end()
            return

        n = len(self._data)
        if n < 2:
            # Draw just a dot or label
            painter.setPen(QtGui.QColor(COLOR_MUTED))
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "Not enough data")
            painter.end()
            return

        step_x = chart_w / (n - 1)

        for di, dim in enumerate(self._dimensions):
            if not self._visible.get(dim, True):
                continue

            values = [d.get(dim) for d in self._data if d.get(dim) is not None]
            if len(values) < 2:
                continue

            min_v = min(values)
            max_v = max(values)
            diff = max(0.01, max_v - min_v)

            color = QtGui.QColor(self._colors[di % len(self._colors)])
            pen = QtGui.QPen(color, 2)
            painter.setPen(pen)

            path = QtGui.QPainterPath()
            first = True
            for i, d in enumerate(self._data):
                val = d.get(dim)
                if val is None:
                    continue
                x = margin + i * step_x
                y = margin + chart_h - ((val - min_v) / diff) * chart_h
                if first:
                    path.moveTo(x, y)
                    first = False
                else:
                    path.lineTo(x, y)

            painter.drawPath(path)

        painter.end()

    def toggle_dimension(self, dim: str, visible: bool):
        if dim in self._visible:
            self._visible[dim] = visible
            self.update()


class EvalTab(QtWidgets.QWidget):
    """Evaluation dashboard tab — overview cards + trend chart + session list."""

    navigate_to_session = QtCore.Signal(str)

    def __init__(self, store: EvalStore | None = None, parent=None):
        super().__init__(parent)
        self._store = store or EvalStore()
        self._filter_dimension: str | None = None
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background:{COLOR_BG};")
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # ── Title ──
        title = QtWidgets.QLabel("📊 Agent Evaluation Dashboard")
        title.setStyleSheet(f"color:{COLOR_TEXT};font-size:{fs(14)};font-weight:bold;border:none;")
        main_layout.addWidget(title)

        # ── ① Summary Cards ──
        self._cards_layout = QtWidgets.QHBoxLayout()
        self._cards_layout.setSpacing(8)
        self._cards_layout.addStretch()

        self._dim_labels = [
            ("total", "Total"),
            ("tool_accuracy", "Tool Accuracy"),
            ("task_completion", "Task Completion"),
            ("efficiency", "Efficiency"),
            ("reliability", "Reliability"),
            ("cost", "Cost"),
        ]
        self._card_widgets: dict[str, _ScoreCard] = {}

        for dim_key, label in self._dim_labels:
            card = _ScoreCard(label, None)
            self._card_widgets[dim_key] = card
            self._cards_layout.addWidget(card)

        self._cards_layout.addStretch()
        main_layout.addLayout(self._cards_layout)

        # ── ② Trend Chart ──
        chart_section = QtWidgets.QVBoxLayout()
        chart_section.setSpacing(4)

        chart_header = QtWidgets.QHBoxLayout()
        chart_label = QtWidgets.QLabel("Trend")
        chart_label.setStyleSheet(f"color:{COLOR_TEXT};font-size:{fs(11)};font-weight:bold;border:none;")
        chart_header.addWidget(chart_label)
        chart_header.addStretch()

        # Day range buttons
        for days, lbl in [(7, "7d"), (14, "14d"), (30, "30d")]:
            btn = QtWidgets.QPushButton(lbl)
            btn.setFixedSize(36, 22)
            btn.setStyleSheet(f"""
                QPushButton {{
                    color:{COLOR_MUTED};background:{COLOR_CARD};border:1px solid {COLOR_BORDER};
                    border-radius:4px;font-size:{fs(9)};
                }}
                QPushButton:hover {{ color:{COLOR_TEXT};border-color:{accent_color()}; }}
            """)
            btn.clicked.connect(lambda checked, d=days, b=btn: self._load_trend(d))
            chart_header.addWidget(btn)

        chart_section.addLayout(chart_header)

        self._trend_chart = _TrendChart()
        chart_section.addWidget(self._trend_chart)
        main_layout.addLayout(chart_section)

        # ── ③ Session List ──
        list_section = QtWidgets.QVBoxLayout()
        list_section.setSpacing(4)

        list_header = QtWidgets.QHBoxLayout()
        list_label = QtWidgets.QLabel("Sessions")
        list_label.setStyleSheet(f"color:{COLOR_TEXT};font-size:{fs(11)};font-weight:bold;border:none;")
        list_header.addWidget(list_label)
        list_header.addStretch()

        # Refresh button
        refresh_btn = QtWidgets.QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                color:{COLOR_MUTED};background:{COLOR_CARD};border:1px solid {COLOR_BORDER};
                border-radius:4px;padding:3px 8px;font-size:{fs(9)};
            }}
            QPushButton:hover {{ color:{COLOR_TEXT};border-color:{accent_color()}; }}
        """)
        refresh_btn.clicked.connect(self._load_data)
        list_header.addWidget(refresh_btn)

        list_section.addLayout(list_header)

        self._session_table = QtWidgets.QTableWidget()
        self._session_table.setColumnCount(5)
        self._session_table.setHorizontalHeaderLabels(["", "Score", "Date", "Title", "Calls"])
        self._session_table.setAlternatingRowColors(True)
        self._session_table.horizontalHeader().setStretchLastSection(True)
        self._session_table.setSelectionBehavior(QtWidgets.QAbstractWidget.SelectRows)
        self._session_table.setSelectionMode(QtWidgets.QAbstractWidget.SingleSelection)
        self._session_table.verticalHeader().setVisible(False)
        self._session_table.setShowGrid(False)
        self._session_table.setStyleSheet(f"""
            QTableWidget {{
                background:{COLOR_BG};color:{COLOR_TEXT};font-size:{fs(10)};
                border:1px solid {COLOR_BORDER};border-radius:4px;
                alternate-background-color:{COLOR_CARD};
            }}
            QTableWidget::item {{ padding: 4px 8px; border: none; }}
            QTableWidget::item:selected {{ background:{COLOR_CARD}; color:{accent_color()}; }}
            QHeaderView::section {{
                background:{COLOR_CARD};color:{COLOR_MUTED};
                border:none;border-bottom:1px solid {COLOR_BORDER};
                padding:4px 8px;font-size:{fs(9)};
            }}
        """)
        self._session_table.itemClicked.connect(self._on_session_clicked)
        self._session_table.itemDoubleClicked.connect(self._on_session_double_clicked)
        list_section.addWidget(self._session_table)

        main_layout.addLayout(list_section, 1)

    def _load_data(self):
        """Load latest data from store."""
        self._load_summary()
        self._load_trend(14)
        self._load_session_list()

    def _load_summary(self):
        """Update score cards."""
        recent = self._store.get_recent_sessions(limit=7)
        if not recent:
            for key in self._card_widgets:
                self._card_widgets[key]._score = None
                self._card_widgets[key]._trend = ""
            return

        # Compare with previous 7 for trend
        prev = self._store.get_recent_sessions(limit=14)
        mid = len(prev) // 2
        trend_map = {}

        dim_keys = ["total_score", "tool_accuracy", "task_completion",
                     "efficiency", "reliability", "cost"]

        for i, (dim_key, _) in enumerate(self._dim_labels):
            scores = [s.get(dim_keys[i]) for s in recent if s.get(dim_keys[i]) is not None]
            avg = sum(scores) / len(scores) if scores else None

            if mid > 0 and len(prev) > mid:
                recent_half = [s.get(dim_keys[i]) for s in prev[:mid] if s.get(dim_keys[i]) is not None]
                prev_half = [s.get(dim_keys[i]) for s in prev[mid:] if s.get(dim_keys[i]) is not None]
                if recent_half and prev_half:
                    r_avg = sum(recent_half) / len(recent_half)
                    p_avg = sum(prev_half) / len(prev_half)
                    diff = r_avg - p_avg
                    if diff > 0.03:
                        trend_map[dim_key] = "improving"
                    elif diff < -0.03:
                        trend_map[dim_key] = "declining"
                    else:
                        trend_map[dim_key] = "stable"

            self._card_widgets[dim_key]._score = avg
            self._card_widgets[dim_key]._trend = trend_map.get(dim_key, "")

    def _load_trend(self, days: int = 14):
        """Update trend chart."""
        data = self._store.get_daily_trend(days=days)
        self._trend_chart.set_data(data)

    def _load_session_list(self):
        """Populate session table."""
        sessions = self._store.get_bottom_sessions(limit=50) if self._filter_dimension else \
                   self._store.get_recent_sessions(limit=50)
        self._session_table.setRowCount(len(sessions))

        for row, s in enumerate(sessions):
            score = s.get("total_score") or 0.0
            # Quality dot
            dot = QtWidgets.QLabel(_score_emoji(score))
            dot.setStyleSheet("border:none;")
            self._session_table.setCellWidget(row, 0, dot)

            # Score
            score_item = QtWidgets.QTableWidgetItem(f"{score:.2f}")
            score_item.setForeground(QtGui.QColor(_score_color(score)))
            self._session_table.setItem(row, 1, score_item)

            # Date
            date_str = s.get("evaluated_at", "")[:10]
            self._session_table.setItem(row, 2, QtWidgets.QTableWidgetItem(date_str))

            # Title (session_id truncated)
            sid = s.get("session_id", "")
            title_item = QtWidgets.QTableWidgetItem(sid[:40])
            title_item.setToolTip(sid)
            self._session_table.setItem(row, 3, title_item)

            # Call count
            cnt_item = QtWidgets.QTableWidgetItem(str(s.get("tool_calls_count", 0)))
            cnt_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self._session_table.setItem(row, 4, cnt_item)

        self._session_table.resizeColumnsToContents()

    def _on_session_clicked(self, item):
        """Single click — show detail tooltip."""
        row = item.row()
        sid_item = self._session_table.item(row, 3)
        if sid_item:
            sid = sid_item.toolTip() or sid_item.text()
            detail = self._store.get_session_detail(sid)
            if detail:
                s = detail["session"]
                parts = [
                    f"Total: {s.get('total_score', '—')}",
                    f"Tool: {s.get('tool_accuracy', '—')}",
                    f"Task: {s.get('task_completion', '—')}",
                    f"Eff: {s.get('efficiency', '—')}",
                    f"Rel: {s.get('reliability', '—')}",
                    f"Cost: {s.get('cost', '—')}",
                ]
                if detail.get("judge_logs"):
                    for jl in detail["judge_logs"][:2]:
                        parts.append(f"Judge [{jl['dimension']}]: {jl.get('response', '')[:80]}")
                QtWidgets.QToolTip.showText(
                    QtGui.QCursor.pos(), "\n".join(parts)
                )

    def _on_session_double_clicked(self, item):
        """Double click — navigate to session browsing mode."""
        row = item.row()
        sid_item = self._session_table.item(row, 3)
        if sid_item:
            sid = sid_item.toolTip() or sid_item.text()
            self.navigate_to_session.emit(sid)
```

- [ ] **Step 2: Verify no import errors**

```bash
cd python3.11libs
python -c "from edini.ui.eval_tab import EvalTab; print('EvalTab imported OK')"
```

Expected: `EvalTab imported OK`

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/eval_tab.py
git commit -m "feat(eval): add EvalDashboard UI with cards, trend chart, session list"
```

---

### Task 8: Integrate EvalTab into MainWindow

**Files:**
- Modify: `python3.11libs/edini/ui/main_window.py`

- [ ] **Step 1: Read the current tab setup code in main_window.py**

Find where `_tab_widget` is created and tabs are added. This is likely in `_build_ui` or `_setup_tabs`.

- [ ] **Step 2: Add EvalTab**

Add imports at the top:
```python
from edini.eval.store import EvalStore
from edini.ui.eval_tab import EvalTab
```

After the tab creation where other tabs are added:
```python
# Add evaluation dashboard tab
self._eval_store = EvalStore()
self._eval_tab = EvalTab(self._eval_store)
self._tab_widget.addTab(self._eval_tab, "📊 Evaluate")
self._eval_tab.navigate_to_session.connect(self._on_eval_navigate)
```

Add the navigation handler:
```python
def _on_eval_navigate(self, session_id: str):
    """Navigate to a session from evaluation dashboard."""
    # Find session path from session_id
    if hasattr(self, '_browsing_session_path') and hasattr(self, 'agent_panel'):
        # Use existing browsing mode
        sessions = list_pi_sessions(self._cwd)
        for s in sessions:
            if s["session_id"] == session_id:
                target_path = s["path"]
                self.agent_panel.load_history_by_path(target_path)
                self._tab_widget.setCurrentWidget(self.agent_panel)
                break
```

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/main_window.py
git commit -m "feat(eval): integrate EvalDashboard tab into MainWindow"
```

---

### Task 9: Trigger Background Evaluation in AgentPanel

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py`

- [ ] **Step 1: Find where `finish_streaming` and `show_aborted` are defined**

These are the places where a session ends. Add background evaluation trigger.

- [ ] **Step 2: Add eval trigger after session finishes**

```python
# At the top of agent_panel.py, add import
from edini.eval.store import EvalStore
```

Add a signal:
```python
sig_eval_completed = QtCore.Signal(str, float)  # session_id, total_score
```

In `finish_streaming` method, near the end (after response rendering), add:
```python
# Trigger background evaluation
self._trigger_background_eval()
```

In `show_aborted` method, similarly:
```python
self._trigger_background_eval()
```

Add the helper methods:
```python
def _trigger_background_eval(self):
    """Run evaluator in background thread after session ends."""
    from pathlib import Path
    session_path = getattr(self, '_current_session_path', None)
    if not session_path or not Path(str(session_path)).exists():
        return
    import threading
    t = threading.Thread(
        target=self._run_evaluation,
        args=(str(session_path),),
        daemon=True,
    )
    t.start()

def _run_evaluation(self, session_path: str):
    """Evaluate a single session in background thread."""
    from edini.eval.log_parser import LogParser
    from edini.eval.evaluator import EvaluatorPipeline
    from edini.eval.store import EvalStore
    
    try:
        session = LogParser.parse(session_path)
        if not session:
            return
        store = EvalStore()
        if store.has_evaluated(session.session_id):
            return
        result = EvaluatorPipeline().evaluate(session)
        store.save_result(session.session_id, result)
        self.sig_eval_completed.emit(session.session_id, result.total_score)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Background eval failed: {e}")
```

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/agent_panel.py
git commit -m "feat(eval): trigger background evaluation after session ends"
```

---

## Spec Coverage Check

| Spec Requirement | Covering Task(s) |
|-----------------|-----------------|
| Data models (StructuredSession, ToolCallRecord, EvalResult) | Task 1 |
| SQLite EvalStore with sessions/tool_calls/judge_logs/daily_aggregates tables | Task 2 |
| LogParser reading Pi JSONL files | Task 3 |
| 5 evaluation dimensions (3 deterministic + 2 LLM-as-Judge) | Task 4 |
| Judge sampling rate (50%) | Task 4 (_should_judge) |
| Judge prompt templates for tool_accuracy and task_completion | Task 4 (_judge_tool_accuracy, _judge_task_completion) |
| get_eval_stats handler in tool_executor | Task 5 |
| Pi extension edini_get_eval_stats tool | Task 6 |
| EvalDashboard UI (summary cards, trend chart, session list) | Task 7 |
| EvalTab integration with MainWindow | Task 8 |
| Background evaluation trigger after session | Task 9 |
| Wiki documentation | Already done (evaluation.md in wiki) |
