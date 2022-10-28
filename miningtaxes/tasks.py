from celery import shared_task

from allianceauth.services.hooks import get_extension_logger

from .app_settings import (  # MEMBERAUDIT_BULK_METHODS_BATCH_SIZE,; MEMBERAUDIT_LOG_UPDATE_STATS,; MEMBERAUDIT_TASKS_MAX_ASSETS_PER_PASS,; MEMBERAUDIT_TASKS_TIME_LIMIT,; MEMBERAUDIT_UPDATE_STALE_RING_2,
    MININGTAXES_TASKS_OBJECT_CACHE_TIMEOUT,
    MININGTAXES_TASKS_TIME_LIMIT,
)
from .models import Character

logger = get_extension_logger(__name__)

# Create your tasks here

TASK_DEFAULT_KWARGS = {"time_limit": MININGTAXES_TASKS_TIME_LIMIT, "max_retries": 3}


@shared_task(**{**TASK_DEFAULT_KWARGS, **{"bind": True}})
def update_character(self, character_pk: int, force_update: bool = False) -> bool:
    """Start respective update tasks for all stale sections of a character

    Args:
    - character_pk: PL of character to update
    - force_update: When set to True will always update regardless of stale status

    Returns:
    - True when update was conducted
    - False when no updated was needed
    """
    character = Character.objects.get_cached(
        pk=character_pk, timeout=MININGTAXES_TASKS_OBJECT_CACHE_TIMEOUT
    )
    if character.is_orphan:
        logger.info("%s: Skipping update for orphaned character", character)
        return False
    needs_update = force_update
    needs_update |= character.is_ledger_stale()

    if not needs_update:
        logger.info("%s: No update required", character)
        return False

    logger.info(
        "%s: Starting %s character update", character, "forced" if force_update else ""
    )

    character.update_mining_ledger()
