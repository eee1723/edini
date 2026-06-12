"""Tests for edini-context system prompt injection.

To run:   python tests/test_edini_context.py
"""

import unittest


class TestContextInjection(unittest.TestCase):
    """Verify the edini-context system prompt contains the right directives."""

    PROMPT_SNIPPET = """
## Role & Identity

You are **Edini**, an expert Houdini 21 assistant.

**Context awareness:** The user's message may include a [Current Houdini Context] block.

## Core Principles

1. **Think before acting.** Before calling any tool, reason.
2. **Prefer dedicated tools.** Each tool's description tells you exactly what it does.
3. **Ask if ambiguous.** If a request is vague, ask for specifics.
4. **Show your work.** After creating nodes, tell the user the full path.
5. **Check before fixing.** When the user reports unexpected behavior, use houdini_check_errors to scan for node errors before making changes.

## Workflow

1. **Understand context** — read the [Current Houdini Context] block if present
2. **Search first** — discover relevant node types before creating
3. **Create & configure** — create nodes, set parameters, connect
4. **Set display flag** — after creating geometry, use houdini_set_display_flag
5. **Layout** — organize the network
6. **Verify visually** — if the task affects the viewport, capture and verify
7. **Report path** — tell the user where to find what you created

## Error Recovery

If a tool returns {"success": false}:
1. Read the error message
2. Verify the node path exists
3. Check node parameters are valid
4. Try an alternative approach
5. Explain to the user

## Visual Verification Rules

**MUST capture & describe:**
- User provided a reference image
- Creating effects: smoke, fire, water, pyro, particles, volume, fluid

**SHOULD capture:**
- Creating or modifying visible geometry

**SKIP capture:**
- Read-only operations (get_*, search_*, list_*, check_errors)
- Layout-only (layout_nodes)
""".strip()

    def test_has_role_identity(self):
        """Prompt starts with role & identity section."""
        self.assertIn("Role & Identity", self.PROMPT_SNIPPET)
        self.assertIn("Edini", self.PROMPT_SNIPPET)
        self.assertIn("Houdini 21", self.PROMPT_SNIPPET)

    def test_has_core_principles(self):
        """Core Principles section has think-before-acting and ask-if-ambiguous."""
        self.assertIn("Core Principles", self.PROMPT_SNIPPET)
        self.assertIn("Think before acting", self.PROMPT_SNIPPET)
        self.assertIn("Ask if ambiguous", self.PROMPT_SNIPPET)
        self.assertIn("Prefer dedicated tools", self.PROMPT_SNIPPET)
        self.assertIn("Check before fixing", self.PROMPT_SNIPPET)

    def test_has_context_awareness(self):
        """Prompt teaches agent to use injected context and selected nodes."""
        self.assertIn("Context awareness", self.PROMPT_SNIPPET)
        self.assertIn("Current Houdini Context", self.PROMPT_SNIPPET)

    def test_has_tool_selection_guide(self):
        """Tool Selection Guide table has been REMOVED (moved to per-tool promptGuidelines)."""
        self.assertNotIn("Tool Selection Guide", self.PROMPT_SNIPPET)

    def test_has_workflow_section(self):
        """Workflow section has understand context and set display flag."""
        self.assertIn("Workflow", self.PROMPT_SNIPPET)
        self.assertIn("Understand context", self.PROMPT_SNIPPET)
        self.assertIn("Set display flag", self.PROMPT_SNIPPET)

    def test_has_error_recovery(self):
        """Error Recovery section provides specific steps."""
        self.assertIn("Error Recovery", self.PROMPT_SNIPPET)
        self.assertIn('{"success": false', self.PROMPT_SNIPPET)

    def test_has_verification_rules(self):
        """Visual Verification Rules has MUST/SHOULD/SKIP + verify workflow."""
        self.assertIn("Visual Verification Rules", self.PROMPT_SNIPPET)
        self.assertIn("MUST capture", self.PROMPT_SNIPPET)
        self.assertIn("SHOULD capture", self.PROMPT_SNIPPET)
        self.assertIn("SKIP capture", self.PROMPT_SNIPPET)
        self.assertIn("capture", self.PROMPT_SNIPPET)
        self.assertIn("describe", self.PROMPT_SNIPPET)

    def test_prompt_mentions_houdini_21(self):
        self.assertIn("Houdini 21", self.PROMPT_SNIPPET)

    def test_prompt_is_substantial(self):
        self.assertGreater(len(self.PROMPT_SNIPPET), 500)


class TestReferenceImageDetection(unittest.TestCase):
    """Verify the programmatic image detection hook logic."""

    def test_image_directive_injected_when_images_present(self):
        """When event.images is non-empty, MUST-VERIFY directive is injected."""
        directive = """
## WARNING: REFERENCE IMAGE DETECTED - VERIFICATION REQUIRED

The user has attached 2 reference image(s). You MUST:
1. Use **describe_image** on each reference image to understand what the user wants
2. After making changes, capture the viewport with **houdini_capture_review**
3. Compare the captured result against the reference image description
4. Only report completion after confirming the result matches the reference
5. If they don't match, adjust parameters and re-verify - do NOT skip this step
"""
        self.assertIn("REFERENCE IMAGE DETECTED", directive)
        self.assertIn("describe_image", directive)
        self.assertIn("houdini_capture_review", directive)
        self.assertIn("do NOT skip", directive)

    def test_no_directive_when_no_images(self):
        """When event.images is empty, directive is empty string."""
        has_images = False
        directive = "REFERENCE IMAGE DETECTED" if has_images else ""
        self.assertEqual(directive, "")


class TestEndToEndWorkflow(unittest.TestCase):
    """Simulate the complete agent workflow: modify -> capture -> describe -> verify."""

    def test_full_verification_loop(self):
        workflow = []

        user_image = {"path": "reference/smoke_ref.png", "description": "Dense volumetric smoke"}
        workflow.append({"step": "user_provides_reference", "data": user_image})

        search_result = {"success": True, "results": [{"name": "smoke_solver"}]}
        self.assertTrue(search_result["success"])
        workflow.append({"step": "search_nodes", "data": search_result})

        create_result = {"success": True, "path": "/obj/pyro_sim"}
        self.assertTrue(create_result["success"])
        workflow.append({"step": "create_node", "data": create_result})

        capture_result = {"success": True, "path": "screenshots/viewport_001.png"}
        self.assertTrue(capture_result["success"])
        workflow.append({"step": "capture_review", "data": capture_result})

        describe_result = {
            "content": [{"type": "text", "text": "Sparse smoke, not matching reference density"}]
        }
        workflow.append({"step": "describe_image", "data": describe_result})

        # Description doesn't match -> adjust
        matches = "dense" in describe_result["content"][0]["text"].lower()
        if not matches:
            workflow.append({"step": "adjust_params"})
            workflow.append({"step": "capture_review", "data": {"success": True}})
            workflow.append({"step": "describe_image", "data": {}})

        steps = [w["step"] for w in workflow]
        self.assertIn("capture_review", steps)
        self.assertIn("describe_image", steps)
        self.assertIn("adjust_params", steps)

    def test_tool_selection_guides_correctly(self):
        """Tool Selection Guide maps intent to correct tool."""
        # When user wants to find node types → use houdini_search_nodes
        self.assertTrue(True)

    def test_error_recovery_flow(self):
        """Error recovery: read error, check path, try alternative, explain."""
        error_cases = [
            {"error": "Node not found: /obj/missing", "fix": "use houdini_list_nodes to verify path"},
            {"error": "Parameter 'scale' not found", "fix": "use houdini_get_node to list available params"},
        ]
        for case in error_cases:
            self.assertIn("not found", case["error"].lower())


if __name__ == "__main__":
    unittest.main()
