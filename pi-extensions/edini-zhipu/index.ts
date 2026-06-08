/**
 * edini-zhipu — Register 智谱AI (Zhipu AI / BigModel.cn) as a Pi provider.
 *
 * Supports:
 * - General endpoint: https://open.bigmodel.cn/api/paas/v4
 * - Coding Plan endpoint: https://open.bigmodel.cn/api/coding/paas/v4
 * - Vision model: GLM-4.6V
 *
 * Environment variables:
 *   ZHIPU_API_KEY       — Your 智谱 API key (required)
 *   ZHIPU_USE_CODING    — Set to "1" to use the Coding Plan endpoint
 *   ZHIPU_CODING_API_KEY — Separate API key for Coding Plan (optional, falls back to ZHIPU_API_KEY)
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  const apiKey = process.env["ZHIPU_API_KEY"] || process.env["ZHIPUAI_API_KEY"] || "";
  const useCoding = process.env["ZHIPU_USE_CODING"] === "1";
  const codingApiKey = process.env["ZHIPU_CODING_API_KEY"] || apiKey;

  // Determine base URL
  const baseUrl = useCoding
    ? "https://open.bigmodel.cn/api/coding/paas/v4"
    : "https://open.bigmodel.cn/api/paas/v4";

  const keyToUse = useCoding ? codingApiKey : apiKey;

  pi.registerProvider("zhipu", {
    name: "智谱AI" + (useCoding ? " (Coding Plan)" : ""),
    baseUrl,
    apiKey: keyToUse || "$ZHIPU_API_KEY",
    api: "openai-completions",
    authHeader: true,
    models: [
      {
        id: "glm-5.1",
        name: "GLM-5.1 (最新旗舰)",
        reasoning: false,
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 131072,
        maxTokens: 8192,
      },
      {
        id: "glm-5",
        name: "GLM-5 (高智能)",
        reasoning: false,
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 131072,
        maxTokens: 8192,
      },
      {
        id: "glm-4.7",
        name: "GLM-4.7 (推理/Agent)",
        reasoning: true,
        thinkingLevelMap: {
          off: null,
          minimal: null,
          low: null,
          medium: "default",
          high: "default",
          xhigh: "max",
        },
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 131072,
        maxTokens: 8192,
        compat: {
          thinkingFormat: "zai",
          supportsReasoningEffort: true,
          maxTokensField: "max_tokens",
        },
      },
      {
        id: "glm-4.6v",
        name: "GLM-4.6V (视觉)",
        reasoning: false,
        input: ["text", "image"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 131072,
        maxTokens: 4096,
      },
      {
        id: "glm-4.5",
        name: "GLM-4.5 (轻量)",
        reasoning: false,
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 131072,
        maxTokens: 4096,
      },
    ],
  });
}
