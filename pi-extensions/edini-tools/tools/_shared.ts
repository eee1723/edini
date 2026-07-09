// pi-extensions/edini-tools/tools/_shared.ts
// Shared HTTP transport for the Edini proxy tools.
//
// Every Edini tool is a thin proxy: it forwards the call to the Houdini-side
// tool executor over HTTP (127.0.0.1:<EDINI_TOOL_PORT>) and returns the
// executor's JSON result wrapped for the agent runtime.
//
// ── Async job protocol (2026-07-09 rework) ─────────────────────────────────
// The transport used to be synchronous: POST /execute and block up to 30s for
// the result. That was the root cause of "Houdini freezes solid during an agent
// run". hou.* scene work is main-thread-affined, so a heavy tool
// (project_finalize ≈ 21 recooks) outlasted the 30s timeout; the client then
// aborted and RETRIED, re-enqueuing the whole sweep on an already-busy
// single-threaded executor. One finalize became up to three orphaned
// back-to-back main-thread recook sweeps (every result discarded), locking
// Houdini for minutes and leaving the executor unreachable to every later call.
//
// The executor now runs work on the main thread and accepts it asynchronously:
//   POST /execute        → {status:"queued", job_id}  (instant, no hou)
//   GET  /result/<id>    → {status:"running"|"done"|"unknown", result?}
//
// forwardTool enqueues once, then POLLS for the outcome. The load-bearing
// INVARIANT: once we hold a job_id we NEVER re-POST /execute for that logical
// call — we only poll. The heavy work is issued exactly once; only cheap status
// polls may retry, and only on a transport hiccup. Timeout→retry→amplification
// is now structurally impossible.
//
// This module is the single source of truth for that transport. It:
//   - resolves the port once (EDINI_TOOL_PORT, default 9876),
//   - retries ENQUEUE transport failures (executor briefly down/restarting),
//   - polls a job to completion with a generous overall cap (never re-enqueues),
//   - normalizes EVERY failure into a structured {success:false, error, ...}
//     body so downstream parsing is uniform whether it came from transport or
//     the executor.

const TOOL_PORT = parseInt(process.env.EDINI_TOOL_PORT || "9876", 10);
const TOOL_URL = `http://127.0.0.1:${TOOL_PORT}/execute`;
const RESULT_URL = `http://127.0.0.1:${TOOL_PORT}/result`;

// Enqueue may be retried a couple times: its only real failure mode is the
// executor being briefly down/restarting (a genuine transient). A successful
// enqueue yields a job id; from there we poll, never re-enqueue.
const ENQUEUE_MAX_RETRIES = 2;
const ENQUEUE_TIMEOUT_MS = 10_000;
// Poll cadence: start fast (light tools finish in milliseconds), back off so a
// long cook doesn't spam the executor with status checks.
const POLL_INTERVAL_MS = 15;
const POLL_INTERVAL_MAX_MS = 250;
const POLL_BACKOFF = 1.5;
// A single POLL's transport hiccup is retried a few times (it's a cheap status
// read). This is NOT re-running the tool.
const POLL_TRANSPORT_RETRIES = 4;
// Overall cap: if a job truly never completes (Houdini hung/crashed), give up
// rather than spin forever. 10 min is generous for any legitimate cook.
const JOB_MAX_MS = 10 * 60 * 1000;

/** True when an error is the kind that might succeed on retry (the agent can't
 *  fix these by changing its arguments — they're transport hiccups). */
function isTransient(status: number | undefined, errMsg: string): boolean {
  // Node's fetch rejects with a TypeError whose message is typically
  // "fetch failed" for any socket-level failure (ECONNRESET, ECONNREFUSED on a
  // briefly-restarting executor, DNS hiccup, ...). Treat those as transient.
  if (status === undefined && /fetch failed|network|socket|timeout|reset|refused/i.test(errMsg)) {
    return true;
  }
  // 5xx and 429 (rate) are server-side and may recover.
  if (status !== undefined && (status >= 500 || status === 429)) {
    return true;
  }
  return false;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Wrap an executor result (success OR executor-level failure envelope) in the
 *  agent-runtime shape. The agent reads the JSON text and parses it. */
function successEnvelope(result: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
    details: result,
  };
}

/** Parse a response body as JSON, tolerating empty/non-JSON (a partially-up
 *  executor or an intercepting proxy). Returns null on any parse failure. */
async function tryJson(resp: Response): Promise<unknown> {
  try {
    const text = await resp.text();
    return text ? JSON.parse(text) : null;
  } catch {
    return null;
  }
}

/**
 * Forward a tool call to the Houdini tool executor and return the agent-runtime
 * result envelope. Never throws — every failure path is normalized into a
 * structured result body so callers (and the agent) see consistent shapes.
 *
 * Two phases (see file header for why):
 *   1. Enqueue: POST /execute → {job_id}. Retried only on transport failure
 *      (executor down). Never re-enqueued once we have a job_id.
 *   2. Poll: GET /result/<id> until done/unknown/overall-cap.
 *
 * @param toolName  executor-side tool name (e.g. "houdini_create_node")
 * @param params    arguments object forwarded as the JSON body
 */
export async function forwardTool(
  toolName: string,
  params: Record<string, unknown>,
): Promise<{ content: { type: "text"; text: string }[]; details: unknown }> {
  // ── Phase 1: enqueue (returns a job id instantly). ──
  let jobId: string | undefined;
  let lastErr = "";
  for (let attempt = 0; attempt <= ENQUEUE_MAX_RETRIES; attempt++) {
    if (attempt > 0) await sleep(150 * attempt);

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ENQUEUE_TIMEOUT_MS);
    let resp: Response;
    try {
      resp = await fetch(TOOL_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool: toolName, params }),
        signal: controller.signal,
      });
    } catch (err) {
      clearTimeout(timer);
      lastErr = err instanceof Error ? err.message : String(err);
      if (controller.signal.aborted) lastErr = `enqueue timeout after ${ENQUEUE_TIMEOUT_MS}ms`;
      // Transport error on enqueue (executor down) → retry.
      if (attempt < ENQUEUE_MAX_RETRIES && isTransient(undefined, lastErr)) continue;
      return makeErrorResult(toolName, params, lastErr, { phase: "enqueue" });
    }
    clearTimeout(timer);

    if (!resp.ok) {
      // 5xx is transient (retry); 4xx is a real pre-queue rejection (unknown
      // tool, bad JSON) — surface its body.
      const body = await tryJson(resp);
      if (isTransient(resp.status, "") && attempt < ENQUEUE_MAX_RETRIES) {
        lastErr = `HTTP ${resp.status}`;
        continue;
      }
      const errMsg =
        body && typeof body === "object" && "error" in body
          ? String((body as Record<string, unknown>).error)
          : `HTTP ${resp.status}`;
      return makeErrorResult(toolName, params, errMsg, { http_status: resp.status, phase: "enqueue" });
    }

    const body = await tryJson(resp);
    if (body && typeof body === "object" && typeof (body as Record<string, unknown>).job_id === "string") {
      jobId = (body as Record<string, unknown>).job_id as string;
      break;
    }
    // Legacy/sync executor returned a direct result envelope.
    if (body && typeof body === "object") {
      return successEnvelope(body);
    }
    lastErr = "enqueue returned no job_id";
  }

  if (!jobId) {
    return makeErrorResult(toolName, params, lastErr || "enqueue failed", { phase: "enqueue" });
  }

  // ── Phase 2: poll for the result. The heavy work is never re-issued. ──
  return pollJob(jobId, toolName, params);
}

/** Poll GET /result/<jobId> until the job is done, unknown (evicted), or the
 *  overall cap elapses. Only individual poll transport hiccups are retried. */
async function pollJob(
  jobId: string,
  toolName: string,
  params: Record<string, unknown>,
): Promise<{ content: { type: "text"; text: string }[]; details: unknown }> {
  const deadline = Date.now() + JOB_MAX_MS;
  let interval = POLL_INTERVAL_MS;
  let transportFails = 0;
  while (Date.now() < deadline) {
    await sleep(interval);
    interval = Math.min(interval * POLL_BACKOFF, POLL_INTERVAL_MAX_MS);

    let resp: Response;
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), ENQUEUE_TIMEOUT_MS);
      resp = await fetch(`${RESULT_URL}/${jobId}`, { signal: controller.signal });
      clearTimeout(timer);
    } catch (err) {
      // Transport hiccup on a POLL — retry the cheap poll, never re-enqueue.
      if (++transportFails > POLL_TRANSPORT_RETRIES) {
        return makeErrorResult(
          toolName,
          params,
          `result poll transport failed: ${err instanceof Error ? err.message : String(err)}`,
          { phase: "poll", retryable: true },
        );
      }
      continue;
    }
    transportFails = 0;

    const body = await tryJson(resp);
    if (!body || typeof body !== "object") continue;
    const status = (body as Record<string, unknown>).status;
    if (status === "done") {
      // result holds the executor's normal envelope — success:true OR
      // success:false with error/hint. Both are "the tool produced a result".
      return successEnvelope((body as Record<string, unknown>).result);
    }
    if (status === "unknown") {
      return makeErrorResult(
        toolName,
        params,
        "job result evicted before retrieval (long delay between enqueue and poll); re-issue the call",
        { phase: "poll", retryable: true },
      );
    }
    // status === "running" → keep polling.
  }
  return makeErrorResult(
    toolName,
    params,
    `job did not complete within ${JOB_MAX_MS}ms`,
    { phase: "poll", retryable: true },
  );
}

/** Build a structured error envelope. The `details` body mirrors the shape the
 * executor itself uses on failure ({success:false, error, ...}) so downstream
 * parsing is uniform whether the error came from transport or executor. */
function makeErrorResult(
  toolName: string,
  params: Record<string, unknown>,
  errMsg: string,
  extra: Record<string, unknown> = {},
) {
  const body = {
    success: false,
    error: errMsg,
    tool: toolName,
    // A compact hint of what was being attempted — enough for the agent to
    // decide whether to retry the same call or adjust its arguments.
    hint: hintFor(toolName, errMsg),
    ...extra,
  };
  return {
    content: [{ type: "text" as const, text: JSON.stringify(body, null, 2) }],
    details: body,
  };
}

/** Lightweight, tool-aware guidance so the agent sees a recovery suggestion in
 *  the same message as the failure. Returns "" when there's nothing useful. */
function hintFor(toolName: string, errMsg: string): string {
  if (/timeout|timed?\s*out|did not complete/i.test(errMsg)) {
    return "The Houdini executor did not finish the job in time — it may be cooking a heavy scene. Re-issue the call; if it persists, the scene may be too heavy.";
  }
  if (/refused|reset|fetch failed|ECONN|transport failed/i.test(errMsg)) {
    return (
      "Could not reach the Houdini tool executor (transport error). " +
      "This is usually transient — re-issue the same call once. " +
      "If it persists, Houdini may be busy or the tool server is down."
    );
  }
  return "";
}
