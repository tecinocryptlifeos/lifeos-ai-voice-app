import assert from "node:assert/strict";
import test from "node:test";

import gateway from "../src/index.js";
import { ORIGIN_STATE_KEY } from "../src/health.js";

const USER_ID = "11111111-1111-4111-8111-111111111111";
const PUBLIC_ORIGIN = "https://losai.ng.eu.org";
const API_ORIGIN = "https://api.losai.ng.eu.org";
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

function baseEnv({ fetcher, rateSuccess = true } = {}) {
  const kv = new MemoryKV();
  return {
    LIFEOS_ALLOWED_ORIGINS: PUBLIC_ORIGIN,
    LIFEOS_PUBLIC_SITE_ORIGIN: PUBLIC_ORIGIN,
    LIFEOS_API_ORIGIN: API_ORIGIN,
    LIFEOS_GATEWAY_SHARED_SECRET: "test-gateway-secret",
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

test("health reports the Cloudflare edge as the active gateway", async () => {
  const env = baseEnv();
  const response = await gateway.fetch(request("/health"), env);
  assert.equal(response.status, 200);
  const data = await response.json();
  assert.equal(data.ok, true);
  assert.equal(data.gateway, true);
  assert.equal(data.preferred_origin, "edge");
  assert.equal(data.render_healthy, false);
  assert.equal(data.northflank_healthy, false);
  assert.equal(data.public_site_available_independently, true);
  assert.equal(data.supabase_is_system_of_record, true);
  assert.equal(data.voice_token_gateway_available, true);
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
  const tokenWrite = env.ORIGIN_STATE.puts.find(item => item.key.startsWith("token-idempotency:"));
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
