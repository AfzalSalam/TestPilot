# Architecture

```mermaid
flowchart LR
  UI[React SPA] -->|/api/v1 JWT| API[FastAPI]
  CI[GitHub Actions] -->|X-API-Key| API
  API --> DB[(PostgreSQL)]
  API -->|enqueue run id| R[(Redis broker)]
  R --> W[Celery worker]
  B[Celery beat, 60 s tick] -->|tick_schedules| R
  W --> DB
  W -->|SSRF-guarded HTTPX| T[APIs under test]
```

## Run lifecycle
```mermaid
sequenceDiagram
  participant U as User/CI/Schedule
  participant A as API
  participant R as Redis
  participant W as Worker
  participant D as DB
  U->>A: start run
  A->>D: insert Run(status=queued, total=N)
  A->>R: enqueue execute_run(run_id)
  R->>W: deliver
  W->>D: claim: UPDATE ... SET status=running WHERE status=queued (compare-and-set)
  loop each test (thread pool)
    W->>T: guarded request
    W->>D: insert TestResult (UNIQUE run_id,test_case_id), heartbeat
  end
  W->>D: aggregate counts, compute regression summary, status=completed
```

## Layering (backend)
- `routers/` thin HTTP layer, auth + validation, unified error envelope.
- `services/engine.py` pure request executor (no DB). `assertions.py` pure evaluators. `ssrf.py` network guard.
- `services/runner.py` run state machine: claim, execute, resume, cancel, recover.
- `services/regression.py` pure comparison logic over result rows.
- `services/scheduler.py`, `dispatch.py`, `openapi_import.py`.
- `worker/` Celery app and tasks (`acks_late`, `reject_on_worker_lost`, prefetch 1).

## Execution modes
`celery` (production), `thread` (single-process dev default), `inline` (tests). Same runner code in all three.

## Crash safety
Delivery is at-least-once, so the runner is idempotent: atomic claim, `UNIQUE(run_id, test_case_id)`, a heartbeat lease so an orphaned `running` run can be re-claimed, and resume that skips tests that already have a result.
