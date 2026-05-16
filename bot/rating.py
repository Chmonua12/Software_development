from __future__ import annotations

import math
from dataclasses import dataclass

from bot.storage import Profile, UserStorage

W_PRIMARY = 0.40
W_BEHAVIOR = 0.60
REFERRAL_CAP = 0.20


@dataclass(frozen=True)
class Scores:
    primary: float
    behavior: float
    combined: float


def _clamp01(x: float) -> float:
    if math.isnan(x) or x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def compute_primary_rating(profile: Profile, store: UserStorage) -> float:
    """Уровень 1: качество и полнота анкеты художника."""
    inputs = store.get_rating_inputs(profile.id)
    bio_len = len((profile.bio or "").strip())
    factors = [
        _clamp01(bio_len / 350.0),
        1.0 if 18 <= profile.age <= 99 else 0.0,
        1.0 if len(profile.city.strip()) >= 2 else 0.0,
        1.0 if inputs.has_avatar else 0.0,
        _clamp01(inputs.photos_count / 5.0),
        _clamp01(inputs.interests_count / 5.0),
        _clamp01(inputs.social_links_count / 3.0),
        1.0 if inputs.has_primary_telegram else 0.65,
    ]
    return _clamp01(sum(factors) / len(factors))


def compute_behavior_rating(
    likes_in: int,
    skips_in: int,
    matches_in: int,
    views_in: int,
    link_clicks_in: int,
) -> float:
    """Уровень 2: реакция сообщества на анкету."""
    impressions = max(views_in, likes_in + skips_in, 1)
    like_ratio = likes_in / float(max(likes_in + skips_in, 1))
    conversion = likes_in / float(impressions)
    match_signal = matches_in / float(max(likes_in, 1))
    click_signal = link_clicks_in / float(impressions)
    return _clamp01(
        0.42 * like_ratio
        + 0.22 * conversion
        + 0.20 * _clamp01(match_signal)
        + 0.16 * _clamp01(click_signal * 2.0)
    )


def compute_combined_rating(primary: float, behavior: float, referral_score: float) -> float:
    """Уровень 3: весовая модель + реферальный бонус."""
    return _clamp01(W_PRIMARY * primary + W_BEHAVIOR * behavior + min(referral_score, REFERRAL_CAP))


def recompute_for_profile(store: UserStorage, profile: Profile) -> Scores:
    inputs = store.get_rating_inputs(profile.id)
    primary = compute_primary_rating(profile, store)
    behavior = compute_behavior_rating(
        inputs.likes_count,
        inputs.skips_count,
        inputs.matches_count,
        inputs.views_count,
        inputs.link_clicks_count,
    )
    combined = compute_combined_rating(primary, behavior, inputs.referral_score)
    store.upsert_rating(
        profile.id,
        primary,
        behavior,
        combined,
        inputs.likes_count,
        inputs.skips_count,
        inputs.matches_count,
        inputs.views_count,
        inputs.link_clicks_count,
        inputs.referral_score,
    )
    return Scores(primary, behavior, combined)


def recompute_all(store: UserStorage) -> int:
    count = 0
    for profile in store.list_all_active_profiles():
        recompute_for_profile(store, profile)
        count += 1
    return count


def ensure_rating(store: UserStorage, profile: Profile):
    recompute_for_profile(store, profile)
    row = store.get_rating_row(profile.id)
    assert row is not None
    return row
