# TestPilot — Distributed API Testing & Regression Platform

Define API tests, run them in parallel on background workers, and get an automatic **regression report** comparing each run with the previous one: new failures, fixes, and statistically-judged slowdowns. Includes scheduling, OpenAPI import, team roles and a CI endpoint for GitHub Actions.

**Stack:** FastAPI · PostgreSQL · SQLAlchemy 2 · Alembic · HTTPX · Celery + Redis · Pytest · Docker Compose · GitHub Actions · React + TypeScript (Vite)

## Quick start (Docker)

```bash
cp .env.example .env          # set TESTPILOT_SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build
python scripts/seed_demo.py --api http://localhost:8000 --target http://demo-api:9000   # optional demo data
```

- UI: http://localhost:8080 · API docs (Swagger): http://localhost:8000/docs
- Demo login after seeding: `demo@testpilot.dev` / `demo-pass-123`
- Break the demo target to see regression detection:
  `curl -X POST localhost:9000/admin/mode -H 'content-type: application/json' -d '{"mode":"broken"}'` then re-run (modes: `healthy`, `broken`, `slow`).

`TESTPILOT_SSRF_ALLOWED_HOSTS=demo-api` in `docker-compose.yml` exists **only** so the demo works on the private Docker network. Remove it for real use.

## Local development

```bash
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head && uvicorn app.main:app --reload          # SQLite, thread execution mode
pytest -q                                                       # 155 tests

cd frontend && npm install && npm run dev                       # http://localhost:5173, proxies /api to :8000
```

Run the suite against PostgreSQL: `TESTPILOT_TEST_DATABASE_URL=postgresql+psycopg2://user:pass@host/db pytest -q`.

## Features

| Area | What you get |
|---|---|
| Test authoring | Endpoints, collections, test cases with headers, query, JSON/text/form bodies, `{{variables}}`, bearer/basic/API-key auth, live "Send" |
| Assertions | Expected status, JSONPath, headers, body contains, response time; operators eq, neq, contains, not_contains, exists, not_exists, gt/gte/lt/lte, regex, type, length |
| Execution | Parallel runs; Celery workers (or thread/inline modes); cancel, re-run; idempotent claim + heartbeat lease so a crashed worker's run is recovered without duplicate results |
| Regression | Baseline = previous completed run of same scope (or choose one). new_failure / fixed / still_failing / new_test, plus robust performance check (median + MAD) |
| Scheduling | Cron schedules with preview, pause, run-now, no overlapping runs |
| Import | OpenAPI 3 / Swagger 2 (JSON or YAML) to endpoints, starter tests, collection, base URL |
| Teams | Owner / editor / viewer roles per project |
| CI | Hashed project API keys, `POST /api/v1/ci/runs`, pollable `conclusion`; example workflow in `.github/workflows/` |
| Security | SSRF guard, encrypted secrets, secret redaction in stored results, rate limiting |

## Security highlights

Every outbound request goes through an SSRF guard: http/https only, no URL credentials, all resolved IPs must be globally routable (IPv4-mapped IPv6 and NAT64 are unwrapped), DNS is resolved once and the connection pinned to the vetted IP, and every redirect hop is re-validated. Auth credentials and project variables are Fernet-encrypted at rest and masked in API output. Sensitive headers, query params and body keys are redacted in stored results.

## Known limitations

See `docs/TECHNICAL_DECISIONS.md`. Notably: the rate limiter is in-process (per API instance), project variables are visible to members (not a secrets vault), and after a hard worker crash with Redis, recovery waits for the broker visibility timeout.

## Documentation

Start at `docs/PROJECT_OVERVIEW.md`. Also: ARCHITECTURE, DATABASE_DESIGN, API_REFERENCE, TECHNICAL_DECISIONS, DEPLOYMENT_AND_TROUBLESHOOTING, and architecture decision records in `docs/adr/`.
