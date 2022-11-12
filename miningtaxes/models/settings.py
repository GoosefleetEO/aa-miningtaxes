# Shamelessly stolen from Member Audit
from django.db import models

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from .. import __title__

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class Settings(models.Model):
    phrase = models.CharField(
        verbose_name="Keyword (case insensitive) that must be present in the donation reason to be counted. Leave blank/empty to count all donations regardless of reason.",
        max_length=10,
        default="",
        blank=True,
    )
    interest_rate = models.FloatField(
        verbose_name="Monthly interest rate (%) if taxes have not been paid",
        default=5.0,
        null=False,
    )
    tax_R64 = models.FloatField(
        verbose_name="Tax for Moon R64 Ore as a percent", default=10.0, null=False
    )
    tax_R32 = models.FloatField(
        verbose_name="Tax for Moon R32 Ore as a percent", default=10.0, null=False
    )
    tax_R16 = models.FloatField(
        verbose_name="Tax for Moon R16 Ore as a percent", default=10.0, null=False
    )
    tax_R8 = models.FloatField(
        verbose_name="Tax for Moon R8 Ore as a percent", default=10.0, null=False
    )
    tax_R4 = models.FloatField(
        verbose_name="Tax for Moon R4 Ore as a percent", default=10.0, null=False
    )
    tax_Gasses = models.FloatField(
        verbose_name="Tax for Gasses as a percent", default=10.0, null=False
    )
    tax_Ice = models.FloatField(
        verbose_name="Tax for Ice as a percent", default=10.0, null=False
    )
    tax_Mercoxit = models.FloatField(
        verbose_name="Tax for Mercoxit Ore as a percent", default=10.0, null=False
    )
    tax_Ores = models.FloatField(
        verbose_name="Tax for Regular Ore as a percent", default=10.0, null=False
    )

    def save(self, *args, **kwargs):
        self.pk = 1
        super(Settings, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
