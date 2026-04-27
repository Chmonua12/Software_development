from __future__ import annotations

import logging
from bot.feed_cache import pop_next_id, refill_if_needed

logger = logging.getLogger(__name__)


class FeedService:
    def __init__(self) -> None:
        pass

    async def get_next_profile(self, storage, viewer_profile_id: int):
        from bot.storage import Profile
        
        profile_dict = storage.get_profile_by_id(viewer_profile_id)
        if profile_dict is None:
            logger.warning("Viewer profile %d not found", viewer_profile_id)
            return None
            
        viewer_obj = Profile(
            id=profile_dict["id"],
            user_id=profile_dict["user_id"],
            display_name=profile_dict["display_name"],
            age=profile_dict["age"],
            city=profile_dict["city"],
            bio=profile_dict["bio"],
            profile_completeness_score=profile_dict["profile_completeness_score"],
            photos_count=profile_dict["photos_count"],
            created_at=profile_dict["created_at"],
            updated_at=profile_dict["updated_at"],
        )
        
        next_id = pop_next_id(viewer_profile_id)
        
        if next_id is None:
            logger.info("Cache empty for user %d, refilling", viewer_profile_id)
            refill_if_needed(storage, viewer_obj, min_len=5)
            next_id = pop_next_id(viewer_profile_id)
            
            if next_id is None:
                logger.warning("No profiles available for user %d", viewer_profile_id)
                return None
        
        profile_dict = storage.get_profile_by_id(next_id)
        if profile_dict is None:
            return None
            
        return Profile(
            id=profile_dict["id"],
            user_id=profile_dict["user_id"],
            display_name=profile_dict["display_name"],
            age=profile_dict["age"],
            city=profile_dict["city"],
            bio=profile_dict["bio"],
            profile_completeness_score=profile_dict["profile_completeness_score"],
            photos_count=profile_dict["photos_count"],
            created_at=profile_dict["created_at"],
            updated_at=profile_dict["updated_at"],
        )
