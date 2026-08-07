# Capacity acceptance

The automated Worker suite sends 50 concurrent `/config` requests and 50 concurrent authenticated `/api/session` requests, requiring every response and all 100 mocked Supabase checks to succeed. The deployment runbook additionally requires a controlled 50-user end-to-end smoke plan because a local contract test cannot certify external provider quotas.
