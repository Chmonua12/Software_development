from __future__ import annotations
import time
import logging
from functools import wraps
from prometheus_client import Counter, Histogram, Gauge, generate_latest
import json
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

like_counter = Counter("artconnect_likes_total", "Total likes", ["profile_id"])
skip_counter = Counter("artconnect_skips_total", "Total skips", ["profile_id"])
match_counter = Counter("artconnect_matches_total", "Total matches")
feed_request_duration = Histogram("artconnect_feed_duration_seconds", "Feed request duration")
cache_hits = Counter("artconnect_cache_hits_total", "Cache hits")
cache_misses = Counter("artconnect_cache_misses_total", "Cache misses")
active_users = Gauge("artconnect_active_users", "Active users")
rating_gauge = Gauge("artconnect_profile_rating", "Profile rating", ["profile_id", "display_name"])


def track_time(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start
            feed_request_duration.observe(duration)
            return result
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}")
            raise
    return wrapper


def log_interaction(event_type: str, from_pid: int, to_pid: int, extra: dict = None):
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "event": event_type,
        "from_profile": from_pid,
        "to_profile": to_pid,
        "extra": extra or {}
    }
    log_file = LOG_DIR / f"interactions_{datetime.now().strftime('%Y%m%d')}.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    
    if event_type == "like":
        like_counter.labels(profile_id=str(to_pid)).inc()
    elif event_type == "skip":
        skip_counter.labels(profile_id=str(to_pid)).inc()
    elif event_type == "match":
        match_counter.inc()


def update_rating_metric(profile_id: int, rating: float, display_name: str):
    rating_gauge.labels(profile_id=str(profile_id), display_name=display_name).set(rating)


def cache_metric(hit: bool):
    if hit:
        cache_hits.inc()
    else:
        cache_misses.inc()


def get_metrics():
    return generate_latest()