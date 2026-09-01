import assert from "node:assert/strict";
import test from "node:test";

import gateway from "../src/index.js";
import { ORIGIN_STATE_KEY, currentOriginState, evaluateOrigins } from "../src/health.js";

const PUBLIC_ORIGIN = "https://lifeosai.pages.dev";
const API_ORIGIN = "https://losai-edge-gateway.lifeostecinoai.workers.dev";

class MemoryKV {
  constructor(initial = {}) {
    this.values = new Map(Object.entries(initial));
    this.puts = [];
  }

  async get(key, options = {}) {
    const value = this.values.get(key);
    if (value == null) return null;
    return options?.type === "json" ? JSON.parse(value) : value;
  }

  async put(key, value) {
    this.puts.push({ key, value: String(value) });
    this.values.set(key, String(value));
  }
}

function env(state = null) {
  const kv = new MemoryKV(state ? { [ORIGIN_STATE_KEY]: JSON.stringify(state) } : {});
  return {
    ORIGIN_STATE: kv,
    LIFEOS_ALLOWED_ORIGINS: PUBLIC_ORIGIN,
    LIFEOS_PUBLIC_SITE_ORIGIN: PUBLIC_ORIGIN,
    LIFEOS_API_ORIGIN: API_ORIGIN,
    SUPABASE_URL: "https://project.supabase.co",
    SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test",
    LIFEOS_GATEWAY_SHARED_SECRET: "test-gateway-secret",
    GEMINI_API_KEY: "test-gemini-key",
    __KV: kv,
  };
}

test("health evaluation is Cloudflare-edge-only", async () => {
  const runtime = env();
  const state = await evaluateOrigins(runtime);

  assert.equal(state.preferred, "edge");
  assert.equal(state.edge.healthy, true);
  assert.equal("legacy" in state, false);
  assert.equal(runtime.__KV.puts.length, 1);
});

test("stale KV health never restores a legacy provider", async () => {
  const stale = {
    checked_at: "2020-01-01T00:00:00.000Z",
    checked_at_ms: 1,
    preferred: "legacy",
    legacy: { name: "legacy", healthy: true, status: 200, latency_ms: 1 },
  };
  const runtime = env(stale);
  const state = await currentOriginState(runtime);

  assert.equal(state.preferred, "edge");
  assert.equal("legacy" in state, false);
});

test("fresh edge state remains edge-only", async () => {
  const fresh = {
    checked_at: new Date().toISOString(),
    checked_at_ms: Date.now(),
    preferred: "edge",
    edge: { name: "edge", healthy: true, status: 200, latency_ms: 0 },
  };
  const state = await currentOriginState(env(fresh));

  assert.equal(state.preferred, "edge");
  assert.equal(state.edge.healthy, true);
  assert.equal("legacy" in state, false);
});

test("public health reports Cloudflare edge as authoritative", async () => {
  const runtime = env();
  const request = new Request(`${API_ORIGIN}/health`, {
    method: "GET",
    headers: { Origin: PUBLIC_ORIGIN },
  });
  const response = await gateway.fetch(request, runtime);
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.equal(body.ok, true);
  assert.equal(body.preferred_origin, "edge");
  assert.equal(body.edge_healthy, true);
  assert.equal("legacy_healthy" in body, false);
});
