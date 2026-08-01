# Split-platform deployment runbook

No step automatically advances to the next. Record the commit SHA and evidence for each gate.

1. **Termux:** switch to `architecture/split-platform`; confirm `main` is unchanged and the complete scope is intentional.
2. **GitHub:** push only that feature branch, open a draft PR, and require the full CI suite to pass.
3. **Cloudflare Pages preview:** build `dist/pages`, deploy to the temporary `pages.dev` URL with `LIFEOS_PAGES_PREVIEW=true`, and test every public/private route. Do not attach the custom domain yet.
4. **Cloudflare Worker preview:** create KV and the rate-limit namespace, render `wrangler.toml`, set secrets with `wrangler secret put`, deploy to `workers.dev`, and run gateway tests. Do not attach `api.losai.ng.eu.org` yet.
5. **Render primary:** take an environment-variable inventory, configure the shared gateway secret, deploy manually with auto-deploy still off, and validate direct `/health` plus Worker-proxied API routes.
6. **Northflank standby:** deploy the slim Docker service, validate `/health`, confirm direct app routes reject missing gateway secrets, and verify essential compatibility through the Worker.
7. **Supabase and end-to-end smoke tests:** verify registration, email confirmation, password reset, Google auth, existing session refresh, profile completion, chat, voice token, admin access, and RLS from Pages preview.
8. **Failover test:** mark or isolate the primary only in a controlled test, run the five-minute probe, verify the KV preferred origin changes and alerts once, verify one-time standby routing, and restore Render.
9. **Capacity test:** pass the 50-request gateway contract and a controlled 50-user smoke plan without quota or error-rate violations.
10. **Routing gate:** only after all prior evidence is 100% green, approve `losai.ng.eu.org` for Pages and `api.losai.ng.eu.org` for the Worker. Then enable Render's gateway guard. Keep rollback DNS and previous deployments available.

Never alter `main`, the existing Back4App branch, live Supabase schema, or production routing as an incidental deployment step. Cloudflare Pages can connect preview branches through its [Git integration](https://developers.cloudflare.com/pages/get-started/git-integration/).
