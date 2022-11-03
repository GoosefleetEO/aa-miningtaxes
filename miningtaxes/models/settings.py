# Shamelessly stolen from Member Audit
from django.db import models

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from .. import __title__

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class Settings(models.Model):
    phrase = models.CharField(max_length=10, default="", blank=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        super(Settings, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class TaxGroups(models.Model):
    setting = models.ForeignKey(
        Settings, on_delete=models.CASCADE, related_name="group"
    )

    group = models.CharField(max_length=10, null=False)
    value = models.FloatField(default=10.0, null=False)
