import {
  GatewayError,
  PUBLIC_COMPATIBILITY_GET_PATHS,
  errorResponse,
  isMutation,
  isSafeGetRetry,
  jsonResponse,
  maintenanceResponse,
  northflankCompatible,
  requestOriginAllowed,
  requireIdempotencyKey,
  responseHeaders,
} from "./policy.js";
import { geminiStatus, issueGeminiToken } from "./gemini.js";
import { issueChatDecision } from "./chat.js";
import { currentOriginState, evaluateOrigins, originUrls } from "./health.js";
import { publicConfig, updateProfile, verifySession } from "./supabase.js";

function preflightResponse(request, env) {
  const headers = responseHeaders(request, env, new Headers({
    "Access-Control-Allow-Methods": "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type, Idempotency-Key, X-Requested-With",
    "Access-Control-Max-Age": "86400",
    "Cache-Control": "no-store",
  }));
  return new Response(null, { status: 204, headers });
}

function publicHealth(request, env, state) {
  return jsonResponse(request, env, 200, {
    ok: true,
    gateway: true,
    preferred_origin: state.preferred,
    render_healthy: Boolean(state.render?.healthy),
    northflank_healthy: Boolean(state.northflank?.healthy),
    checked_at: state.checked_at,
    public_site_available_independently: true,
    supabase_is_system_of_record: true,
    voice_token_gateway_available: Boolean(String(env.GEMINI_API_KEY || "").trim()),
  });
}

function gatewayHeaders(env, requestHeaders) {
  const headers = new Headers(requestHeaders);
  headers.delete("Host");
  headers.delete("CF-Connecting-IP");
  headers.delete("CF-Ray");
  headers.set("X-LifeOS-Gateway", "cloudflare-worker-v1");
  const secret = String(env.LIFEOS_GATEWAY_SHARED_SECRET || "").trim();
  if (!secret) {
    throw new GatewayError(503, "GATEWAY_SECRET_MISSING", "The backend gateway secret is not configured.");
  }
  headers.set("X-LifeOS-Gateway-Secret", secret);
  return headers;
}

async function proxyOnce(request, env, origin) {
  const source = new URL(request.url);
  const target = new URL(source.pathname + source.search, origin);
  const init = {
    method: request.method,
    headers: gatewayHeaders(env, request.headers),
    redirect: "manual",
    signal: AbortSignal.timeout(30000),
  };
  if (isMutation(request.method)) init.body = await request.arrayBuffer();
  const outboundFetch = typeof env.__TEST_FETCH__ === "function" ? env.__TEST_FETCH__ : fetch;
  const response = await outboundFetch(target, init);
  const headers = new Headers(response.headers);
  const location = headers.get("Location");
  if (location?.startsWith(origin)) {
    headers.set("Location", new URL(location.slice(origin.length) || "/", source.origin).toString());
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders(request, env, headers),
  });
}

async function compatibilityProxy(request, env, pathname, state) {
  const origins = originUrls(env);
  const safeRetry = isSafeGetRetry(request.method, pathname);
  const mutation = isMutation(request.method);
  if (mutation) requireIdempotencyKey(request);

  if (state.render?.healthy) {
    try {
      const response = await proxyOnce(request, env, origins.render);
      if (response.status < 500) return response;
      if (!safeRetry) {
        if (response.body?.cancel) await response.body.cancel().catch(() => {});
        return maintenanceResponse(
          request,
          env,
          pathname,
          mutation ? "PRIMARY_MUTATION_NOT_REPLAYED" : "PRIMARY_UNAVAILABLE",
        );
      }
    } catch (error) {
      if (!safeRetry) {
        return maintenanceResponse(request, env, pathname, "PRIMARY_MUTATION_NOT_REPLAYED");
      }
    }
    if (safeRetry && state.northflank?.healthy && northflankCompatible(request.method, pathname)) {
      return proxyOnce(request, env, origins.northflank).catch(() =>
        maintenanceResponse(request, env, pathname, "BOTH_ORIGINS_UNAVAILABLE"));
    }
    return maintenanceResponse(request, env, pathname, "PRIMARY_UNAVAILABLE");
  }

  if (state.northflank?.healthy && northflankCompatible(request.method, pathname)) {
    return proxyOnce(request, env, origins.northflank).catch(() =>
      maintenanceResponse(request, env, pathname, "STANDBY_UNAVAILABLE"));
  }
  return maintenanceResponse(request, env, pathname, "NO_COMPATIBLE_ORIGIN");
}

async function handleRequest(request, env) {
  if (!requestOriginAllowed(request, env)) {
    throw new GatewayError(403, "ORIGIN_NOT_ALLOWED", "This browser origin is not allowed.");
  }
  if (request.method === "OPTIONS") return preflightResponse(request, env);

  const url = new URL(request.url);
  const pathname = url.pathname.replace(/\/$/, "") || "/";

  if (request.method === "GET" && pathname === "/health") {
    return publicHealth(request, env, await currentOriginState(env));
  }
  if (request.method === "GET" && ["/config", "/api/auth-config"].includes(pathname)) {
    return jsonResponse(request, env, 200, publicConfig(env));
  }
  if (request.method === "GET" && pathname === "/api/gemini-live-status") {
    return jsonResponse(request, env, geminiStatus(env));
  }
  if (request.method === "GET" && ["/api/session", "/api/session-status"].includes(pathname)) {
    const session = await verifySession(request, env, { profile: "optional" });
    return jsonResponse(request, env, 200, {
      ok: true,
      user_id: session.user.id,
      profile_complete: Boolean(session.profile?.complete),
    });
  }
  if (request.method === "POST" && pathname === "/api/gemini-live-token") {
    const idempotencyKey = requireIdempotencyKey(request);
    const session = await verifySession(request, env, { profile: "required" });
    return jsonResponse(request, env, 200, await issueGeminiToken(request, env, session, idempotencyKey));
  }

  // LOSAI_WORKER_CHAT_FALLBACK_V2_ROUTE
  if (request.method === "POST" && pathname === "/api/chat-decision") {
    const idempotencyKey = requireIdempotencyKey(request);
    const session = await verifySession(request, env, { profile: "required" });
    const state = await currentOriginState(env);

    if (state.render?.healthy) {
      return compatibilityProxy(request, env, pathname, state);
    }

    return jsonResponse(
      request,
      env,
      200,
      await issueChatDecision(
        request,
        env,
        session,
        idempotencyKey,
      ),
    );
  }

  if (pathname === "/api/account-profile" && request.method === "GET") {
    const session = await verifySession(request, env, { profile: "optional" });
    return jsonResponse(request, env, 200, session.profile);
  }

  if (pathname === "/api/account-profile" && request.method === "POST") {
    requireIdempotencyKey(request);
    const session = await verifySession(request, env, { profile: "optional" });
    const payload = await request.json().catch(() => ({}));
    const profile = await updateProfile(env, session.token, session.user.id, payload);
    return jsonResponse(request, env, 200, profile);
  }

  if (!pathname.startsWith("/api/") && !pathname.startsWith("/audio/")) {
    throw new GatewayError(404, "NOT_FOUND", "Not found.");
  }
  if (!(request.method === "GET" && PUBLIC_COMPATIBILITY_GET_PATHS.has(pathname))) {
    await verifySession(request, env, { profile: "required" });
  }
  return compatibilityProxy(request, env, pathname, await currentOriginState(env));
}

export default {
  async fetch(request, env) {
    try {
      return await handleRequest(request, env);
    } catch (error) {
      return errorResponse(request, env, error);
    }
  },
  async scheduled(_event, env, ctx) {
    ctx.waitUntil(evaluateOrigins(env));
  },
};

export { handleRequest };
