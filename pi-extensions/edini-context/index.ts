// pi-extensions/edini-context/index.ts
// Injects Houdini context + iron rules (铁律) into the system prompt.

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

const KNOWLEDGE_DIR = path.join(os.homedir(), ".pi", "agent", "edini-knowledge");
const RULES_FILE = path.join(KNOWLEDGE_DIR, "rules.json");

interface IronRule {
  id: string;
  category: string;
  title: string;
  content: string;
  enabled: boolean;
  created_at: string;
}

const CATEGORY_ICONS: Record<string, string> = {
  "避坑": "⚠️",
  "技巧": "💡",
  "工作流": "📋",
  "配置": "⚙️",
};

function loadEnabledRules(): IronRule[] {
  try {
    if (fs.existsSync(RULES_FILE)) {
      const raw = fs.readFileSync(RULES_FILE, "utf-8");
      const rules: IronRule[] = JSON.parse(raw);
      return rules.filter((r) => r.enabled !== false);
    }
  } catch (_) {
    // ignore — first run won't have the file yet
  }
  return [];
}

function buildRulesContext(): string {
  const rules = loadEnabledRules();
  if (rules.length === 0) return "";

  const lines: string[] = ["", "## 铁律（必须遵守的知识）", ""];
  for (const r of rules) {
    const icon = CATEGORY_ICONS[r.category] || "📌";
    lines.push(`- [${icon} ${r.category}] **${r.title}**: ${r.content}`);
  }
  return lines.join("\n");
}

export default function (pi: ExtensionAPI) {
  pi.on("before_agent_start", async (event, ctx) => {
    const houdiniContext = `
You are operating inside Houdini 21 (a 3D animation/VFX package by SideFX) as Edini, the Houdini AI assistant.

Your available tools allow you to:
- Create, delete, connect, and inspect Houdini nodes
- Set and read node parameters
- Search for node types by keyword
- Inspect geometry (point counts, attributes, etc.)
- Execute Python code in Houdini's Python environment
- Execute VEX code via temporary Attribute Wrangle nodes
- Create and inspect HDAs (digital assets)

The user is interacting with you through a panel inside Houdini. They can see the scene viewport alongside your chat. When you create or modify nodes, the user sees the changes in real-time.

**Guidelines:**
1. When the user asks to create an effect (smoke, fire, water, destruction, etc.), use houdini_search_nodes to find relevant node types first, then create them step by step.
2. After creating nodes, use houdini_layout_nodes to clean up the network layout.
3. Use dedicated node tools whenever possible. Only use houdini_run_python for operations that can't be done with dedicated tools.
4. When you create nodes, tell the user the full path so they can find them in the network view.
5. If an operation fails, explain why and suggest alternatives.
6. Houdini node paths use /obj as the default object-level container.
7. Fetch scene info with houdini_get_scene_info when you need context.
`.trim();

    // Inject iron rules (enabled rules from knowledge store)
    const rulesText = buildRulesContext();

    return { systemPrompt: event.systemPrompt + "\n\n" + houdiniContext + rulesText };
  });
}
