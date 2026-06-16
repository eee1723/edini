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
