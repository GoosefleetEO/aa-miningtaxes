# Shamelessly stolen from Member Audit
from django.db import models

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from .. import __title__

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class General(models.Model):
    """Meta model for app permissions"""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("basic_access", "Can access this app"),
            (
                "admin_access",
                "Can set tax rates for groups and add accountant characters",
            ),
            ("auditor_access", "Can view all registered characters data"),
        )
