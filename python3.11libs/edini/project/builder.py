"""Project HDA → component scaffold builder + parameter promoter.

REWRITTEN for the component-pipeline paradigm (replaces the old
rooted-assembly build_project_model). Implementation lands in Task 4
(scaffold) and Task 5 (promote). This stub keeps the import path stable
so tool_executor wiring (Task 6) can reference it without a half-built
module.

See docs/superpowers/specs/2026-07-02-project-component-foundation-design.md.
"""
from __future__ import annotations
