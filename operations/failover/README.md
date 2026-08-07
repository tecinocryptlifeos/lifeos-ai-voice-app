# Failover operations

The Worker cron probes Render and Northflank every five minutes. It writes `origin-health-v1` to `ORIGIN_STATE` and chooses `render`, `northflank`, or `edge`. A preferred-origin transition sends one alert attempt and records whether it succeeded.

Do not force failover by editing DNS or publishing a backend origin. For a controlled drill, make only the primary test deployment unhealthy, wait for or explicitly test the scheduled handler, inspect `/health`, exercise one supported new standby request, and then restore Render. Never retry an in-flight mutation during the drill.
