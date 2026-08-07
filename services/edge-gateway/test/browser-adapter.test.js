import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";


const ADAPTER = readFileSync(
  new URL("../../../web/lifeos_voice/assets/lifeos_api_gateway_v1.js", import.meta.url),
  "utf8",
);

function browser(apiOrigin = "https://api.losai.ng.eu.org") {
  const calls = [];
  const nativeFetch = async (input, init) => {
    calls.push({ input, init });
    return new Response(null, { status: 204 });
  };
  const window = {
    fetch: nativeFetch,
    location: { origin: "https://preview.pages.dev" },
    crypto: globalThis.crypto,
    LIFEOS_API_ORIGIN: "",
  };
  const context = vm.createContext({
    window,
    document: {
      querySelector(selector) {
        assert.equal(selector, 'meta[name="lifeos-api-origin"]');
        return apiOrigin ? { content: apiOrigin } : null;
      },
    },
    Request,
    Response,
    Headers,
    URL,
    Uint32Array,
    Date,
    Math,
  });
  vm.runInContext(ADAPTER, context, { filename: "lifeos_api_gateway_v1.js" });
  return { window, calls };
}

test("browser adapter moves only API paths and adds mutation idempotency", async () => {
  const { window, calls } = browser();
  await window.fetch("/api/chat-decision", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: [] }),
  });
  const outbound = calls[0].input;
  assert.equal(outbound.url, "https://api.losai.ng.eu.org/api/chat-decision");
  assert.match(outbound.headers.get("Idempotency-Key"), /^[A-Za-z0-9][A-Za-z0-9._:-]{15,199}$/);

  await window.fetch("/assets/lifeos-logo.png");
  await window.fetch("/healthz");
  await window.fetch("https://project.supabase.co/auth/v1/token", { method: "POST" });
  assert.equal(calls[1].input, "/assets/lifeos-logo.png");
  assert.equal(calls[2].input, "/healthz");
  assert.equal(calls[3].input, "https://project.supabase.co/auth/v1/token");
});

test("browser adapter remains same-origin until a Pages API origin is injected", async () => {
  const { window, calls } = browser("");
  await window.fetch("/api/auth-config", { cache: "no-store" });
  assert.equal(calls[0].input.url, "https://preview.pages.dev/api/auth-config");
  assert.equal(calls[0].input.headers.has("Idempotency-Key"), false);
});
