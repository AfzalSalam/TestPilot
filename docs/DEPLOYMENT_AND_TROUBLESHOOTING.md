# Deployment & Troubleshooting Guide

This document captures operational lessons learned, troubleshooting steps, and configuration nuances discovered when running TestPilot in a full Docker environment.

---

## 1. Celery / Kombu Redis Transport: `packaging` Dependency

### Symptom
When starting background workers (`worker`) or beat scheduler (`beat`), or when dispatching runs from the API (`api`), the process crashed or returned:
```
ModuleNotFoundError: No module named 'packaging'
```
UI error when clicking **Start Run**:
```
The job queue is unavailable; the run was not started (HTTP 503)
```

### Cause
In Python 3.12 with `celery>=5.4` and `redis>=5.0`, Kombu's Redis transport module (`kombu.transport.redis`) imports `from packaging.version import Version` at runtime. Without `packaging` explicitly specified in `backend/requirements.txt`, worker processes and API producer pools fail to establish connections to the Redis broker.

### Solution
`packaging>=23.0` was added to `backend/requirements.txt`. Both the API and worker containers now bundle this dependency during image build.

---

## 2. Fernet Encryption Key Format

### Symptom
When creating a project, importing OpenAPI specs, or running seed scripts, the API returned an HTTP 500 error:
```
sqlalchemy.exc.StatementError: (builtins.ValueError) Fernet key must be 32 url-safe base64-encoded bytes.
```

### Cause
Project variables and secrets are encrypted at rest using Fernet symmetric encryption (`app/db_types.py`). Fernet requires a 32-byte URL-safe base64-encoded key. Supplying arbitrary plaintext (e.g., `TESTPILOT_ENCRYPTION_KEY=my-secret-pass`) fails validation.

### Solution
`TESTPILOT_ENCRYPTION_KEY` in `.env` is **optional**:
- **Recommended (Default):** Leave it empty:
  ```env
  TESTPILOT_ENCRYPTION_KEY=
  ```
  TestPilot automatically derives a valid Fernet key from `TESTPILOT_SECRET_KEY` on startup (`app/config.py`).
- **Explicit Key Generation:** If a dedicated encryption key is desired, generate one using:
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```

---

## 3. PostgreSQL Docker Volume & Password Synchronization

### Symptom
On fresh runs or after updating passwords in `.env`:
```
psycopg2.OperationalError: connection to server at "postgres", port 5432 failed: FATAL: password authentication failed for user "testpilot"
```

### Cause
The official Postgres Docker container initializes the data directory (`/var/lib/postgresql/data`) and sets the database password **only once** when the volume is created. Changing `POSTGRES_PASSWORD` in `.env` afterwards changes what the API attempts to send, but does not alter the password inside the already-initialized `testpilot_pgdata` volume.

### Solution
Whenever the database password in `.env` is modified for local testing, the stale volume must be wiped:
```bash
docker compose down -v
docker compose up -d
```
*(Note: `-v` deletes local volume data. For production databases, update passwords via SQL `ALTER USER` instead).*

---

## 4. Nginx Upstream DNS Caching (502 Bad Gateway)

### Symptom
After recreating or restarting the backend API container (`testpilot-api-1`), visiting the frontend UI or logging in results in:
```
502 Bad Gateway
```
Nginx error log:
```
connect() failed (111: Connection refused) while connecting to upstream, upstream: "http://172.20.0.5:8000/..."
```

### Cause
The frontend container uses Nginx to proxy `/api/` traffic to `http://api:8000`. By default, Nginx resolves the upstream hostname (`api`) to an IP address at startup. When the `api` container is recreated, Docker assigns it a new IP address, leaving Nginx's proxy pointing to the old, unreachable IP.

### Solution
Restart the frontend container to force Nginx to re-resolve the upstream hostname:
```bash
docker restart testpilot-frontend-1
```
Or restart the entire compose project:
```bash
docker compose restart frontend
```

---

## 5. Test Run Concurrency Explained

When starting a test run in the UI, a **Concurrency** slider is presented (default: `5 parallel requests`, up to `20`):

```
Concurrency: 5 parallel requests
How many tests this run executes at the same time (server cap applies)
```

### How it Works
- TestPilot's Celery worker executes test suites using asynchronous HTTP requests (via `httpx.AsyncClient`).
- The concurrency setting configures the `asyncio.Semaphore` limit for that specific run.
- **Concurrency = 1:** Executes tests strictly sequentially (one after another). Useful for APIs with strict sequential dependencies or very aggressive rate limits.
- **Concurrency = 5 (Default):** Batches 5 simultaneous requests. Ideal balance between test execution speed and target server load.
- **Concurrency = 10–20:** High-throughput parallel execution. Finishes large test suites (50+ tests) quickly, but requires the target API to handle concurrent load without returning `429 Too Many Requests`.

---

## 6. Verification Checklist

To verify a fully functional environment:

1. **Containers Health:**
   ```bash
   docker compose ps
   ```
   All 7 containers (`api`, `worker`, `beat`, `frontend`, `postgres`, `redis`, `demo-api`) should be `Up` or `healthy`.

2. **Backend Health Check:**
   ```bash
   curl http://localhost:8000/api/v1/health
   # Expected: {"status":"ok", ... "checks":{"database":"ok","queue":"ok"}}
   ```

3. **Frontend Health Proxy:**
   ```bash
   curl http://localhost:8080/api/v1/health
   # Expected: 200 OK with identical JSON payload
   ```

4. **Seed Sample Data & Execute Runs:**
   ```bash
   python scripts/seed_demo.py --api http://localhost:8000 --target http://demo-api:9000
   ```
   All 5 sample runs should report `completed (8/8 passed)`.
