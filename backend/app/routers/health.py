from fastapi import APIRouter
from sqlalchemy import text

from app import __version__
from app.config import get_settings
from app.database import engine

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Liveness + dependency check (database, queue)")
def health():
    settings = get_settings()
    checks: dict[str, str] = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"

    if settings.execution_mode == "celery":
        try:
            import redis

            redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1).ping()
            checks["queue"] = "ok"
        except Exception:
            checks["queue"] = "unavailable"
    else:
        checks["queue"] = "not_used"

    healthy = all(v in ("ok", "not_used") for v in checks.values())
    return {
        "status": "ok" if healthy else "degraded",
        "version": __version__,
        "execution_mode": settings.execution_mode,
        "environment": settings.environment,
        "checks": checks,
        "limits": {
            "max_concurrency": settings.max_concurrency,
            "default_concurrency": settings.default_concurrency,
            "max_timeout_s": settings.max_timeout_s,
            "max_response_bytes": settings.max_response_bytes,
            "max_tests_per_run": settings.max_tests_per_run,
        },
    }
