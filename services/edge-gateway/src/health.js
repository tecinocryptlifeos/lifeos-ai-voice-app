export const ORIGIN_STATE_KEY = "origin-health-v1";
export const ORIGIN_STATE_MAX_AGE_MS = 6 * 60 * 1000;

export async function currentOriginState(_env) {
  return {
    checked_at: new Date().toISOString(),
    checked_at_ms: Date.now(),
    preferred: "edge",
    edge: {
      name: "edge",
      healthy: true,
      status: 200,
      latency_ms: 0,
    },
  };
}

export async function evaluateOrigins(env) {
  return currentOriginState(env);
}
