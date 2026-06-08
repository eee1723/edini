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
                    0,
                    result.tool_calls_count,
                    result.total_latency_ms,
                ),
            )

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

    def get_bottom_sessions(self, limit: int = 20,
                            dimension: str | None = None) -> list[dict]:
        """Get lowest-scoring sessions for a dimension (or total)."""
        valid_dims = {"tool_accuracy", "task_completion", "efficiency",
                      "reliability", "cost"}
        col = dimension if dimension in valid_dims else "total_score"

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
        """Get full evaluation detail for a session."""
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
                "SELECT * FROM judge_logs WHERE session_id = ?",
                (session_id,),
            ).fetchall()

        columns = [d[0] for d in conn.execute("PRAGMA table_info(sessions)")]
        tc_cols = [d[0] for d in conn.execute("PRAGMA table_info(tool_calls)")]
        jl_cols = [d[0] for d in conn.execute("PRAGMA table_info(judge_logs)")]

        return {
            "session": dict(zip(columns, s)),
            "tool_calls": [dict(zip(tc_cols, tc)) for tc in tcs],
            "judge_logs": [dict(zip(jl_cols, jl)) for jl in jls],
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

        dims = ["tool_accuracy", "task_completion", "efficiency",
                "reliability", "cost"]
        avg_scores = {}
        for dim in dims:
            scores = [s[dim] for s in recent if s.get(dim) is not None]
            avg_scores[dim] = round(sum(scores) / len(scores), 3) if scores else None

        mid = len(recent) // 2
        if mid > 0:
            first_avg = sum(s["total_score"] for s in recent[:mid]) / mid
            second_avg = sum(s["total_score"] for s in recent[mid:]) / max(1, len(recent) - mid)
            if second_avg - first_avg > 0.03:
                trend = "improving"
            elif first_avg - second_avg > 0.03:
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
