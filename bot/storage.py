from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class User:
    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    referral_code: str | None
    referred_by: int | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Profile:
    id: int
    user_id: int
    display_name: str
    age: int
    city: str
    bio: str | None
    profile_completeness_score: float
    photos_count: int
    created_at: str
    updated_at: str
    deleted_at: str | None = None


@dataclass(frozen=True)
class ProfileRating:
    id: int
    profile_id: int
    primary_rating: float
    behavior_rating: float
    combined_rating: float
    likes_count: int
    skips_count: int
    matches_count: int
    dialogs_count: int
    referral_score: float
    views_count: int
    link_clicks_count: int
    last_recalculated_at: str | None


@dataclass(frozen=True)
class Photo:
    id: int
    profile_id: int
    storage_key: str
    file_id: str | None
    is_avatar: bool
    order_index: int
    created_at: str
    url: str | None = None


@dataclass(frozen=True)
class SocialLink:
    id: int
    profile_id: int
    platform: str
    url: str
    is_primary: bool
    created_at: str


@dataclass(frozen=True)
class RatingInputs:
    has_avatar: bool
    photos_count: int
    interests_count: int
    social_links_count: int
    has_primary_telegram: bool
    likes_count: int
    skips_count: int
    matches_count: int
    views_count: int
    link_clicks_count: int
    referral_score: float


class UserStorage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL UNIQUE,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    referral_code TEXT UNIQUE,
                    referred_by INTEGER REFERENCES users(id),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    age INTEGER NOT NULL,
                    city TEXT NOT NULL,
                    bio TEXT,
                    profile_completeness_score REAL DEFAULT 0.0,
                    photos_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS profile_photos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    storage_key TEXT NOT NULL,
                    file_id TEXT,
                    url TEXT,
                    is_avatar INTEGER NOT NULL DEFAULT 0,
                    order_index INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS profile_social_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    platform TEXT NOT NULL,
                    url TEXT NOT NULL,
                    is_primary INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS profile_interests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    tag TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS profile_likes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_profile_id INTEGER NOT NULL,
                    to_profile_id INTEGER NOT NULL,
                    like_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(from_profile_id) REFERENCES profiles(id),
                    FOREIGN KEY(to_profile_id) REFERENCES profiles(id)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS profile_favorites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    favorite_profile_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(profile_id, favorite_profile_id),
                    FOREIGN KEY(profile_id) REFERENCES profiles(id),
                    FOREIGN KEY(favorite_profile_id) REFERENCES profiles(id)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile1_id INTEGER NOT NULL,
                    profile2_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    UNIQUE(profile1_id, profile2_id),
                    FOREIGN KEY(profile1_id) REFERENCES profiles(id),
                    FOREIGN KEY(profile2_id) REFERENCES profiles(id)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS link_clicks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    viewer_profile_id INTEGER NOT NULL,
                    social_link_id INTEGER,
                    platform TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id),
                    FOREIGN KEY(viewer_profile_id) REFERENCES profiles(id),
                    FOREIGN KEY(social_link_id) REFERENCES profile_social_links(id)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS profile_ratings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL UNIQUE,
                    primary_rating REAL DEFAULT 0.0,
                    behavior_rating REAL DEFAULT 0.0,
                    combined_rating REAL DEFAULT 0.0,
                    likes_count INTEGER DEFAULT 0,
                    skips_count INTEGER DEFAULT 0,
                    matches_count INTEGER DEFAULT 0,
                    dialogs_count INTEGER DEFAULT 0,
                    referral_score REAL DEFAULT 0.0,
                    views_count INTEGER DEFAULT 0,
                    link_clicks_count INTEGER DEFAULT 0,
                    last_recalculated_at TEXT,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inviter_profile_id INTEGER NOT NULL,
                    invited_user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'registered',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(inviter_profile_id) REFERENCES profiles(id),
                    FOREIGN KEY(invited_user_id) REFERENCES users(id)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS events_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    from_profile_id INTEGER,
                    to_profile_id INTEGER,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            self._migrate_existing_db(conn)
            self._create_indexes(conn)
            conn.commit()

    def _migrate_existing_db(self, conn: sqlite3.Connection) -> None:
        self._add_column_if_missing(conn, "profiles", "deleted_at", "TEXT")
        self._add_column_if_missing(conn, "profile_photos", "url", "TEXT")
        for name, definition in {
            "skips_count": "INTEGER DEFAULT 0",
            "matches_count": "INTEGER DEFAULT 0",
            "dialogs_count": "INTEGER DEFAULT 0",
            "referral_score": "REAL DEFAULT 0.0",
            "views_count": "INTEGER DEFAULT 0",
            "link_clicks_count": "INTEGER DEFAULT 0",
        }.items():
            self._add_column_if_missing(conn, "profile_ratings", name, definition)

    @staticmethod
    def _add_column_if_missing(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _create_indexes(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_profiles_visible ON profiles(deleted_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_profile_likes_from ON profile_likes(from_profile_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_profile_likes_to ON profile_likes(to_profile_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ratings_combined ON profile_ratings(combined_rating DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_link_clicks_profile ON link_clicks(profile_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type_created ON events_log(event_type, created_at)")

    def register_or_update_user(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        referral_code: str | None = None,
    ) -> tuple[User, bool]:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,),
            ).fetchone()
            if row is None:
                referral_code = referral_code or str(uuid.uuid4())[:8]
                cursor = conn.execute(
                    """INSERT INTO users (
                        telegram_id, username, first_name, last_name,
                        referral_code, referred_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)""",
                    (telegram_id, username, first_name, last_name, referral_code, now, now),
                )
                user_id = cursor.lastrowid
                created = True
            else:
                conn.execute(
                    """UPDATE users SET username = ?, first_name = ?,
                       last_name = ?, updated_at = ?
                       WHERE telegram_id = ?""",
                    (username, first_name, last_name, now, telegram_id),
                )
                user_id = row["id"]
                created = False
            conn.commit()
            current = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return (self._row_to_user(current), created)

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> User:
        return User(
            id=row["id"],
            telegram_id=row["telegram_id"],
            username=row["username"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            referral_code=row["referral_code"],
            referred_by=row["referred_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> Profile:
        return Profile(
            id=row["id"],
            user_id=row["user_id"],
            display_name=row["display_name"],
            age=row["age"],
            city=row["city"],
            bio=row["bio"],
            profile_completeness_score=row["profile_completeness_score"],
            photos_count=row["photos_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row["deleted_at"] if "deleted_at" in row.keys() else None,
        )

    def save_profile(
        self,
        user_id: int,
        display_name: str,
        age: int,
        city: str,
        bio: str | None = None,
    ) -> Profile:
        now = datetime.now(timezone.utc).isoformat()
        completeness = self._calc_completeness(display_name, age, city, bio)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM profiles WHERE user_id = ?", (user_id,),
            ).fetchone()
            if existing is None:
                cursor = conn.execute(
                    """INSERT INTO profiles (
                        user_id, display_name, age, city, bio,
                        profile_completeness_score, photos_count,
                        created_at, updated_at, deleted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, NULL)""",
                    (user_id, display_name, age, city, bio, completeness, now, now),
                )
                profile_id = cursor.lastrowid
            else:
                profile_id = existing["id"]
                conn.execute(
                    """UPDATE profiles SET display_name = ?, age = ?,
                       city = ?, bio = ?, profile_completeness_score = ?,
                       updated_at = ?, deleted_at = NULL
                       WHERE id = ?""",
                    (display_name, age, city, bio, completeness, now, profile_id),
                )
            conn.commit()
        profile = self.get_profile_by_id(profile_id)
        assert profile is not None
        return profile

    def update_profile_fields(
        self,
        profile_id: int,
        display_name: str | None = None,
        age: int | None = None,
        city: str | None = None,
        bio: str | None = None,
    ) -> Profile | None:
        profile = self.get_profile_by_id(profile_id)
        if profile is None:
            return None
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """UPDATE profiles SET
                    display_name = COALESCE(?, display_name),
                    age = COALESCE(?, age),
                    city = COALESCE(?, city),
                    bio = COALESCE(?, bio),
                    updated_at = ?
                   WHERE id = ?""",
                (display_name, age, city, bio, now, profile_id),
            )
            conn.execute(
                "UPDATE profiles SET profile_completeness_score = ? WHERE id = ?",
                (self._calc_completeness_by_profile(profile_id), profile_id),
            )
            conn.commit()
        return self.get_profile_by_id(profile_id)

    def soft_delete_profile(self, profile_id: int) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE profiles SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                (now, now, profile_id),
            )
            conn.commit()
        return cur.rowcount > 0

    def add_photo(
        self,
        profile_id: int,
        storage_key: str,
        file_id: str | None = None,
        is_avatar: bool = False,
        url: str | None = None,
    ) -> Photo:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            if is_avatar:
                conn.execute(
                    "UPDATE profile_photos SET is_avatar = 0 WHERE profile_id = ?",
                    (profile_id,),
                )
            order = conn.execute(
                "SELECT COALESCE(MAX(order_index), -1) + 1 FROM profile_photos WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()[0]
            cursor = conn.execute(
                """INSERT INTO profile_photos
                   (profile_id, storage_key, file_id, url, is_avatar, order_index, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (profile_id, storage_key, file_id, url, int(is_avatar), order, now),
            )
            if not is_avatar:
                conn.execute(
                    "UPDATE profiles SET photos_count = photos_count + 1 WHERE id = ?",
                    (profile_id,),
                )
            conn.execute(
                "UPDATE profiles SET profile_completeness_score = ? WHERE id = ?",
                (self._calc_completeness_by_profile(profile_id), profile_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM profile_photos WHERE id = ?", (cursor.lastrowid,),
            ).fetchone()
        return self._row_to_photo(row)

    @staticmethod
    def _row_to_photo(row: sqlite3.Row) -> Photo:
        return Photo(
            id=row["id"],
            profile_id=row["profile_id"],
            storage_key=row["storage_key"],
            file_id=row["file_id"],
            url=row["url"] if "url" in row.keys() else None,
            is_avatar=bool(row["is_avatar"]),
            order_index=row["order_index"],
            created_at=row["created_at"],
        )

    def add_social_link(
        self,
        profile_id: int,
        platform: str,
        url: str,
        is_primary: bool = False,
    ) -> SocialLink:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            if is_primary:
                conn.execute(
                    "UPDATE profile_social_links SET is_primary = 0 WHERE profile_id = ?",
                    (profile_id,),
                )
            cursor = conn.execute(
                """INSERT INTO profile_social_links (profile_id, platform, url, is_primary, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (profile_id, platform, url, int(is_primary), now),
            )
            conn.execute(
                "UPDATE profiles SET profile_completeness_score = ? WHERE id = ?",
                (self._calc_completeness_by_profile(profile_id), profile_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM profile_social_links WHERE id = ?", (cursor.lastrowid,),
            ).fetchone()
        return self._row_to_social(row)

    @staticmethod
    def _row_to_social(row: sqlite3.Row) -> SocialLink:
        return SocialLink(
            id=row["id"],
            profile_id=row["profile_id"],
            platform=row["platform"],
            url=row["url"],
            is_primary=bool(row["is_primary"]),
            created_at=row["created_at"],
        )

    def add_interest(self, profile_id: int, tag: str) -> None:
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT id FROM profile_interests WHERE profile_id = ? AND lower(tag) = lower(?)",
                (profile_id, tag),
            ).fetchone()
            if exists is None:
                conn.execute(
                    "INSERT INTO profile_interests (profile_id, tag) VALUES (?, ?)",
                    (profile_id, tag),
                )
            conn.execute(
                "UPDATE profiles SET profile_completeness_score = ? WHERE id = ?",
                (self._calc_completeness_by_profile(profile_id), profile_id),
            )
            conn.commit()

    def replace_interests(self, profile_id: int, tags: list[str]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM profile_interests WHERE profile_id = ?", (profile_id,))
            for tag in tags:
                conn.execute(
                    "INSERT INTO profile_interests (profile_id, tag) VALUES (?, ?)",
                    (profile_id, tag),
                )
            conn.execute(
                "UPDATE profiles SET profile_completeness_score = ? WHERE id = ?",
                (self._calc_completeness_by_profile(profile_id), profile_id),
            )
            conn.commit()

    def get_profile_by_telegram_id(self, telegram_id: int) -> Profile | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT p.* FROM profiles p
                   JOIN users u ON u.id = p.user_id
                   WHERE u.telegram_id = ? AND p.deleted_at IS NULL""",
                (telegram_id,),
            ).fetchone()
        return self._row_to_profile(row) if row else None

    def get_profile_by_id(self, profile_id: int) -> Profile | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM profiles WHERE id = ? AND deleted_at IS NULL",
                (profile_id,),
            ).fetchone()
        return self._row_to_profile(row) if row else None

    def get_user_by_profile_id(self, profile_id: int) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT u.* FROM users u
                   JOIN profiles p ON p.user_id = u.id
                   WHERE p.id = ?""",
                (profile_id,),
            ).fetchone()
        return self._row_to_user(row) if row else None

    def get_photos_by_profile_id(self, profile_id: int) -> list[Photo]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM profile_photos WHERE profile_id = ? ORDER BY is_avatar DESC, order_index",
                (profile_id,),
            ).fetchall()
        return [self._row_to_photo(r) for r in rows]

    def get_social_links_by_profile_id(self, profile_id: int) -> list[SocialLink]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM profile_social_links WHERE profile_id = ? ORDER BY is_primary DESC, created_at",
                (profile_id,),
            ).fetchall()
        return [self._row_to_social(r) for r in rows]

    def get_social_link(self, social_link_id: int) -> SocialLink | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM profile_social_links WHERE id = ?",
                (social_link_id,),
            ).fetchone()
        return self._row_to_social(row) if row else None

    def get_interests_by_profile_id(self, profile_id: int) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT tag FROM profile_interests WHERE profile_id = ? ORDER BY tag",
                (profile_id,),
            ).fetchall()
        return [r["tag"] for r in rows]

    @staticmethod
    def _calc_completeness(
        display_name: str,
        age: int,
        city: str,
        bio: str | None,
    ) -> float:
        score = 0.0
        if display_name and len(display_name.strip()) >= 2:
            score += 0.20
        if 18 <= age <= 99:
            score += 0.20
        if city and len(city.strip()) >= 2:
            score += 0.20
        if bio and len(bio.strip()) >= 20:
            score += 0.20
        elif bio and len(bio.strip()) >= 8:
            score += 0.10
        return round(score, 2)

    def _calc_completeness_by_profile(self, profile_id: int) -> float:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT display_name, age, city, bio FROM profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
            if row is None:
                return 0.0
            base = self._calc_completeness(
                row["display_name"], row["age"], row["city"], row["bio"],
            )
            has_avatar = conn.execute(
                "SELECT 1 FROM profile_photos WHERE profile_id = ? AND is_avatar = 1 LIMIT 1",
                (profile_id,),
            ).fetchone() is not None
            works = conn.execute(
                "SELECT COUNT(*) AS c FROM profile_photos WHERE profile_id = ? AND is_avatar = 0",
                (profile_id,),
            ).fetchone()["c"]
            interests = conn.execute(
                "SELECT COUNT(*) AS c FROM profile_interests WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()["c"]
            socials = conn.execute(
                "SELECT COUNT(*) AS c FROM profile_social_links WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()["c"]
        base += 0.10 if has_avatar else 0.0
        base += min(works * 0.04, 0.16)
        base += min(interests * 0.03, 0.12)
        base += 0.12 if socials else 0.0
        return round(min(base, 1.0), 2)

    def init_rating(self, profile_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        primary = self._calc_completeness_by_profile(profile_id)
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO profile_ratings
                   (profile_id, primary_rating, behavior_rating, combined_rating,
                    likes_count, skips_count, matches_count, dialogs_count,
                    referral_score, views_count, link_clicks_count, last_recalculated_at)
                   VALUES (?, ?, 0.5, ?, 0, 0, 0, 0, 0.0, 0, 0, ?)
                   ON CONFLICT(profile_id) DO UPDATE SET
                    primary_rating = excluded.primary_rating,
                    combined_rating = excluded.combined_rating,
                    last_recalculated_at = excluded.last_recalculated_at""",
                (profile_id, primary, min(primary * 0.4 + 0.5 * 0.6, 1.0), now),
            )
            conn.commit()

    def get_rating_row(self, profile_id: int) -> ProfileRating | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM profile_ratings WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
        if row is None:
            return None
        return ProfileRating(
            id=row["id"],
            profile_id=row["profile_id"],
            primary_rating=row["primary_rating"],
            behavior_rating=row["behavior_rating"],
            combined_rating=row["combined_rating"],
            likes_count=row["likes_count"],
            skips_count=row["skips_count"],
            matches_count=row["matches_count"],
            dialogs_count=row["dialogs_count"],
            referral_score=row["referral_score"],
            views_count=row["views_count"],
            link_clicks_count=row["link_clicks_count"],
            last_recalculated_at=row["last_recalculated_at"],
        )

    def upsert_rating(
        self,
        profile_id: int,
        primary: float,
        behavior: float,
        combined: float,
        likes: int,
        skips: int,
        matches: int,
        views: int = 0,
        link_clicks: int = 0,
        referral_score: float = 0.0,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO profile_ratings (
                    profile_id, primary_rating, behavior_rating, combined_rating,
                    likes_count, skips_count, matches_count, views_count,
                    link_clicks_count, referral_score, last_recalculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                    primary_rating = excluded.primary_rating,
                    behavior_rating = excluded.behavior_rating,
                    combined_rating = excluded.combined_rating,
                    likes_count = excluded.likes_count,
                    skips_count = excluded.skips_count,
                    matches_count = excluded.matches_count,
                    views_count = excluded.views_count,
                    link_clicks_count = excluded.link_clicks_count,
                    referral_score = MAX(profile_ratings.referral_score, excluded.referral_score),
                    last_recalculated_at = excluded.last_recalculated_at""",
                (
                    profile_id, primary, behavior, combined, likes, skips, matches,
                    views, link_clicks, referral_score, now,
                ),
            )
            conn.commit()

    def get_rating_inputs(self, profile_id: int) -> RatingInputs:
        with self._connect() as conn:
            likes = conn.execute(
                """SELECT COUNT(*) FROM profile_likes
                   WHERE to_profile_id = ? AND like_type IN ('communication', 'favorite', 'like')""",
                (profile_id,),
            ).fetchone()[0]
            skips = conn.execute(
                "SELECT COUNT(*) FROM profile_likes WHERE to_profile_id = ? AND like_type = 'skip'",
                (profile_id,),
            ).fetchone()[0]
            matches = conn.execute(
                """SELECT COUNT(*) FROM matches
                   WHERE (profile1_id = ? OR profile2_id = ?) AND status = 'active'""",
                (profile_id, profile_id),
            ).fetchone()[0]
            views = conn.execute(
                "SELECT COALESCE(views_count, 0) FROM profile_ratings WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
            clicks = conn.execute(
                "SELECT COUNT(*) FROM link_clicks WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()[0]
            referral = conn.execute(
                "SELECT COALESCE(referral_score, 0.0) FROM profile_ratings WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
            has_avatar = conn.execute(
                "SELECT 1 FROM profile_photos WHERE profile_id = ? AND is_avatar = 1 LIMIT 1",
                (profile_id,),
            ).fetchone() is not None
            photos = conn.execute(
                "SELECT COUNT(*) FROM profile_photos WHERE profile_id = ? AND is_avatar = 0",
                (profile_id,),
            ).fetchone()[0]
            interests = conn.execute(
                "SELECT COUNT(*) FROM profile_interests WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()[0]
            socials = conn.execute(
                "SELECT COUNT(*) FROM profile_social_links WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()[0]
            telegram = conn.execute(
                """SELECT 1 FROM profile_social_links
                   WHERE profile_id = ? AND platform = 'telegram' AND is_primary = 1 LIMIT 1""",
                (profile_id,),
            ).fetchone() is not None
        return RatingInputs(
            has_avatar=has_avatar,
            photos_count=photos,
            interests_count=interests,
            social_links_count=socials,
            has_primary_telegram=telegram,
            likes_count=likes,
            skips_count=skips,
            matches_count=matches,
            views_count=int(views[0]) if views else 0,
            link_clicks_count=clicks,
            referral_score=float(referral[0]) if referral else 0.0,
        )

    def recompute_aggregates_from_db(self, profile_id: int) -> tuple[int, int, int]:
        inputs = self.get_rating_inputs(profile_id)
        return inputs.likes_count, inputs.skips_count, inputs.matches_count

    def record_profile_view(self, viewer_profile_id: int, target_profile_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO profile_ratings (profile_id, views_count, last_recalculated_at)
                   VALUES (?, 1, ?)
                   ON CONFLICT(profile_id) DO UPDATE SET
                    views_count = COALESCE(views_count, 0) + 1,
                    last_recalculated_at = excluded.last_recalculated_at""",
                (target_profile_id, now),
            )
            conn.commit()
        self.record_event("profile_viewed", viewer_profile_id, target_profile_id)

    def add_interaction(
        self,
        from_profile_id: int,
        to_profile_id: int,
        like_type: str,
    ) -> tuple[bool, bool, int | None]:
        if like_type not in {"communication", "favorite", "skip", "like"}:
            raise ValueError(f"Unsupported interaction type: {like_type}")
        now = datetime.now(timezone.utc).isoformat()
        mutual = False
        match_id: int | None = None
        with self._connect() as conn:
            existing = conn.execute(
                """SELECT id FROM profile_likes
                   WHERE from_profile_id = ? AND to_profile_id = ?""",
                (from_profile_id, to_profile_id),
            ).fetchone()
            if existing is not None:
                return False, False, None
            conn.execute(
                """INSERT INTO profile_likes (from_profile_id, to_profile_id, like_type, created_at)
                   VALUES (?, ?, ?, ?)""",
                (from_profile_id, to_profile_id, like_type, now),
            )
            if like_type == "favorite":
                conn.execute(
                    """INSERT OR IGNORE INTO profile_favorites
                       (profile_id, favorite_profile_id, created_at)
                       VALUES (?, ?, ?)""",
                    (from_profile_id, to_profile_id, now),
                )
            if like_type in {"communication", "like"}:
                previous = conn.execute(
                    """SELECT id FROM profile_likes
                       WHERE from_profile_id = ? AND to_profile_id = ?
                       AND like_type IN ('communication', 'like')""",
                    (to_profile_id, from_profile_id),
                ).fetchone()
                mutual = previous is not None
                if mutual:
                    low, high = sorted((from_profile_id, to_profile_id))
                    cursor = conn.execute(
                        """INSERT OR IGNORE INTO matches (profile1_id, profile2_id, created_at, status)
                           VALUES (?, ?, ?, 'active')""",
                        (low, high, now),
                    )
                    if cursor.lastrowid:
                        match_id = cursor.lastrowid
                    else:
                        row = conn.execute(
                            "SELECT id FROM matches WHERE profile1_id = ? AND profile2_id = ?",
                            (low, high),
                        ).fetchone()
                        match_id = int(row["id"]) if row else None
            conn.commit()
        self.record_event(f"profile_{like_type}", from_profile_id, to_profile_id)
        return True, mutual, match_id

    def record_social_click(
        self,
        viewer_profile_id: int,
        social_link_id: int,
    ) -> SocialLink | None:
        link = self.get_social_link(social_link_id)
        if link is None:
            return None
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO link_clicks
                   (profile_id, viewer_profile_id, social_link_id, platform, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (link.profile_id, viewer_profile_id, link.id, link.platform, now),
            )
            conn.execute(
                """INSERT INTO profile_ratings (profile_id, link_clicks_count, last_recalculated_at)
                   VALUES (?, 1, ?)
                   ON CONFLICT(profile_id) DO UPDATE SET
                    link_clicks_count = COALESCE(link_clicks_count, 0) + 1,
                    last_recalculated_at = excluded.last_recalculated_at""",
                (link.profile_id, now),
            )
            conn.commit()
        self.record_event("social_link_clicked", viewer_profile_id, link.profile_id, {"platform": link.platform})
        return link

    def get_already_shown_to_ids(self, profile_id: int) -> list[int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT to_profile_id FROM profile_likes WHERE from_profile_id = ?",
                (profile_id,),
            ).fetchall()
        return [r["to_profile_id"] for r in rows]

    def list_candidate_profiles(
        self,
        viewer: Profile,
        exclude_ids: list[int],
        limit: int = 500,
    ) -> list[Profile]:
        with self._connect() as conn:
            params: list[Any] = [viewer.id]
            exclude_sql = ""
            if exclude_ids:
                placeholders = ",".join("?" * len(exclude_ids))
                exclude_sql = f"AND p.id NOT IN ({placeholders})"
                params.extend(exclude_ids)
            params.append(limit)
            rows = conn.execute(
                f"""SELECT p.* FROM profiles p
                    WHERE p.id != ? AND p.deleted_at IS NULL
                    {exclude_sql}
                    ORDER BY p.id ASC
                    LIMIT ?""",
                params,
            ).fetchall()
        return [self._row_to_profile(r) for r in rows]

    def list_all_active_profiles(self) -> list[Profile]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM profiles WHERE deleted_at IS NULL ORDER BY id",
            ).fetchall()
        return [self._row_to_profile(r) for r in rows]

    def get_top_profiles(self, limit: int = 10) -> list[tuple[Profile, ProfileRating]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT p.*, r.id AS rating_id, r.primary_rating, r.behavior_rating,
                          r.combined_rating, r.likes_count, r.skips_count,
                          r.matches_count, r.dialogs_count, r.referral_score,
                          r.views_count, r.link_clicks_count, r.last_recalculated_at
                   FROM profiles p
                   JOIN profile_ratings r ON r.profile_id = p.id
                   WHERE p.deleted_at IS NULL
                   ORDER BY r.combined_rating DESC, r.likes_count DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        result: list[tuple[Profile, ProfileRating]] = []
        for row in rows:
            profile = self._row_to_profile(row)
            rating = ProfileRating(
                id=row["rating_id"],
                profile_id=row["id"],
                primary_rating=row["primary_rating"],
                behavior_rating=row["behavior_rating"],
                combined_rating=row["combined_rating"],
                likes_count=row["likes_count"],
                skips_count=row["skips_count"],
                matches_count=row["matches_count"],
                dialogs_count=row["dialogs_count"],
                referral_score=row["referral_score"],
                views_count=row["views_count"],
                link_clicks_count=row["link_clicks_count"],
                last_recalculated_at=row["last_recalculated_at"],
            )
            result.append((profile, rating))
        return result

    def record_referral(self, inviter_profile_id: int, invited_user_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT id FROM referrals WHERE inviter_profile_id = ? AND invited_user_id = ?",
                (inviter_profile_id, invited_user_id),
            ).fetchone()
            if exists is None:
                conn.execute(
                    """INSERT INTO referrals (inviter_profile_id, invited_user_id, status, created_at)
                       VALUES (?, ?, 'registered', ?)""",
                    (inviter_profile_id, invited_user_id, now),
                )
                conn.execute(
                    """INSERT INTO profile_ratings (profile_id, referral_score, last_recalculated_at)
                       VALUES (?, 0.05, ?)
                       ON CONFLICT(profile_id) DO UPDATE SET
                        referral_score = MIN(0.2, COALESCE(referral_score, 0.0) + 0.05),
                        last_recalculated_at = excluded.last_recalculated_at""",
                    (inviter_profile_id, now),
                )
            conn.commit()
        self.record_event("referral_registered", inviter_profile_id, None, {"invited_user_id": invited_user_id})

    def get_event_log_payload(
        self,
        event_type: str,
        from_pid: int | None,
        to_pid: int | None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "event": event_type,
            "from": from_pid,
            "to": to_pid,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "extra": extra or {},
        }
        return json.dumps(payload, ensure_ascii=False)

    def record_event(
        self,
        event_type: str,
        from_pid: int | None,
        to_pid: int | None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = self.get_event_log_payload(event_type, from_pid, to_pid, extra)
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO events_log
                   (event_type, from_profile_id, to_profile_id, payload, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (event_type, from_pid, to_pid, payload, now),
            )
            conn.commit()
