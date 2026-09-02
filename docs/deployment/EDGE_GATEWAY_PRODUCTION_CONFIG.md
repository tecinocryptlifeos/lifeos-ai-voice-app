# Edge gateway production configuration

The production API edge is the Cloudflare Worker `losai-edge-gateway`.

## Required origins

- `LIFEOS_PUBLIC_SITE_ORIGIN=https://lifeosai.pages.dev`
- `LIFEOS_ALLOWED_ORIGINS=https://lifeosai.pages.dev`
- `LIFEOS_API_ORIGIN=https://losai-edge-gateway.lifeostecinoai.workers.dev`

The Pages site is the public UI origin. The Worker origin is the API origin. Do not point `LIFEOS_API_ORIGIN` back to the Pages site.

## Trigger contract

The Worker source exports `fetch()` only. It does not export `scheduled()` and production must not attach a legacy five-minute cron trigger. The repository test contract explicitly rejects the old `*/5 * * * *` trigger.

Therefore the Cloudflare Worker configuration must have no scheduled trigger configured. Do not add a no-op `scheduled()` export to mask a stale Cloudflare trigger.
