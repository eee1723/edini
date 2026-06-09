#!/usr/bin/env node
// Pi data bridge — extracts provider/model info from installed pi-ai package.
// Called by Edini's Python settings dialog to get the latest provider list.
// Usage: node pi_data_bridge.js [providers|models|vision-models]
"use strict";
const fs = require("fs");
const path = require("path");

// Locate pi-ai models.generated.js
const PI_AI_DIR = path.join(
  process.env.APPDATA || "",
  "npm/node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-ai"
);
const MODELS_FILE = path.join(PI_AI_DIR, "dist/models.generated.js");
const DISPLAY_NAMES_FILE = path.join(
  process.env.APPDATA || "",
  "npm/node_modules/@earendil-works/pi-coding-agent/dist/core/provider-display-names.js"
);

function loadModels() {
  const content = fs.readFileSync(MODELS_FILE, "utf-8");
  // Find the line starting with 'export const MODELS'
  const idx = content.indexOf("export const MODELS");
  if (idx < 0) return {};
  let jsonish = content.slice(idx)
    .replace(/^export\s+const\s+MODELS\s*=\s*/, "")
    .replace(/;\s*\/\/#\s+sourceMapping.*$/s, "")
    .trimEnd();
  if (jsonish.endsWith(";")) jsonish = jsonish.slice(0, -1);
  return new Function("return " + jsonish)();
}

function loadDisplayNames() {
  const content = fs.readFileSync(DISPLAY_NAMES_FILE, "utf-8");
  const match = content.match(/export const BUILT_IN_PROVIDER_DISPLAY_NAMES\s*=\s*(\{[\s\S]*?\});/);
  if (!match) return {};
  return new Function("return " + match[1])();
}

const MODELS = loadModels();
const DISPLAY_NAMES = loadDisplayNames();
const command = process.argv[2] || "providers";

if (command === "providers") {
  // Output: [{id, name, authType, modelCount, imageModelCount}]
  const result = [];
  for (const [prov, models] of Object.entries(MODELS)) {
    const modelList = Object.values(models);
    const withImage = modelList.filter(
      (m) => m.input && m.input.includes("image")
    );
    result.push({
      id: prov,
      name: DISPLAY_NAMES[prov] || prov,
      modelCount: modelList.length,
      imageModelCount: withImage.length,
    });
  }
  console.log(JSON.stringify(result));
} else if (command === "models") {
  // Output for a specific provider: --provider <id>
  const providerId = process.argv[3];
  if (!providerId || !MODELS[providerId]) {
    console.log("[]");
    process.exit(0);
  }
  const result = Object.values(MODELS[providerId]).map((m) => ({
    id: m.id,
    name: m.name || m.id,
    reasoning: !!m.reasoning,
    input: m.input || ["text"],
  }));
  console.log(JSON.stringify(result));
} else if (command === "vision-models") {
  // Output all models that support image input (for vision model selector)
  const result = [];
  for (const [prov, models] of Object.entries(MODELS)) {
    for (const m of Object.values(models)) {
      if (m.input && m.input.includes("image")) {
        result.push({
          provider: prov,
          id: m.id,
          name: (m.name || m.id) + " (" + (DISPLAY_NAMES[prov] || prov) + ")",
          reasoning: !!m.reasoning,
        });
      }
    }
  }
  console.log(JSON.stringify(result));
}
