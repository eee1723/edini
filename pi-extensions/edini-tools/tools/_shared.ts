// pi-extensions/edini-tools/tools/_shared.ts
// Shared HTTP transport for the Edini proxy tools.
//
// Every Edini tool is a thin proxy: it forwards the call to the Houdini-side
// tool executor over HTTP (127.0.0.1:<EDINI_TOOL_PORT>/execute) and returns
// the executor's JSON result wrapped for the agent runtime.
//
// Historically this transport was copy-pasted into 9 tool files with identical
// bodies and NO error handling — a transient network blip surfaced to the agent
// as the bare string "fetch failed", which carries no hint about whether to
// retry, reconnect, or fix the args. The chair-modeling log (2026-07-07) showed
// exactly this: 3 connect_nodes calls died with "fetch failed" mid-session and
// the agent could not tell them from real failures.
//
// This module is the single source of truth for that transport. It:
//   - resolves the port once (EDINI_TOOL_PORT, default 9876),
//   - retries transient failures (network error + a small set of 5xx codes),
//   - enforces a timeout so a wedged executor can't hang the agent forever,
//   - normalizes EVERY failure into a structured {success:false, error, ...}
//     body so the agent sees actionable errors instead of bare strings.

const TOOL_PORT = parseInt(process.env.EDINI_TOOL_PORT || "9876", 10);
const TOOL_URL = `http://127.0.0.1:${TOOL_PORT}/execute`;

// How many times to retry a transient (network/timeout/5xx) failure before
// giving up. Each retry is spaced by RETRY_BACKOFF_MS * attempt.
const MAX_RETRIES = 2;
const RETRY_BACKOFF_MS = 150;
// Overall cap on a single HTTP attempt. The executor runs Python in Houdini
// synchronously, so most calls return in well under a second; 30s is a generous
// ceiling for heavier cooks without letting a truly stuck call hang the agent.
const REQUEST_TIMEOUT_MS = 30_000;

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

/**
 * Forward a tool call to the Houdini tool executor and return the agent-runtime
 * result envelope. Never throws — every failure path is normalized into a
 * structured result body so callers (and the agent) see consistent shapes.
 *
 * @param toolName  executor-side tool name (e.g. "houdini_create_node")
 * @param params    arguments object forwarded as the JSON body
 */
export async function forwardTool(
  toolName: string,
  params: Record<string, unknown>,
): Promise<{ content: { type: "text"; text: string }[]; details: unknown }> {
  const body = JSON.stringify({ tool: toolName, params });
  let lastErr = "";
  let lastStatus: number | undefined;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    if (attempt > 0) {
      await sleep(RETRY_BACKOFF_MS * attempt);
    }

    // An AbortController gives us a real timeout rather than relying on the
    // runtime's default (which is unbounded for Node fetch).
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    let response: Response;
    try {
      response = await fetch(TOOL_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        signal: controller.signal,
      });
    } catch (err) {
      clearTimeout(timer);
      lastStatus = undefined;
      lastErr = err instanceof Error ? err.message : String(err);
      // Aborted-by-timeout is reported as "The operation was aborted" — surface
      // a clearer label to the agent.
      if (controller.signal.aborted) lastErr = `request timeout after ${REQUEST_TIMEOUT_MS}ms`;
      if (attempt < MAX_RETRIES && isTransient(lastStatus, lastErr)) continue;
      return transientFailureResult(toolName, params, lastErr, attempt);
    }
    clearTimeout(timer);

    lastStatus = response.status;

    // Non-JSON / empty body — happens if the executor is partially up or a
    // proxy intercepts. Parse defensively.
    let result: unknown;
    try {
      const text = await response.text();
      result = text ? JSON.parse(text) : null;
    } catch {
      result = null;
    }

    // Transient HTTP status → retry.
    if (isTransient(response.status, "")) {
      lastErr = `HTTP ${response.status}`;
      if (attempt < MAX_RETRIES) continue;
      return transientFailureResult(toolName, params, lastErr, attempt);
    }

    // Non-2xx that isn't transient (e.g. 4xx) — the executor still returns a
    // JSON error body in most cases; pass it through if present, else synthesize.
    if (!response.ok) {
      const errMsg =
        (result && typeof result === "object" && "error" in result
          ? String((result as Record<string, unknown>).error)
          : `HTTP ${response.status}`);
      return makeErrorResult(toolName, params, errMsg, { http_status: response.status });
    }

    // Success path — same envelope every tool file used before.
    return {
      content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
      details: result,
    };
  }

  // All retries exhausted.
  return transientFailureResult(toolName, params, lastErr || "exhausted retries", MAX_RETRIES);
}

/** Build the structured failure body for a transient/transport error. Marked
 *  retryable so the agent knows a re-issued call may well succeed. */
function transientFailureResult(
  toolName: string,
  params: Record<string, unknown>,
  errMsg: string,
  attempt: number,
) {
  const detail = makeErrorResult(toolName, params, errMsg, {
    transient: true,
    retryable: true,
    attempts: attempt + 1,
  });
  return detail;
}

/** Build a structured error envelope. The `details` body mirrors the shape the
 *  executor itself uses on failure ({success:false, error, ...}) so downstream
 *  parsing is uniform whether the error came from transport or executor. */
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
  if (/timeout|timed?\s*out/i.test(errMsg)) {
    return "The Houdini executor did not respond in time — it may be cooking. Re-try the call; if it persists, the scene may be too heavy.";
  }
  if (/refused|reset|fetch failed|ECONN/i.test(errMsg)) {
    return (
      "Could not reach the Houdini tool executor (transport error). " +
      "This is usually transient — re-issue the same call once. " +
      "If it persists, Houdini may be busy or the tool server is down."
    );
  }
  return "";
}
