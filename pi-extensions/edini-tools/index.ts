// pi-extensions/edini-tools/index.ts
// Edini tools extension — registers all Houdini proxy tools.

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { sceneTools } from "./tools/scene";
import { queryTools } from "./tools/query";
import { scriptTools } from "./tools/script";
import { ediniGetEvalStats } from "./tools/eval";
import { ediniSearchKnowledge } from "./tools/knowledge";

export default function (pi: ExtensionAPI) {
  const allTools = [...sceneTools, ...queryTools, ...scriptTools, ediniGetEvalStats, ediniSearchKnowledge];

  for (const tool of allTools) {
    pi.registerTool(tool);
  }

  pi.on("session_start", async (_event, ctx) => {
    ctx.ui.notify(
      `Edini tools loaded (${allTools.length} tools, Houdini port ${process.env.EDINI_TOOL_PORT || "9876"})`,
      "info"
    );
  });
}
