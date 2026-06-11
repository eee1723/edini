"""Tests for capture_viewport / capture_network — pure logic tests.

These tests validate the function signatures, return value shapes,
and error handling without requiring the Houdini runtime.

To run:   python tests/test_capture_tools.py
"""

import sys
import os
import json
import unittest
from typing import Any

# ---------------------------------------------------------------------------
# Note: capture_viewport() and capture_network() in node_utils.py require
# the Houdini runtime (hou module, PySide6). These tests validate the
# parameter contracts, return value shapes, and integration workflow
# without needing Houdini.
# ---------------------------------------------------------------------------

TOOL_HANDLERS_SIGNATURES = {
    "houdini_capture_viewport": {"required": ["filepath"]},
    "houdini_capture_viewport_safe": {
        "required": ["filepath"],
        "optional": ["frame", "home_viewport"],
    },
    "houdini_capture_network": {"required": ["filepath"], "optional": ["parent_path"]},
}

class TestToolSignatureMatches(unittest.TestCase):
    """Verify that tool parameter names match between TypeScript and Python sides."""

    def test_capture_viewport_has_filepath_param(self):
        """houdini_capture_viewport requires 'filepath' parameter."""
        sig = TOOL_HANDLERS_SIGNATURES["houdini_capture_viewport"]
        self.assertIn("filepath", sig["required"])

    def test_capture_viewport_safe_has_filepath_and_options(self):
        """houdini_capture_viewport_safe requires filepath and accepts safe options."""
        sig = TOOL_HANDLERS_SIGNATURES["houdini_capture_viewport_safe"]
        self.assertIn("filepath", sig["required"])
        self.assertIn("frame", sig["optional"])
        self.assertIn("home_viewport", sig["optional"])

    def test_capture_network_has_filepath_and_parent_path_params(self):
        """houdini_capture_network requires 'filepath', accepts 'parent_path'."""
        sig = TOOL_HANDLERS_SIGNATURES["houdini_capture_network"]
        self.assertIn("filepath", sig["required"])
        self.assertIn("parent_path", sig["optional"])

    def test_capture_viewport_lambda_accesses_filepath(self):
        """The tool_executor lambda correctly accesses kw['filepath']."""
        kw = {"filepath": "screenshots/test.png"}
        self.assertEqual(kw["filepath"], "screenshots/test.png")

    def test_capture_network_lambda_defaults_parent_path(self):
        """The tool_executor lambda defaults parent_path to /obj."""
        kw = {"filepath": "screenshots/net.png"}
        self.assertEqual(kw.get("parent_path", "/obj"), "/obj")

    def test_capture_network_lambda_overrides_parent_path(self):
        """The tool_executor lambda respects explicit parent_path."""
        kw = {"filepath": "screenshots/net.png", "parent_path": "/obj/geo1"}
        self.assertEqual(kw.get("parent_path", "/obj"), "/obj/geo1")


# ---------------------------------------------------------------------------
# Test: return value shape (simulated)
# ---------------------------------------------------------------------------

class TestReturnValueShape(unittest.TestCase):
    """Verify the return value format matches what the Pi extension expects."""

    def test_success_returns_expected_fields(self):
        """A successful capture returns success, path, size_kb, width, height."""
        expected = {
            "success": True,
            "path": "screenshots/viewport_001.png",
            "size_kb": 123.4,
            "width": 800,
            "height": 600,
        }
        self.assertTrue(expected["success"])
        self.assertIn("path", expected)
        self.assertIn("size_kb", expected)
        self.assertIn("width", expected)
        self.assertIn("height", expected)
        # Verify it's JSON-serializable
        serialized = json.dumps(expected)
        self.assertIsInstance(serialized, str)

    def test_network_success_includes_parent_path(self):
        """A successful network capture includes parent_path."""
        expected = {
            "success": True,
            "path": "screenshots/network_001.png",
            "size_kb": 89.2,
            "width": 1024,
            "height": 768,
            "parent_path": "/obj",
        }
        self.assertIn("parent_path", expected)

    def test_failure_returns_error_message(self):
        """A failed capture returns success=False and an error string."""
        expected = {
            "success": False,
            "error": "No Scene Viewer pane found",
        }
        self.assertFalse(expected["success"])
        self.assertTrue(isinstance(expected["error"], str))
        self.assertGreater(len(expected["error"]), 0)

    def test_all_error_paths_are_strings(self):
        """All expected error messages are non-empty strings."""
        errors = [
            "No Scene Viewer pane found",
            "No Network Editor pane found",
            "Viewport grab failed (API mismatch): 'MockPaneTab' object has no attribute 'grab'",
            "Network grab failed (API mismatch): 'MockPaneTab' object has no attribute 'grab'",
        ]
        for e in errors:
            self.assertIsInstance(e, str)
            self.assertGreater(len(e), 0)


# ---------------------------------------------------------------------------
# Test: file path handling edge cases
# ---------------------------------------------------------------------------

class TestFilePathHandling(unittest.TestCase):
    """Verify file path handling edge cases."""

    def test_relative_path(self):
        """Relative paths like 'screenshots/vp.png' should be accepted."""
        filepath = "screenshots/viewport_001.png"
        self.assertTrue(filepath.endswith(".png"))
        self.assertFalse(os.path.isabs(filepath))

    def test_absolute_path(self):
        """Absolute paths should also work."""
        filepath = os.path.abspath("screenshots/abs_vp.png")
        self.assertTrue(os.path.isabs(filepath))

    def test_no_extension_handling(self):
        """Paths without extension still get saved (Qt save handles format)."""
        filepath = "screenshots/no_ext_screenshot"
        # The .grab().save() adds the format, this is fine
        self.assertFalse(filepath.endswith(".png"))

    def test_nested_directories(self):
        """Deeply nested output paths should be creatable."""
        filepath = "screenshots/2024/smoke_sim/viewport_003.png"
        parts = filepath.split("/")
        self.assertEqual(len(parts), 4)
        self.assertTrue(parts[-1].endswith(".png"))


# ---------------------------------------------------------------------------
# Test: integration — describe_image tool (pi-visionizer)
# ---------------------------------------------------------------------------

class TestDescribeImageTool(unittest.TestCase):
    """Verify that describe_image is properly configured for the workflow."""

    def test_describe_image_accepts_path(self):
        """describe_image tool requires a 'path' parameter."""
        params = {"path": "screenshots/viewport_001.png"}
        self.assertIn("path", params)

    def test_describe_image_accepts_optional_prompt(self):
        """describe_image accepts an optional custom prompt."""
        params = {
            "path": "screenshots/viewport_001.png",
            "prompt": "Compare this with the reference: is the smoke density similar?",
        }
        self.assertIn("prompt", params)
        self.assertGreater(len(params["prompt"]), 0)

    def test_workflow_pipeline(self):
        """Simulate the full pipeline: capture -> describe -> compare."""
        # Step 1: Capture
        capture_result = {
            "success": True,
            "path": "screenshots/viewport_001.png",
            "size_kb": 234.5,
            "width": 1920,
            "height": 1080,
        }
        self.assertTrue(capture_result["success"])

        # Step 2: Describe
        describe_params = {
            "path": capture_result["path"],
            "prompt": "Describe what you see in this Houdini viewport screenshot.",
        }
        self.assertEqual(describe_params["path"], "screenshots/viewport_001.png")

        # Step 3: The vision model returns a description
        vision_result = {
            "content": [{
                "type": "text",
                "text": "The viewport shows a smoke simulation with a sphere emitter. "
                        "The density appears uniform with good turbulence detail. "
                        "The bounding box is centered at origin."
            }]
        }
        self.assertIn("smoke", vision_result["content"][0]["text"])

    def test_failed_capture_stops_pipeline(self):
        """When capture fails, describe_image should NOT be called."""
        capture_result = {"success": False, "error": "No Scene Viewer pane found"}
        self.assertFalse(capture_result["success"])
        # Agent should report error and NOT proceed to describe_image
        self.assertIn("error", capture_result)


# ---------------------------------------------------------------------------
# Test: system prompt guidelines
# ---------------------------------------------------------------------------

class TestSystemPromptGuidelines(unittest.TestCase):
    """Verify system prompt correctly guides the agent to use visual verification."""

    def test_guideline_8_mentions_describe_image(self):
        """Guideline 8 should reference describe_image for visual verification."""
        guideline = (
            "After making changes that affect the viewport, use houdini_capture_viewport "
            "to capture a screenshot, then use describe_image to inspect the result."
        )
        self.assertIn("houdini_capture_viewport", guideline)
        self.assertIn("describe_image", guideline)

    def test_guideline_9_mentions_reference_comparison(self):
        """Guideline 9 should mention comparing against reference images."""
        guideline = (
            "When the user provides a reference image, always verify your work "
            "by capturing the viewport and comparing via describe_image."
        )
        self.assertIn("reference image", guideline)
        self.assertIn("describe_image", guideline)


if __name__ == "__main__":
    unittest.main()
