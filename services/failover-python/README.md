# Northflank warm standby

This intentionally slim service exposes only health, public/auth configuration, session and account validation, Gemini Live token compatibility, and essential grounded chat. It does not serve the site, admin operations, analytics, email, queues, or generated media.

Build from the repository root using `services/failover-python/Dockerfile`. Every application route requires `X-LifeOS-Gateway-Secret`; `/health` is the only public route.
