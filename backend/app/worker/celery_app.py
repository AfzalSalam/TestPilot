"""Celery application (the distributed worker side of TestPilot).

Run a worker:   celery -A app.worker.celery_app.celery_app worker -l info -c 4
Run the ticker: celery -A app.worker.celery_app.celery_app beat -l info
"""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery("testpilot", broker=settings.redis_url, backend=settings.redis_url, include=["app.worker.tasks"])

celery_app.conf.update(
    task_acks_late=True,  # ack only AFTER the task finishes -> crash => redelivery (at-least-once)
    task_reject_on_worker_lost=True,  # a killed worker's task goes back to the queue
    worker_prefetch_multiplier=1,  # long tasks: don't hoard messages
    task_track_started=True,
    task_time_limit=60 * 30,
    task_soft_time_limit=60 * 25,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": settings.broker_visibility_timeout_s},
    result_expires=3600,
    timezone="UTC",
    beat_schedule={
        "tick-schedules": {"task": "testpilot.tick_schedules", "schedule": 60.0},
    },
)
