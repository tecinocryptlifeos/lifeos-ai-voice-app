# Environment-variable register

Values are recorded in provider secret stores, never in Git. “Public” means safe to expose to a browser, not optional.

| Variable | Pages | Worker | Render | Northflank | Classification |
|---|---:|---:|---:|---:|---|
| `LIFEOS_PUBLIC_SITE_ORIGIN` | build | yes | yes | no | Public exact origin |
| `LIFEOS_API_ORIGIN` | build | yes | no | no | Public exact origin |
| `LIFEOS_ALLOWED_ORIGINS` | no | yes | optional | no | Public exact allowlist; no `*` |
| `RENDER_ORIGIN` | no | yes | no | no | Public origin, operationally sensitive |
| `NORTHFLANK_ORIGIN` | no | yes | no | no | Public origin, operationally sensitive |
| `LIFEOS_GATEWAY_REQUIRED` | no | no | yes | implicit | Public control flag |
| `LIFEOS_GATEWAY_SHARED_SECRET` | no | secret | secret | secret | Secret; same generated value on all three |
| `LIFEOS_FAILOVER_ALERT_WEBHOOK_URL` | no | secret | no | no | Secret |
| `SUPABASE_URL` | build/CSP | yes | yes | yes | Public project URL |
| `SUPABASE_PUBLISHABLE_KEY` | via config | yes | yes | yes | Public key, protected by RLS |
| `SUPABASE_SECRET_KEY` | never | never | secret | secret | High-impact secret |
| `GEMINI_API_KEY` | never | secret | secret | secret | Secret |
| `LIFEOS_ADMIN_EMAILS` | no | no | secret config | no | Private authorization input |
| `LIFEOS_GA_MEASUREMENT_ID` | build | no | no | no | Optional public identifier |
| `LIFEOS_ADSENSE_PUBLISHER_ID` | build | no | retained legacy | no | Optional public identifier |
| `ORIGIN_STATE_KV_ID` | no | deploy config | no | no | Public infrastructure identifier |
| `RATE_LIMIT_NAMESPACE_ID` | no | deploy config | no | no | Public positive integer identifier |

Before cutover, verify that no secret appears in `git diff`, the Pages artifact, `/config`, browser source, Worker logs, health output, or test fixtures.
