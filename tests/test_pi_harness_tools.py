"""Text-level tests for Pi harness tool registration."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_harness_tools_file_contains_all_tool_names():
    text = read("pi-extensions/edini-tools/tools/harness.ts")
    for name in [
        "houdini_collect_diagnostics",
        "houdini_run_python_sandbox",
        "houdini_verify_asset",
        "houdini_commit_sandbox",
        "houdini_discard_sandbox",
        "houdini_capture_viewport_safe",
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
    assert "not sandboxed" in text
    assert "houdini_run_python_sandbox" in text


def test_viewport_guidance_mentions_safe_capture():
    text = read("pi-extensions/edini-tools/tools/scene.ts")
    assert "houdini_capture_viewport_safe" in text


def test_procedural_modeling_skill_requires_harness():
    text = read("skills/procedural-modeling/SKILL.md")
    assert "houdini_run_python_sandbox" in text
    assert "houdini_collect_diagnostics" in text
    assert "houdini_verify_asset" in text
    assert "houdini_commit_sandbox" in text
    assert "houdini_discard_sandbox" in text
    assert "Do not delete a failed procedural node" in text
    assert "Do not explore Qt widgets" in text
    assert "Diagnose before switching strategy" in text
    assert "switch to Python SOP only if diagnostics" in text


def test_procedural_modeling_preview_mentions_harness_lifecycle():
    text = read("skills/procedural-modeling/preview.html")
    assert "houdini_commit_sandbox" in text
    assert "houdini_discard_sandbox" in text
    assert "Do not explore Qt widgets" in text
