export const ORIGIN_STATE_KEY = "origin-health-v1";
export const ORIGIN_STATE_MAX_AGE_MS = 6 * 60 * 1000;

function fetchImpl(env) {
  return typeof env.__TEST_FETCH__ === "function" ? env.__TEST_FETCH__ : fetch;
}

function safeOrigin(value, name) {
  const candidate = String(value || "").trim().replace(/\/$/, "");
  let parsed;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new GatewayError(503, "ORIGIN_NOT_CONFIGURED", `${name} is not configured.`);
  }
  if (parsed.protocol !== "https:" || parsed.origin !== candidate) {
    throw new GatewayError(503, "ORIGIN_NOT_CONFIGURED", `${name} is not configured.`);
  }
  return candidate;
}

export function originUrls(env) {
  const northflankValue = String(env.NORTHFLANK_ORIGIN || "").trim();
  return {
    render: safeOrigin(env.RENDER_ORIGIN, "The Render origin"),
    northflank: northflankValue
      ? safeOrigin(northflankValue, "The Northflank origin")
      : null,
  };
}

export async function probeOrigin(env, name, origin) {
  const headers = new Headers({ Accept: "application/json, text/plain;q=0.9" });
  const secret = String(env.LIFEOS_GATEWAY_SHARED_SECRET || "").trim();
  if (secret) headers.set("X-LifeOS-Gateway-Secret", secret);
  const started = Date.now();
  try {
    const response = await fetchImpl(env)(`${origin}/health`, {
      method: "GET",
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (response.body?.cancel) await response.body.cancel().catch(() => {});
    return {
      name,
      healthy: response.ok,
      status: response.status,
      latency_ms: Date.now() - started,
    };
  } catch {
    return { name, healthy: false, status: 0, latency_ms: Date.now() - started };
  }
}

async function sendChangeAlert(env, previous, current) {
  const webhook = String(env.LIFEOS_FAILOVER_ALERT_WEBHOOK_URL || "").trim();
  if (!webhook) {
    console.error("LOSAI_FAILOVER_ALERT_UNCONFIGURED", { previous, current });
    return false;
  }
  try {
    const parsed = new URL(webhook);
    if (parsed.protocol !== "https:") return false;
    const response = await fetchImpl(env)(webhook, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event: "losai_preferred_origin_changed",
        previous,
        current,
        changed_at: new Date().toISOString(),
      }),
      signal: AbortSignal.timeout(8000),
    });
    if (response.body?.cancel) await response.body.cancel().catch(() => {});
    return response.ok;
  } catch {
    return false;
  }
}

export async function evaluateOrigins(env) {
  if (!env.ORIGIN_STATE?.get || !env.ORIGIN_STATE?.put) {
    throw new GatewayError(503, "KV_NOT_CONFIGURED", "Cloudflare KV failover state is not configured.");
  }
  const origins = originUrls(env);
  const [render, northflank] = await Promise.all([
    probeOrigin(env, "render", origins.render),
    origins.northflank
      ? probeOrigin(env, "northflank", origins.northflank)
      : Promise.resolve({
          name: "northflank",
          configured: false,
          healthy: false,
          status: 0,
          latency_ms: 0,
        }),
  ]);
  const previous = await env.ORIGIN_STATE.get(ORIGIN_STATE_KEY, { type: "json" });
  const preferred = render.healthy ? "render" : northflank.healthy ? "northflank" : "edge";
  const state = {
    checked_at: new Date().toISOString(),
    checked_at_ms: Date.now(),
    preferred,
    render,
    northflank,
  };
  if (previous?.preferred && previous.preferred !== preferred) {
    state.alert_sent = await sendChangeAlert(env, previous.preferred, preferred);
  }
  await env.ORIGIN_STATE.put(ORIGIN_STATE_KEY, JSON.stringify(state));
  return state;
}

export async function currentOriginState(env) {
  if (!env.ORIGIN_STATE?.get) {
    throw new GatewayError(503, "KV_NOT_CONFIGURED", "Cloudflare KV failover state is not configured.");
  }
  const state = await env.ORIGIN_STATE.get(ORIGIN_STATE_KEY, { type: "json" });
  if (
    state?.preferred &&
    Number.isFinite(Number(state.checked_at_ms)) &&
    Date.now() - Number(state.checked_at_ms) <= ORIGIN_STATE_MAX_AGE_MS
  ) {
    return state;
  }
  return evaluateOrigins(env);
}
