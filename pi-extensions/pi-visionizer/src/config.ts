/**
 * Configuration management for pi-visionizer.
 *
 * Persists vision model selection to session custom entries so it survives restarts.
 */

import type { ExtensionContext } from "@mariozechner/pi-coding-agent";

export const CUSTOM_TYPE = "visionizer-config";

export interface VisionizerConfig {
  /** Provider name of the vision model (e.g. "openai", "anthropic"). */
  provider: string;
  /** Model ID of the vision model (e.g. "gpt-4.1-mini", "claude-sonnet-4-20250514"). */
  modelId: string;
  /** Custom prompt sent to the vision model for describing images. */
  prompt?: string;
  /** Require HTTPS for the vision model endpoint. Default true. Set to false for local models. */
  requireHttps?: boolean;
}

/**
 * Read vision config from environment variables (set by Edini settings).
 * These take lowest priority — session config wins over env vars.
 */
export function getEnvConfig(): VisionizerConfig | undefined {
  const provider = process.env["VISIONIZER_PROVIDER"];
  const modelId = process.env["VISIONIZER_MODEL_ID"];
  const apiKey = process.env["VISIONIZER_API_KEY"];
  if (provider && modelId) {
    const cfg: VisionizerConfig = { provider, modelId };
    if (apiKey) {
      (cfg as any).apiKey = apiKey;
    }
    return cfg;
  }
  return undefined;
}

/** Hardcoded default vision model — lowest priority fallback.
 * Must match the provider name registered in ~/.pi/agent/models.json */
export const DEFAULT_VISION_MODEL: VisionizerConfig = {
  provider: "aliyun",
  modelId: "qwen-vl-max",
};

export const DEFAULT_PROMPT = [
  "Describe this image in detail and factually. Your description will be read by a coding agent that cannot see the image.",
  "",
  "If this is a screenshot of a UI, webpage, code editor, or terminal:",
  "- Transcribe all visible text, code, error messages, logs, and UI labels verbatim",
  "- Describe the layout, colors, and any visual issues (misalignment, broken elements, error states, unexpected behavior)",
  "- Note the apparent tool, framework, or context (e.g. React app, Chrome DevTools, VS Code)",
  "",
  "If this is a photo, artwork, or image of a person/character:",
  "- Describe appearance, clothing, expression, pose, and setting",
  "- If the subject appears to be a known character, public figure, or recognizable entity, identify them",
  "",
  "If this is a diagram, chart, architecture drawing, or table:",
  "- Describe the structure, labels, relationships, and key data points",
  "",
  "For any other image type, describe all visible elements, text, and context factually.",
].join("\n");

export const PROCEDURAL_VERIFY_PROMPT = [
  "You are verifying a procedural 3D asset captured from Houdini viewport (multi-view contact sheet).",
  "NOTE: Viewport wireframe/shaded captures may not show subtle surface smoothing (bevels < 0.02 units, subdivision creases). Judge STRUCTURAL complexity, not surface smoothness.",
  "NOTE: Small/thin components (chains, spokes, bolts, pedals, cables) are often present but below viewport pixel resolution. If GEOMETRY_INVENTORY lists them with prim_count > 0, treat them as PRESENT and request a closer capture rather than reporting them missing.",
  "",
  "A GEOMETRY_INVENTORY text block may be provided alongside the image. It lists, per component:",
  "  component_id -> prim_count + bounding box size (x,y,z)",
  "Use it to cross-reference what SHOULD be in the geometry before reporting anything as missing.",
  "",
  "CHECK EACH VIEW FOR THESE DEFECTS:",
  "",
  "1. ORIENTATION: Are all components oriented correctly?",
  "   - Wheels/discs should be VERTICAL (upright), not lying flat",
  "   - Roofs/tops should be on TOP, not on the side",
  "   - Handles/bars should be HORIZONTAL",
  "   - Flag any component that appears rotated 90 degrees from expected",
  "",
  "2. PROPORTIONS: Do parts have reasonable proportions?",
  "   - Compare sub-component sizes to the whole",
  "   - Flag any part that is drastically too large or too small",
  "",
  "3. SYMMETRY: If the object should be symmetric, is it?",
  "   - Check left/right and front/back symmetry where expected",
  "   - Flag missing or extra parts on one side",
  "",
  "4. COMPLETENESS: Are all expected sub-components visible?",
  "   - If something is described as having N parts, can you count N?",
  "   - A component counts as MISSING only if it is ABSENT from GEOMETRY_INVENTORY",
  "   - If a component is IN the inventory (prim_count > 0) but you cannot see it, do NOT report it missing — report closer_capture:<component> instead",
  "",
  "5. INTERSECTION: Are parts overlapping when they should not?",
  "   - Bodies passing through other bodies",
  "   - Components embedded inside others",
  "",
  "6. SCALE: Are sub-parts at correct scale relative to the whole?",
  "",
  "7. STRUCTURAL DETAIL: Rate based on geometric STRUCTURE, not surface smoothness:",
  "   - 1 = Raw boxes/cylinders with no shaping (unacceptable)",
  "   - 2 = Correct silhouette but flat/featureless surfaces, no sub-parts",
  "   - 3 = Distinct sub-components visible, shaped profiles (curves/bevels on silhouette), panel lines or seams as geometry (minimum acceptable)",
  "   - 4 = Rich structure: secondary components (bolts, vents, handles), varied cross-sections, visible construction logic",
  "   - UNCERTAIN = Cannot judge detail at this viewport resolution (do NOT report as level 1 or 2 when uncertain)",
  "",
  "RESOLUTION RULE (very important):",
  "- NEVER report a component as \"missing\" merely because it is hard to see at default viewport resolution.",
  "- If you cannot CONFIRM presence or absence of a component, output closer_capture:<component> for it, NOT missing:<component>.",
  "- When GEOMETRY_INVENTORY lists a component with prim_count > 0 but it is not visible, the verdict for that component MUST be closer_capture:<id>, NOT missing:<id>.",
  "",
  "OUTPUT FORMAT (use exactly this structure):",
  "DEFECTS:",
  "- [critical/major/minor] description of defect",
  "STRUCTURAL_DETAIL: N or UNCERTAIN",
  "ORIENTATION_OK: yes/no (if no, describe what is wrong)",
  "MISSING_COMPONENTS: list or none   (ONLY for components ABSENT from GEOMETRY_INVENTORY)",
  "VERDICT: accept | fix:<list> | closer_capture:<list> | uncertain",
].join("\n");

/**
 * Read the persisted visionizer config from session custom entries.
 * Returns undefined if not configured (no session entry found and no clear marker).
 */
export function getConfig(ctx: ExtensionContext): VisionizerConfig | undefined {
  const entries = ctx.sessionManager.getEntries();
  // Iterate in reverse — newest config entry wins. appendEntry() adds
  // entries to the end, so the last matching entry is the current config.
  //
  // Cap the search to the last 20 entries to avoid performance degradation
  // in long sessions where config may have been toggled many times.
  const startIdx = Math.max(0, entries.length - 20);
  for (let i = entries.length - 1; i >= startIdx; i--) {
    const entry = entries[i];
    if (entry.type === "custom" && entry.customType === CUSTOM_TYPE) {
      const data = entry.data as VisionizerConfig | undefined;
      if (data?.provider && data?.modelId) {
        return data;
      }
      // A null/empty entry from /visionizer-clear → stop searching;
      // anything before it is stale.
      if (data === null || data === undefined) {
        return undefined;
      }
    }
  }
  return undefined;
}

/**
 * Resolve visionizer config (priority: session > env var > hardcoded default).
 *
 * Session config: set via /visionizer-model command (persists in session entries)
 * Env var config: set by Edini UI via VISIONIZER_PROVIDER / VISIONIZER_MODEL_ID
 * Hardcoded default: last resort (aliyun/qwen-vl-max)
 */
export function resolveConfig(ctx: ExtensionContext): VisionizerConfig | undefined {
  return getConfig(ctx) ?? getEnvConfig() ?? DEFAULT_VISION_MODEL;
}
