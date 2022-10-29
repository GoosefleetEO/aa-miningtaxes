# Shamelessly stolen from Member Audit
from django.db import models
from eveuniverse.models import EveType

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from .. import __title__

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


def get_tax(eve_type):
    return 0.10


def get_price(eve_type):
    ore = OrePrices.objects.filter(id=eve_type.id)
    if len(ore) == 0:
        if eve_type.market_price.average_price is None:
            return eve_type.market_price.adjusted_price
        return eve_type.market_price.average_price
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
