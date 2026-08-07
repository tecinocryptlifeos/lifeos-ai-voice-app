# Cloudflare Pages settings

- Repository: `tecinocryptlifeos/lifeosai`
- Production branch: `main` only after the final routing gate
- Preview branch: `architecture/split-platform`
- Root directory: `/`
- Build command: `python apps/web/build.py`
- Build output: `dist/pages`
- Temporary address: the generated `*.pages.dev` deployment
- Final custom domain: `losai.ng.eu.org`, after approval and smoke tests

Set `LIFEOS_PAGES_PREVIEW=true` while validating the temporary address. This emits a site-wide `X-Robots-Tag` and a disallowing `robots.txt`. Set it to `false` only when the custom domain is approved and the final routing checklist is complete.

Optional public build values are `LIFEOS_GA_MEASUREMENT_ID` and `LIFEOS_ADSENSE_PUBLISHER_ID`. Invalid or absent values inject nothing; advertisements are never injected into `/chat`, `/voice`, `/account`, `/admin`, or `/reset-password`.

The build and output-directory behavior follows [Cloudflare Pages build configuration](https://developers.cloudflare.com/pages/configuration/build-configuration/). `_headers` and `_redirects` follow the [Pages headers](https://developers.cloudflare.com/pages/configuration/headers/) and [Pages redirects](https://developers.cloudflare.com/pages/configuration/redirects/) formats.
