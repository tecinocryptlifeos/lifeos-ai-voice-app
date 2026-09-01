import { GatewayError } from "./policy.js";

export const ORIGIN_STATE_KEY = "origin-health-v1";
export const ORIGIN_STATE_MAX_AGE_MS = 6 * 60 * 1000;

// Cloudflare is the production edge. The Worker must not discover, probe,
// select, or fail over to an external Render/Northflank origin.
export function edgeOriginState() {
  return {
    checked_at: new Date().toISOString(),
    checked_at_ms: Date.now(),
    preferred: "edge",
    edge: { name: "edge", healthy: true, status: 200, latency_ms: 0 },
  };
}

export async function evaluateOrigins(env) {
  // Retain the health API for compatibility, but make evaluation
  // Cloudflare-edge-only. No external origin is read or probed.
  const state = edgeOriginState();
  if (env.ORIGIN_STATE?.put) {
    await env.ORIGIN_STATE.put(ORIGIN_STATE_KEY, JSON.stringify(state));
  }
  return state;
}

export async function currentOriginState(env) {
  // A stale/missing KV health record must never trigger an external-origin
  // lookup. KV remains available for unrelated idempotency storage elsewhere.
  if (env.ORIGIN_STATE?.get) {
    const state = await env.ORIGIN_STATE.get(ORIGIN_STATE_KEY, { type: "json" });
    if (
      state?.preferred === "edge" &&
      Number.isFinite(Number(state.checked_at_ms)) &&
      Date.now() - Number(state.checked_at_ms) <= ORIGIN_STATE_MAX_AGE_MS
    ) {
      return state;
    }
  }
  return evaluateOrigins(env);
}
