"""Text-level tests for Pi harness tool registration."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_harness_tools_file_contains_all_tool_names():
    text = read("pi-extensions/edini-tools/tools/harness.ts")
    # Post-Task-7: tool names were streamlined (houdini_ prefix dropped on
    # renamed tools; old names still work via TOOL_ALIASES in tool_executor.py).
    # Stage-1 (single-build-path): build_component/assemble_components removed
    # (the old component_builder/assembly_engine backend) — the only build
    # entry point is now build_procedural_asset.
    for name in [
        "houdini_collect_diagnostics",
        "houdini_run_python_sandbox",
        "houdini_verify_asset",
        "commit_sandbox",
        "discard_sandbox",
        "capture_review",
        "verify_orientation",
        "build_procedural_asset",
        "validate_recipe",
        "dump_parm_catalog",
    ]:
        assert name in text


def test_verify_asset_expected_is_object_shaped():
    text = read("pi-extensions/edini-tools/tools/harness.ts")
    assert "Type.Record(Type.String(), Type.Unknown())" in text
    assert "expected?: Record<string, unknown>" in text


def test_index_registers_harness_tools():
    text = read("pi-extensions/edini-tools/index.ts")
    assert 'import { harnessTools } from "./tools/harness";' in text
    assert "...harnessTools" in text


def test_raw_python_guidance_mentions_sandbox():
    text = read("pi-extensions/edini-tools/tools/script.ts")
    # Task 7 removed houdini_run_python. The VEX/HDA tools are the only
    # remaining non-sandboxed tools. The VEX tool must warn about this.
    assert "not sandboxed" in text.lower()
    assert "houdini_run_python_sandbox" in text or "houdini_run_vex" in text


def test_review_guidance_mentions_views():
    text = read("pi-extensions/edini-tools/tools/harness.ts")
    assert "views=['perspective','top','front','right']" in text


def test_procedural_modeling_skill_requires_harness():
    text = read("skills/procedural-modeling/SKILL.md")
    # Post-Task-8: skill was rewritten with streamlined tool names
    # and new pipeline-phase routing. Stage-1 (single-build-path) made
    # build_procedural_asset the sole build entry point; build_component/
    # assemble_components tools were removed, so we assert the canonical
    # build entry point instead.
    assert "validate_recipe" in text
    assert "build_procedural_asset" in text
    assert "commit_sandbox" in text
    assert "query_parms" in text or "houdini" in text.lower()
    assert "recipe-authoring" in text or "Recipe" in text
    assert "component-building" in text or "component" in text.lower()
    assert "verification" in text.lower()


def test_procedural_modeling_preview_mentions_harness_lifecycle():
    text = read("skills/procedural-modeling/preview.html")
    assert "houdini_commit_sandbox" in text
    assert "houdini_discard_sandbox" in text
    assert "Do not explore Qt widgets" in text


def test_batch_params_schema_exists():
    """Verify the houdini_set_params_batch tool is defined in Pi extension."""
    text = read("pi-extensions/edini-tools/tools/scene.ts")
    assert "houdini_set_params_batch" in text, (
        "houdini_set_params_batch should be defined in scene.ts"
    )
