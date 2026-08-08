# Northflank optional warm-standby deployment

Northflank is deferred and is **not a current LifeOS release dependency**. Do not create or fund a Northflank deployment solely to satisfy the present Worker configuration. These instructions are retained for a future standby activation.

Build the repository using `services/failover-python/Dockerfile`, expose container port `8080` over HTTP, and keep one warm instance. Configure HTTP startup, readiness, and liveness probes on `/health`; a 2xx response is healthy.

Required runtime values:

- `GEMINI_API_KEY`
- `LIFEOS_GATEWAY_SHARED_SECRET` (exactly the same generated secret as Render and the Worker)
- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SECRET_KEY`
- `LIFEOS_EMAIL_AUTH_ENABLED=true`
- `LIFEOS_REGISTRATION_ENABLED=true`
- `LIFEOS_GOOGLE_AUTH_ENABLED=true`
- `LIFEOS_MINIMUM_AGE=13`
- `LIFEOS_PASSWORD_MIN_LENGTH=10`
- `LIFEOS_QUEUE_WORKER_ENABLED=false`

Do not add static-site, admin, analytics, queue, email, or media routes. Only if this standby is explicitly enabled and validated should the Worker store its exact HTTPS origin as `NORTHFLANK_ORIGIN`; otherwise that Worker variable remains empty or omitted. Northflank HTTP probes pass for status codes from 200 through 399 and accept a relative path such as `/health`, per its [health-check documentation](https://northflank.com/docs/v1/application/observe/configure-health-checks).
