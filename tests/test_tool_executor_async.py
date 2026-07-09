"""Async job/queue protocol for the tool executor (2026-07-09 rework).

Context: the executor was rewritten so hou work runs on a background drain thread and
HTTP never blocks on it. The protocol is now:

    POST /execute      → {status:"queued", job_id}        (instant, no hou)
    GET  /result/<id>  → {status:"running"|"done"|"unknown", result?}

These tests exercise that protocol end-to-end over real HTTP against a
ToolExecutor whose hou is stubbed (so the executor's drain thread runs jobs
inline — the documented headless fallback). They pin the load-bearing
invariants: enqueue is instant and never blocks; a result is retrievable by
polling; the heavy handler runs exactly once; finished jobs are GC'd.
"""
import json
import sys
import threading
import time
import types
import urllib.request

import pytest

# Stub hou before importing edini.tool_executor (it imports hou transitively).
if "hou" not in sys.modules:
    sys.modules["hou"] = types.ModuleType("hou")

from edini import tool_executor as te
from edini.tool_executor import ToolExecutor, ToolJobExecutor, _Job


@pytest.fixture
def executor(cleanup_executors):
    """A started ToolExecutor on a free port, with a temporary test handler."""
    exe = ToolExecutor()
    exe.start()
    cleanup_executors.append(exe)
    yield exe


@pytest.fixture
def cleanup_executors():
    created = []
    yield created
    for exe in created:
        try:
            exe.stop()
        except Exception:
            pass


def _post(exe, payload):
    req = urllib.request.Request(
        f"http://127.0.0.1:{exe.port}/execute",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def _get(exe, job_id):
    with urllib.request.urlopen(f"http://127.0.0.1:{exe.port}/result/{job_id}",
                                timeout=5) as r:
        return json.loads(r.read())


def test_enqueue_returns_job_id_instantly(executor):
    """POST /execute must return a queued+job_id, NOT run the work inline on
    the HTTP thread (that was the old freeze)."""
    te.TOOL_HANDLERS["_test_echo"] = lambda **kw: {"success": True, "got": kw}
    try:
        body = _post(executor, {"tool": "_test_echo", "params": {"x": 1}})
        assert body["status"] == "queued"
        assert isinstance(body["job_id"], str) and body["job_id"]
    finally:
        del te.TOOL_HANDLERS["_test_echo"]


def test_poll_returns_done_result(executor):
    """A queued job's result is retrievable by polling GET /result/<id>."""
    te.TOOL_HANDLERS["_test_echo"] = lambda **kw: {"success": True, "got": kw}
    try:
        job_id = _post(executor, {"tool": "_test_echo",
                                  "params": {"x": 42}})["job_id"]
        result = _poll_until(executor, job_id, "done", timeout=5)
        assert result["status"] == "done"
        assert result["result"]["success"] is True
        assert result["result"]["got"] == {"x": 42}
    finally:
        del te.TOOL_HANDLERS["_test_echo"]


def test_running_status_observable_then_done(executor):
    """While a handler is mid-flight, GET /result must report 'running' (not
    block, not hang). This is what lets the client poll instead of holding a
    connection open (the old synchronous freeze)."""
    release = threading.Event()
    started = threading.Event()
    call_count = [0]

    def slow_handler(**kw):
        call_count[0] += 1
        started.set()
        release.wait(timeout=5)            # deterministically block the drain thread
        return {"success": True, "ran": True}

    te.TOOL_HANDLERS["_test_slow"] = slow_handler
    try:
        job_id = _post(executor, {"tool": "_test_slow", "params": {}})["job_id"]
        assert started.wait(timeout=5), "handler never started on drain thread"
        # While blocked → running (observed before release).
        running = _poll_until(executor, job_id, "running", timeout=5)
        assert running["status"] == "running"
        # Release → done.
        release.set()
        done = _poll_until(executor, job_id, "done", timeout=5)
        assert done["result"]["ran"] is True
        # The heavy handler ran EXACTLY once (no retry amplification).
        assert call_count[0] == 1
    finally:
        del te.TOOL_HANDLERS["_test_slow"]


def test_unknown_tool_rejected_pre_queue(executor):
    """An unknown tool is rejected at enqueue (no job created) with a clear
    error — the client never gets a job_id to poll for nonsense."""
    body = _post(executor, {"tool": "no_such_tool", "params": {}})
    assert body["success"] is False
    assert "no_such_tool" in body["error"]
    assert "job_id" not in body


def test_handler_exception_does_not_hang_client(executor):
    """If the handler raises, the job still completes with an error envelope —
    a polling client is never left waiting forever."""
    def boom(**kw):
        raise RuntimeError("kaboom")

    te.TOOL_HANDLERS["_test_boom"] = boom
    try:
        job_id = _post(executor, {"tool": "_test_boom", "params": {}})["job_id"]
        result = _poll_until(executor, job_id, "done", timeout=5)
        assert result["status"] == "done"
        assert result["result"]["success"] is False
        assert "kaboom" in result["result"]["error"]
    finally:
        del te.TOOL_HANDLERS["_test_boom"]


def test_finished_jobs_garbage_collected_past_cap():
    """The job store must bound memory: finished jobs beyond the cap are
    evicted, so a long session doesn't leak. Running jobs are never evicted."""
    exe = ToolJobExecutor()
    exe.start()                      # inline fallback (hou stubbed)
    try:
        cap = ToolJobExecutor._MAX_JOBS
        for i in range(cap + 50):
            exe.submit("_test_echo", {"i": i})
        # Let the drain thread clear the queue.
        deadline = time.time() + 5
        while exe._queue and time.time() < deadline:  # noqa: SLF001
            time.sleep(0.01)
        time.sleep(0.05)
        assert len(exe._jobs) <= cap + 1, len(exe._jobs)  # +1 headroom for in-flight
    finally:
        exe.stop()


def _poll_until(exe, job_id, want_status, timeout=5):
    """Poll GET /result until status==want_status or timeout."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = _get(exe, job_id)
        if last.get("status") == want_status:
            return last
        time.sleep(0.01)
    assert last is not None
    raise AssertionError(f"never reached status={want_status!r}; last={last}")
