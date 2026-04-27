from __future__ import annotations

import math
from dataclasses import dataclass

from bot.storage import Profile, UserStorage, ProfileRating

W_PRIMARY = 0.45
W_BEHAVIOR = 0.45
W_REFERRAL = 0.1
REF_BONUS_MAX = 0.08


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


def compute_primary_rating(profile: Profile) -> float:
    parts: list[float] = []
    bio_len = len((profile.bio or "").strip())
    parts.append(_clamp01(bio_len / 400.0))
    parts.append(_clamp01(profile.photos_count / 4.0))
    parts.append(0.8)
    parts.append(0.8)
    parts.append(0.8)
    city_len = len((profile.city or "").strip())
    parts.append(_clamp01(city_len / 10.0))
    return _clamp01(sum(parts) / len(parts))


def compute_behavior_rating(
    likes_in: int,
    skips_in: int,
    matches_in: int,
) -> float:
    total = likes_in + skips_in
    if total == 0:
        return 0.5
    like_ratio = likes_in / float(total)
    denom = max(1, likes_in)
    match_signal = _clamp01(matches_in / float(denom))
    return _clamp01(0.55 * like_ratio + 0.45 * match_signal)


def compute_referral_placeholder(profile: Profile) -> float:
    base = 0.5 * _clamp01(len(profile.bio or "") / 500.0) + 0.5 * _clamp01(min(profile.photos_count, 4) / 4.0)
    return _clamp01(REF_BONUS_MAX * base)


def compute_combined_rating(primary: float, behavior: float, referral: float) -> float:
    ref_01 = _clamp01(referral / REF_BONUS_MAX) if REF_BONUS_MAX > 0 else 0.0
    return _clamp01(W_PRIMARY * primary + W_BEHAVIOR * behavior + W_REFERRAL * ref_01)


def recompute_for_profile(store: UserStorage, profile: Profile) -> Scores:
    li, sk, mt = store.recompute_aggregates_from_db(profile.id)
    primary = compute_primary_rating(profile)
    behavior = compute_behavior_rating(li, sk, mt)
    referral = compute_referral_placeholder(profile)
    comb = compute_combined_rating(primary, behavior, referral)
    store.upsert_rating(
        profile.id,
        primary,
        behavior,
        comb,
        li,
        sk,
        mt,
    )
    return Scores(primary, behavior, comb)


def ensure_rating(store: UserStorage, profile: Profile) -> ProfileRating:
    recompute_for_profile(store, profile)
    row = store.get_rating_row(profile.id)
    assert row is not None
    return row
