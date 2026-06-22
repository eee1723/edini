"""Skill-document freshness guard (optimization 2 from the architectural review).

This test is a DRIFT DETECTOR, not a behavior test. It asserts that the
agent-facing skill docs describe the CURRENT code reality. When a refactor
changes a fact (a tool is deleted, a gate is added, a check is renamed),
this test fails until the docs are updated to match — preventing the kind of
wide doc/code drift that accumulated during the single-path refactor
(removed tools still documented, deleted PCA fallback still taught, etc.).

How to use: if you intentionally change one of the guarded facts, UPDATE the
doc the assertion points at in the SAME commit. Do not weaken the assertion.
Each assertion names the fact it guards and where the doc should state it.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


# ─── Skills root ─────────────────────────────────────────────────────────
SKILL = "skills"


def _all_skill_md() -> dict[str, str]:
    """Return {relative_path: text} for every SKILL.md under skills/."""
    out = {}
    for p in (ROOT / SKILL).rglob("SKILL.md"):
        out[str(p.relative_to(ROOT)).replace("\\", "/")] = p.read_text(encoding="utf-8")
    return out


ALL_SKILLS = _all_skill_md()


# ═══════════════════════════════════════════════════════════════════════════
#  Guard 1: deleted tools must not be documented as usable
# ═══════════════════════════════════════════════════════════════════════════
# Stage 1 deleted build_component / assemble_components. If a skill doc tells
# the agent to call them, the agent will hit a tool-not-found and flail.

@pytest.mark.parametrize("path,text", list(ALL_SKILLS.items()),
                         ids=lambda p: p)
def test_no_skill_documents_deleted_tools(path, text):
    # 'build_component' as a tool CALL (not the internal build step name).
    # Allow 'build_procedural_asset' (the real entry). The deleted tool was
    # invoked as build_component(...); flag that call form.
    lower = text.lower()
    assert "build_component(" not in text, (
        f"{path}: documents the DELETED build_component tool call. "
        "Use build_procedural_asset(recipe) instead.")
    assert "assemble_components(" not in text, (
        f"{path}: documents the DELETED assemble_components tool call.")
    # The handler names in tool_executor must not appear as live tools.
    assert '"build_component"' not in text, (
        f"{path}: references deleted build_component handler.")


# ═══════════════════════════════════════════════════════════════════════════
#  Guard 2: PCA fallback must not be taught as a live path
# ═══════════════════════════════════════════════════════════════════════════
# Stage 5 removed the PCA estimation branch (hub 90° bug). A prim without a
# baked edini_world_axis now fails (method:"no_axis"), not falls back to PCA.

def test_no_skill_teaches_pca_fallback():
    decl = read(f"{SKILL}/procedural-modeling/references/declarative-builder.md")
    # The canonical stale phrasing was "falls back to PCA on point positions".
    assert "falls back to pca" not in decl.lower(), (
        "declarative-builder.md teaches the REMOVED PCA fallback. Stage 5 "
        "deleted it — a prim without edini_world_axis fails (method:no_axis). "
        "construction_axis is now mandatory (A8), not 'preferred over PCA'.")
    # construction_axis must be framed as mandatory, not optional/preferred.
    assert "preferred over leaving orientation to pca" not in decl.lower(), (
        "declarative-builder.md calls construction_axis 'preferred'. It is "
        "MANDATORY (A8) post-Stage-2.")


# ═══════════════════════════════════════════════════════════════════════════
#  Guard 3: validation must be advertised as A1-A9, not A1-A6
# ═══════════════════════════════════════════════════════════════════════════
# Stage 2 added A7 (backend), A8 (construction_axis), A9 (hardcoded size).

def test_recipe_authoring_lists_a1_a9():
    ra = read(f"{SKILL}/recipe-authoring/SKILL.md")
    assert "A9" in ra and "A8" in ra, (
        "recipe-authoring must list A1-A9 (Stage 2 added A7/A8/A9). "
        "Found missing A8 or A9 — the pre-flight checklist is incomplete.")
    # The old 'all 6 checks' framing must be gone.
    assert "全部 6 项" not in ra and "all 6 checks" not in ra.lower(), (
        "recipe-authoring still claims 'all 6 checks' — it is 9 now.")


def test_router_advertises_a1_a9():
    router = read(f"{SKILL}/procedural-modeling/SKILL.md")
    assert "A1-A9" in router or "A1–A9" in router, (
        "procedural-modeling router must advertise A1-A9 validation.")


# ═══════════════════════════════════════════════════════════════════════════
#  Guard 4: raw network_mode must not be recommended for multi-component
# ═══════════════════════════════════════════════════════════════════════════
# network_mode builds don't bake edini_world_axis and cannot pass G3. Skills
# must not present it as a co-equal build path for multi-component/repeated
# assets.

def test_assembly_wiring_does_not_recommend_network_mode():
    aw = read(f"{SKILL}/assembly-wiring/SKILL.md")
    # The dangerous pattern was 'build_component(network_mode=true)' as the
    # normal path for spokes/chain. That exact phrase must be gone.
    assert "build_component(network_mode=true)" not in aw, (
        "assembly-wiring recommends the deleted network_mode Workspace for "
        "micro-repetition — those builds cannot pass the G3 commit gate. "
        "Use multi-anchor CTP or houdini_variant_scatter.")


def test_vexlib_usage_build_path_consistent():
    vu = read(f"{SKILL}/procedural-modeling/scripts/vexlib-usage.md")
    # The stale form was 'built via build_procedural_asset OR network_mode'.
    # After the fix it must say build_procedural_asset only (+ G3 caveat).
    assert "or `network_mode`" not in vu.lower(), (
        "vexlib-usage.md lists network_mode as a co-equal build path. It "
        "cannot pass G3 for multi-component assets.")


# ═══════════════════════════════════════════════════════════════════════════
#  Guard 5: the verification_receipt must be documented where commit is taught
# ═══════════════════════════════════════════════════════════════════════════
# Stage 4 made commit_sandbox return a tamper-evident receipt; Stage 7 made
# referencing it mandatory in the completion report.

def test_verification_skill_documents_receipt():
    v = read(f"{SKILL}/verification/SKILL.md")
    assert "verification_receipt" in v, (
        "verification/SKILL.md must document the verification_receipt "
        "(Stage 4/7) and the rule that completion reports reference it.")


def test_router_mentions_receipt():
    router = read(f"{SKILL}/procedural-modeling/SKILL.md")
    assert "verification_receipt" in router, (
        "procedural-modeling router must mention the verification_receipt "
        "in the commit step.")


# ═══════════════════════════════════════════════════════════════════════════
#  Guard 6: the G3 commit gate must be documented in the verification protocol
# ═══════════════════════════════════════════════════════════════════════════

def test_verification_protocol_documents_g3_gate():
    vp = read(f"{SKILL}/procedural-modeling/references/verification-protocol.md")
    # The commit step must mention the G3 gate (bake + orientation + health).
    assert "G3" in vp, (
        "verification-protocol.md must document the G3 commit gate "
        "(bake + orientation + health defense-in-depth layers).")


# ═══════════════════════════════════════════════════════════════════════════
#  Guard 7: every sub-skill must have an exit-condition block
# ═══════════════════════════════════════════════════════════════════════════
# A sub-skill loaded in isolation must tell the agent where to go next.
# The exit block is marked by a '## 完成后' or '## Phase 6' heading.

SUB_SKILLS_WITH_EXIT = [
    "skills/recipe-authoring/SKILL.md",
    "skills/component-building/SKILL.md",
    "skills/assembly-wiring/SKILL.md",
    "skills/verification/SKILL.md",
    "skills/parametric-testing/SKILL.md",
    "skills/edini-brainstorm/SKILL.md",
]


@pytest.mark.parametrize("path", SUB_SKILLS_WITH_EXIT,
                         ids=lambda p: p)
def test_sub_skill_has_exit_block(path):
    text = read(path)
    has_exit = (
        "## 完成后" in text
        or "## Phase 6" in text
        or "## Transition to Implementation" in text
    )
    assert has_exit, (
        f"{path}: no exit-condition block ('## 完成后' or equivalent). "
        "A sub-skill loaded in isolation must tell the agent where to go "
        "next — see edini-brainstorm Phase 6 as the template.")


# ═══════════════════════════════════════════════════════════════════════════
#  Guard 8: harness.ts tool registry must match tool_executor handlers
# ═══════════════════════════════════════════════════════════════════════════
# If a tool is registered in TS but not handled in Python (or vice versa),
# the agent sees a tool it can't call, or a handler nothing invokes.

def test_harness_ts_and_tool_executor_agree_on_tools():
    ts = read("pi-extensions/edini-tools/tools/harness.ts")
    exe = read("python3.11libs/edini/tool_executor.py")
    # Extract `name: "..."` tool names from harness.ts tool definitions.
    import re
    ts_names = set(re.findall(r'name:\s*"([a-z_]+)"', ts))
    # Extract handler keys "name": from the executor dispatch dict.
    exe_names = set(re.findall(r'"([a-z_]+)":\s*lambda', exe))
    # Tools defined in TS but with no Python handler = broken (agent calls,
    # handler 404s). Allow a small set of known non-dispatched names.
    # (Some TS names may be display-only; we check the critical direction.)
    missing_handlers = ts_names - exe_names
    # Filter out names that are intentionally not dispatched (e.g. aliases
    # handled via TOOL_ALIASES). If this set grows, investigate.
    assert not missing_handlers, (
        f"harness.ts defines tools with no tool_executor handler: "
        f"{sorted(missing_handlers)}. Either add the handler or the TS def "
        f"is stale.")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
