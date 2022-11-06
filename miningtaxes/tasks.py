import requests
from celery import shared_task

from django.db import Error
from django.shortcuts import get_object_or_404
from django.utils import timezone

from allianceauth.eveonline.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger

from .app_settings import (
    MININGTAXES_PRICE_JANICE_API_KEY,
    MININGTAXES_PRICE_METHOD,
    MININGTAXES_PRICE_SOURCE_ID,
    MININGTAXES_PRICE_SOURCE_NAME,
    MININGTAXES_TASKS_TIME_LIMIT,
    MININGTAXES_TAX_ONLY_CORP_MOONS,
)
from .helpers import PriceGroups
from .models import AdminCharacter, AdminMiningObsLog, Character, OrePrices, Settings

logger = get_extension_logger(__name__)
TASK_DEFAULT_KWARGS = {"time_limit": MININGTAXES_TASKS_TIME_LIMIT, "max_retries": 3}


@shared_task(**{**TASK_DEFAULT_KWARGS, **{"bind": True}})
def update_daily(self):
    update_all_prices()
    characters = AdminCharacter.objects.all()
    for character in characters:
        update_admin_character(character_pk=character.id, celery=True)
    characters = Character.objects.all()
    for character in characters:
        update_character(character_pk=character.id, celery=True)
    add_corp_moon_taxes()
    add_tax_credits()


def valid_janice_api_key():
    c = requests.get(
        "https://janice.e-351.com/api/rest/v2/markets",
        headers={
            "Content-Type": "text/plain",
            "X-ApiKey": MININGTAXES_PRICE_JANICE_API_KEY,
            "accept": "application/json",
        },
    ).json()

    if "status" in c:
        logger.debug("Janice API status: %s" % c)
        return False
    else:
        return True


def get_bulk_prices(type_ids):
    r = None
    if MININGTAXES_PRICE_METHOD == "Fuzzwork":
        r = requests.get(
            "https://market.fuzzwork.co.uk/aggregates/",
            params={
                "types": ",".join([str(x) for x in type_ids]),
                "station": MININGTAXES_PRICE_SOURCE_ID,
            },
        ).json()
    elif MININGTAXES_PRICE_METHOD == "Janice":
        r = requests.post(
            "https://janice.e-351.com/api/rest/v2/pricer?market=2",
            data="\n".join([str(x) for x in type_ids]),
            headers={
                "Content-Type": "text/plain",
                "X-ApiKey": MININGTAXES_PRICE_JANICE_API_KEY,
                "accept": "application/json",
            },
        ).json()

        # Make Janice data look like Fuzzworks
        output = {}
        for item in r:
            output[str(item["itemType"]["eid"])] = {
                "buy": {"max": str(item["top5AveragePrices"]["buyPrice"])},
                "sell": {"min": str(item["top5AveragePrices"]["sellPrice"])},
            }
        r = output
    else:
        raise f"Unknown pricing method: {MININGTAXES_PRICE_METHOD}"
    return r


@shared_task(**{**TASK_DEFAULT_KWARGS, **{"bind": True}})
def update_all_prices(self):
    type_ids = []
    market_data = {}
    api_up = True

    # Get all type ids
    prices = PriceGroups().items

    if MININGTAXES_PRICE_METHOD == "Fuzzwork":
        logger.debug(
            "Price setup starting for %s items from Fuzzworks API from station id %s (%s), this may take up to 30 seconds..."
            % (
                len(prices),
                MININGTAXES_PRICE_SOURCE_ID,
                MININGTAXES_PRICE_SOURCE_NAME,
            )
        )
    elif MININGTAXES_PRICE_METHOD == "Janice":
        if valid_janice_api_key():
            logger.debug(
                "Price setup starting for %s items from Janice API for Jita 4-4, this may take up to 30 seconds..."
                % (len(prices),)
            )
        else:
            logger.debug(
                "Price setup failed for Janice, invalid API key! Provide a working key or change price source to Fuzzwork"
            )
            api_up = False
    else:
        logger.error(
            "Unknown pricing method: '%s', skipping" % MININGTAXES_PRICE_METHOD
        )
        return

    if api_up:
        # Build suitable bulks to fetch prices from API
        for item in prices:
            type_ids.append(item.id)

            if len(type_ids) == 1000:
                market_data.update(get_bulk_prices(type_ids))
                type_ids.clear()

        # Get leftover data from the bulk
        if len(type_ids) > 0:
            market_data.update(get_bulk_prices(type_ids))

        logger.debug("Market data fetched, starting database update...")
        existing = OrePrices.objects.all()
        toupdate = []
        tocreate = []
        for price in prices:
            if not str(price.id) in market_data:
                logger.debug(f"Missing data on {price}")
                continue
            buy = int(float(market_data[str(price.id)]["buy"]["max"]))
            sell = int(float(market_data[str(price.id)]["sell"]["min"]))
            now = timezone.now()

            found = None
            for e in existing:
                if price.id == e.eve_type.id:
                    found = e
                    break
            if found is not None:
                found.buy = buy
                found.sell = sell
                found.updated = now
                toupdate.append(found)
            else:
                tocreate.append(
                    OrePrices(eve_type_id=price.id, buy=buy, sell=sell, updated=now)
                )
        logger.debug("Objects to be created: %d" % len(tocreate))
        logger.debug("Objects to be updated: %d" % len(toupdate))
        try:
            OrePrices.objects.bulk_create(tocreate)
            OrePrices.objects.bulk_update(toupdate, ["buy", "sell", "updated"])
            logger.debug("All prices succesfully updated")
        except Error as e:
            logger.error("Error updating prices: %s" % e)

    else:
        logger.error("Price source API is not up! Prices not updated.")


@shared_task(**{**TASK_DEFAULT_KWARGS, **{"bind": True}})
def update_admin_character(
    self, character_pk: int, force_update: bool = False, celery=False
) -> bool:
    """Start respective update tasks for all stale sections of a character

    Args:
    - character_pk: PL of character to update
    - force_update: When set to True will always update regardless of stale status

    Returns:
    - True when update was conducted
    - False when no updated was needed
    """
    character = AdminCharacter.objects.get(pk=character_pk)
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

    character.update_all()
    if not celery and MININGTAXES_TAX_ONLY_CORP_MOONS:
        add_corp_moon_taxes()


def add_tax_credits():
    settings = Settings.load()
    characters = AdminCharacter.objects.all()
    for character in characters:
        entries = character.corp_ledger.all()
        for entry in entries:
            if settings.phrase != "" and settings.phrase not in entry.reason:
                continue
            print(entry, entry.reason, entry.amount, entry.date, entry.taxed_id)
            payee = None
            try:
                payee = get_object_or_404(
                    Character,
                    eve_character_id=EveCharacter.objects.get(
                        character_id=entry.taxed_id
                    ).pk,
                )
            except EveCharacter.DoesNotExist:
                pass
            if payee is None:
                continue
            print(payee)
            payee.tax_credits.update_or_create(date=entry.date, credit=entry.amount)


def add_corp_moon_taxes():
    characters = Character.objects.all()
    for character in characters:
        add_corp_moon_taxes_by_char(character)


def add_corp_moon_taxes_by_char(character):
    entries = AdminMiningObsLog.objects.filter(
        miner_id=character.eve_character.character_id
    )
    for entry in entries:
        (row, _) = character.mining_ledger.update_or_create(
            date=entry.date,
            eve_solar_system=entry.eve_solar_system,
            eve_type=entry.eve_type,
            defaults={"quantity": entry.quantity},
        )
        row.calc_prices()


@shared_task(**{**TASK_DEFAULT_KWARGS, **{"bind": True}})
def update_character(
    self, character_pk: int, force_update: bool = False, celery=False
) -> bool:
    """Start respective update tasks for all stale sections of a character

    Args:
    - character_pk: PL of character to update
    - force_update: When set to True will always update regardless of stale status

    Returns:
    - True when update was conducted
    - False when no updated was needed
    """
    character = Character.objects.get(pk=character_pk)
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
    if not celery and MININGTAXES_TAX_ONLY_CORP_MOONS:
        add_corp_moon_taxes_by_char(character)
