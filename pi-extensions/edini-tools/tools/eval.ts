// pi-extensions/edini-tools/tools/eval.ts
// Agent self-evaluation tool — queries the Edini eval system.

import { Type } from "typebox";

const TOOL_PORT = parseInt(process.env.EDINI_TOOL_PORT || "9876", 10);
const TOOL_URL = `http://127.0.0.1:${TOOL_PORT}/execute`;

async function forwardTool(toolName: string, params: Record<string, unknown>) {
  const response = await fetch(TOOL_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool: toolName, params }),
  });
  const result = await response.json();
  return {
    content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
    details: result,
  };
}

export const ediniGetEvalStats = {
  name: "edini_get_eval_stats",
  label: "Get Eval Stats",
  description:
    "Query the agent's own evaluation history. " +
    "Returns average scores across all dimensions (tool_accuracy, task_completion, efficiency, reliability, cost), " +
    "recent trend direction (improving/declining/stable), weakest dimension, and common failure patterns. " +
    "Use at the start or end of a session for self-reflection and to identify areas for improvement. " +
    "If a dimension score is low, focus on that aspect in subsequent tool calls.",
  promptSnippet:
    "Get my evaluation history, performance trends, and common failure patterns",
  promptGuidelines: [
    "Use edini_get_eval_stats at the start of a session to understand your recent performance trends.",
    "If tool_accuracy is your weakest dimension, be extra careful with parameter extraction and tool selection.",
    "If reliability is low, double-check tool parameters before calling and handle errors gracefully.",
    "Review common_failures to avoid repeating past mistakes.",
    "Use this after completing tasks to build a self-improvement loop.",
  ],
  parameters: Type.Object({
    period: Type.Optional(
      Type.Number({
        description: "Number of recent sessions to analyze (default: 10, max: 100)",
        default: 10,
      })
    ),
  }),
  async execute(_toolCallId: string, params: { period?: number }) {
    return forwardTool("edini_get_eval_stats", params);
  },
};
