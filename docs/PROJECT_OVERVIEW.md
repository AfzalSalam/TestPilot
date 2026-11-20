# Project Overview

**TestPilot** is a platform for testing HTTP APIs and catching regressions between runs.

## The problem
Teams ship API changes constantly. A suite of requests in a script tells you pass/fail *now*, but not "what changed since last time", and nobody notices an endpoint getting 3x slower while still returning 200.

## What TestPilot does
1. You describe tests (request + assertions) in a project, grouped into collections.
2. A run executes them in parallel on background workers and stores every result.
3. When a run completes, it is compared with a baseline (the previous completed run of the same scope) and classified: **new failure, fixed, still failing, new test, still passing**, plus **performance regressions** judged statistically.
4. A verdict (`pass`, `warn`, `fail`, `no_baseline`) summarises the run. CI can gate on it.

## Components
| Component | Role |
|---|---|
| React UI | Authoring, run monitoring, regression report, settings |
| FastAPI API | Auth, CRUD, run orchestration, analytics, CI endpoints |
| PostgreSQL | System of record (SQLite supported for dev/tests) |
| Celery workers + Redis | Execute runs; beat ticks schedules every 60 s |
| Demo target | Small store API that can be broken/slowed on demand |

## Scope and non-goals
In scope: functional API checks, regression comparison, scheduling, CI integration, team roles.
Not in scope: load testing, browser/UI testing, distributed multi-region probes, a secrets vault.
