import assert from "node:assert/strict";
import test from "node:test";

import gateway from "../src/index.js";
import { ORIGIN_STATE_KEY } from "../src/health.js";

const USER_ID = "11111111-1111-4111-8111-111111111111";
const PUBLIC_ORIGIN = "https://losai.ng.eu.org";
const API_ORIGIN = "https://api.losai.ng.eu.org";
const RENDER_ORIGIN = "https://losai.onrender.com";
const NORTHFLANK_ORIGIN = "https://losai-standby.example.com";
const SUPABASE_ORIGIN = "https://project.supabase.co";

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

  async put(key, value, options = {}) {
    if (options.expirationTtl != null && options.expirationTtl < 60) {
      throw new RangeError("Cloudflare KV expirationTtl must be at least 60 seconds");
    }
    this.puts.push({ key, options: { ...options } });
    this.values.set(key, String(value));
  }
}

class RateLimiter {
  constructor(success = true) {
    this.success = success;
    this.keys = [];
  }

  async limit({ key }) {
    this.keys.push(key);
    return { success: this.success };
  }
}

function token(payload = {}) {
  const encode = value => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ iat: 200, ...payload })}.signature`;
}

function profile(overrides = {}) {
  return {
    user_id: USER_ID,
    email: "owner@example.com",
    first_name: "LifeOS",
    surname: "Owner",
    country: "Nigeria",
    terms_accepted_at: "2026-08-01T00:00:00Z",
    birth_year: 1990,
    age_verified_at: "2026-08-01T00:00:00Z",
    dob_retention: "eligibility_only",
    ...overrides,
  };
}

function healthyState(overrides = {}) {
  return {
    checked_at: new Date().toISOString(),
    checked_at_ms: Date.now(),
    preferred: "render",
    render: { name: "render", healthy: true, status: 200, latency_ms: 10 },
    northflank: { name: "northflank", healthy: true, status: 200, latency_ms: 12 },
    ...overrides,
  };
}

function baseEnv({ state = healthyState(), fetcher, rateSuccess = true } = {}) {
  const kv = new MemoryKV({ [ORIGIN_STATE_KEY]: JSON.stringify(state) });
  return {
    LIFEOS_ALLOWED_ORIGINS: PUBLIC_ORIGIN,
    LIFEOS_PUBLIC_SITE_ORIGIN: PUBLIC_ORIGIN,
    LIFEOS_API_ORIGIN: API_ORIGIN,
    RENDER_ORIGIN,
    NORTHFLANK_ORIGIN,
    LIFEOS_GATEWAY_SHARED_SECRET: "test-gateway-secret",
    LIFEOS_FAILOVER_ALERT_WEBHOOK_URL: "https://alerts.example.com/lifeos",
    SUPABASE_URL: SUPABASE_ORIGIN,
    SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test",
    LIFEOS_EMAIL_AUTH_ENABLED: "true",
    LIFEOS_REGISTRATION_ENABLED: "true",
    LIFEOS_GOOGLE_AUTH_ENABLED: "true",
    LIFEOS_MINIMUM_AGE: "13",
    LIFEOS_PASSWORD_MIN_LENGTH: "10",
    LIFEOS_GEMINI_LIVE_PRIMARY_MODEL: "gemini-3.1-flash-live-preview",
    LIFEOS_GEMINI_LIVE_FALLBACK_MODEL: "gemini-2.5-flash-native-audio-preview-12-2025",
    GEMINI_API_KEY: "gemini-secret-test",
    ORIGIN_STATE: kv,
    API_RATE_LIMITER: new RateLimiter(rateSuccess),
    __TEST_FETCH__: fetcher || (() => {
      throw new Error("Unexpected outbound request");
    }),
  };
}

function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Origin", options.origin || PUBLIC_ORIGIN);
  return new Request(`${API_ORIGIN}${path}`, { ...options, headers });
}

function authenticated(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${token()}`);
  return request(path, { ...options, headers });
}

function authFetcher(extra, selectedProfile = profile()) {
  return async (input, options = {}) => {
    const url = String(input);
    if (url === `${SUPABASE_ORIGIN}/auth/v1/user`) {
      assert.equal(options.headers.Authorization.startsWith("Bearer "), true);
      return Response.json({ id: USER_ID, email: "owner@example.com", app_metadata: {} });
    }
    if (url.startsWith(`${SUPABASE_ORIGIN}/rest/v1/lifeos_profiles?`)) {
      assert.equal(options.headers.apikey, "sb_publishable_test");
      return Response.json([selectedProfile]);
    }
    return extra(input, options);
  };
}

test("unknown browser origins fail closed without wildcard CORS", async () => {
  const env = baseEnv();
  const response = await gateway.fetch(request("/config", { origin: "https://evil.example" }), env);
  assert.equal(response.status, 403);
  assert.equal(response.headers.has("Access-Control-Allow-Origin"), false);
  assert.equal((await response.json()).code, "ORIGIN_NOT_ALLOWED");
});

test("public config exposes only public authentication values", async () => {
  const env = baseEnv();
  env.SUPABASE_SECRET_KEY = "must-not-leak";
  const response = await gateway.fetch(request("/config"), env);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("Access-Control-Allow-Origin"), PUBLIC_ORIGIN);
  const data = await response.json();
  assert.equal(data.api_origin, API_ORIGIN);
  assert.equal(data.public_site_origin, PUBLIC_ORIGIN);
  assert.equal(data.supabase_anon_key, "sb_publishable_test");
  assert.equal(JSON.stringify(data).includes("must-not-leak"), false);
});

test("session validation uses Supabase and reports profile completion", async () => {
  const env = baseEnv({ fetcher: authFetcher(() => { throw new Error("unexpected"); }) });
  const response = await gateway.fetch(authenticated("/api/session"), env);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    ok: true,
    user_id: USER_ID,
    profile_complete: true,
  });
});

test("Gemini token issuance is authenticated, constrained, rate-limited and idempotent", async () => {
  let tokenCalls = 0;
  const env = baseEnv({
    fetcher: authFetcher(async (input, options) => {
      assert.equal(String(input), "https://generativelanguage.googleapis.com/v1beta/auth_tokens");
      tokenCalls += 1;
      assert.equal(options.headers["x-goog-api-key"], "gemini-secret-test");
      const body = JSON.parse(options.body);
      assert.equal(body.uses, 1);
      assert.equal(body.liveConnectConstraints.model, "models/gemini-3.1-flash-live-preview");
      assert.deepEqual(body.liveConnectConstraints.config.responseModalities, ["AUDIO"]);
      return Response.json({ name: "auth_tokens/ephemeral-test" });
    }),
  });
  const options = {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": "11111111-2222-4333-8444-555555555555",
    },
    body: JSON.stringify({ model_preference: "primary" }),
  };
  const first = await gateway.fetch(authenticated("/api/gemini-live-token", options), env);
  assert.equal(first.status, 200);
  assert.equal((await first.json()).idempotent_replay, false);
  const second = await gateway.fetch(authenticated("/api/gemini-live-token", options), env);
  assert.equal(second.status, 200);
  assert.equal((await second.json()).idempotent_replay, true);
  assert.equal(tokenCalls, 1);
  assert.equal(env.API_RATE_LIMITER.keys.length, 1);
  const tokenWrite = env.ORIGIN_STATE.puts.find(item =>
    item.key.startsWith("token-idempotency:"));
  assert.equal(tokenWrite.options.expirationTtl, 60);
});

test("every mutation requires an idempotency key", async () => {
  const env = baseEnv({ fetcher: authFetcher(() => { throw new Error("must not reach origin"); }) });
  const response = await gateway.fetch(authenticated("/api/chat-decision", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: [{ role: "user", content: "Hello" }] }),
  }), env);
  assert.equal(response.status, 400);
  assert.equal((await response.json()).code, "IDEMPOTENCY_KEY_REQUIRED");
});

test("a failed mutation is never replayed to Northflank", async () => {
  const calls = [];
  const env = baseEnv({
    fetcher: authFetcher(async input => {
      calls.push(String(input));
      if (String(input).startsWith(RENDER_ORIGIN)) throw new Error("render unavailable");
      if (String(input).startsWith(NORTHFLANK_ORIGIN)) return Response.json({ ok: true });
      throw new Error("unexpected");
    }),
  });
  const response = await gateway.fetch(authenticated("/api/chat-decision", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
    },
    body: JSON.stringify({ messages: [{ role: "user", content: "Hello" }] }),
  }), env);
  assert.equal(response.status, 503);
  assert.equal((await response.json()).reason, "PRIMARY_MUTATION_NOT_REPLAYED");
  assert.equal(calls.filter(item => item.startsWith(RENDER_ORIGIN)).length, 1);
  assert.equal(calls.some(item => item.startsWith(NORTHFLANK_ORIGIN)), false);
});

test("a supported account read routes once to standby when primary is already down", async () => {
  const calls = [];

  const state = healthyState({
    preferred: "northflank",
    render: {
      name: "render",
      healthy: false,
      status: 503,
      latency_ms: 20,
    },
    northflank: {
      name: "northflank",
      healthy: true,
      status: 200,
      latency_ms: 12,
    },
  });

  const env = baseEnv({
    state,
    fetcher: authFetcher(async (input, options) => {
      const url = String(input);
      calls.push(url);

      assert.equal(
        options.headers.get("X-LifeOS-Gateway-Secret"),
        "test-gateway-secret",
      );

      return Response.json({
        ok: true,
        origin: "standby",
      });
    }),
  });

  const response = await gateway.fetch(
    authenticated("/api/account-profile"),
    env,
  );

  assert.equal(response.status, 200);

  assert.deepEqual(
    await response.json(),
    {
      ok: true,
      origin: "standby",
    },
  );

  assert.equal(
    calls.some(item => item.startsWith(RENDER_ORIGIN)),
    false,
  );

  assert.equal(
    calls.filter(item =>
      item.startsWith(NORTHFLANK_ORIGIN))
      .length,
    1,
  );
});

// LOSAI_WORKER_CHAT_FALLBACK_V2_TEST
test("a new chat mutation uses the Worker fallback when primary is already down", async () => {
  const calls = [];

  const state = healthyState({
    preferred: "edge",
    render: {
      name: "render",
      healthy: false,
      status: 503,
      latency_ms: 20,
    },
    northflank: {
      name: "northflank",
      healthy: false,
      status: 503,
      latency_ms: 20,
    },
  });

  const env = baseEnv({
    state,
    fetcher: authFetcher(async (input, options) => {
      const url = String(input);
      calls.push(url);

      if (
        url.startsWith(
          "https://generativelanguage.googleapis.com/v1beta/models/",
        )
      ) {
        assert.equal(
          options.headers["x-goog-api-key"],
          "gemini-secret-test",
        );

        const body = JSON.parse(options.body);

        assert.equal(
          Array.isArray(body.contents),
          true,
        );

        assert.deepEqual(
          body.tools,
          [{ google_search: {} }],
        );

        assert.equal(
          body.systemInstruction.parts[0].text.includes(
            "LifeOSAI Synthetic Artificial Intelligence assistant",
          ),
          true,
        );

        assert.equal(
          body.systemInstruction.parts[0].text.includes(
            "IGBO UNDERSTANDING POLICY",
          ),
          true,
        );

        assert.equal(
          body.systemInstruction.parts[0].text.includes(
            "Igbo Izugbe",
          ),
          true,
        );

        return Response.json({
          candidates: [
            {
              content: {
                parts: [
                  {
                    text: "Worker fallback reply",
                  },
                ],
              },
              groundingMetadata: {
                groundingChunks: [
                  {
                    web: {
                      uri: "https://example.com/source",
                      title: "Example source",
                    },
                  },
                ],
              },
            },
          ],
        });
      }

      throw new Error(`Unexpected outbound request: ${url}`);
    }),
  });

  const makeRequest = () =>
    authenticated("/api/chat-decision", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key":
          "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff",
      },
      body: JSON.stringify({
        messages: [
          {
            role: "user",
            content: "Hello",
          },
        ],
      }),
    });

  const first = await gateway.fetch(
    makeRequest(),
    env,
  );

  assert.equal(first.status, 200);

  const firstData = await first.json();

  assert.equal(
    firstData.reply,
    "Worker fallback reply",
  );

  assert.equal(
    firstData.fallback_origin,
    "cloudflare-worker",
  );

  assert.equal(
    firstData.idempotent_replay,
    false,
  );

  assert.equal(firstData.grounded, true);
  assert.equal(firstData.sources.length, 1);

  const second = await gateway.fetch(
    makeRequest(),
    env,
  );

  assert.equal(second.status, 200);

  assert.equal(
    (await second.json()).idempotent_replay,
    true,
  );

  assert.equal(
    calls.some(item =>
      item.startsWith(RENDER_ORIGIN)),
    false,
  );

  assert.equal(
    calls.some(item =>
      item.startsWith(NORTHFLANK_ORIGIN)),
    false,
  );

  assert.equal(
    calls.filter(item =>
      item.startsWith(
        "https://generativelanguage.googleapis.com/v1beta/models/",
      ))
      .length,
    1,
  );

  assert.equal(
    env.API_RATE_LIMITER.keys.length,
    1,
  );

  const cacheWrite = env.ORIGIN_STATE.puts.find(
    item =>
      item.key.startsWith("chat-idempotency:"),
  );

  assert.equal(
    cacheWrite.options.expirationTtl,
    60,
  );
});

test("an authenticated account read is not blindly replayed", async () => {
  const calls = [];
  const env = baseEnv({
    fetcher: authFetcher(async (input, options) => {
      const url = String(input);
      calls.push(url);
      if (url.startsWith(RENDER_ORIGIN)) return Response.json({ ok: false }, { status: 503 });
      if (url.startsWith(NORTHFLANK_ORIGIN)) return Response.json({ ok: true, origin: "standby" });
      throw new Error("unexpected");
    }),
  });
  const response = await gateway.fetch(authenticated("/api/account-profile"), env);
  assert.equal(response.status, 503);
  assert.equal((await response.json()).reason, "PRIMARY_UNAVAILABLE");
  assert.equal(calls.filter(item => item.startsWith(RENDER_ORIGIN)).length, 1);
  assert.equal(calls.filter(item => item.startsWith(NORTHFLANK_ORIGIN)).length, 0);
});

test("an incomplete account can load its profile through the primary", async () => {
  let primaryCalls = 0;
  const env = baseEnv({
    fetcher: authFetcher(async input => {
      assert.equal(String(input), `${RENDER_ORIGIN}/api/account-profile`);
      primaryCalls += 1;
      return Response.json({ ok: true, complete: false, profile: {} });
    }, profile({ first_name: "" })),
  });
  const response = await gateway.fetch(authenticated("/api/account-profile"), env);
  assert.equal(response.status, 200);
  assert.equal((await response.json()).complete, false);
  assert.equal(primaryCalls, 1);
});

test("an account-profile mutation is unavailable instead of spilling to standby", async () => {
  const calls = [];
  const state = healthyState({
    preferred: "northflank",
    render: { name: "render", healthy: false, status: 503, latency_ms: 20 },
    northflank: { name: "northflank", healthy: true, status: 200, latency_ms: 12 },
  });
  const env = baseEnv({
    state,
    fetcher: authFetcher(async input => {
      calls.push(String(input));
      return Response.json({ ok: true });
    }, profile({ first_name: "" })),
  });
  const response = await gateway.fetch(authenticated("/api/account-profile", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": "cccccccc-dddd-4eee-8fff-aaaaaaaaaaaa",
    },
    body: JSON.stringify({ first_name: "LifeOS" }),
  }), env);
  assert.equal(response.status, 503);
  assert.equal((await response.json()).reason, "NO_COMPATIBLE_ORIGIN");
  assert.equal(calls.some(item => item.startsWith(RENDER_ORIGIN)), false);
  assert.equal(calls.some(item => item.startsWith(NORTHFLANK_ORIGIN)), false);
});

test("five-minute health evaluation stores preferred origin and alerts on change", async () => {
  const previous = healthyState({
    preferred: "render",
    render: { name: "render", healthy: true, status: 200, latency_ms: 5 },
  });
  let alertCalls = 0;
  const env = baseEnv({
    state: previous,
    fetcher: async input => {
      const url = String(input);
      if (url === `${RENDER_ORIGIN}/health`) return new Response("down", { status: 503 });
      if (url === `${NORTHFLANK_ORIGIN}/health`) return new Response("OK", { status: 200 });
      if (url === "https://alerts.example.com/lifeos") {
        alertCalls += 1;
        return new Response(null, { status: 204 });
      }
      throw new Error(`Unexpected ${url}`);
    },
  });
  let task;
  await gateway.scheduled({}, env, { waitUntil(value) { task = value; } });
  await task;
  const stored = await env.ORIGIN_STATE.get(ORIGIN_STATE_KEY, { type: "json" });
  assert.equal(stored.preferred, "northflank");
  assert.equal(stored.render.healthy, false);
  assert.equal(stored.northflank.healthy, true);
  assert.equal(stored.alert_sent, true);
  assert.equal(alertCalls, 1);
  assert.equal(
    env.ORIGIN_STATE.puts.filter(item => item.key === ORIGIN_STATE_KEY).length,
    1,
  );
});

test("both Python origins can fail while the edge health and public site contract stay online", async () => {
  const state = healthyState({
    preferred: "edge",
    render: { name: "render", healthy: false, status: 0, latency_ms: 8000 },
    northflank: { name: "northflank", healthy: false, status: 0, latency_ms: 8000 },
  });
  const env = baseEnv({ state });
  const response = await gateway.fetch(request("/health"), env);
  assert.equal(response.status, 200);
  const data = await response.json();
  assert.equal(data.preferred_origin, "edge");
  assert.equal(data.public_site_available_independently, true);
  assert.equal(data.supabase_is_system_of_record, true);
  assert.equal(data.voice_token_gateway_available, true);
});

test("capacity contract handles fifty concurrent public configuration requests", async () => {
  const env = baseEnv();
  const responses = await Promise.all(Array.from({ length: 50 }, () =>
    gateway.fetch(request("/config"), env)));
  assert.equal(responses.every(response => response.status === 200), true);
  const payloads = await Promise.all(responses.map(response => response.json()));
  assert.equal(payloads.length, 50);
  assert.equal(payloads.every(item => item.api_origin === API_ORIGIN), true);
});

test("capacity contract validates fifty concurrent authenticated sessions", async () => {
  let userChecks = 0;
  let profileChecks = 0;
  const env = baseEnv({
    fetcher: async input => {
      const url = String(input);
      if (url === `${SUPABASE_ORIGIN}/auth/v1/user`) {
        userChecks += 1;
        return Response.json({ id: USER_ID, email: "owner@example.com", app_metadata: {} });
      }
      if (url.startsWith(`${SUPABASE_ORIGIN}/rest/v1/lifeos_profiles?`)) {
        profileChecks += 1;
        return Response.json([profile()]);
      }
      throw new Error(`Unexpected ${url}`);
    },
  });
  const responses = await Promise.all(Array.from({ length: 50 }, () =>
    gateway.fetch(authenticated("/api/session"), env)));
  assert.equal(responses.every(response => response.status === 200), true);
  assert.equal(userChecks, 50);
  assert.equal(profileChecks, 50);
});
