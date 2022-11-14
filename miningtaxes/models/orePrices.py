# Shamelessly stolen from Member Audit
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from eveuniverse.models import EveType, EveTypeMaterial

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from .. import __title__
from ..app_settings import MININGTAXES_REFINED_RATE
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


def ore_calc_prices(eve_type, q):
    try:
        ore = OrePrices.objects.get(eve_type=eve_type)
        return q * ore.raw_price, q * ore.refined_price, q * ore.taxed_price
    except OrePrices.DoesNotExist:
        pass
    quantity = q
    raw_price = quantity * get_price(eve_type)
    materials = EveTypeMaterial.objects.filter(
        eve_type_id=eve_type.id
    ).prefetch_related("eve_type")
    refined_price = 0.0
    for mat in materials:
        q = MININGTAXES_REFINED_RATE * (mat.quantity * quantity) / eve_type.portion_size
        refined_price += q * get_price(mat.material_eve_type)
    if refined_price == 0.0:
        refined_price = raw_price
    taxed_value = refined_price
    if raw_price > taxed_value:
        taxed_value = raw_price
    return raw_price, refined_price, taxed_value


def get_price(eve_type):
    ore = None
    try:
        ore = OrePrices.objects.get(eve_type=eve_type)
    except ObjectDoesNotExist:
        pass
    if ore is None:
        mp = None
        try:
            mp = eve_type.market_price
        except EveType.market_price.RelatedObjectDoesNotExist:
            pass
        if mp is None:
            return 0.0
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
    raw_price = models.FloatField(default=0.0)
    refined_price = models.FloatField(default=0.0)
    taxed_price = models.FloatField(default=0.0)
    updated = models.DateTimeField()

    def calc_prices(self):
        self.raw_price = self.buy
        materials = EveTypeMaterial.objects.filter(
            eve_type_id=self.eve_type.id
        ).prefetch_related("eve_type")
        self.refined_price = 0.0
        for mat in materials:
            q = MININGTAXES_REFINED_RATE * mat.quantity / self.eve_type.portion_size
            self.refined_price += q * get_price(mat.material_eve_type)
        if self.refined_price == 0.0:
            self.refined_price = self.raw_price
        self.taxed_price = self.refined_price
        if self.raw_price > self.taxed_price:
            self.taxed_price = self.raw_price
        self.save()
