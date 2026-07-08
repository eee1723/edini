"""Pytest configuration for Edini tests."""
import os
import sys

import pytest

# Ensure python3.11libs is on sys.path for all tests.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
# tests/ itself: conftest is imported BEFORE pytest adds the test dir to
# sys.path (that happens at collection), so it must add its own dir to reach
# the shared _hython helper. Test files then import _hython the same way.
sys.path.insert(0, os.path.dirname(__file__))

from _hython import HYTHON, DECISIVE_HYTHON_MODULES  # noqa: E402  (after sys.path setup)

# Manual diagnostic scripts live under tests/ and are meant to be pasted into
# the Houdini Python Shell (`import hou`), not run by pytest. They either crash
# collection (top-level `import hou` on machines without Houdini) or are
# interactive. Exclude them globally so the suite collects cleanly.
collect_ignore_glob = ["manual_*"]


def pytest_report_header(config):
    """Make hython availability LOUD in the test header.

    Decisive real-Houdini tests (``@skipUnless(HYTHON)``) SKIP silently when
    hython is absent — which let a mock-only run report "all green" while the
    decisive layer (setInput / spare parm / cook / relative ch()) was never
    exercised. This header line states plainly whether hython was found and
    names the modules that will skip, so a skipped decisive layer can't hide
    behind a passing mock count.
    """
    if HYTHON:
        return [f"edini hython: AVAILABLE ({HYTHON}) — decisive real-Houdini tests WILL run."]
    return [
        "edini hython: NOT FOUND — decisive real-Houdini tests will SKIP.",
        "  decisive modules that will skip: " + ", ".join(DECISIVE_HYTHON_MODULES),
        "  Set EDINI_HYTHON (or run on a Houdini machine) for real-geometry proof,",
        "  or pass --edini-require-hython to make this a hard failure.",
    ]


def pytest_addoption(parser):
    parser.addoption(
        "--edini-require-hython",
        action="store_true",
        default=False,
        help="Fail (instead of skip) decisive real-Houdini tests when hython is "
             "unavailable. Also activatable via EDINI_REQUIRE_HYTHON=1.",
    )


def pytest_configure(config):
    """Honour --edini-require-hython: if decisive tests are required but
    hython is missing, fail the run loudly at configure time (before
    collection) instead of letting everything skip silently."""
    require = config.getoption("--edini-require-hython") or bool(
        os.environ.get("EDINI_REQUIRE_HYTHON")
    )
    if require and not HYTHON:
        pytest.exit(
            "edini: --edini-require-hython set but hython was not found. "
            "Set EDINI_HYTHON or run on a Houdini machine for decisive tests.",
            returncode=1,
        )


def reload_edini_modules(*names):
    """Remove specific ``edini.*`` modules from ``sys.modules`` so the next
    ``import`` re-executes them against the current ``sys.modules['hou']``.

    WHY THIS EXISTS
        Several test suites install a mock ``hou`` into ``sys.modules`` and must
        then re-import a target module (e.g. ``edini.node_utils``) so its
        module-level ``import hou`` binds to the mock. The old idiom was::

            for _m in list(sys.modules):
                if _m.startswith("edini"):
                    del sys.modules[_m]

        That sweeps the ENTIRE ``edini.*`` namespace, including UI/chat modules
        whose class identity must stay stable across the suite. Re-executing a
        module produces NEW class objects, so a widget created with the old
        ``UserBubble`` fails ``isinstance``/``findChildren`` against the freshly
        re-imported one — producing flaky ``test_base_driver`` /
        ``test_project_chat_driver`` failures (see wiki/pitfalls.md,
        "test pollution: edini.* module sweep").

    USAGE
        # Only what this test actually needs to re-bind to the mock hou:
        reload_edini_modules("edini.node_utils")
        reload_edini_modules("edini.project.builder", "edini.node_utils")

    Each name clears itself plus any ``<name>.<sub>`` submodules, but NEVER
    touches unrelated ``edini.ui.*`` / ``edini.project.*`` modules.
    """
    for _m in list(sys.modules):
        if _m in names or any(_m.startswith(n + ".") for n in names):
            del sys.modules[_m]
