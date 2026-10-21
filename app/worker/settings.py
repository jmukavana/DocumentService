"""ARQ worker settings."""

from arq.connections import RedisSettings

from app.core.config import settings


class WorkerSettings:
    functions: list[str] = [  # noqa: RUF012
        "app.worker.tasks.ocr_task",
        "app.worker.tasks.thumbnail_task",
    ]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    job_timeout = settings.MAX_OCR_PAGES * 120 + 60
    max_tries = 3
    keep_result = 3600
