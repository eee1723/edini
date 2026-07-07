r"""Diagnose why the Project HDA chat panel shows "disconnected".

Run this in the Houdini Python Console (Window > Python Shell, or the in-pane
console). It reproduces the exact RpcClient startup path the chat dialog uses,
but captures Pi's stdout/stderr/exit-code inline so you can see WHY Pi dies
instead of staring at a bare "disconnected" status.

Usage in Houdini Python Console:
    import sys; sys.path.insert(0, r"E:\edini")
    import diagnose_rpc; diagnose_rpc.run()

Or from a shell with Houdini's python:
    python diagnose_rpc.py

What it reports:
  1. Whether the pi executable is found and runnable.
  2. Whether the tool executor (HTTP server) is up on the expected port.
  3. Pi's startup events (extensions loaded? errors?).
  4. Pi's stderr (the real crash reason -- this is what [pi:stderr] mirrors).
  5. Pi's exit code and whether it stayed alive with stdin held open.

The single most common cause of instant "disconnected" is a Pi-side fatal error
printed to stderr that the dialog never surfaces -- this script surfaces it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time


def _section(title: str) -> None:
    print(f"\n{'=' * 60}\n {title}\n{'=' * 60}")


def _find_pi() -> str | None:
    """Mirror edini.config._find_pi so we test the SAME resolution."""
    env_path = os.environ.get("EDINI_PI_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    npm_root = os.environ.get("APPDATA", "") + r"\npm"
    for name in ("pi.cmd", "pi"):
        p = os.path.join(npm_root, name)
        if os.path.isfile(p):
            return p
    import shutil
    found = shutil.which("pi")
    return found


def run(duration: float = 8.0) -> None:
    _section("1. Pi executable")
    pi = _find_pi()
    if not pi:
        print("✗ pi NOT FOUND. Set EDINI_PI_PATH or install "
              "@earendil-works/pi-coding-agent globally.")
        return
    print(f"✓ found: {pi}")

    _section("2. Tool executor HTTP server (edini tools target this port)")
    port = None
    try:
        from edini.tool_executor import get_active_tool_port
        port = get_active_tool_port()
        print(f"✓ active tool port: {port}")
    except Exception as e:
        print(f"  (could not get tool port via tool_executor: {e})")
        port = int(os.environ.get("EDINI_TOOL_PORT", "9876"))
        print(f"  falling back to EDINI_TOOL_PORT/env default: {port}")

    if port is not None:
        import urllib.request
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/", timeout=2
            )
        except Exception as e:
            # HTTPError (404/405) means the server IS up — it just doesn't
            # serve GET /. Only a connection-refused is a real problem.
            name = type(e).__name__
            if name == "HTTPError":
                print(f"✓ server responds (HTTP {e.code} on / — that's healthy)")
            elif name in ("URLError", "ConnectionError") or "refused" in str(e).lower():
                print(f"✗ CANNOT reach tool server on port {port}: {e}")
                print("  The HTTP server inside Houdini isn't running. Pi tool "
                      "calls would fail. This alone can cause failures but not "
                      "an instant disconnected.")
            else:
                print(f"  (probe inconclusive: {name}: {e})")

    _section("3. Launching Pi exactly as the chat dialog does")
    # Build the command mirroring config.get_pi_command()
    ext_dir = os.path.dirname(os.path.abspath(__file__))
    extensions = [
        os.path.join(ext_dir, "pi-extensions", "edini-tools", "index.ts"),
        os.path.join(ext_dir, "pi-extensions", "edini-context", "index.ts"),
    ]
    cmd = [pi, "--mode", "rpc", "--approve", "--no-skills"]
    for e in extensions:
        if os.path.isfile(e):
            cmd.extend(["-e", e])
        else:
            print(f"  ⚠ extension missing, skipping: {e}")

    env = dict(os.environ)
    if port is not None:
        env["EDINI_TOOL_PORT"] = str(port)

    print(f"cmd: {' '.join(cmd[:6])} ...")
    print(f"EDINI_TOOL_PORT={env.get('EDINI_TOOL_PORT', '(unset)')}")

    stderr_lines: list[str] = []
    events: list[dict] = []

    popen_kwargs: dict = dict(
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1, env=env,
    )
    # Mirror rpc_client: isolate Pi in its own process group on Windows so a
    # parent-side console-control event can't cascade in and kill it with
    # 0xC000013A. This is THE fix for the "instant disconnected" symptom.
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW
            | subprocess.CREATE_NEW_PROCESS_GROUP
        )
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        popen_kwargs["startupinfo"] = startupinfo

    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except FileNotFoundError:
        print("✗ FileNotFoundError — pi executable couldn't be spawned.")
        return
    except Exception as e:
        print(f"✗ Popen failed: {e!r}")
        return

    # Read stderr in a thread so we can show it.
    def _drain_stderr():
        try:
            for line in proc.stderr:
                stderr_lines.append(line.rstrip())
        except Exception:
            pass
    threading.Thread(target=_drain_stderr, daemon=True).start()

    # Read stdout in a background thread too. The main thread MUST NOT call
    # readline() on Pi's stdout directly: in RPC mode Pi stays quiet after the
    # startup events (it waits for stdin commands), so a blocking readline()
    # would hang forever and the deadline check below would never run —
    # freezing the whole script. The thread feeds events into a list the main
    # loop inspects.
    def _drain_stdout():
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    events.append({"type": "non_json", "raw": line[:200]})
        except Exception:
            pass
    threading.Thread(target=_drain_stdout, daemon=True).start()

    # Poll for `duration` seconds, watching for Pi exiting. stdin stays OPEN
    # (the dialog does this — closing stdin makes Pi exit cleanly and masks a
    # real crash). We do NOT call readline() here — only poll the process.
    deadline = time.time() + duration
    exited_code = None
    while time.time() < deadline:
        rc = proc.poll()
        if rc is not None:
            exited_code = rc
            elapsed = duration - (deadline - time.time())
            print(f"\n✗ Pi EXITED after {elapsed:.1f}s with code {rc} "
                  f"(0x{(rc & 0xFFFFFFFF):08X})")
            break
        time.sleep(0.1)  # yield; don't busy-spin
    else:
        print(f"\n✓ Pi still alive after {duration}s — did NOT exit on its own.")

    # Clean up.
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    _section("4. Pi stdout events captured")
    if not events:
        print("(none — Pi produced no JSONL events before exiting)")
    for ev in events:
        t = ev.get("type", "?")
        msg = ev.get("message") or ev.get("error") or ""
        print(f"  [{t}] {str(msg)[:160]}")
        s = json.dumps(ev)
        if "error" in s.lower():
            print(f"      full: {s[:300]}")

    _section("5. Pi stderr (THE crash reason — this is what [pi:stderr] shows)")
    if not stderr_lines:
        print("(empty — Pi wrote nothing to stderr)")
    else:
        for line in stderr_lines:
            print(f"  [pi:stderr] {line}")

    _section("6. Diagnosis")
    # exited_code is the code Pi died with DURING the watch window (None = it
    # survived the full duration). Do NOT use proc.returncode here — by now we
    # have terminate()'d Pi during cleanup, which would misleadingly read as a
    # nonzero exit even when Pi was healthy the whole time.
    rc_final = exited_code
    # The signature of the console-control-event kill on Windows:
    # 0xC000013A = STATUS_CONTROL_C_EXIT. When Pi dies with this and no stderr,
    # it was NOT a Pi bug — a parent-side console control event cascaded into
    # Pi's process group and terminated it. The fix is spawning Pi with
    # CREATE_NEW_PROCESS_GROUP (now applied in rpc_client.py).
    CTRL_C_EXIT = 0xC000013A  # 3221225786

    if rc_final is None:
        print("✓ Pi stays alive for the full window. The console-isolation fix")
        print("  is working (CREATE_NEW_PROCESS_GROUP). Re-open the chat dialog —")
        print("  it should now stay 'connected'.")
    elif rc_final == CTRL_C_EXIT:
        print(f"✗ Pi killed by a CONSOLE CONTROL EVENT (exit 0xC000013A).")
        print("  This is the 'instant disconnected' root cause: Pi shared its")
        print("  console session with Houdini, so a control event inside")
        print("  Houdini cascaded to Pi and terminated it. The fix is")
        print("  CREATE_NEW_PROCESS_GROUP — if you still see this after the")
        print("  rpc_client.py fix, the flag isn't being applied.")
    elif rc_final == 0 and not stderr_lines:
        print("  Pi exited cleanly (code 0) with no stderr. If it emitted events")
        print("  first, this is the stdin-EOF self-exit — normal when nothing")
        print("  holds the pipe. NOT the disconnected symptom.")
    elif stderr_lines:
        print("✗ Pi crashed on startup. The stderr above is the cause.")
        print("  Common fixes:")
        print("   • Missing/invalid API key → set it in Edini settings or .pi env")
        print("   • Node version too old → Pi needs Node 18+")
        print("   • Corrupted install → npm install -g @earendil-works/pi-coding-agent")
    else:
        print(f"  Pi exited (code {rc_final}) with no stderr and no events —")
        print("  unusual. Try running pi directly in a terminal with the same")
        print("  flags to reproduce.")


if __name__ == "__main__":
    run()
