from __future__ import annotations
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


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


@dataclass(frozen=True)
class Photo:
    id: int
    profile_id: int
    storage_key: str
    file_id: str | None
    is_avatar: bool
    order_index: int
    created_at: str


@dataclass(frozen=True)
class SocialLink:
    id: int
    profile_id: int
    platform: str
    url: str
    is_primary: bool
    created_at: str


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
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS profile_photos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    storage_key TEXT NOT NULL,
                    file_id TEXT,
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
                """CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile1_id INTEGER NOT NULL,
                    profile2_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    FOREIGN KEY(profile1_id) REFERENCES profiles(id),
                    FOREIGN KEY(profile2_id) REFERENCES profiles(id)
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
            conn.commit()

    def register_or_update_user(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        referral_code: str | None = None,
    ) -> tuple[User, bool]:
        import uuid
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,),
            ).fetchone()
            if row is None:
                if referral_code is None:
                    referral_code = str(uuid.uuid4())[:8]
                cursor = conn.execute(
                    """INSERT INTO users (
                        telegram_id, username, first_name, last_name,
                        referral_code, referred_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)""",
                    (telegram_id, username, first_name, last_name,
                     referral_code, now, now),
                )
                conn.commit()
                user_id = cursor.lastrowid
                created = True
            else:
                conn.execute(
                    """UPDATE users SET username = ?, first_name = ?,
                       last_name = ?, updated_at = ?
                       WHERE telegram_id = ?""",
                    (username, first_name, last_name, now, telegram_id),
                )
                conn.commit()
                user_id = row["id"]
                created = False
            current = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,),
            ).fetchone()
            return (
                User(
                    id=current["id"],
                    telegram_id=current["telegram_id"],
                    username=current["username"],
                    first_name=current["first_name"],
                    last_name=current["last_name"],
                    referral_code=current["referral_code"],
                    referred_by=current["referred_by"],
                    created_at=current["created_at"],
                    updated_at=current["updated_at"],
                ),
                created,
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
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                    (user_id, display_name, age, city, bio,
                     completeness, now, now),
                )
                profile_id = cursor.lastrowid
            else:
                profile_id = existing["id"]
                conn.execute(
                    """UPDATE profiles SET display_name = ?, age = ?,
                       city = ?, bio = ?,
                       profile_completeness_score = ?, updated_at = ?
                       WHERE id = ?""",
                    (display_name, age, city, bio, completeness, now, profile_id),
                )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM profiles WHERE id = ?", (profile_id,),
            ).fetchone()
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
            )

    def add_photo(
        self,
        profile_id: int,
        storage_key: str,
        file_id: str | None = None,
        is_avatar: bool = False,
    ) -> Photo:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            order = conn.execute(
                "SELECT COALESCE(MAX(order_index), -1) + 1 FROM profile_photos WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()[0]
            conn.execute(
                """INSERT INTO profile_photos (profile_id, storage_key, file_id, is_avatar, order_index, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (profile_id, storage_key, file_id, int(is_avatar), order, now),
            )
            if not is_avatar:
                conn.execute(
                    "UPDATE profiles SET photos_count = photos_count + 1, profile_completeness_score = ? WHERE id = ?",
                    (self._calc_completeness_by_profile(profile_id), profile_id),
                )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM profile_photos WHERE id = (SELECT last_insert_rowid())",
            ).fetchone()
            return Photo(
                id=row["id"],
                profile_id=row["profile_id"],
                storage_key=row["storage_key"],
                file_id=row["file_id"],
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
            conn.commit()
            row = conn.execute(
                "SELECT * FROM profile_social_links WHERE id = ?", (cursor.lastrowid,),
            ).fetchone()
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
                   WHERE u.telegram_id = ?""",
                (telegram_id,),
            ).fetchone()
            if row is None:
                return None
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
            )

    def get_photos_by_profile_id(self, profile_id: int) -> list[Photo]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM profile_photos WHERE profile_id = ? ORDER BY order_index",
                (profile_id,),
            ).fetchall()
            return [
                Photo(
                    id=r["id"], profile_id=r["profile_id"],
                    storage_key=r["storage_key"], file_id=r["file_id"],
                    is_avatar=bool(r["is_avatar"]),
                    order_index=r["order_index"], created_at=r["created_at"],
                )
                for r in rows
            ]

    def get_social_links_by_profile_id(self, profile_id: int) -> list[SocialLink]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM profile_social_links WHERE profile_id = ? ORDER BY is_primary DESC, created_at",
                (profile_id,),
            ).fetchall()
            return [
                SocialLink(
                    id=r["id"], profile_id=r["profile_id"],
                    platform=r["platform"], url=r["url"],
                    is_primary=bool(r["is_primary"]), created_at=r["created_at"],
                )
                for r in rows
            ]

    @staticmethod
    def _calc_completeness(
        display_name: str, age: int, city: str, bio: str | None
    ) -> float:
        score = 0.0
        if display_name and len(display_name) >= 2:
            score += 0.25
        if 18 <= age <= 99:
            score += 0.25
        if city and len(city) >= 2:
            score += 0.25
        if bio and len(bio) >= 10:
            score += 0.25
        return round(score, 2)

    def _calc_completeness_by_profile(self, profile_id: int) -> float:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT display_name, age, city, bio FROM profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
            if row is None:
                return 0.0
            base = self._calc_completeness(row["display_name"], row["age"], row["city"], row["bio"])
            photos = conn.execute(
                "SELECT COUNT(*) as c FROM profile_photos WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()["c"]
            base += min(photos * 0.05, 0.25)
            interests = conn.execute(
                "SELECT COUNT(*) as c FROM profile_interests WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()["c"]
            base += min(interests * 0.03, 0.15)
            return round(min(base, 1.0), 2)

    def get_interests_by_profile_id(self, profile_id: int) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT tag FROM profile_interests WHERE profile_id = ?",
                (profile_id,),
            ).fetchall()
            return [r["tag"] for r in rows]

    # ── Rating methods ──────────────────────────────────────────
    def init_rating(self, profile_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        primary = self._calc_completeness_by_profile(profile_id)
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO profile_ratings
                   (profile_id, primary_rating, behavior_rating, combined_rating,
                    likes_count, skips_count, matches_count, dialogs_count,
                    referral_score, last_recalculated_at)
                   VALUES (?, ?, 0.0, ?, 0, 0, 0, 0, 0.0, ?)""",
                (profile_id, primary, primary, now),
            )
            conn.commit()

    def get_rating(self, profile_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM profile_ratings WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    def increment_likes(self, profile_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE profile_ratings SET likes_count = likes_count + 1, "
                "behavior_rating = MIN(1.0, behavior_rating + 0.02), "
                "last_recalculated_at = ? WHERE profile_id = ?",
                (datetime.now(timezone.utc).isoformat(), profile_id),
            )
            conn.commit()

    def increment_skip(self, profile_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE profile_ratings SET skips_count = skips_count + 1, "
                "behavior_rating = MAX(0.0, behavior_rating - 0.01), "
                "last_recalculated_at = ? WHERE profile_id = ?",
                (datetime.now(timezone.utc).isoformat(), profile_id),
            )
            conn.commit()

    def increment_match(self, profile_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE profile_ratings SET matches_count = matches_count + 1, "
                "behavior_rating = MIN(1.0, behavior_rating + 0.05), "
                "last_recalculated_at = ? WHERE profile_id = ?",
                (datetime.now(timezone.utc).isoformat(), profile_id),
            )
            conn.commit()

    def recalculate_combined(self) -> int:
        """Recalculate combined_rating for all profiles. Returns count."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM profile_ratings").fetchall()
            updated = 0
            for row in rows:
                primary = row["primary_rating"]
                behavior = row["behavior_rating"]
                referral = row["referral_score"]
                combined = round(0.4 * primary + 0.6 * behavior + referral, 4)
                conn.execute(
                    "UPDATE profile_ratings SET combined_rating = ?, "
                    "last_recalculated_at = ? WHERE profile_id = ?",
                    (combined, now, row["profile_id"]),
                )
                updated += 1
            conn.commit()
            return updated

    def get_top_profiles(self, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT p.*, r.combined_rating
                   FROM profiles p
                   JOIN profile_ratings r ON r.profile_id = p.id
                   ORDER BY r.combined_rating DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_feed_candidates(self, viewer_profile_id: int, limit: int = 10) -> list[dict]:
        """Get ranked profiles excluding viewer and already-liked/skipped."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT p.*, r.combined_rating
                   FROM profiles p
                   JOIN profile_ratings r ON r.profile_id = p.id
                   WHERE p.id != ?
                     AND p.id NOT IN (
                         SELECT to_profile_id FROM profile_likes
                         WHERE from_profile_id = ?
                     )
                   ORDER BY r.combined_rating DESC, RANDOM()
                   LIMIT ?""",
                (viewer_profile_id, viewer_profile_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def record_referral(self, inviter_profile_id: int, invited_user_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO referrals (inviter_profile_id, invited_user_id, status, created_at)
                   VALUES (?, ?, 'registered', ?)""",
                (inviter_profile_id, invited_user_id, now),
            )
            conn.execute(
                "UPDATE profile_ratings SET referral_score = referral_score + 0.05 WHERE profile_id = ?",
                (inviter_profile_id,),
            )
            conn.commit()

    def get_profile_by_id(self, profile_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM profiles WHERE id = ?", (profile_id,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)
