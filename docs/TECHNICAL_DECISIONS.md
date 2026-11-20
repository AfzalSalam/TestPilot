# Technical Decisions

Full records are in `adr/`. Summary:

| Decision | Choice | Why |
|---|---|---|
| Delivery semantics | At-least-once + idempotent runner | Exactly-once is not available from Redis; idempotency is testable |
| Run claim | Atomic compare-and-set + heartbeat lease | Safe with several workers; orphan recovery |
| SSRF | Resolve once, pin IP, re-validate redirects | Prevents DNS rebinding and redirect-to-internal |
| Perf regression | median + MAD + absolute floor, min 3 samples | Robust to outliers; avoids flagging jitter |
| Secrets | Fernet at rest, masked on read, redacted in results | Defence in depth |
| JSONPath | Own small subset | Avoids a dependency; behaviour fully specified and tested |
| Frontend charts | Custom SVG | No charting dependency for 4 simple charts |

## Honest limitations
- **Rate limiter is in-memory** per API process; with several API replicas limits are per replica. Use Redis-backed limiting for strict global limits.
- **Variables are not a vault.** They are encrypted at rest but readable by project members; do not store production secrets.
- **Redis redelivery latency.** After `kill -9` of a worker, recovery was observed ~100 s after the visibility timeout window (Kombu checks for restorable messages every 10th poll). Expect roughly `visibility_timeout + up to ~100 s` (default timeout 300 s, `TESTPILOT_BROKER_VISIBILITY_TIMEOUT_S`).
- Request bodies and responses are size-capped; very large payloads are truncated.
- Regression compares against one baseline run; it is not a trend model.
