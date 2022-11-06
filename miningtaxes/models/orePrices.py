# Shamelessly stolen from Member Audit
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from eveuniverse.models import EveType

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from .. import __title__
from ..helpers import PriceGroups
from .settings import Settings

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


def get_tax(eve_type):
    settings = Settings.load()
    pg = PriceGroups()
    if eve_type.eve_group_id not in pg.taxgroups:
        logger.debug(
            "Unknown evetype for %s, group: %d" % (eve_type, eve_type.eve_group_id)
        )
        return 0.10
    group = "tax_" + pg.taxgroups[eve_type.eve_group_id]
    return settings.__dict__[group] / 100.0


def get_price(eve_type):
    try:
        ore = OrePrices.objects.get(eve_type=eve_type)
    except ObjectDoesNotExist:
        if eve_type.market_price.average_price is not None:
            return eve_type.market_price.average_price
        if eve_type.market_price.adjusted_price is not None:
            return eve_type.market_price.adjusted_price
        return 0.0
    return ore.buy


class OrePrices(models.Model):
    eve_type = models.OneToOneField(
        EveType,
        on_delete=models.deletion.CASCADE,
        unique=True,
    )
    buy = models.FloatField()
    sell = models.FloatField()
    updated = models.DateTimeField()
