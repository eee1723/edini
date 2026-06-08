# Agent Evaluation & Logging System — Design Spec

> **Date:** 2026-06-08
> **Project:** Edini — Houdini AI Assistant
> **Status:** Draft for review

## Overview

Build an **agent evaluation system** and **logging system** for Edini to enable continuous optimization. The system records every agent interaction (tool calls, thinking, latencies), scores each session across 5 dimensions, and provides both a UI dashboard for developers and an AgentEval tool for the agent itself to self-reflect.

### Core Principles

- **JSONL is the single source of truth** — All raw interaction data lives in Pi's existing JSONL session files. No data is written to JSONL by the eval system.
- **SQLite is an evaluation view cache** — Evaluation results are stored in a SQLite database alongside session data. It can be rebuilt from JSONL at any time.
- **Backward compatible** — Zero changes to existing Pi extension or JSONL format. All new code is in `edini/eval/` and `edini/ui/eval_tab.py`.
- **Incremental evaluation** — Only evaluate sessions that haven't been scored yet.
- **Sampled LLM-as-Judge** — Judge calls use a configurable sampling rate (default: 100% for first session, 50% thereafter) to manage API costs.

---

## Architecture

```
Pi JSONL (session files)                  ← Existing, unchanged
      │
      ▼
LogParser                                  ← New: edini/eval/log_parser.py
  Reads JSONL lines, extracts:
  - user_queries (per round)
  - tool_calls (name, params, result, latency)
  - thinking_steps
  - assistant_responses
  - metadata (model, tokens, timestamps)
      │
      ▼
StructuredSession                          ← Data class: edini/eval/models.py
      │
      ▼
EvaluatorPipeline                          ← New: edini/eval/evaluator.py
  ├── ReliabilityEval    (deterministic)   — success_rate = successful_calls / total_calls
  ├── EfficiencyEval     (deterministic)   — convergence = min_optimal_steps / actual_steps
  ├── CostEval           (deterministic)   — token & latency percentiles vs task type baseline
  ├── ToolAccuracyEval   (LLM-as-Judge)    — tool selection + parameter correctness
  └── TaskCompletionEval (LLM-as-Judge)    — did the agent achieve the user's goal?
      │
      ▼
SQLite Database                            ← New: edini/eval/store.py
  ├── sessions table       — per-session scores (all 5 dimensions + total)
  ├── tool_calls table     — per-call evaluation details
  ├── judge_logs table     — LLM-as-Judge prompts & responses (debugging)
  └── daily_aggregates     — pre-aggregated trends for fast dashboard queries
      │
      ├────► EvalDashboard (UI)            ← New: edini/ui/eval_tab.py
      │      PySide6 tab in AgentPanel
      │      ├── Summary cards (5 dimensions + total)
      │      ├── Trend chart (7/14/30 days)
      │      └── Session list (sortable, color-coded, click to browse)
      │
      └────► edini_get_eval_stats (Tool)   ← New: pi-extensions tool
             Agent can query own stats for self-reflection
```

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `python3.11libs/edini/eval/__init__.py` | Create | Package init |
| `python3.11libs/edini/eval/models.py` | Create | Data classes: `StructuredSession`, `ToolCallRecord`, `EvalResult`, `EvalDimension` |
| `python3.11libs/edini/eval/log_parser.py` | Create | Parse Pi JSONL files into StructuredSession |
| `python3.11libs/edini/eval/evaluator.py` | Create | EvaluatorPipeline with all 5 evaluators |
| `python3.11libs/edini/eval/store.py` | Create | SQLite EvalStore (CRUD + aggregates) |
| `python3.11libs/edini/ui/eval_tab.py` | Create | EvalDashboard QWidget (3-section layout) |
| `python3.11libs/edini/ui/main_window.py` | Modify | Add EvalTab to tab widget |
| `python3.11libs/edini/ui/agent_panel.py` | Modify | Add trigger for background evaluation after session finishes |
| `python3.11libs/edini/tool_executor.py` | Modify | Register `edini_get_eval_stats` handler |
| `pi-extensions/edini-tools/tools/eval.ts` | Create | Pi extension tool definition for `edini_get_eval_stats` |
| `pi-extensions/edini-tools/index.ts` | Modify | Export eval tool |

---

## Data Models

### StructuredSession (in-memory)

```python
@dataclass
class ToolCallRecord:
    index: int                         # Call order in session
    tool_name: str                     # e.g. "houdini_create_node"
    params: dict[str, Any]             # Parsed parameters
    result_success: bool               # Did execution succeed?
    error_message: str | None          # Error if any
    latency_ms: int                    # Duration of tool execution
    tokens_used: int | None            # Token cost if tracked

@dataclass
class StructuredSession:
    session_id: str
    jsonl_path: str
    cwd: str
    model_id: str | None
    created_at: str
    user_queries: list[str]            # Each user message (by round)
    tool_calls: list[ToolCallRecord]
    thinking_steps: list[str]
    assistant_responses: list[str]
    total_latency_ms: int
    total_tokens: int | None
    message_count: int
```

### EvalResult

```python
@dataclass
class EvalResult:
    session_id: str
    evaluated_at: str
    
    # Dimension scores [0.0, 1.0]
    tool_accuracy: float | None     # LLM-as-Judge
    task_completion: float | None   # LLM-as-Judge
    efficiency: float               # Deterministic
    reliability: float              # Deterministic
    cost: float                     # Deterministic
    
    total_score: float              # Weighted sum
    
    # Detailed breakdown
    tool_call_details: list[dict]   # Per-call eval results
    judge_logs: list[dict]          # Judge prompts/responses (for debugging)
    
    # Derived
    thinking_steps_count: int
    tool_calls_count: int
    total_latency_ms: int
```

---

## SQLite Schema

```sql
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
    total_latency_ms INTEGER DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0,
    user_queries    TEXT  -- JSON array for display
);

CREATE TABLE IF NOT EXISTS tool_calls (
    call_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(session_id),
    call_index      INTEGER NOT NULL,
    tool_name       TEXT NOT NULL,
    params          TEXT,          -- JSON
    result_status   TEXT,          -- 'success' | 'error' | 'timeout'
    error_message   TEXT,
    latency_ms      INTEGER,
    eval_correct    INTEGER,       -- 0/1/None — LLM-as-Judge verdict
    eval_optimal    INTEGER,       -- 0/1/None — Was this the best tool choice?
    eval_reason     TEXT,
    token_usage     INTEGER
);

CREATE TABLE IF NOT EXISTS judge_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(session_id),
    dimension       TEXT NOT NULL, -- 'tool_accuracy' | 'task_completion'
    prompt          TEXT,          -- Full prompt sent to judge model
    response        TEXT,          -- Judge's full response
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

CREATE INDEX IF NOT EXISTS idx_tool_calls_session ON tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_judge_logs_session ON judge_logs(session_id);
```

---

## Evaluation Dimensions

| Dimension | Weight | Type | Method | Description |
|-----------|--------|------|--------|-------------|
| tool_accuracy | 30% | LLM-as-Judge | Judge model scores tool selection + parameter correctness + ordering | Did the agent pick the right tool and fill parameters correctly? |
| task_completion | 30% | LLM-as-Judge | Judge model scores whether user goal was achieved | Was the user's request (e.g. "create a smoke sim") fully satisfied? |
| efficiency | 15% | Deterministic | convergence = min_optimal_steps / actual_steps | How close is the agent's path to the optimal path for similar queries |
| reliability | 15% | Deterministic | success_rate = successful_calls / total_calls | Tool execution success rate (no errors, no timeouts) |
| cost | 10% | Deterministic | Percentile-based: token + latency vs task-type baseline | Resource efficiency per task type |

### Total Score

```
total_score = 0.30 * tool_accuracy
            + 0.30 * task_completion
            + 0.15 * efficiency
            + 0.15 * reliability
            + 0.10 * cost
```

If LLM-as-Judge scores are None (sampling skipped), total_score is computed from available dimensions only, with weights re-normalized.

### Color Thresholds

| Range | Label | Color |
|-------|-------|-------|
| ≥ 0.85 | Excellent | 🟢 |
| 0.70 – 0.84 | Needs attention | 🟡 |
| < 0.70 | Needs improvement | 🔴 |

---

## LLM-as-Judge

### Sampling Strategy

- **First evaluation of a session:** 100% run Judge (build baseline)
- **Subsequent sessions:** 50% sampling rate (configurable via eval settings)
- **Judge model:** Uses the configured vision model (e.g., qwen-vl-max) or a dedicated judge model. Typically a more capable model works better for judging.
- **Judge calls are async background tasks** — never block the UI.

### Judge Prompts

**Tool Accuracy Judge:**
```
You are an evaluator for a Houdini AI assistant. 
Analyze the following tool call record and determine:

1. Was the correct tool selected for the user's intent?
2. Were the parameters correctly extracted and valid?
3. Was the tool called at the right time in the sequence?

Session context:
{user_query}

Tool call {index}: {tool_name}
Parameters: {params}
Result: {result_success} {error_message}

Output JSON only:
{"score": 0.0-1.0, "reason": "..."}
```

**Task Completion Judge:**
```
You are an evaluator for a Houdini AI assistant.
Analyze the entire session below and determine if the user's task was accomplished.

User's original request: {first_user_query}

Summary of actions:
{tool_call_summary}

Final assistant response: {assistant_response}

Consider:
- Was the original request fulfilled?
- Is the final output usable in Houdini?
- Were there any critical errors?

Output JSON only:
{"score": 0.0-1.0, "reason": "..."}
```

---

## EvalDashboard UI

### Tab Location

New tab in AgentPanel: `[Agent] [History] [⚙ Settings] [📊 Evaluate]`

### Three Sections

**1. Summary Cards (top)**
- One card per dimension + total score
- Shows: recent 7-day average, trend arrow (↑↓→) vs previous 7 days
- Color-coded per threshold
- Click a card to filter the session list below by that dimension

**2. Trend Chart (middle)**
- Custom `QWidget.paintEvent` or `QGraphicsView`
- X-axis: dates (last 7/14/30 days, toggleable)
- Y-axis: score 0.0–1.0
- One line per dimension (toggleable visibility)
- Auto-refresh on tab switch

**3. Session List (bottom)**
- `QTableWidget` with columns: quality dot | total score | date | session title | details
- Sortable by any column
- Rows color-coded by total score threshold
- Click → expand detail panel showing per-dimension breakdown + Judge reasons
- Double-click → navigate to session browsing mode (`set_browsing_mode`)

### Footer Buttons

| Button | Action |
|--------|--------|
| 📥 Export Report | Generate self-contained HTML report of current view |
| 🔄 Re-evaluate | Re-run all evaluators on all sessions |
| ⚙ Config | Dialog: Judge model, sampling rate, dimension weights |

---

## AgentEval Tool (`edini_get_eval_stats`)

### Pi Extension

**File:** `pi-extensions/edini-tools/tools/eval.ts`

```typescript
export const ediniGetEvalStats = {
  name: "edini_get_eval_stats",
  label: "Get Eval Stats",
  description: `Query the agent's own evaluation history. Returns average scores across all dimensions, 
recent trend direction, weakest dimension, and common failure patterns. 
Use after completing a task for self-reflection and improvement.`,
  promptSnippet: "Get my evaluation history and performance trends",
  promptGuidelines: [
    "Use edini_get_eval_stats at the start or end of a session to understand your recent performance trends.",
    "If your tool_accuracy score is low, be extra careful with parameter extraction and tool selection.",
    "Use the 'common_failures' field to avoid repeating past mistakes.",
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

### Handler in tool_executor.py

```python
"edini_get_eval_stats": lambda **kw: get_eval_stats(
    period=kw.get("period", 10),
),
```

### Implementation

```python
def get_eval_stats(period: int = 10) -> dict:
    """Read from SQLite and return evaluation stats for agent self-reflection.
    
    Returns:
        success: bool
        avg_scores: dict of dimension→float
        trend: "improving" | "declining" | "stable"
        weakest_dimension: str
        common_failures: list[str]
        session_count: int
    """
    from edini.eval.store import EvalStore
    store = EvalStore()
    
    recent = store.get_recent_sessions(limit=max(1, period))
    if not recent:
        return {"success": True, "avg_scores": {}, "trend": "stable", 
                "weakest_dimension": "", "common_failures": [], "session_count": 0}
    
    # Calculate averages
    dims = ["tool_accuracy", "task_completion", "efficiency", "reliability", "cost"]
    avg_scores = {}
    for dim in dims:
        scores = [s[dim] for s in recent if s.get(dim) is not None]
        avg_scores[dim] = round(sum(scores) / len(scores), 3) if scores else None
    
    # Trend by comparing first half vs second half
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
    
    # Weakest dimension
    valid = {k: v for k, v in avg_scores.items() if v is not None}
    weakest = min(valid, key=valid.get) if valid else ""
    
    # Common failures (aggregated from tool_calls errors)
    failures = store.get_common_failures(limit=period, max_items=5)
    
    return {
        "success": True,
        "avg_scores": avg_scores,
        "trend": trend,
        "weakest_dimension": weakest,
        "common_failures": [f["error"] for f in failures],
        "session_count": len(recent),
    }
```

---

## Integration Points

### MainWindow

In `_build_tabs()` or equivalent, add:
```python
from edini.ui.eval_tab import EvalTab
from edini.eval.store import EvalStore

self._eval_store = EvalStore()
self._eval_tab = EvalTab(self._eval_store)
self._tab_widget.addTab(self._eval_tab, "📊 Evaluate")
```

### AgentPanel (evaluation trigger)

After a session finishes (`finish_streaming`, `show_aborted`), trigger background evaluation:
```python
def _trigger_background_eval(self):
    """Run evaluator in background thread after session ends."""
    import threading
    session_path = self._current_session_path
    if not session_path or not Path(session_path).exists():
        return
    t = threading.Thread(
        target=self._run_evaluation,
        args=(session_path,),
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
        # Emit signal to refresh dashboard if tab is visible
        self.sig_eval_completed.emit(session.session_id, result.total_score)
    except Exception as e:
        logger.warning(f"Background eval failed: {e}")
```

### Pi Extension Registration

In `pi-extensions/edini-tools/index.ts`, add:
```typescript
import { ediniGetEvalStats } from "./tools/eval";
export const tools = [
  ...sceneTools,
  ...scriptTools,
  ...hdaTools,
  ediniGetEvalStats,
];
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| JSONL file corrupt/malformed | LogParser skips malformed lines, returns partial StructuredSession |
| SQLite file missing | EvalStore auto-creates DB and tables |
| Judge API call fails | ToolAccuracy/TaskCompletion scores = None, total_score computed from available dims |
| Re-evaluation | Overwrites existing scores for session_id |
| Concurrent access | SQLite WAL mode for read-concurrent safety. Single-writer via store's internal lock |

---

## Edge Cases

- **Empty session** (JSONL with header only): Evaluator returns all-None scores, not crash
- **Session with no tool calls** (pure chat): ToolAccuracy = None, Efficiency = 1.0 (0 steps = optimal)
- **Session with all failing tools**: Reliability = 0, but TaskCompletion may still be >0 if agent tried
- **First ever session**: No baseline for cost_percentile → use fixed default values
- **Session directory deleted but DB has records**: get_eval_stats still works from cached DB
- **Switching between different models**: DB tracks model_id, panel can filter by model
- **Very long sessions (100+ tool calls)**: LogParser handles efficiently; Judge prompt may need truncation — implement max tool_calls to include in judge prompt (default: last 20)
