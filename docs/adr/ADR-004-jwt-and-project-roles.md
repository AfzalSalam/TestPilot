# ADR-004: JWT auth and project-scoped roles
**Status:** Accepted
**Decision:** Stateless JWT (PyJWT), bcrypt password hashes, per-project roles owner/editor/viewer. Non-members receive 404. CI uses separate hashed API keys scoped to one project.
**Consequences:** No server-side session revocation for JWTs (tokens expire after 12 h by default; configurable). Keys are revocable.
