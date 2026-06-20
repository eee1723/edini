// Spawn picli in RPC mode and send a prompt command, capture events.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

// Prefer the vendored Pi; fall back to the global npm install.
function findPiCli() {
  const vendored = path.join(
    ROOT, "vendor/node_modules/@earendil-works/pi-coding-agent/dist/cli.js");
  if (existsSync(vendored)) return vendored;
  const globalNm = path.join(
    process.env.APPDATA || "",
    "npm/node_modules/@earendil-works/pi-coding-agent/dist/cli.js");
  return globalNm;
}

const child = spawn("node", [
  findPiCli(),
  "--mode", "rpc",
  "--model", "zai-coding-cn/glm-5.2",
  "--thinking", "high",
], { stdio: ["pipe", "pipe", "inherit"] });

let buf = "";
let gotError = false;
child.stdout.on("data", (chunk) => {
  buf += chunk.toString();
  let idx;
  while ((idx = buf.indexOf("\n")) >= 0) {
    const line = buf.slice(0, idx).trim();
    buf = buf.slice(idx + 1);
    if (!line) continue;
    let obj;
    try { obj = JSON.parse(line); } catch { continue; }
    // Look for assistant message final events
    if (obj.type === "message" && obj.message?.role === "assistant") {
      console.log("ASSISTANT stopReason:", obj.message.stopReason, "| error:", obj.message.errorMessage || "(none)");
      if (obj.message.stopReason === "error") gotError = true;
    }
    if (obj.type === "response" && obj.command === "prompt") {
      console.log("PROMPT RESPONSE success:", obj.success, obj.error || "");
    }
  }
});

// Wait for ready, then send a prompt
setTimeout(() => {
  const cmd = JSON.stringify({ id: "1", type: "prompt", message: "hi" }) + "\n";
  child.stdin.write(cmd);
}, 3000);

// Exit after 20s
setTimeout(() => {
  console.log("=== DONE (gotError=" + gotError + ") ===");
  child.kill();
  process.exit(gotError ? 1 : 0);
}, 20000);
