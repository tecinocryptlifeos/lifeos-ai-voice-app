# Restore checklist

1. Select a previously tested Git commit and record its SHA.
2. Restore Pages and Worker versions without changing the API hostname.
3. Restore Render manually with auto-deploy disabled.
4. Restore Northflank independently and test `/health`.
5. Confirm the same Supabase project and RLS policies; do not import data over a live project without a separate approved recovery plan.
6. Run health, auth, profile, chat, voice-token, admin, failover, and non-replay tests before reopening routing.
