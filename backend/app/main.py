"""FastAPI application factory."""

import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.errors import register_error_handlers
from app.logging_config import configure_logging
from app.routers import analytics, api_keys, auth, ci, collections, endpoints, health, imports, projects, runs, schedules, testcases

logger = logging.getLogger("testpilot")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.validate_for_environment()
    configure_logging(settings.log_level)
    if settings.auto_create_tables:
        import app.models  # noqa: F401  (register tables)

        Base.metadata.create_all(engine)

    stop = threading.Event()
    ticker = None
    if settings.execution_mode != "celery":
        from app.services.runner import recover_interrupted_runs
        from app.services.scheduler import scheduler_loop

        with SessionLocal() as db:
            recovered = recover_interrupted_runs(db)
            if recovered:
                logger.warning("marked %d interrupted run(s) as failed after restart", recovered)
        if settings.scheduler_enabled and settings.execution_mode == "thread":
            ticker = threading.Thread(target=scheduler_loop, args=(stop,), daemon=True, name="scheduler")
            ticker.start()
    logger.info("TestPilot %s started (mode=%s)", __version__, settings.execution_mode)
    yield
    stop.set()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="TestPilot API",
        version=__version__,
        description="Distributed API testing & regression platform. Interactive docs: /docs",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,  # bearer tokens travel in a header, not cookies
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        response = await call_next(request)
        duration = round((time.perf_counter() - started) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        # path only (no query string) so tokens/keys in URLs never reach the logs
        logger.info(
            "request",
            extra={"request_id": request_id, "method": request.method, "path": request.url.path,
                   "status": response.status_code, "duration_ms": duration},
        )  # fmt: skip
        return response

    register_error_handlers(app)

    api = APIRouter(prefix="/api/v1")
    for module in (health, auth, projects, endpoints, collections, testcases, runs, schedules, api_keys, imports, analytics, ci):
        api.include_router(module.router)
    app.include_router(api)
    return app


app = create_app()
