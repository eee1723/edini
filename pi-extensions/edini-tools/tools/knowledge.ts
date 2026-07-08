// pi-extensions/edini-tools/tools/knowledge.ts
// Knowledge search tool — lets the agent query the accumulated knowledge base.

import { Type } from "typebox";
import { forwardTool } from "./_shared";

export const ediniSearchKnowledge = {
  name: "edini_search_knowledge",
  label: "Search Knowledge Base",
  description:
    "Search the accumulated knowledge base for relevant tips, pitfalls, workflows, and configuration notes. " +
    "The knowledge base contains lessons learned from past sessions — both iron rules (always applied) and " +
    "detailed entries (searchable). Use this to avoid repeating past mistakes and to leverage known techniques. " +
    "Search by keyword, category, or both.",
  promptSnippet: "Search the knowledge base for relevant tips and pitfalls",
  promptGuidelines: [
    "Use edini_search_knowledge at the start of a session to check if there are known tips or pitfalls related to the user's request.",
    "When working with unfamiliar node types or effects, search the knowledge base first to avoid known issues.",
    "If you encounter an error, search the knowledge base to see if this is a known pitfall with a documented solution.",
    "Categories: 避坑 (pitfalls), 技巧 (tips), 工作流 (workflows), 配置 (configuration).",
  ],
  parameters: Type.Object({
    query: Type.String({
      description: "Search keyword to match against title and content",
    }),
    category: Type.Optional(
      Type.String({
        description: "Filter by category: 避坑, 技巧, 工作流, 配置",
      })
    ),
    limit: Type.Optional(
      Type.Number({
        description: "Maximum results to return (default: 10)",
        default: 10,
      })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { query: string; category?: string; limit?: number }
  ) {
    return forwardTool("edini_search_knowledge", params);
  },
};

// Drafts are auto-captured failure modes from project_finalize (Phase 5a).
// They are quarantined out of edini_search_knowledge until a human promotes
// them, so search THIS tool — not the main one — when diagnosing a failure.
export const ediniSearchDrafts = {
  name: "edini_search_drafts",
  label: "Search Failure Drafts",
  description:
    "Search auto-captured failure-mode drafts from past sessions. " +
    "Every project_finalize failure is recorded as a draft (category, component, " +
    "param, message, fix hint). Drafts are excluded from the main knowledge base " +
    "until promoted — use THIS tool, not edini_search_knowledge, to find prior " +
    "diagnoses of a failure you are hitting now.",
  promptSnippet: "Search past failure diagnoses before retrying a failed verify/finalize",
  promptGuidelines: [
    "When verify_parametric / verify_robust / project_finalize fails, search drafts for the same failure category (dead_param, degenerate, cook_error, orientation, incomplete) before retrying — a past session may have already solved it.",
    "Each draft carries a fix hint in its content — read it.",
    "Drafts are unverified (auto-captured). Confirm the fix applies to your case; if a draft is broadly correct, ask the user to raise (promote) it.",
  ],
  parameters: Type.Object({
    query: Type.Optional(
      Type.String({
        description: "Search keyword to match against title and content",
      })
    ),
    category: Type.Optional(
      Type.String({
        description: "Filter by category: 避坑, 技巧, 工作流, 配置",
      })
    ),
    limit: Type.Optional(
      Type.Number({
        description: "Maximum results to return (default: 10)",
        default: 10,
      })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { query?: string; category?: string; limit?: number }
  ) {
    return forwardTool("edini_search_drafts", params);
  },
};
