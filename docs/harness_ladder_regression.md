# Procedural Harness Ladder Regression

This note captures the 2026-06-11 ladder incident as a regression target for Edini's procedural harness.

Expected behavior after Phase B:

- The agent creates a ladder in a live sandbox first.
- Failed Python SOP or node-network attempts are preserved until diagnostics are collected.
- Diagnostics include node path, node errors, node warnings, traceback when available, geometry stats, and bounds.
- Verification checks non-empty geometry and non-zero bounds before commit.
- Visual capture uses `houdini_capture_viewport_safe`.
- The agent does not explore Qt widgets or unsupported viewport internals when capture fails.

The unit regression in `tests/test_procedural_harness.py::TestLadderRegression` verifies the structural part of this workflow without requiring Houdini.
