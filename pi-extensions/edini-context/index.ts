// pi-extensions/edini-context/index.ts
// Injects Houdini context + knowledge base into the system prompt.

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

const KNOWLEDGE_FILE = path.join(os.homedir(), ".pi", "agent", "edini-knowledge.json");

interface KnowledgeEntry {
  id: string;
  category: string;
  title: string;
  content: string;
  created_at: string;
}

const CATEGORY_ICONS: Record<string, string> = {
  "避坑": "🐛",
  "技巧": "💡",
  "工作流": "📋",
  "模型局限": "⚠️",
};

function loadKnowledge(): KnowledgeEntry[] {
  try {
    if (fs.existsSync(KNOWLEDGE_FILE)) {
      const raw = fs.readFileSync(KNOWLEDGE_FILE, "utf-8");
      return JSON.parse(raw);
    }
  } catch (_) {
    // ignore
  }
  return [];
}

function buildKnowledgeContext(): string {
  const entries = loadKnowledge();
  if (entries.length === 0) return "";

  const lines: string[] = ["", "## 知识库（来自之前对话的沉淀）", ""];
  for (const e of entries) {
    const icon = CATEGORY_ICONS[e.category] || "📌";
    lines.push(`- [${icon} ${e.category}] ${e.title}: ${e.content}`);
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

    // Inject knowledge base (from previous conversations)
    const knowledgeText = buildKnowledgeContext();

    return { systemPrompt: event.systemPrompt + "\n\n" + houdiniContext + knowledgeText };
  });
}
