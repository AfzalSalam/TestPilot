"""Environment-based configuration.

Every setting can be overridden with an environment variable prefixed with
``TESTPILOT_`` (for example ``TESTPILOT_DATABASE_URL``). Defaults are tuned for
local development; production refuses to start with the default secret key.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET = "dev-only-secret-change-me-before-deploying-0123456789"


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TESTPILOT_", extra="ignore")

    app_name: str = "TestPilot"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    # --- storage ---------------------------------------------------------
    database_url: str = "sqlite:///./testpilot.db"
    auto_create_tables: bool = True  # dev convenience; production uses Alembic

    # --- security --------------------------------------------------------
    secret_key: str = DEFAULT_SECRET
    encryption_key: str = ""  # Fernet key; derived from secret_key when empty
    supabase_url: str = ""       # e.g. https://xxxx.supabase.co
    supabase_anon_key: str = ""  # Supabase Dashboard -> Settings -> API -> anon public key
    supabase_jwt_secret: str = ""  # kept for legacy; no longer used for verification
    access_token_expire_minutes: int = 60 * 12
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- execution -------------------------------------------------------
    # celery : enqueue to Redis, executed by `celery worker` (production mode)
    # thread : run in a background thread inside the API process (no Redis needed)
    # inline : run synchronously inside the request (used by the test-suite)
    execution_mode: Literal["celery", "thread", "inline"] = "thread"
    redis_url: str = "redis://localhost:6379/0"
    default_concurrency: int = 5
    max_concurrency: int = 20
    max_tests_per_run: int = 500
    run_lease_seconds: int = 120  # a "running" run with an older heartbeat is considered orphaned
    # Redis broker only: how long an un-acked message stays invisible before being redelivered.
    # After a worker crash the run is retried once this elapses (duplicates are harmless: see runner.claim_run).
    broker_visibility_timeout_s: int = 300
    scheduler_enabled: bool = True  # thread mode only; in celery mode Celery beat ticks
    min_schedule_interval_minutes: int = 1  # protects the platform from "* * * * *" abuse if raised

    # --- outbound request safety (SSRF + resource limits) ----------------
    ssrf_allowed_hosts: str = ""  # comma separated hostnames exempt from the private-IP block
    default_timeout_s: float = 10.0
    max_timeout_s: float = 60.0
    max_redirects: int = 5
    max_response_bytes: int = 2_000_000
    response_preview_bytes: int = 4096

    # --- rate limiting (in-memory sliding window) -------------------------
    rate_limit_enabled: bool = True
    rate_limit_auth_per_minute: int = 10
    rate_limit_runs_per_minute: int = 20
    rate_limit_execute_per_minute: int = 60

    # --- regression detection --------------------------------------------
    regression_history_window: int = 5
    regression_min_samples: int = 3
    regression_slowdown_ratio: float = 1.5
    regression_min_delta_ms: float = 100.0

    @property
    def cors_origin_list(self) -> list[str]:
        return _split(self.cors_origins)

    @property
    def ssrf_allowed_host_set(self) -> set[str]:
        return {h.lower() for h in _split(self.ssrf_allowed_hosts)}

    def validate_for_environment(self) -> None:
        if self.environment == "production" and self.secret_key == DEFAULT_SECRET:
            raise RuntimeError("TESTPILOT_SECRET_KEY must be set to a unique value in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
