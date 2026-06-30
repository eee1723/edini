#!/usr/bin/env node
// Pi data bridge — extracts provider/model info from the installed pi-ai package.
// Called by Edini's Python settings dialog to get the latest provider/model list.
// Usage: node pi_data_bridge.mjs [providers|models <providerId>|vision-models]
//
// ════════════════════════════════════════════════════════════════════════════
// WHY THIS EXISTS (and why the old version broke)
// ════════════════════════════════════════════════════════════════════════════
// The previous bridge parsed pi-ai's models.generated.js as a self-contained
// object literal via `new Function("return " + source)()`. That worked when the
// MODELS export was inline JSON, but pi-ai (v0.80+) split each provider's model
// table into its own module and the aggregate now reads
//     export const MODELS = { "x": X_MODELS, ... }   // X_MODELS is an import
// so the literal is full of free identifiers the eval sandbox can't resolve →
// ReferenceError → empty provider list in the settings panel.
//
// THE FIX: stop parsing source text. Use pi-ai's own module system to load it,
// via its public provider API (builtinProviders / getModels). This tracks any
// future restructuring automatically — we read the resolved data, never the
// source layout.
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

// ── Locate the pi-ai package across the known install layouts ───────────────
// Try several roots; the first one exposing dist/providers/all.js wins. This
// makes the bridge resilient to whether pi was installed globally
// (npm/node_modules), vendored inside Edini, or via hoisted monorepo style.
function findPiAiDir() {
  const candidates = [];
  const appdata = process.env.APPDATA || "";
  if (appdata) {
    candidates.push(
      path.join(appdata, "npm/node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-ai"),
    );
  }
  candidates.push(path.join(process.cwd(), "vendor/node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-ai"));
  candidates.push(path.join(process.cwd(), "node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-ai"));
  candidates.push(path.join(process.cwd(), "node_modules/@earendil-works/pi-ai"));
  for (const dir of candidates) {
    if (dir && fs.existsSync(path.join(dir, "dist/providers/all.js"))) return dir;
  }
  return null;
}

const PI_AI_DIR = findPiAiDir();
if (!PI_AI_DIR) {
  // Emit a JSON envelope Python can still parse so the panel degrades to
  // "no providers" instead of surfacing a crash traceback.
  console.error("pi_data_bridge: could not locate @earendil-works/pi-ai dist/providers/all.js");
  console.log("[]");
  process.exit(0);
}

// pi-ai is an ESM package ("type": "module"); import its provider registry.
// pathToFileURL yields the file:// URL Node requires on Windows.
const ALL_URL = pathToFileURL(path.join(PI_AI_DIR, "dist/providers/all.js")).href;

try {
  const all = await import(ALL_URL);
  const command = process.argv[2] || "providers";

  // Each provider object: { id, name, auth, getModels(), ... }
  // getModels() returns a { modelId: modelObj } map synchronously.
  const providers = all.builtinProviders();

  if (command === "providers") {
    // Output: [{id, name, authType, modelCount, imageModelCount}]
    const result = providers.map((p) => {
      const models = Object.values(p.getModels());
      const withImage = models.filter((m) => m.input && m.input.includes("image"));
      const authKeys = p.auth ? Object.keys(p.auth) : [];
      return {
        id: p.id,
        name: p.name || p.id,
        authType: authKeys[0] || "",
        modelCount: models.length,
        imageModelCount: withImage.length,
      };
    });
    console.log(JSON.stringify(result));
  } else if (command === "models") {
    // Output for a specific provider: argv[3] = provider id
    const providerId = process.argv[3];
    const p = providers.find((x) => x.id === providerId);
    if (!p) {
      console.log("[]");
    } else {
      const result = Object.values(p.getModels()).map((m) => ({
        id: m.id,
        name: m.name || m.id,
        reasoning: !!m.reasoning,
        input: m.input || ["text"],
      }));
      console.log(JSON.stringify(result));
    }
  } else if (command === "vision-models") {
    // Output: all models that support image input (for the vision selector)
    const result = [];
    for (const p of providers) {
      for (const m of Object.values(p.getModels())) {
        if (m.input && m.input.includes("image")) {
          result.push({
            provider: p.id,
            id: m.id,
            name: (m.name || m.id) + " (" + (p.name || p.id) + ")",
            reasoning: !!m.reasoning,
          });
        }
      }
    }
    console.log(JSON.stringify(result));
  } else {
    console.log("[]");
  }
} catch (e) {
  console.error("pi_data_bridge error:", e.message);
  console.log("[]");
}
