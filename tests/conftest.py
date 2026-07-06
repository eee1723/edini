"""Pytest configuration for Edini tests."""
import sys
import os

# Ensure python3.11libs is on sys.path for all tests.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))

# Manual diagnostic scripts live under tests/ and are meant to be pasted into
# the Houdini Python Shell (`import hou`), not run by pytest. They either crash
# collection (top-level `import hou` on machines without Houdini) or are
# interactive. Exclude them globally so the suite collects cleanly.
collect_ignore_glob = ["manual_*"]


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
        reload_edini_modules("edini.assembly_builder", "edini.exprs")

    Each name clears itself plus any ``<name>.<sub>`` submodules, but NEVER
    touches unrelated ``edini.ui.*`` / ``edini.project.*`` modules.
    """
    for _m in list(sys.modules):
        if _m in names or any(_m.startswith(n + ".") for n in names):
            del sys.modules[_m]
