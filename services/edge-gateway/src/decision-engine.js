import { GatewayError, stableHash } from "./policy.js";

const MAX_BODY_BYTES = 60000;
const MAX_MESSAGES = 12;
const MAX_USER_CHARS = 1400;
const MAX_ASSISTANT_CHARS = 1000;
const IDEMPOTENCY_TTL_SECONDS = 60;

export const SOPHIA_DECISION_SYSTEM_INSTRUCTION = `
You are Sophia, the LifeOSAI Synthetic Artificial Intelligence decision-intelligence system.
You are not a generic chatbot. Your primary purpose is to help the user understand a decision and choose a sound next action.

LANGUAGE AND CONTEXT:
- Understand the complete conversation, not isolated words. Preserve names, numbers, dates, currency, units, negation, corrections, preferences, and unresolved questions.
- Answer in the latest user's language or natural language mixture unless another language is requested.
- Treat Igbo as a first-class language. When the user speaks or requests Igbo, reason directly in fluent contemporary Standard Igbo (Igbo Izugbe), not by translating an English answer word-for-word. Preserve confident diacritics and do not invent cultural meanings.
- Resolve ordinary transcription, spelling, grammar, and code-switching errors from context. If an ambiguity could materially change the decision, ask one precise clarification.

DECISION-INTELLIGENCE FRAMEWORK:
- Identify the actual decision, desired outcome, constraints, assumptions, and missing information.
- Examine likely short-term and long-term consequences for each meaningful option.
- Compare alternatives rather than merely validating the user's first choice.
- Identify the primary risk, secondary risks, hidden costs, opportunity cost, reversibility, dependencies, and possible downside.
- Identify a safer or more robust alternative where one exists.
- Separate verified facts from inference, estimates, assumptions, and uncertainty.
- Distinguish likely, possible, and unknown outcomes. Never guarantee a future result, profit, price, medical outcome, or legal outcome.
- When current or externally verifiable information materially affects the decision, use Google Search grounding when available. Never invent a source or claim a search occurred when it did not.
- Finish with one practical next action that is proportionate to the evidence.

AUDIT OUTPUT:
Produce a concise but substantive decision audit with exactly these sections:
Verdict:
Reality Check:
Main Risk:
Alternatives:
Future Outcome:
Better Move:
Next Action:
Final Truth:

For ordinary conversation that is not a decision, answer normally instead of forcing the audit structure.
Be direct, rigorous, practical, and complete. Do not claim consciousness, private-system access, or tools you do not possess. Protect privacy and never expose secrets.
`.trim();

const fetchImpl = env =>
  typeof env.__TEST_FETCH__ === "function" ? env.__TEST_FETCH__ : fetch;

function enabled(value, fallback = false) {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (!normalized) return fallback;
  return ["1", "true", "yes", "on"].includes(normalized);
}

function normalizeModel(value) {
  const model = String(value || "").trim().replace(/^models\//, "");
  return /^[A-Za-z0-9._-]{3,120}$/.test(model) ? model : "";
}

function configuredModels(env) {
  const configured = String(
    env.GEMINI_DECISION_MODELS ||
    env.GEMINI_GROUNDED_TEXT_MODELS ||
    env.GEMINI_TEXT_MODELS ||
    "gemini-2.5-flash,gemini-2.5-flash-lite",
  );
  return [...new Set(configured.split(",").map(normalizeModel).filter(Boolean))].slice(0, 3);
}

function generationConfig(model, maxOutputTokens = 1200) {
  const config = { maxOutputTokens };
  if (model.startsWith("gemini-2.5-")) {
    config.thinkingConfig = { thinkingBudget: 2048 };
  } else if (model.startsWith("gemini-3")) {
    config.thinkingConfig = { thinkingLevel: "medium" };
  }
  return config;
}

function compactMessages(payload) {
  if (!Array.isArray(payload?.messages)) {
    throw new GatewayError(400, "CHAT_MESSAGES_INVALID", "Messages must be supplied as a list.");
  }

  const selected = [];
  for (const item of payload.messages.slice(-MAX_MESSAGES)) {
    if (!item || typeof item !== "object") continue;
    const role = String(item.role || "").trim().toLowerCase();
    const content = String(item.content || "").trim();
    if (!["user", "assistant"].includes(role) || !content) continue;
    selected.push({
      role,
      content: content.slice(0, role === "user" ? MAX_USER_CHARS : MAX_ASSISTANT_CHARS),
    });
  }

  const firstUser = selected.findIndex(item => item.role === "user");
  if (firstUser < 0) {
    throw new GatewayError(400, "CHAT_USER_MESSAGE_REQUIRED", "A user message is required.");
  }

  const compacted = [];
  for (const message of selected.slice(firstUser)) {
    const previous = compacted[compacted.length - 1];
    if (previous?.role === message.role) {
      previous.content = `${previous.content}\n\n${message.content}`.slice(
        0,
        message.role === "user" ? MAX_USER_CHARS : MAX_ASSISTANT_CHARS,
      );
    } else {
      compacted.push({ ...message });
    }
  }
  return compacted;
}

function contentsFor(messages) {
  return messages.map(message => ({
    role: message.role === "assistant" ? "model" : "user",
    parts: [{ text: message.content }],
  }));
}

function extractText(payload) {
  return (payload?.candidates?.[0]?.content?.parts || [])
    .filter(part => part && part.thought !== true && typeof part.text === "string")
    .map(part => part.text.trim())
    .filter(Boolean)
    .join("\n")
    .trim();
}

function extractSources(payload) {
  const chunks = payload?.candidates?.[0]?.groundingMetadata?.groundingChunks || [];
  const sources = [];
  const seen = new Set();
  for (const chunk of chunks) {
    const web = chunk?.web;
    if (!web?.uri) continue;
    try {
      const parsed = new URL(String(web.uri));
      if (!["http:", "https:"].includes(parsed.protocol)) continue;
      parsed.hash = "";
      const url = parsed.toString();
      if (seen.has(url)) continue;
      seen.add(url);
      sources.push({ title: String(web.title || parsed.hostname).trim().slice(0, 180), url });
      if (sources.length >= 5) break;
    } catch {
      // Ignore malformed grounding metadata.
    }
  }
  return sources;
}

async function callGemini(env, contents, { search = true, maxOutputTokens = 1200 } = {}) {
  const apiKey = String(env.GEMINI_API_KEY || "").trim();
  if (!apiKey) {
    throw new GatewayError(503, "GEMINI_NOT_CONFIGURED", "The decision-intelligence service is not configured.");
  }

  const models = configuredModels(env);
  if (!models.length) {
    throw new GatewayError(503, "GEMINI_MODEL_MISSING", "No decision-intelligence model is configured.");
  }

  let lastFailure = "No configured Gemini model returned a response.";
  const searchModes = search && enabled(env.LIFEOS_CHAT_SEARCH_ENABLED, true) ? [true, false] : [false];

  for (const model of models) {
    for (const useSearch of searchModes) {
      try {
        const body = {
          systemInstruction: { parts: [{ text: SOPHIA_DECISION_SYSTEM_INSTRUCTION }] },
          contents,
          ...(useSearch ? { tools: [{ google_search: {} }] } : {}),
          generationConfig: generationConfig(model, maxOutputTokens),
        };

        const response = await fetchImpl(env)(
          `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json", "x-goog-api-key": apiKey },
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(20000),
          },
        );
        const payload = await response.json().catch(() => ({}));
        const text = response.ok ? extractText(payload) : "";
        if (response.ok && text) {
          const sources = extractSources(payload);
          return { text, sources, model, grounded: sources.length > 0 };
        }
        lastFailure = `${model} returned HTTP ${response.status}`;
        if (useSearch && [400, 403, 429].includes(response.status)) continue;
        break;
      } catch (error) {
        lastFailure = `${model} failed with ${error?.name || "Error"}`;
        break;
      }
    }
  }

  console.error("LOSAI_DECISION_ENGINE_FAILED", { reason: lastFailure });
  throw new GatewayError(503, "DECISION_ENGINE_UNAVAILABLE", "The LifeOSAI decision-intelligence engine is temporarily unavailable.");
}

function decisionPrompt(messages) {
  return [
    ...contentsFor(messages),
    {
      role: "user",
      parts: [{ text: "Perform the specialised LifeOSAI decision audit now. Do not merely continue generic conversation. Explicitly evaluate the decision, alternatives, risks, opportunity cost, and likely/possible/unknown future outcomes. End with a concrete next action." }],
    },
  ];
}

export async function issueDecisionIntelligence(request, env, session, idempotencyKey) {
  const userId = String(session?.user?.id || "").trim();
  if (!userId) throw new GatewayError(401, "AUTH_REQUIRED", "Sign-in is required.");
  if (!idempotencyKey) throw new GatewayError(400, "IDEMPOTENCY_KEY_REQUIRED", "A valid Idempotency-Key is required.");

  const idempotencyMaterial = `${userId}:${idempotencyKey}`;
  const cacheKey = `decision-idempotency:${await stableHash(idempotencyMaterial)}`;
  const cached = await env.ORIGIN_STATE?.get(cacheKey, { type: "json" });
  if (cached?.ok && cached?.reply) return { ...cached, idempotent_replay: true };

  const contentLength = Number.parseInt(request.headers.get("Content-Length") || "0", 10);
  if (Number.isFinite(contentLength) && (contentLength < 0 || contentLength > MAX_BODY_BYTES)) {
    throw new GatewayError(413, "CHAT_REQUEST_TOO_LARGE", "The decision request body is too large.");
  }

  const raw = await request.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_BODY_BYTES || !raw.trim()) {
    throw new GatewayError(400, "CHAT_REQUEST_INVALID", "The decision request body is invalid.");
  }

  let payload;
  try { payload = JSON.parse(raw); } catch {
    throw new GatewayError(400, "CHAT_REQUEST_INVALID", "The decision request body is invalid.");
  }

  const messages = compactMessages(payload);
  const generated = await callGemini(env, decisionPrompt(messages), { search: true, maxOutputTokens: 1200 });

  const result = {
    ok: true,
    reply: generated.text,
    audit: generated.text,
    sources: generated.sources,
    grounded: generated.grounded,
    model: generated.model,
    audio_url: null,
    tts_error: null,
    decision_engine: "sophia-specialised-v1",
    fallback_origin: "cloudflare-worker",
    idempotent_replay: false,
  };

  if (env.ORIGIN_STATE?.put) {
    await env.ORIGIN_STATE.put(cacheKey, JSON.stringify(result), { expirationTtl: IDEMPOTENCY_TTL_SECONDS });
  }
  return result;
}
