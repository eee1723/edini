/**
 * Vision model client — calls OpenAI / Anthropic / Google APIs to describe images.
 *
 * Uses model info and API key from pi's ModelRegistry so users don't need
 * separate API keys. Supports all three API formats pi works with.
 */

// ---- Public API ----

/** Minimum model info needed from ctx.modelRegistry.find(). */
export interface VisionModelInfo {
  id: string;
  api: string;
  baseUrl: string;
  name?: string;
  provider: string;
}

export interface VisionCallParams {
  /** Image data as base64-encoded string (without data: prefix). */
  imageBase64: string;
  /** Image MIME type (e.g. "image/png", "image/jpeg"). */
  mediaType: string;
  /** Model info from ctx.modelRegistry.find(). */
  model: VisionModelInfo;
  /** Resolved API key. */
  apiKey: string;
  /** Prompt for the vision model. */
  prompt: string;
  /** Require HTTPS endpoint. Default true. Set false for local models (Ollama, etc.). */
  requireHttps?: boolean;
}

export interface VisionCallResult {
  description: string;
  error?: string;
}

/**
 * Describe an image using the configured vision model.
 * Dispatches to the correct API format based on model.api.
 */
export async function describeImage(params: VisionCallParams): Promise<VisionCallResult> {
  const api = params.model.api;
  if (api === "openai-completions" || api === "openai-responses") {
    return callOpenAIVision(params);
  }
  if (api === "anthropic-messages") {
    return callAnthropicVision(params);
  }
  if (api === "google-generative-ai") {
    return callGoogleVision(params);
  }
  return {
    description: "",
    error: `Unsupported API type: ${api}. Supported: openai-completions, anthropic-messages, google-generative-ai`,
  };
}

// ---- Cache ----

const imageCache = new Map<string, string>();

export function getCached(key: string): string | undefined {
  const value = imageCache.get(key);
  if (value !== undefined) {
    // True LRU: refresh position by re-inserting at the end
    imageCache.delete(key);
    imageCache.set(key, value);
  }
  return value;
}

export function setCache(key: string, description: string): void {
  // LRU eviction: delete least-recently-used (first in insertion order)
  if (imageCache.size >= 100) {
    const first = imageCache.keys().next().value;
    if (first) imageCache.delete(first);
  }
  imageCache.set(key, description);
}

export function clearCache(): void {
  imageCache.clear();
}

export function getCacheSize(): number {
  return imageCache.size;
}

// ---- HTTP helper (uses Node https directly, bypasses Pi's undici global dispatcher) ----

const VISION_API_TIMEOUT_MS = 30_000;

async function httpsRequest(
  url: string,
  options: {
    method?: string;
    headers?: Record<string, string>;
    body?: string;
    timeoutMs?: number;
  },
): Promise<{ status: number; text: string }> {
  const https = await import("node:https");
  const http = await import("node:http");
  const { URL } = await import("node:url");

  const parsed = new URL(url);
  const isHttps = parsed.protocol === "https:";
  const mod = isHttps ? https : http;
  const timeoutMs = options.timeoutMs ?? VISION_API_TIMEOUT_MS;

  return new Promise((resolve, reject) => {
    const req = mod.request(
      {
        hostname: parsed.hostname,
        port: parsed.port || (isHttps ? 443 : 80),
        path: parsed.pathname + parsed.search,
        method: options.method ?? "POST",
        headers: {
          "Content-Type": "application/json",
          ...options.headers,
          "Content-Length": String(Buffer.byteLength(options.body ?? "")),
        },
        timeout: timeoutMs,
      },
      (res) => {
        let data = "";
        res.setEncoding("utf8");
        res.on("data", (chunk: string) => (data += chunk));
        res.on("end", () => resolve({ status: res.statusCode ?? 0, text: data }));
      },
    );

    req.on("timeout", () => {
      req.destroy();
      reject(new Error(`HTTPS request timed out after ${timeoutMs / 1000}s`));
    });
    req.on("error", reject);

    if (options.body) req.write(options.body);
    req.end();
  });
}

// ---- OpenAI Chat Completions ----

async function callOpenAIVision(params: VisionCallParams): Promise<VisionCallResult> {
  const { imageBase64, mediaType, model, apiKey, prompt } = params;
  const baseUrl = model.baseUrl.replace(/\/+$/, "");

  // Basic validation
  if (!imageBase64 || imageBase64.trim().length === 0) {
    return { description: "", error: "Empty image data" };
  }
  if (params.requireHttps !== false && !baseUrl.startsWith("https://")) {
    return { description: "", error: "Vision model must use HTTPS. Set requireHttps=false for local models." };
  }

  try {
    const body = JSON.stringify({
      model: model.id,
      messages: [
        {
          role: "user",
          content: [
            { type: "text", text: prompt },
            { type: "image_url", image_url: { url: `data:${mediaType};base64,${imageBase64}` } },
          ],
        },
      ],
      max_tokens: 1024,
      temperature: 0,
    });

    const result = await httpsRequest(`${baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body,
    });

    if (result.status < 200 || result.status >= 300) {
      return { description: "", error: `OpenAI API error (${result.status}): ${result.text.slice(0, 200)}` };
    }

    const data = JSON.parse(result.text) as {
      choices?: Array<{ message?: { content?: string } }>;
    };

    const description = data.choices?.[0]?.message?.content?.trim() ?? "";
    return { description };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { description: "", error: `OpenAI request failed: ${message}` };
  }
}

// ---- Anthropic Messages ----

async function callAnthropicVision(params: VisionCallParams): Promise<VisionCallResult> {
  const { imageBase64, mediaType, model, apiKey, prompt } = params;
  const baseUrl = model.baseUrl.replace(/\/+$/, "");

  if (!imageBase64 || imageBase64.trim().length === 0) {
    return { description: "", error: "Empty image data" };
  }
  if (params.requireHttps !== false && !baseUrl.startsWith("https://")) {
    return { description: "", error: "Vision model must use HTTPS. Set requireHttps=false for local models." };
  }

  try {
    const body = JSON.stringify({
      model: model.id,
      max_tokens: 1024,
      messages: [
        {
          role: "user",
          content: [
            { type: "image", source: { type: "base64", media_type: mediaType, data: imageBase64 } },
            { type: "text", text: prompt },
          ],
        },
      ],
    });

    const result = await httpsRequest(`${baseUrl}/messages`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
      },
      body,
    });

    if (result.status < 200 || result.status >= 300) {
      return { description: "", error: `Anthropic API error (${result.status}): ${result.text.slice(0, 200)}` };
    }

    const data = JSON.parse(result.text) as {
      content?: Array<{ type: string; text?: string }>;
    };

    const textParts = data.content?.filter((c) => c.type === "text").map((c) => c.text ?? "") ?? [];
    const description = textParts.join("").trim();
    return { description };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { description: "", error: `Anthropic request failed: ${message}` };
  }
}

// ---- Google Generative AI ----

async function callGoogleVision(params: VisionCallParams): Promise<VisionCallResult> {
  const { imageBase64, mediaType, model, apiKey, prompt } = params;
  const baseUrl = model.baseUrl.replace(/\/+$/, "");

  if (!imageBase64 || imageBase64.trim().length === 0) {
    return { description: "", error: "Empty image data" };
  }
  if (params.requireHttps !== false && !baseUrl.startsWith("https://")) {
    return { description: "", error: "Vision model must use HTTPS. Set requireHttps=false for local models." };
  }

  try {
    const body = JSON.stringify({
      contents: [
        {
          parts: [
            { text: prompt },
            { inlineData: { mimeType: mediaType, data: imageBase64 } },
          ],
        },
      ],
      generationConfig: { maxOutputTokens: 1024, temperature: 0 },
    });

    const result = await httpsRequest(`${baseUrl}/models/${model.id}:generateContent`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-goog-api-key": apiKey,
      },
      body,
    });

    if (result.status < 200 || result.status >= 300) {
      return { description: "", error: `Google API error (${result.status}): ${result.text.slice(0, 200)}` };
    }

    const data = JSON.parse(result.text) as {
      candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>;
    };

    const parts = data.candidates?.[0]?.content?.parts ?? [];
    const description = parts.map((p) => p.text ?? "").join("").trim();
    return { description };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { description: "", error: `Google request failed: ${message}` };
  }
}
