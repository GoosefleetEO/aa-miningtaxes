from django.conf import settings

from app_utils.django import clean_setting

# put your app settings here

EXAMPLE_SETTING_ONE = getattr(settings, "EXAMPLE_SETTING_ONE", None)

MININGTAXES_UPDATE_LEDGER_STALE = clean_setting("MININGTAXES_UPDATE_LEDGER_STALE", 240)
"""Minutes after which a character's mining ledger is considered stale
"""

MININGTAXES_UPDATE_STALE_OFFSET = clean_setting("MINGINGTAXES_UPDATE_STALE_OFFSET", 5)
"""Actual value for considering staleness of a ring will be the above value
minus this offset. Required to avoid time synchronization issues.
"""

MININGTAXES_TASKS_OBJECT_CACHE_TIMEOUT = clean_setting(
    "MEMBERAUDIT_TASKS_OBJECT_CACHE_TIMEOUT", 600
)

MININGTAXES_TASKS_TIME_LIMIT = clean_setting("MININGTAXES_TASKS_TIME_LIMIT", 7200)
"""Global timeout for tasks in seconds to reduce task accumulation during outages."""

MININGTAXES_REFINED_RATE = clean_setting("MININGTAXES_REFINED_RATE", 0.9063)
"""Refining rate for ores."""
