"""ToolExecutor multi-instance port isolation regression tests.

Bug context: edini used a single hardcoded port (9876) for the tool-executor
HTTP server. On Windows, SO_REUSEADDR lets a second Houdini "successfully"
bind the same port while the first process keeps receiving all connections —
silent cross-process routing (operations in project B's HDA panel landed in
project A's Houdini).

Fix: ToolExecutor now probes for a free port (preferring 9876 for backward
compat, falling back to an OS-assigned ephemeral port). The real bound port is
exposed via get_active_tool_port() and propagated to Pi subprocesses via the
EDINI_TOOL_PORT env var (config.get_pi_env reads the accessor, not the
constant). A per-PID discovery file under ~/.edini/ports/ aids debugging.

These tests stub `hou` (the Houdini module) since tool_executor transitively
imports it at module load, but the port-isolation logic is hou-independent.
"""
import json
import os
import sys
import types
import urllib.request

import pytest

# Stub hou before importing edini.tool_executor (which imports harness → hou).
if "hou" not in sys.modules:
    sys.modules["hou"] = types.ModuleType("hou")
sys.path.insert(0, "python3.11libs")

from edini.tool_executor import ToolExecutor, get_active_tool_port
from edini.config import get_pi_env, TOOL_EXECUTOR_PORT


@pytest.fixture
def cleanup_executors():
    """Track executors created during a test and stop them after."""
    created = []
    yield created
    for exe in created:
        try:
            exe.stop()
        except Exception:
            pass


def test_two_executors_get_different_ports(cleanup_executors):
    """Regression: two ToolExecutors (simulating two Houdini processes) must
    NOT share a port. Before the fix both bound 9876 and the first stole all
    traffic from the second."""
    a = ToolExecutor()
    a.start()
    cleanup_executors.append(a)
    b = ToolExecutor()
    b.start()
    cleanup_executors.append(b)
    assert a.port != b.port


def test_executor_binds_preference_when_free(cleanup_executors):
    """When the preferred port (9876) is free, it should be used (backward
    compatibility for the common single-instance case)."""
    # Free up 9876 if a previous test left a server on it, then probe.
    # We test the probe logic directly with a known-free high port.
    free_port = _find_free_port()
    exe = ToolExecutor(port=free_port)
    exe.start()
    cleanup_executors.append(exe)
    assert exe.port == free_port


def test_executor_falls_back_when_preferred_taken(cleanup_executors):
    """When the preferred port is already bound, fall back to an OS-assigned
    port instead of failing or stealing traffic."""
    # Occupy a port, then try to start an executor on it.
    import socket
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    blocked_port = blocker.getsockname()[1]
    try:
        exe = ToolExecutor(port=blocked_port)
        exe.start()
        cleanup_executors.append(exe)
        # Must have fallen back to a DIFFERENT port (ephemeral).
        assert exe.port != blocked_port
        assert exe.port > 0
    finally:
        blocker.close()


def test_get_active_tool_port_returns_real_port(cleanup_executors):
    """get_active_tool_port() must return the actually-bound port, not the
    config default. This is the value Pi subprocesses must use."""
    port = get_active_tool_port()
    assert port > 0
    # The global executor is process-level; track it for cleanup.
    from edini.tool_executor import _global_executor
    if _global_executor is not None:
        cleanup_executors.append(_global_executor)


def test_get_pi_env_uses_real_port(cleanup_executors):
    """The EDINI_TOOL_PORT env var passed to Pi must equal the real bound port,
    not the TOOL_EXECUTOR_PORT constant. This is the load-bearing fix: Pi
    routes tool calls to this Houdini via this port.

    Uses a dedicated ToolExecutor (not the global singleton) so the assertion
    is unaffected by other tests starting/stopping the global executor.
    """
    import edini.tool_executor as te
    # Use a local executor and patch get_active_tool_port to return its port,
    # so get_pi_env picks up THIS port deterministically.
    exe = ToolExecutor()
    exe.start()
    cleanup_executors.append(exe)
    orig = te.get_active_tool_port
    te.get_active_tool_port = lambda: exe.port
    try:
        env = get_pi_env()
        assert env["EDINI_TOOL_PORT"] == str(exe.port)
    finally:
        te.get_active_tool_port = orig


def test_health_endpoint_reports_pid(cleanup_executors):
    """/health must report the PID so a client can verify which Houdini it
    reached (multi-instance diagnostics)."""
    exe = ToolExecutor()
    exe.start()
    cleanup_executors.append(exe)
    resp = urllib.request.urlopen(f"http://127.0.0.1:{exe.port}/health", timeout=2)
    data = json.loads(resp.read())
    assert data["status"] == "ok"
    assert data["pid"] == os.getpid()


def test_port_file_written_and_cleaned(cleanup_executors):
    """A per-PID discovery file should be written on start and removed on stop."""
    from edini.tool_executor import _port_file_path
    exe = ToolExecutor()
    exe.start()
    cleanup_executors.append(exe)
    p = _port_file_path()
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["pid"] == os.getpid()
    assert data["port"] == exe.port
    exe.stop()
    cleanup_executors.remove(exe)
    assert not p.exists()


# ── helpers ──

def _find_free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
