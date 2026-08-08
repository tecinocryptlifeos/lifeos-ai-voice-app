# Failover operations

The Worker cron probes Render every five minutes and probes the optional standby only when `NORTHFLANK_ORIGIN` is configured. It writes `origin-health-v1` to `ORIGIN_STATE` and chooses `render`, the configured standby, or `edge`. A preferred-origin transition sends one alert attempt and records whether it succeeded.

Do not force failover by editing DNS or publishing a backend origin. For the current no-standby deployment, make only the primary test deployment unhealthy, wait for or explicitly test the scheduled handler, inspect `/health`, verify the preferred state becomes `edge`, and confirm Python-dependent routes return controlled maintenance while edge-native operations remain available. Then restore Render. Never retry an in-flight mutation during the drill.

If a standby is enabled in the future, independently verify its health, gateway-secret protection, compatibility routes, and one-time routing behavior before treating it as part of failover.
