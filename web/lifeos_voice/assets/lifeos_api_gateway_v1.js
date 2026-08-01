(() => {
  "use strict";

  const nativeFetch = window.fetch.bind(window);
  const API_PREFIXES = ["/api/", "/audio/"];
  const API_EXACT_PATHS = new Set(["/health", "/config"]);

  function configuredOrigin() {
    const value = String(
      window.LIFEOS_API_ORIGIN ||
      document.querySelector('meta[name="lifeos-api-origin"]')?.content ||
      "",
    ).trim().replace(/\/$/, "");
    if (!value) return "";
    try {
      const parsed = new URL(value);
      return parsed.protocol === "https:" && parsed.origin === value ? value : "";
    } catch (_) {
      return "";
    }
  }

  function isGatewayPath(pathname) {
    return API_EXACT_PATHS.has(pathname) || API_PREFIXES.some(prefix => pathname.startsWith(prefix));
  }

  function idempotencyKey() {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    const entropy = window.crypto?.getRandomValues
      ? Array.from(window.crypto.getRandomValues(new Uint32Array(4)), value => value.toString(16)).join("")
      : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
    return `lifeos-${entropy}`.slice(0, 80);
  }

  window.fetch = function lifeosGatewayFetch(input, init = {}) {
    const source = input instanceof Request ? input : null;
    const originalUrl = source ? source.url : String(input);
    let url;
    try {
      url = new URL(originalUrl, window.location.origin);
    } catch (_) {
      return nativeFetch(input, init);
    }
    if (url.origin !== window.location.origin || !isGatewayPath(url.pathname)) {
      return nativeFetch(input, init);
    }

    const origin = configuredOrigin();
    if (origin) url = new URL(url.pathname + url.search, origin);

    const method = String(init.method || source?.method || "GET").toUpperCase();
    const headers = new Headers(source?.headers || undefined);
    new Headers(init.headers || undefined).forEach((value, name) => headers.set(name, value));
    if (!["GET", "HEAD", "OPTIONS"].includes(method) && !headers.has("Idempotency-Key")) {
      headers.set("Idempotency-Key", idempotencyKey());
    }

    const request = source
      ? new Request(url, source)
      : new Request(url, init);
    return nativeFetch(new Request(request, { ...init, headers }));
  };

  window.LifeOSAPI = Object.freeze({
    get origin() { return configuredOrigin() || window.location.origin; },
    idempotencyKey,
  });
})();
