
from __future__ import annotations
import json
import logging
import time
from typing import Any

import redis

logger = logging.getLogger(__name__)

FEED_TTL = 60 * 10  # 10 минут
BATCH_SIZE = 10


class FeedService:
    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        try:
            self.redis = redis.Redis.from_url(redis_url, decode_responses=True)
            self.redis.ping()
            self._available = True
            logger.info("Redis connected for feed cache")
        except redis.ConnectionError:
            self.redis = None
            self._available = False
            logger.warning("Redis not available, feed will work without cache")

    def _key(self, viewer_id: int) -> str:
        return f"feed:{viewer_id}"

    def _cursor_key(self, viewer_id: int) -> str:
        return f"feed_cursor:{viewer_id}"

    def get_or_prefetch(
        self,
        viewer_profile_id: int,
        fetch_fn,
    ) -> dict[str, Any]:
        """Получить следующую анкету.
        fetch_fn(profile_id, limit) -> list[dict] кандидатов.
        Возвращает {profile, from_cache, remaining}.
        """
        if not self._available:
            # Без Redis: берём напрямую из БД
            candidates = fetch_fn(viewer_profile_id, 10)
            return self._serve_from_list(candidates, viewer_profile_id)

        key = self._key(viewer_profile_id)
        cursor_key = self._cursor_key(viewer_profile_id)

        # Проверяем кэш
        cached = self.redis.get(key)
        if cached is None:
            # Кэш пуст — подгружаем пачку
            candidates = fetch_fn(viewer_profile_id, BATCH_SIZE)
            if not candidates:
                return {"profile": None, "from_cache": False, "remaining": 0}
            self.redis.setex(key, FEED_TTL, json.dumps(candidates))
            self.redis.set(cursor_key, 0, ex=FEED_TTL)
            logger.info("Feed cache populated for viewer %d (%d items)", viewer_profile_id, len(candidates))

        # Берём текущий элемент
        cursor = int(self.redis.get(cursor_key) or 0)
        cached_list = json.loads(self.redis.get(key))

        if cursor >= len(cached_list):
            # Пачка кончилась — обновляем
            candidates = fetch_fn(viewer_profile_id, BATCH_SIZE)
            if not candidates:
                return {"profile": None, "from_cache": False, "remaining": 0}
            self.redis.setex(key, FEED_TTL, json.dumps(candidates))
            self.redis.set(cursor_key, 0, ex=FEED_TTL)
            cached_list = candidates
            cursor = 0

        profile = cached_list[cursor]
        cursor += 1
        self.redis.set(cursor_key, cursor, ex=FEED_TTL)
        remaining = len(cached_list) - cursor

        return {
            "profile": profile,
            "from_cache": True,
            "remaining": remaining,
        }

    def _serve_from_list(self, candidates: list[dict], viewer_profile_id: int) -> dict[str, Any]:
        if not candidates:
            return {"profile": None, "from_cache": False, "remaining": 0}
        return {
            "profile": candidates[0],
            "from_cache": False,
            "remaining": len(candidates) - 1,
        }

    def invalidate(self, viewer_profile_id: int) -> None:
        if self._available:
            self.redis.delete(self._key(viewer_profile_id))
            self.redis.delete(self._cursor_key(viewer_profile_id))
