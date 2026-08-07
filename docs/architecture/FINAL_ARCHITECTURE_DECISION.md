# LOSAI final split-platform architecture decision

Status: implementation candidate; production routing remains unchanged until every gate passes.

| Responsibility | Permanent owner | Failure behavior |
|---|---|---|
| Development and recovery | Termux | Recreate the feature branch from GitHub; never develop directly on `main` |
| Source of truth and CI | GitHub | No deploy proceeds from an untested or unreviewed commit |
| Homepage and public/private static interfaces | Cloudflare Pages | Remain available when both Python services are down |
| Stable API address, session validation, rate limiting, Live tokens, health state | Cloudflare Worker | Critical edge routes remain available; incompatible routes return controlled maintenance |
| Full legacy Python application | Render | Primary origin; no public front door after gateway enforcement |
| Slim Python compatibility service | Northflank | Warm standby for essential chat and account validation only |
| Identity and durable application data | Supabase | Shared system of record with RLS; no passwords exposed to administrators |

Public routes are `losai.ng.eu.org/`, `/chat`, `/voice`, `/account`, and `/admin`. The temporary Pages address is used until custom-domain approval. The stable API is `api.losai.ng.eu.org`.

The homepage uses an ordinary secure link to the product. WebSocket transport is used only for live voice. Pages owns homepage, legal/public pages, account interface, chat, premium voice visualizer, assets/PWA, analytics, Search Console, and public-content-only AdSense.

The Worker validates Supabase access tokens and profile status, enforces exact-origin CORS and security headers, rate-limits and issues one-use constrained Gemini Live ephemeral tokens, exposes `/health` and `/config`, and protects both Python origins with a shared secret. Cloudflare's scheduled handler probes Render and Northflank every five minutes, stores the result in KV, and alerts whenever the preferred origin changes.

Routing is deterministic:

1. When Render is healthy, compatible API traffic goes to Render.
2. When Render is known unhealthy, critical config/session/Live-token work stays at the edge and supported compatibility traffic goes once to Northflank.
3. If both Python origins fail, Pages, Supabase identity/data, Worker health/config/session validation, and Live-token issuance stay available. Noncritical features return a controlled maintenance response.

Replay policy is intentionally narrow. Only `/health`, `/config`, and public-content reads may be automatically retried. Authenticated token issuance is repeatable only through its short-lived idempotency record. Account deletion, email, database mutations, payments, and admin actions are never blindly replayed. Every mutation must carry an `Idempotency-Key`.

The capacity acceptance target is 50 simultaneous public users. This is a release contract, not a claim of unlimited upstream Gemini, Render, Northflank, Supabase, or Cloudflare quota.

Gemini's official ephemeral-token API supports one-use tokens plus expiry and Live connection constraints: [Gemini Live ephemeral tokens](https://ai.google.dev/gemini-api/docs/live-api/ephemeral-tokens). Cloudflare documents scheduled triggers in Wrangler and their replacement behavior on deploy: [Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/).
