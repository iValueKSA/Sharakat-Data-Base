# ADR: Production authentication

**Status:** Accepted for Phase 1

Use opaque, random, server-side sessions in an HTTP-only, SameSite=Lax cookie. Store only a SHA-256 digest of the cookie token in PostgreSQL and expire sessions after eight hours. Passwords use Python's scrypt KDF with per-password random salt. User roles are `admin`, `analyst`, and `viewer`; production admin APIs require an authenticated session. Analysts can resolve review items, while source configuration, user management, and system controls require an admin. Production rejects legacy shared-token authentication. Login has rate limiting, failed-login tracking, temporary lockout, account disablement, and audit events.

OIDC can be added later behind the session boundary. This phase does not implement SSO or a browser CSRF token; same-site cookie policy and exact-origin CORS are required deployment controls.
