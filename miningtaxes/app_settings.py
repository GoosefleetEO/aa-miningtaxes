from app_utils.django import clean_setting

MININGTAXES_TAX_CACHE_VIEW_TIMEOUT = clean_setting(
    "MININGTAXES_TAX_CACHE_VIEW_TIMEOUT", 60 * 60 * 6
)
"""Number of seconds before view cache expires.
"""


MININGTAXES_TAX_ONLY_CORP_MOONS = clean_setting("MININGTAXES_TAX_ONLY_CORP_MOONS", True)
"""Only tax corporate moons using moon observers as opposed to all moons appearing
in the personal mining ledgers.
"""

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


MININGTAXES_PRICE_SOURCE_ID = clean_setting("MININGTAXES_PRICE_SOURCE_ID", 60003760)

MININGTAXES_PRICE_SOURCE_NAME = clean_setting("MININGTAXES_PRICE_SOURCE_NAME", "Jita")

MININGTAXES_PRICE_METHOD = clean_setting("MININGTAXES_PRICE_METHOD", "Fuzzwork")

MININGTAXES_PRICE_JANICE_API_KEY = clean_setting("MININGTAXES_PRICE_JANICE_API_KEY", "")
