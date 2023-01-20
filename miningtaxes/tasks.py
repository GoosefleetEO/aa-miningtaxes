from datetime import date

import requests
from celery import shared_task

from django.db import Error
from django.http.response import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.timezone import now
from eveuniverse.models import EveType, EveTypeMaterial

from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications import notify
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
from .models import (
    AdminCharacter,
    AdminMiningCorpLedgerEntry,
    AdminMiningObsLog,
    Character,
    OrePrices,
    Settings,
)

logger = get_extension_logger(__name__)
TASK_DEFAULT_KWARGS = {"time_limit": MININGTAXES_TASKS_TIME_LIMIT, "max_retries": 3}


def calctaxes():
    n = now().date()
    curmonth = date(year=n.year, month=n.month, day=1)
    user2taxes = {}
    characters = Character.objects.all()
    for character in characters:
        taxes = character.get_monthly_taxes()
        total = 0.0
        for k in taxes.keys():
            if k != curmonth:
                total += taxes[k]
        if character.user not in user2taxes:
            user2taxes[character.user] = [0.0, 0.0, character]
        user2taxes[character.user][0] += total
        if total > user2taxes[character.user][1]:
            user2taxes[character.user][1] = total
            user2taxes[character.user][2] = character
        credits = character.get_lifetime_credits()
        user2taxes[character.user][0] -= credits

    for user in user2taxes.keys():
        taxes_due = round(user2taxes[user][0], 2)
        if taxes_due == 0.00:
            taxes_due = abs(taxes_due)
        user2taxes[user][0] = taxes_due
    return user2taxes


@shared_task(**{**TASK_DEFAULT_KWARGS, **{"bind": True}})
def notify_taxes_due(self):
    user2taxes = calctaxes()

    for u in user2taxes.keys():
        if user2taxes[u][0] > 0.01:
            title = "Taxes are due!"
            message = "Please pay {:,.2f} ISK or you will be charged interest!".format(
                user2taxes[u][0]
            )
            notify(user=u, title=title, message=message, level="INFO")


@shared_task(**{**TASK_DEFAULT_KWARGS, **{"bind": True}})
def apply_interest(self):
    settings = Settings.load()
    user2taxes = calctaxes()

    for u in user2taxes.keys():
        if user2taxes[u][0] <= 0.01:
            continue
        interest = round(user2taxes[u][0] * settings.interest_rate / 100.0, 2)
        if interest > 0.01:
            user2taxes[u][2].give_credit(-1.0 * interest, "interest")
            title = "Taxes are overdue!"
            message = (
                "An interest of {:,.2f} ISK has been charged for late taxes.".format(
                    interest
                )
            )
            notify(user=u, title=title, message=message, level="WARN")


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

    # Update EveUniverse objects
    matset = set()
    for item in prices:
        EveType.objects.update_or_create_esi(
            id=item.id,
            enabled_sections=EveType.Section.TYPE_MATERIALS,
            include_children=True,
            wait_for_children=True,
        )
        materials = EveTypeMaterial.objects.filter(
            eve_type_id=item.id
        ).prefetch_related("eve_type")
        for mat in materials:
            mat = mat.material_eve_type
            matset.add(mat.id)

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
            if price.id in matset:
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

        # Handling refined material prices
        logger.debug("Materials price updating...")
        type_ids = list(matset)
        market_data = {}
        market_data.update(get_bulk_prices(type_ids))
        for mat in matset:
            if not str(mat) in market_data:
                logger.debug(f"Missing data on {mat}")
                continue
            buy = int(float(market_data[str(mat)]["buy"]["max"]))
            sell = int(float(market_data[str(mat)]["sell"]["min"]))
            now = timezone.now()

            found = None
            for e in existing:
                if mat == e.eve_type.id:
                    found = e
                    break
            if found is not None:
                found.buy = buy
                found.sell = sell
                found.updated = now
                toupdate.append(found)
            else:
                tocreate.append(
                    OrePrices(eve_type_id=mat, buy=buy, sell=sell, updated=now)
                )

        logger.debug("Objects to be created: %d" % len(tocreate))
        logger.debug("Objects to be updated: %d" % len(toupdate))
        try:
            OrePrices.objects.bulk_create(tocreate)
            OrePrices.objects.bulk_update(toupdate, ["buy", "sell", "updated"])
            logger.debug("All prices succesfully updated")
        except Error as e:
            logger.error("Error updating prices: %s" % e)

        existing = OrePrices.objects.all()
        for e in existing:
            e.calc_prices()
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
    phrase = settings.phrase.lower().strip()
    for character in characters:
        entries = character.corp_ledger.all()
        for entry in entries:
            if phrase != "" and phrase not in entry.reason.lower():
                continue
            try:
                payee = get_object_or_404(
                    Character,
                    eve_character_id=EveCharacter.objects.get(
                        character_id=entry.taxed_id
                    ).pk,
                )
            except EveCharacter.DoesNotExist:
                continue
            except Http404:
                continue
            payee.tax_credits.update_or_create(
                date=entry.date, credit=entry.amount, defaults={"credit_type": "paid"}
            )


def add_tax_credits_by_char(character):
    settings = Settings.load()
    entries = AdminMiningCorpLedgerEntry.objects.filter(
        taxed_id=character.eve_character.character_id
    )
    for entry in entries:
        if settings.phrase != "" and settings.phrase not in entry.reason:
            continue
        character.tax_credits.update_or_create(
            date=entry.date, credit=entry.amount, defaults={"credit_type": "paid"}
        )


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
    add_tax_credits_by_char(character)
    if not celery and MININGTAXES_TAX_ONLY_CORP_MOONS:
        add_corp_moon_taxes_by_char(character)
