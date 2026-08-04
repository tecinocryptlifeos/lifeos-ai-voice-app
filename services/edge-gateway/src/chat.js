// LOSAI_WORKER_CHAT_FALLBACK_V2
import { GatewayError, stableHash } from "./policy.js";

export const CHAT_IDEMPOTENCY_TTL_SECONDS = 60;

const MAX_CHAT_BODY_BYTES = 60000;
const MAX_CHAT_MESSAGES = 8;
const MAX_USER_MESSAGE_CHARACTERS = 900;
const MAX_ASSISTANT_MESSAGE_CHARACTERS = 700;

const DEFAULT_CHAT_MODELS = Object.freeze([
  "gemini-2.5-flash",
  "gemini-2.5-flash-lite",
]);

const SYSTEM_INSTRUCTION = `
You are Sophia, the LifeOS AI decision-intelligence assistant.

Answer the user's exact current request in the user's current language.
Use relevant conversation context without inventing facts.

Distinguish verified facts, reasonable inference, and uncertainty.
For decisions, identify likely short-term and long-term consequences,
the principal risk, the main opportunity cost, a safer alternative,
and one practical next action.

Never guarantee future profit, prices, legal outcomes, medical outcomes,
or other uncertain results. Protect personal information.

Return a direct, complete, readable answer.
`.trim();

function fetchImpl(env) {
  return typeof env.__TEST_FETCH__ === "function"
    ? env.__TEST_FETCH__
    : fetch;
}

function enabled(value, fallback = false) {
  const normalized = String(value ?? "").trim().toLowerCase();

  if (!normalized) return fallback;

  return ["1", "true", "yes", "on"].includes(normalized);
}

function normalizeModel(value) {
  const model = String(value || "")
    .trim()
    .replace(/^models\//, "");

  return /^[A-Za-z0-9._-]{3,120}$/.test(model) ? model : "";
}

function configuredModels(env) {
  const configured = String(
    env.GEMINI_GROUNDED_TEXT_MODELS ||
    env.GEMINI_TEXT_MODELS ||
    DEFAULT_CHAT_MODELS.join(","),
  );

  const models = configured
    .split(",")
    .map(normalizeModel)
    .filter(Boolean);

  return [...new Set(models)].slice(0, 3);
}

async function requestPayload(request) {
  const contentLength = request.headers.get("Content-Length");
  const declaredLength = contentLength
    ? Number.parseInt(contentLength, 10)
    : 0;

  if (
    Number.isFinite(declaredLength) &&
    (declaredLength < 0 || declaredLength > MAX_CHAT_BODY_BYTES)
  ) {
    throw new GatewayError(
      413,
      "CHAT_REQUEST_TOO_LARGE",
      "The chat request body is too large.",
    );
  }

  const raw = await request.text();

  if (new TextEncoder().encode(raw).byteLength > MAX_CHAT_BODY_BYTES) {
    throw new GatewayError(
      413,
      "CHAT_REQUEST_TOO_LARGE",
      "The chat request body is too large.",
    );
  }

  if (!raw.trim()) {
    throw new GatewayError(
      400,
      "CHAT_REQUEST_INVALID",
      "The chat request body is required.",
    );
  }

  let payload;

  try {
    payload = JSON.parse(raw);
  } catch {
    throw new GatewayError(
      400,
      "CHAT_REQUEST_INVALID",
      "The chat request body is invalid.",
    );
  }

  if (
    !payload ||
    typeof payload !== "object" ||
    Array.isArray(payload)
  ) {
    throw new GatewayError(
      400,
      "CHAT_REQUEST_INVALID",
      "The chat request body must be an object.",
    );
  }

  return payload;
}

function cleanMessages(payload) {
  if (!Array.isArray(payload.messages)) {
    throw new GatewayError(
      400,
      "CHAT_MESSAGES_INVALID",
      "Messages must be supplied as a list.",
    );
  }

  const excludedFragments = [
    "could not complete the continuation",
    "under high demand",
    "reviewing the decision thread",
  ];

  const selected = [];

  for (const item of payload.messages.slice(-MAX_CHAT_MESSAGES)) {
    if (!item || typeof item !== "object") continue;

    const role = String(item.role || "").trim().toLowerCase();
    const content = String(item.content || "").trim();

    if (!["user", "assistant"].includes(role) || !content) continue;

    if (
      excludedFragments.some(fragment =>
        content.toLowerCase().includes(fragment))
    ) {
      continue;
    }

    selected.push({
      role,
      content: content.slice(
        0,
        role === "user"
          ? MAX_USER_MESSAGE_CHARACTERS
          : MAX_ASSISTANT_MESSAGE_CHARACTERS,
      ),
    });
  }

  const firstUserIndex = selected.findIndex(
    item => item.role === "user",
  );

  if (firstUserIndex < 0) {
    throw new GatewayError(
      400,
      "CHAT_USER_MESSAGE_REQUIRED",
      "A user message is required.",
    );
  }

  const compacted = [];

  for (const message of selected.slice(firstUserIndex)) {
    const previous = compacted[compacted.length - 1];

    if (previous?.role === message.role) {
      previous.content = `${previous.content}\n\n${message.content}`.slice(
        0,
        message.role === "user"
          ? MAX_USER_MESSAGE_CHARACTERS
          : MAX_ASSISTANT_MESSAGE_CHARACTERS,
      );
      continue;
    }

    compacted.push({ ...message });
  }

  return compacted;
}

function generationConfig(model) {
  const config = {
    maxOutputTokens: 900,
  };

  if (model.startsWith("gemini-2.5-")) {
    config.thinkingConfig = {
      thinkingBudget: 1024,
    };
  } else if (model.startsWith("gemini-3")) {
    config.thinkingConfig = {
      thinkingLevel: "low",
    };
  }

  return config;
}

function modelRequest(messages, model, useSearch) {
  return {
    systemInstruction: {
      parts: [{ text: SYSTEM_INSTRUCTION }],
    },
    contents: messages.map(message => ({
      role: message.role === "assistant" ? "model" : "user",
      parts: [{ text: message.content }],
    })),
    ...(useSearch
      ? {
          tools: [{ google_search: {} }],
        }
      : {}),
    generationConfig: generationConfig(model),
  };
}

function extractText(payload) {
  const parts = payload?.candidates?.[0]?.content?.parts || [];

  return parts
    .filter(
      part =>
        part &&
        part.thought !== true &&
        typeof part.text === "string",
    )
    .map(part => part.text.trim())
    .filter(Boolean)
    .join("\n")
    .trim();
}

function extractSources(payload) {
  const chunks =
    payload?.candidates?.[0]?.groundingMetadata?.groundingChunks || [];

  const sources = [];
  const seen = new Set();

  for (const chunk of chunks) {
    const web = chunk?.web;

    if (!web?.uri) continue;

    try {
      const parsed = new URL(String(web.uri));

      if (!["http:", "https:"].includes(parsed.protocol)) continue;

      parsed.hash = "";

      const normalized = parsed.toString();

      if (seen.has(normalized)) continue;

      seen.add(normalized);

      sources.push({
        title: String(web.title || parsed.hostname)
          .trim()
          .slice(0, 180),
        url: normalized,
      });

      if (sources.length >= 5) break;
    } catch {
      // Malformed grounding links are ignored.
    }
  }

  return sources;
}

async function generateFallbackReply(env, messages) {
  const apiKey = String(env.GEMINI_API_KEY || "").trim();

  if (!apiKey) {
    throw new GatewayError(
      503,
      "GEMINI_NOT_CONFIGURED",
      "The Worker chat fallback is not configured.",
    );
  }

  const models = configuredModels(env);

  if (!models.length) {
    throw new GatewayError(
      503,
      "GEMINI_MODEL_MISSING",
      "No Worker chat fallback model is configured.",
    );
  }

  const searchEnabled = enabled(
    env.LIFEOS_CHAT_SEARCH_ENABLED,
    true,
  );

  let lastFailure =
    "No configured Gemini model returned a usable response.";

  for (const model of models) {
    const searchModes = searchEnabled
      ? [true, false]
      : [false];

    for (const useSearch of searchModes) {
      try {
        const response = await fetchImpl(env)(
          `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "x-goog-api-key": apiKey,
            },
            body: JSON.stringify(
              modelRequest(messages, model, useSearch),
            ),
            signal: AbortSignal.timeout(20000),
          },
        );

        const payload = await response
          .json()
          .catch(() => ({}));

        const text = response.ok
          ? extractText(payload)
          : "";

        if (response.ok && text) {
          const sources = extractSources(payload);

          return {
            text,
            sources,
            grounded: sources.length > 0,
            model,
          };
        }

        lastFailure =
          `${model} returned HTTP ${response.status}` +
          (useSearch ? " with Search grounding" : "");

        if (
          useSearch &&
          [400, 403, 429].includes(response.status)
        ) {
          continue;
        }

        break;
      } catch (error) {
        lastFailure =
          `${model} failed with ${error?.name || "Error"}`;

        break;
      }
    }
  }

  console.error("LOSAI_WORKER_CHAT_FALLBACK_FAILED", {
    reason: lastFailure,
  });

  throw new GatewayError(
    503,
    "WORKER_CHAT_FALLBACK_FAILED",
    "The emergency chat service is temporarily unavailable.",
  );
}

export async function issueChatDecision(
  request,
  env,
  session,
  idempotencyKey,
) {
  const userId = String(session?.user?.id || "").trim();

  if (!userId) {
    throw new GatewayError(
      401,
      "AUTH_REQUIRED",
      "Sign-in is required.",
    );
  }

  const idempotencyMaterial =
    `${userId}:${idempotencyKey}`;

  const cacheKey =
    `chat-idempotency:${await stableHash(idempotencyMaterial)}`;

  const cached = await env.ORIGIN_STATE?.get(
    cacheKey,
    { type: "json" },
  );

  if (cached?.ok && cached?.reply) {
    return {
      ...cached,
      idempotent_replay: true,
    };
  }

  if (!env.API_RATE_LIMITER?.limit) {
    throw new GatewayError(
      503,
      "RATE_LIMITER_MISSING",
      "The LifeOS API rate limiter is not configured.",
    );
  }

  const limited = await env.API_RATE_LIMITER.limit({
    key: `${userId}:worker-chat-fallback`,
  });

  if (!limited?.success) {
    throw new GatewayError(
      429,
      "RATE_LIMITED",
      "Please wait before sending another chat request.",
      {
        retry_after: 60,
      },
    );
  }

  const payload = await requestPayload(request);
  const messages = cleanMessages(payload);
  const generated = await generateFallbackReply(env, messages);

  const result = {
    ok: true,
    reply: generated.text,
    sources: generated.sources,
    grounded: generated.grounded,
    model: generated.model,
    audio_url: null,
    tts_error: null,
    fallback_origin: "cloudflare-worker",
    idempotent_replay: false,
  };

  if (env.ORIGIN_STATE?.put) {
    await env.ORIGIN_STATE.put(
      cacheKey,
      JSON.stringify(result),
      {
        expirationTtl: CHAT_IDEMPOTENCY_TTL_SECONDS,
      },
    );
  }

  return result;
}
