from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Protocol

from bot.metrics import cache_metric
from bot.rating import recompute_for_profile
from bot.storage import Profile, UserStorage

logger = logging.getLogger(__name__)

PREFETCH_N = 10
REDIS_KEY = "feed_queue:{}"
MQ_KEY = "mq:interaction_events"
TOP_KEY = "top_profiles"


class SupportsRedis(Protocol):
    def lpush(self, name: str, *values: bytes | str) -> int: ...
    def rpop(self, name: str) -> str | None: ...
    def llen(self, name: str) -> int: ...
    def delete(self, *names: str) -> int: ...
    def expire(self, name: str, time: int) -> bool: ...


class InMemoryCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: dict[str, list[str]] = {}

    def lpush(self, name: str, *values: bytes | str) -> int:
        with self._lock:
            q = self._queues.setdefault(name, [])
            for v in reversed(values):
                s = v.decode() if isinstance(v, bytes) else str(v)
                q.insert(0, s)
            return len(q)

    def rpop(self, name: str) -> str | None:
        with self._lock:
            q = self._queues.get(name, [])
            if not q:
                return None
            return q.pop()

    def llen(self, name: str) -> int:
        with self._lock:
            return len(self._queues.get(name, []))

    def delete(self, *names: str) -> int:
        n = 0
        with self._lock:
            for name in names:
                if name in self._queues:
                    del self._queues[name]
                    n += 1
        return n

    def expire(self, name: str, time: int) -> bool:
        return name in self._queues


def _connect_redis() -> SupportsRedis | None:
    url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    if os.getenv("DISABLE_REDIS", "").lower() in ("1", "true", "yes"):
        return None
    try:
        import redis
    except ImportError:
        return None
    try:
        r = redis.from_url(url, decode_responses=True, socket_connect_timeout=2.0)
        r.ping()
        logger.info("Connected to Redis")
        return r
    except Exception as exc:
        logger.warning("Redis unavailable, using in-memory cache: %s", exc)
        return None


_CACHE: InMemoryCache | None = None
_REDIS: SupportsRedis | None = None


def _get_backend() -> tuple[SupportsRedis | InMemoryCache, str]:
    global _REDIS, _CACHE
    if _REDIS is None and _CACHE is None:
        _REDIS = _connect_redis()
        if _REDIS is None:
            _CACHE = InMemoryCache()
    if _REDIS is not None:
        return _REDIS, "redis"
    assert _CACHE is not None
    return _CACHE, "memory"


def _key_for(viewer_profile_id: int) -> str:
    return REDIS_KEY.format(viewer_profile_id)


def build_ranked_ids(store: UserStorage, viewer: Profile, include_seen: bool = False) -> list[int]:
    excluded = [] if include_seen else store.get_already_shown_to_ids(viewer.id)
    candidates = store.list_candidate_profiles(viewer, excluded, limit=500)
    scored: list[tuple[float, int]] = []

    for profile in candidates:
        scores = recompute_for_profile(store, profile)
        # Stable tiny boost imitates a time-window signal without hiding the main rating.
        activity_boost = (profile.id % 24) * 0.0005
        scored.append((scores.combined + activity_boost, profile.id))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [profile_id for _, profile_id in scored]


def refill_if_needed(store: UserStorage, viewer: Profile, min_len: int = 3) -> None:
    backend, backend_name = _get_backend()
    key = _key_for(viewer.id)
    current_len = backend.llen(key)
    if current_len >= min_len:
        cache_metric(True)
        return

    cache_metric(False)
    ids = build_ranked_ids(store, viewer)
    if not ids:
        return

    to_push = [str(pid) for pid in ids[:PREFETCH_N]]
    backend.delete(key)
    for sid in reversed(to_push):
        backend.lpush(key, sid)
    try:
        backend.expire(key, 60 * 15)
    except Exception:
        pass
    logger.info("Refilled %s feed cache for profile %s with %d ids", backend_name, viewer.id, len(to_push))


def pop_next_id(viewer_profile_id: int) -> int | None:
    backend, _ = _get_backend()
    raw = backend.rpop(_key_for(viewer_profile_id))
    if raw is None:
        return None
    return int(raw)


def invalidate(viewer_profile_id: int) -> None:
    backend, _ = _get_backend()
    backend.delete(_key_for(viewer_profile_id))


def publish_interaction_event(
    store: UserStorage,
    event_type: str,
    from_pid: int,
    to_pid: int,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = store.get_event_log_payload(event_type, from_pid, to_pid, extra)
    backend, backend_name = _get_backend()
    try:
        backend.lpush(MQ_KEY, payload)
        if backend_name == "redis":
            backend.expire(MQ_KEY, 60 * 60 * 24)
    except Exception as exc:
        logger.warning("Could not publish event to queue: %s", exc)
    store.record_event(event_type, from_pid, to_pid, extra)


def refresh_top_cache(store: UserStorage, limit: int = 10) -> int:
    backend, _ = _get_backend()
    rows = store.get_top_profiles(limit=limit)
    payload = [
        {
            "profile_id": profile.id,
            "display_name": profile.display_name,
            "city": profile.city,
            "combined_rating": rating.combined_rating,
            "likes_count": rating.likes_count,
        }
        for profile, rating in rows
    ]
    backend.delete(TOP_KEY)
    if payload:
        backend.lpush(TOP_KEY, json.dumps(payload, ensure_ascii=False))
        try:
            backend.expire(TOP_KEY, 300)
        except Exception:
            pass
    return len(payload)


def get_cached_top() -> list[dict[str, Any]] | None:
    backend, _ = _get_backend()
    raw = backend.rpop(TOP_KEY)
    if raw is None:
        return None
    backend.lpush(TOP_KEY, raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
