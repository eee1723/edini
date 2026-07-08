"""Shared hython discovery for decisive real-Houdini tests.

Centralized so:

- ``tests/conftest.py`` can report hython availability in the pytest header
  (a decisive test that SKIPs because hython is absent is correct, but it
  used to be SILENT — a mock-only run reported "all green" while the
  decisive layer was unexercised).
- ``test_project_hython`` and ``test_skill_workflow_hython`` don't each carry
  their own copy of ``_find_hython`` (DRY — see pitfalls.md "复制粘贴是技术债
  温床"). The two copies had already drifted: project_hython picked the NEWEST
  installed Houdini, skill_workflow picked the FIRST found. The newest-picking
  version is canonical here.

A *decisive* test exercises real hou behavior (setInput / spare parm / cook /
relative ch()) that mock_hou cannot model. When hython is absent these SKIP;
pass ``--edini-require-hython`` (or set ``EDINI_REQUIRE_HYTHON=1``) to turn
that absence into a hard failure for "I want real proof" runs.
"""
import os
import shutil

_HOUDINI_CANDIDATES = [
    r"C:\Program Files\Side Effects Software",  # 精创机
    r"D:\houdini",                               # 另一台开发机
    "/Applications/Houdini",
    "/opt/hfs",
]


def find_hython():
    """Locate the hython executable, or return None.

    Resolution order: ``EDINI_HYTHON`` / ``HYTHON`` env var → ``shutil.which``
    → the candidate install dirs above. When a candidate dir holds multiple
    Houdini versions, the NEWEST (by directory name, reverse-sorted) wins —
    a single install returns immediately.
    """
    env = os.environ.get("EDINI_HYTHON") or os.environ.get("HYTHON")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("hython") or shutil.which("hython.exe")
    if found:
        return found
    for base in _HOUDINI_CANDIDATES:
        if not os.path.isdir(base):
            continue
        candidates = []
        for exe in ("hython.exe" if os.name == "nt" else "hython",):
            exe_path = os.path.join(base, "bin", exe)
            if os.path.isfile(exe_path):
                candidates.append(("0-direct", exe_path))
        for name in os.listdir(base):
            exe = os.path.join(base, name, "bin",
                               "hython.exe" if os.name == "nt" else "hython")
            if os.path.isfile(exe):
                candidates.append((name, exe))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
    return None


HYTHON = find_hython()

# Test modules whose entire body is @skipUnless(HYTHON) decisive tests.
# conftest's report header uses this to name what gets skipped when hython
# is absent. Add new hython-only modules here.
DECISIVE_HYTHON_MODULES = (
    "test_project_hython",
    "test_skill_workflow_hython",
)
