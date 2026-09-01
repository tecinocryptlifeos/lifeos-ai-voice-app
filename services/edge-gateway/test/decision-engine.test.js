import test from "node:test";
import assert from "node:assert/strict";

import {
  SOPHIA_DECISION_SYSTEM_INSTRUCTION,
  issueDecisionIntelligence,
} from "../src/decision-engine.js";

test("Sophia decision policy contains the specialised intelligence contract", () => {
  for (const phrase of [
    "decision-intelligence system",
    "short-term and long-term consequences",
    "alternatives",
    "opportunity cost",
    "Future Outcome",
    "likely, possible, and unknown",
    "Standard Igbo",
    "Google Search",
  ]) {
    assert.match(SOPHIA_DECISION_SYSTEM_INSTRUCTION, new RegExp(phrase.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&"), "i"));
  }
  assert.doesNotMatch(SOPHIA_DECISION_SYSTEM_INSTRUCTION, /onrender\.com|render\.com/i);
});

test("specialised decision endpoint sends native Gemini multi-turn contents with search grounding", async () => {
  let captured;
  const env = {
    GEMINI_API_KEY: "test-key",
    GEMINI_DECISION_MODELS: "gemini-2.5-flash",
    LIFEOS_CHAT_SEARCH_ENABLED: "true",
    __TEST_FETCH__: async (_url, options) => {
      captured = JSON.parse(options.body);
      return new Response(JSON.stringify({
        candidates: [{
          content: { parts: [{ text: "Verdict: Test decision audit.\nReality Check: Facts separated from assumptions.\nMain Risk: Test risk.\nAlternatives: Test alternative.\nFuture Outcome: Likely outcome identified.\nBetter Move: Test safer move.\nNext Action: Take the smallest reversible step.\nFinal Truth: Evidence should drive the decision." }] },
          groundingMetadata: { groundingChunks: [{ web: { title: "Example", uri: "https://example.com/source" } }] },
        }],
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    },
  };

  const request = new Request("https://lifeosai.pages.dev/api/chat-decision", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Content-Length": "78" },
    body: JSON.stringify({ messages: [
      { role: "user", content: "I have two options. Help me decide which is safer." },
    ] }),
  });

  const result = await issueDecisionIntelligence(
    request,
    env,
    { user: { id: "user-1" } },
    "idem-key-1234567890",
  );

  assert.equal(result.ok, true);
  assert.equal(result.decision_engine, "sophia-specialised-v1");
  assert.equal(result.grounded, true);
  assert.equal(result.sources.length, 1);
  assert.equal(captured.contents.at(-1).role, "user");
  assert.equal(captured.tools[0].google_search !== undefined, true);
  assert.match(captured.systemInstruction.parts[0].text, /decision-intelligence system/i);
});
