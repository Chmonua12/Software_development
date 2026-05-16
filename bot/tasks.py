from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

from bot.feed_cache import refresh_top_cache as refresh_top_cache_backend
from bot.rating import recompute_all, recompute_for_profile
from bot.storage import UserStorage

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("BOT_DB_PATH", "data/bot.sqlite3"))


def _store() -> UserStorage:
    return UserStorage(DB_PATH)


try:
    from celery import Celery
except ImportError:
    Celery = None  # type: ignore[assignment]


celery_app = None
if Celery is not None:
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    celery_app = Celery("artconnect", broker=redis_url, backend=redis_url)
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Europe/Moscow",
        enable_utc=True,
        beat_schedule={
            "recalculate-ratings-every-hour": {
                "task": "bot.tasks.recalculate_all_ratings_task",
                "schedule": 3600.0,
            },
            "warm-top-cache-every-5-minutes": {
                "task": "bot.tasks.refresh_top_cache_task",
                "schedule": 300.0,
            },
        },
    )


def recalculate_all_ratings() -> int:
    count = recompute_all(_store())
    logger.info("Recalculated ratings for %d profiles", count)
    return count


def process_interaction_async(event_data: dict) -> bool:
    store = _store()
    target_id = event_data.get("to")
    if not target_id:
        return False
    profile = store.get_profile_by_id(int(target_id))
    if profile is None:
        return False
    recompute_for_profile(store, profile)
    logger.info("Processed interaction event: %s", event_data)
    return True


def refresh_top_cache() -> int:
    store = _store()
    count = refresh_top_cache_backend(store, limit=10)
    logger.info("Top cache warm-up touched %d profiles", count)
    return count


if celery_app is not None:

    @celery_app.task(name="bot.tasks.recalculate_all_ratings_task")
    def recalculate_all_ratings_task() -> int:
        return recalculate_all_ratings()

    @celery_app.task(name="bot.tasks.process_interaction_task")
    def process_interaction_task(event_data: dict) -> bool:
        return process_interaction_async(event_data)

    @celery_app.task(name="bot.tasks.refresh_top_cache_task")
    def refresh_top_cache_task() -> int:
        return refresh_top_cache()


class BackgroundScheduler:
    """Local fallback for demos when Celery worker is not running."""

    def __init__(self, interval_seconds: int = 3600) -> None:
        self.interval_seconds = interval_seconds
        self.running = os.getenv("DISABLE_LOCAL_SCHEDULER", "").lower() not in {"1", "true", "yes"}
        self.thread: threading.Thread | None = None
        if self.running:
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def _run(self) -> None:
        while self.running:
            time.sleep(self.interval_seconds)
            try:
                recalculate_all_ratings()
                refresh_top_cache()
            except Exception as exc:
                logger.warning("Background scheduler failed: %s", exc)


background_scheduler = BackgroundScheduler()
