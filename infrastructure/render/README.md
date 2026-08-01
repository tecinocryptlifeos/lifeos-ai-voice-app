# Render primary backend

`render.split-platform.yaml` is an additive migration blueprint, not an instruction to apply immediately. It preserves the full legacy Python service, disables automatic deploys, keeps `/health` public, and makes every other route require the Cloudflare gateway when `LIFEOS_GATEWAY_REQUIRED=true`.

Do not replace the live `render.yaml` or enable the gateway guard until Pages, Worker, and Northflank validation has passed. Render documents `autoDeployTrigger: off` as the current way to disable Git-triggered deploys in its [Blueprint specification](https://render.com/docs/blueprint-spec).
