# ADR-001: At-least-once delivery with an idempotent runner
**Status:** Accepted
**Context:** Celery with `acks_late` redelivers a task if the worker dies. A run could be executed twice, producing duplicate results.
**Decision:** Accept at-least-once and make execution idempotent: atomic claim (`queued→running` compare-and-set), heartbeat lease (`run_lease_seconds`) so a stale `running` run may be re-claimed, `UNIQUE(run_id,test_case_id)`, and resume that skips tests that already have results.
**Consequences:** No duplicates after a real `kill -9` (verified: 8 results, 8 distinct cases, attempts=2). Redelivery latency depends on the broker visibility timeout. A test may be executed twice if the worker dies between the request and the result insert (side-effectful targets should be idempotent).
**Alternatives:** Exactly-once (not offered by Redis); a DB-backed queue (more code, fewer moving parts but loses Celery ecosystem).
