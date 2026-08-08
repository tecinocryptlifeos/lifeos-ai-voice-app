# Disaster recovery

## Pages unavailable

Roll back to the last known-good Pages deployment. Keep the API Worker unchanged. If the custom domain itself is impaired, publish the verified `pages.dev` address through the existing owner-controlled communication channel.

## Worker unavailable

Roll back the Worker deployment/version first. Do not expose Render or any optional standby as a public browser API origin. If Worker recovery is not immediate, leave Pages informational surfaces online and place protected dynamic features in controlled maintenance.

## Render unavailable

Allow the next scheduled five-minute probe to record the new preferred state, or run the scheduled handler only through the documented Cloudflare test facility. If a configured standby is healthy, new supported requests may go once to that standby. If no standby is configured, the Worker remains preferred at the edge for edge-native operations and Python-dependent features return controlled maintenance. Existing in-flight mutations are never replayed.

## All configured Python origins unavailable

Keep homepage, legal pages, sign-in, Supabase data, `/health`, `/config`, session validation, and Gemini Live token issuance online at the edge. Chat and other Python-dependent features show controlled maintenance. Restore Render first, then verify any configured standby independently.

## Supabase unavailable

Fail authentication and profile checks closed. Do not bypass RLS, substitute a local password store, or expose service credentials. Pages public information can remain online; protected features report maintenance until Supabase recovers.

## Repository or Termux loss

GitHub is authoritative. Clone `tecinocryptlifeos/lifeosai`, fetch the reviewed feature/release commit, verify its signed or recorded SHA, restore only separately backed-up environment registers, and rerun the entire release test suite. Never reconstruct secrets from logs or commit them.

Recovery is complete only when health, auth, profile, chat, voice-token, admin, failover-state, and mutation non-replay checks all pass.
