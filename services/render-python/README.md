# Render primary Python service

The full legacy Render implementation remains canonical in `app/lifeos_voice_server.py` with its supporting `app/` modules. It is intentionally referenced rather than duplicated here, so fixes do not diverge between two copies.

`LIFEOS_GATEWAY_REQUIRED` defaults off. The split deployment turns it on only after the Worker and both origins pass the final gate; then `/health` remains public, reports unhealthy when required runtime configuration is absent, and all application surfaces require the shared Worker secret (with the existing separately authenticated queue-internal exception).
