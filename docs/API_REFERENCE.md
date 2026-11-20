# API Reference

Base path `/api/v1`. Interactive docs at `/docs`. Auth: `Authorization: Bearer <jwt>` (CI endpoints: `X-API-Key`). Errors: `{"error":{"code","message","details"}}`. Non-members get **404**, not 403, to avoid leaking project existence.

| Group | Routes |
|---|---|
| Health | `GET /health` |
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| Dashboard | `GET /dashboard` |
| Projects | `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}` |
| Members | `GET/POST /projects/{id}/members`, `PATCH/DELETE .../members/{user_id}` |
| Endpoints | CRUD `/projects/{id}/endpoints` |
| Collections | CRUD `/projects/{id}/collections` |
| Test cases | CRUD `/projects/{id}/test-cases`; `POST /execute` (ad-hoc), `POST /{tc}/execute`, `POST /{tc}/duplicate` |
| Runs | `GET/POST /projects/{id}/runs`, `GET .../{run}`, `GET .../{run}/results`, `GET .../{run}/regression?baseline_run_id=`, `POST .../{run}/cancel`, `POST .../{run}/rerun`, `DELETE .../{run}` |
| Schedules | CRUD `/projects/{id}/schedules`, `GET /schedules/preview?cron=`, `POST /schedules/{s}/trigger` |
| API keys | `GET/POST /projects/{id}/api-keys`, `DELETE .../{key}` (revoke) |
| Import | `POST /projects/{id}/import/openapi` |
| Analytics | `GET /projects/{id}/analytics` |
| CI | `POST /ci/runs`, `GET /ci/runs/{id}?fail_on_performance=` → `conclusion`: pending / success / failure |

Roles: viewer reads; editor writes tests/collections/runs/schedules/keys; owner also manages members, project settings and deletion.
