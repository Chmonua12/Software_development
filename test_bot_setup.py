#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


def ok(message: str) -> None:
    print(f"[OK] {message}")


def fail(message: str) -> None:
    print(f"[FAIL] {message}")


def test_imports() -> bool:
    required = [
        "aiogram",
        "redis",
        "celery",
        "minio",
        "prometheus_client",
    ]
    passed = True
    for module in required:
        try:
            __import__(module)
            ok(f"import {module}")
        except ImportError as exc:
            fail(f"import {module}: {exc}")
            passed = False
    return passed


def test_project_files() -> bool:
    required_files = [
        "bot/__init__.py",
        "bot/main.py",
        "bot/storage.py",
        "bot/feed.py",
        "bot/feed_cache.py",
        "bot/rating.py",
        "bot/tasks.py",
        "bot/minio_client.py",
        "bot/metrics.py",
        "run_bot.py",
        "requirements.txt",
        "docker-compose.yml",
        "README.md",
        "ARCHITECTURE.md",
        "docs/schema.dbml",
    ]
    passed = True
    for file_path in required_files:
        if Path(file_path).exists():
            ok(file_path)
        else:
            fail(f"{file_path} missing")
            passed = False
    return passed


def test_database() -> bool:
    try:
        from bot.storage import UserStorage

        db_path = Path("data/test_setup.sqlite3")
        if db_path.exists():
            db_path.unlink()
        store = UserStorage(db_path)
        user, created = store.register_or_update_user(
            telegram_id=10001,
            username="artist",
            first_name="Art",
            last_name="User",
        )
        profile = store.save_profile(user.id, "Artist", 21, "Moscow", "Digital art and illustration")
        store.add_interest(profile.id, "digital")
        store.add_social_link(profile.id, "telegram", "https://t.me/artist", is_primary=True)
        store.init_rating(profile.id)
        assert created is True
        assert store.get_profile_by_telegram_id(10001) is not None
        assert store.get_rating_row(profile.id) is not None
        ok("SQLite schema, profile, rating")
        return True
    except Exception as exc:
        fail(f"database smoke test: {exc}")
        return False


def test_rating_and_feed() -> bool:
    try:
        from bot.feed_cache import build_ranked_ids, invalidate
        from bot.rating import recompute_for_profile
        from bot.storage import UserStorage

        db_path = Path("data/test_feed.sqlite3")
        db_path.unlink(missing_ok=True)
        store = UserStorage(db_path)
        user1, _ = store.register_or_update_user(20001, "a1", "A", "One")
        user2, _ = store.register_or_update_user(20002, "a2", "A", "Two")
        p1 = store.save_profile(user1.id, "Viewer", 25, "Moscow", "Painter")
        p2 = store.save_profile(user2.id, "Target", 26, "Saint Petersburg", "Illustrator with portfolio")
        store.add_interest(p2.id, "illustration")
        store.add_social_link(p2.id, "telegram", "https://t.me/target", True)
        store.init_rating(p1.id)
        store.init_rating(p2.id)
        store.record_profile_view(p1.id, p2.id)
        store.add_interaction(p1.id, p2.id, "favorite")
        recompute_for_profile(store, p2)
        ids = build_ranked_ids(store, p1, include_seen=True)
        assert p2.id in ids
        invalidate(p1.id)
        ok("rating and feed ranking")
        return True
    except Exception as exc:
        fail(f"rating/feed smoke test: {exc}")
        return False


def test_environment() -> bool:
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        ok("TELEGRAM_BOT_TOKEN set")
    else:
        print("[WARN] TELEGRAM_BOT_TOKEN is not set; bot run requires it.")
    return True


def main() -> int:
    sys.path.insert(0, str(Path.cwd()))
    tests = [
        test_imports,
        test_project_files,
        test_database,
        test_rating_and_feed,
        test_environment,
    ]
    results = [test() for test in tests]
    passed = sum(1 for result in results if result)
    print(f"\nResult: {passed}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
