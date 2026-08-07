# Supabase permanent identity and data layer

Both Python services and the Worker use the same existing Supabase project. Supabase remains responsible for registration, password reset, Google authentication, sessions, profiles, administrator authorization metadata, operational analytics, export/deletion records, chat metadata, and row-level security.

- Add the temporary Pages URL and final `https://losai.ng.eu.org` callbacks before testing sign-in.
- Retain RLS on `lifeos_profiles` and all user-owned tables; browser profile reads use the verified user JWT.
- Keep `SUPABASE_SECRET_KEY` only on Render and Northflank. It is never a Pages or Worker public variable.
- Keep the publishable key in public configuration; it is intentionally browser-safe when RLS is correct.
- Do not store passwords, large media, voice audio, or conversation bodies in administration analytics.
- Apply no new migration during the infrastructure split unless a separately reviewed data requirement appears.

Supabase documents that server-side authorization checks should validate the token with `getUser`/the Auth user endpoint rather than trust local session storage alone: [Auth guide](https://supabase.com/docs/guides/auth) and [`getUser` reference](https://supabase.com/docs/reference/javascript/auth-getuser).
