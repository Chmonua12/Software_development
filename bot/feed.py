from __future__ import annotations

import logging

from bot.feed_cache import pop_next_id, refill_if_needed
from bot.metrics import track_time

logger = logging.getLogger(__name__)


class FeedService:
    @track_time
    async def get_next_profile(self, storage, viewer_profile_id: int):
        viewer = storage.get_profile_by_id(viewer_profile_id)
        if viewer is None:
            logger.warning("Viewer profile %d not found", viewer_profile_id)
            return None

        next_id = pop_next_id(viewer_profile_id)
        if next_id is None:
            refill_if_needed(storage, viewer, min_len=5)
            next_id = pop_next_id(viewer_profile_id)

        if next_id is None:
            return None

        target = storage.get_profile_by_id(next_id)
        if target is None:
            return None

        storage.record_profile_view(viewer_profile_id, target.id)
        return target
