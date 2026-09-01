# Environment-variable register

Values are recorded in provider secret stores, never in Git. “Public” means safe to expose to a browser, not optional.

| Variable | Pages | Worker | Render | Northflank | Classification |
|---|---:|---:|---:|---:|---|
| `LIFEOS_PUBLIC_SITE_ORIGIN` | build | yes | yes | no | Public exact origin |
| `LIFEOS_API_ORIGIN` | build | yes | no | no | Public exact origin |
| `LIFEOS_ALLOWED_ORIGINS` | no | yes | optional | no | Public exact allowlist; no `*` |
| `LIFEOS_GATEWAY_REQUIRED` | no | no | retained legacy | implicit | Public control flag |
| `LIFEOS_GATEWAY_SHARED_SECRET` | no | secret | retained legacy | no | Secret |
| `SUPABASE_URL` | build/CSP | yes | retained legacy | no | Public project URL |
| `SUPABASE_PUBLISHABLE_KEY` | via config | yes | retained legacy | no | Public key, protected by RLS |
| `SUPABASE_SECRET_KEY` | never | never | retained legacy | no | High-impact secret |
| `GEMINI_API_KEY` | never | secret | retained legacy | no | Secret |
| `LIFEOS_ADMIN_EMAILS` | no | no | retained legacy | no | Private authorization input |
| `LIFEOS_GA_MEASUREMENT_ID` | build | no | no | no | Optional public identifier |
| `LIFEOS_ADSENSE_PUBLISHER_ID` | build | no | retained legacy | no | Optional public identifier |
| `ORIGIN_STATE_KV_ID` | no | deploy config | no | no | Public infrastructure identifier |
| `RATE_LIMIT_NAMESPACE_ID` | no | deploy config | no | no | Public positive integer identifier |

The production Worker is Cloudflare-only. It must not define, read, probe, proxy to, or fail over through `RENDER_ORIGIN` or `NORTHFLANK_ORIGIN`.

Before cutover, verify that no secret appears in `git diff`, the Pages artifact, `/config`, browser source, Worker logs, health output, or test fixtures.