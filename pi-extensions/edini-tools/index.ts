// pi-extensions/edini-tools/index.ts
// Edini tools extension — registers all Houdini proxy tools.

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { sceneTools } from "./tools/scene";
import { queryTools } from "./tools/query";
import { scriptTools } from "./tools/script";
import { harnessTools } from "./tools/harness";
import { recipeTools } from "./tools/recipe";
import { rootedTools } from "./tools/rooted";
import { projectTools } from "./tools/project";
import { ediniGetEvalStats } from "./tools/eval";
import { ediniSearchKnowledge } from "./tools/knowledge";

export default function (pi: ExtensionAPI) {
  // Visual verification gate — when disabled, hide capture_review (and the
  // vision describe_image tool, gated in pi-visionizer). Toggle via
  // settings.json visual_verification_enabled → EDINI_VISUAL_VERIFICATION env.
  // [VISUAL-VERIFY-GATE]
  const visualVerificationOn = process.env.EDINI_VISUAL_VERIFICATION === "true";

  const allTools = [
    ...sceneTools,
    ...queryTools,
    ...scriptTools,
    ...harnessTools,
    ...recipeTools,
    ...rootedTools,
    ...projectTools,
    ediniGetEvalStats,
    ediniSearchKnowledge,
  ].filter((tool) => visualVerificationOn || tool.name !== "capture_review");

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
