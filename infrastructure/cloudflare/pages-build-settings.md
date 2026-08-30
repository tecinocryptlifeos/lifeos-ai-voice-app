# Cloudflare Pages production settings

- Repository: `tecinocryptlifeos/lifeosai`
- Production branch: `main`
- Preview branches: optional; previews must never be treated as production
- Root directory: `/`
- Build command: `python apps/web/build.py`
- Build output: `dist/pages`
- Production site: `https://lifeosai.pages.dev`
- API origin: `https://losai-edge-gateway.lifeostecinoai.workers.dev`

The production deployment path is intentionally simple:

`GitHub main` -> `Cloudflare Pages` -> `lifeosai.pages.dev`

GitHub Actions is used for release validation and testing, not as a second Cloudflare deployment mechanism. Do not create a GitHub Actions workflow that independently deploys the Pages site unless this architecture is deliberately changed.

`LIFEOS_PAGES_PREVIEW=true` is reserved for temporary preview validation. Production builds use `LIFEOS_PAGES_PREVIEW=false`.

Optional public build values are `LIFEOS_GA_MEASUREMENT_ID` and `LIFEOS_ADSENSE_PUBLISHER_ID`. Invalid or absent values inject nothing; advertisements are never injected into `/chat`, `/voice`, `/account`, `/admin`, or `/reset-password`.

The build and output-directory behavior follows Cloudflare Pages build configuration. `_headers` and `_redirects` follow the Cloudflare Pages formats.
