# Shamelessly stolen from Member Audit
import datetime as dt
import hashlib
import json
from typing import Any, Optional

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils.functional import cached_property
from django.utils.timezone import now
from esi.errors import TokenError
from esi.models import Token
from eveuniverse.models import EveSolarSystem, EveType

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger
from app_utils.allianceauth import notify_throttled
from app_utils.caching import ObjectCacheMixin
from app_utils.logging import LoggerAddTag

from .. import __title__
from ..app_settings import (
    MININGTAXES_TAX_ONLY_CORP_MOONS,
    MININGTAXES_UPDATE_LEDGER_STALE,
    MININGTAXES_UPDATE_STALE_OFFSET,
)
from ..decorators import fetch_token_for_character
from ..helpers import PriceGroups
from ..providers import esi
from .orePrices import get_tax, ore_calc_prices

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class CharacterQuerySet(models.QuerySet):
    def eve_character_ids(self) -> set:
        return set(self.values_list("eve_character__character_id", flat=True))

    def owned_by_user(self, user: User) -> models.QuerySet:
        """Filter character owned by user."""
        return self.filter(eve_character__character_ownership__user__pk=user.pk)


class CharacterManagerBase(ObjectCacheMixin, models.Manager):
    def unregistered_characters_of_user_count(self, user: User) -> int:
        return CharacterOwnership.objects.filter(
            user=user, character__memberaudit_character__isnull=True
        ).count()


CharacterManager = CharacterManagerBase.from_queryset(CharacterQuerySet)


class CharacterAbstract(models.Model):
    id = models.AutoField(primary_key=True)
    eve_character = models.OneToOneField(
        EveCharacter, related_name="miningtaxes_character", on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    objects = CharacterManager()

    class Meta:
        abstract = True
        default_permissions = ()

    def __str__(self) -> str:
        return f"{self.eve_character.character_name} (PK:{self.pk})"

    def __repr__(self) -> str:
        return f"Character(pk={self.pk}, eve_character='{self.eve_character}')"

    @cached_property
    def name(self) -> str:
        return self.eve_character.character_name

    @cached_property
    def character_ownership(self) -> Optional[CharacterOwnership]:
        try:
            return self.eve_character.character_ownership
        except ObjectDoesNotExist:
            return None

    @cached_property
    def user(self) -> Optional[User]:
        try:
            return self.character_ownership.user
        except AttributeError:
            return None

    @cached_property
    def main_character(self) -> Optional[EveCharacter]:
        try:
            return self.character_ownership.user.profile.main_character
        except AttributeError:
            return None

    @cached_property
    def is_main(self) -> bool:
        """returns True if this character is a main character, else False"""
        try:
            return self.main_character.character_id == self.eve_character.character_id
        except AttributeError:
            return False

    def fetch_token(self, scopes=None) -> Token:
        """returns valid token for character

        Args:
        - scopes: Optionally provide the required scopes.
        Otherwise will use all scopes defined for this character.

        Exceptions:
        - TokenError: If no valid token can be found
        """
        if self.is_orphan:
            raise TokenError(
                f"Can not find token for orphaned character: {self}"
            ) from None
        token = (
            Token.objects.prefetch_related("scopes")
            .filter(user=self.user, character_id=self.eve_character.character_id)
            .require_scopes(scopes if scopes else self.get_esi_scopes())
            .require_valid()
            .first()
        )
        if not token:
            message_id = f"{__title__}-fetch_token-{self.pk}-TokenError"
            title = f"{__title__}: Invalid or missing token for {self.eve_character}"
            message = (
                f"Mining Taxes could not find a valid token for your "
                f"character {self.eve_character}.\n"
                f"Please re-add that character to Mining Taxes"
                "at your earliest convenience to update your token."
            )
            notify_throttled(
                message_id=message_id, user=self.user, title=title, message=message
            )
            raise TokenError(f"Could not find a matching token for {self}")
        return token

    @cached_property
    def is_orphan(self) -> bool:
        """Whether this character is not owned by a user."""
        return self.character_ownership is None

    def user_is_owner(self, user: User) -> bool:
        """Return True if the given user is owner of this character"""
        try:
            return self.user == user
        except AttributeError:
            return False

    def user_has_access(self, user: User) -> bool:
        """Returns True if given user has permission to access this character
        in the character viewer
        """
        try:
            if self.user == user:  # shortcut for better performance
                return True
        except AttributeError:
            pass
        return Character.objects.user_has_access(user).filter(pk=self.pk).exists()

    def is_update_status_ok(self) -> bool:
        """returns status of last update

        Returns:
        - True: If update was complete and without errors
        - False if there where any errors
        - None: if last update is incomplete
        """
        errors_count = self.update_status_set.filter(is_success=False).count()
        ok_count = self.update_status_set.filter(is_success=True).count()
        if errors_count > 0:
            return False
        elif ok_count == len(Character.UpdateSection.choices):
            return True
        else:
            return None

    @classmethod
    def update_time_until_stale(cls) -> dt.timedelta:
        minutes = MININGTAXES_UPDATE_LEDGER_STALE
        return dt.timedelta(minutes=minutes - MININGTAXES_UPDATE_STALE_OFFSET)

    def is_ledger_stale(self) -> bool:
        """returns True if the ledger is stale, else False"""
        try:
            update_status = self.update_status_set.get(
                is_success=True,
                started_at__isnull=False,
                finished_at__isnull=False,
            )
        except (CharacterUpdateStatus.DoesNotExist, ObjectDoesNotExist, AttributeError):
            return True

        deadline = now() - self.update_time_until_stale()
        return update_status.started_at < deadline


class Character(CharacterAbstract):
    @fetch_token_for_character("esi-industry.read_character_mining.v1")
    def update_mining_ledger(self, token: Token):
        """Update mining ledger from ESI for this character."""
        logger.info("%s: Fetching mining ledger from ESI", self)
        entries = esi.client.Industry.get_characters_character_id_mining(
            character_id=self.eve_character.character_id,
            token=token.valid_access_token(),
        ).results()
        for entry in entries:
            eve_type, _ = EveType.objects.get_or_create_esi(id=entry["type_id"])
            if (
                eve_type.eve_group_id in PriceGroups.moon_ore_groups
            ) and MININGTAXES_TAX_ONLY_CORP_MOONS:
                continue

            eve_solar_system, _ = EveSolarSystem.objects.get_or_create_esi(
                id=entry["solar_system_id"]
            )
            (row, _) = self.mining_ledger.update_or_create(
                date=entry["date"],
                eve_solar_system=eve_solar_system,
                eve_type=eve_type,
                defaults={"quantity": entry["quantity"]},
            )
            row.calc_prices()

    @classmethod
    def get_esi_scopes(cls) -> list:
        return [
            "esi-industry.read_character_mining.v1",
        ]

    def standardize(self, months):
        newmonths = {}
        for h in months:
            if type(h["month"]) == dt.datetime:
                h["month"] = h["month"].date()
            newmonths[h["month"]] = h["total"]
        return newmonths

    def get_lifetime_taxes(self):
        amount = self.mining_ledger.all().aggregate(Sum("taxes_owed"))[
            "taxes_owed__sum"
        ]
        if amount is None:
            amount = 0.0
        return round(amount, 2)

    def get_lifetime_credits(self):
        amount = self.tax_credits.all().aggregate(Sum("credit"))["credit__sum"]
        if amount is None:
            amount = 0.0
        return round(amount, 2)

    def get_monthly_taxes(self):
        return self.standardize(
            self.mining_ledger.all()
            .annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(total=Sum("taxes_owed"))
            .order_by("month")
        )

    def get_monthly_credits(self):
        return self.standardize(
            self.tax_credits.all()
            .annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(total=Sum("credit"))
            .order_by("month")
        )

    def get_monthly_mining(self):
        return self.standardize(
            self.mining_ledger.all()
            .annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(total=Sum("taxed_value"))
            .order_by("month")
        )

    def get_90d_mining(self):
        b = now().date() - dt.timedelta(days=90)
        return self.mining_ledger.filter(date__gte=b)

    def last_paid(self):
        dt = self.tax_credits.last()
        if dt is None:
            return None
        return dt.date

    def give_credit(self, isk, credit_type):
        if credit_type not in ("credit", "paid", "interest"):
            raise Exception("Unknown credit type")
        self.tax_credits.create(date=now(), credit=isk, credit_type=credit_type)


class CharacterTaxCredits(models.Model):
    character = models.ForeignKey(
        Character, on_delete=models.CASCADE, related_name="tax_credits"
    )
    date = models.DateTimeField(db_index=True)
    credit = models.FloatField(default=0.0)
    credit_type = models.CharField(max_length=32, default="")

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=["character", "date", "credit"],
                name="functional_pk_miningtaxes_charactertaxes",
            )
        ]

    def __str__(self) -> str:
        return f"{self.character} - {self.date} - {self.credit} ISK"


class CharacterUpdateStatus(models.Model):
    """Update status for a character"""

    character = models.ForeignKey(
        Character, on_delete=models.CASCADE, related_name="update_status_set"
    )

    is_success = models.BooleanField(
        null=True,
        default=None,
        db_index=True,
    )
    content_hash_1 = models.CharField(max_length=32, default="")
    content_hash_2 = models.CharField(max_length=32, default="")
    content_hash_3 = models.CharField(max_length=32, default="")
    last_error_message = models.TextField()
    root_task_id = models.CharField(
        max_length=36,
        default="",
        db_index=True,
        help_text="ID of update_all_characters task that started this update",
    )
    parent_task_id = models.CharField(
        max_length=36,
        default="",
        db_index=True,
        help_text="ID of character_update task that started this update",
    )
    started_at = models.DateTimeField(null=True, default=None, db_index=True)
    finished_at = models.DateTimeField(null=True, default=None, db_index=True)

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=["character"],
                name="functional_pk_miningtaxes_charactersyncstatus",
            )
        ]

    def __str__(self) -> str:
        return f"{self.character}"

    @property
    def is_updating(self) -> bool:
        if not self.started_at and not self.finished_at:
            return False
        else:
            return self.started_at is not None and self.finished_at is None

    def has_changed(self, content: Any, hash_num: int = 1) -> bool:
        """returns True if given content is not the same as previous one, else False"""
        new_hash = self._calculate_hash(content)
        if hash_num == 2:
            content_hash = self.content_hash_2
        elif hash_num == 3:
            content_hash = self.content_hash_3
        else:
            content_hash = self.content_hash_1

        return new_hash != content_hash

    def update_content_hash(self, content: Any, hash_num: int = 1):
        new_hash = self._calculate_hash(content)
        if hash_num == 2:
            self.content_hash_2 = new_hash
        elif hash_num == 3:
            self.content_hash_3 = new_hash
        else:
            self.content_hash_1 = new_hash

        self.save()

    @staticmethod
    def _calculate_hash(content: Any) -> str:
        return hashlib.md5(
            json.dumps(content, cls=DjangoJSONEncoder).encode("utf-8")
        ).hexdigest()

    def reset(self, root_task_id: str = None, parent_task_id: str = None) -> None:
        """resets this update status"""
        self.is_success = None
        self.last_error_message = ""
        self.started_at = now()
        self.finished_at = None
        self.root_task_id = root_task_id if root_task_id else ""
        self.parent_task_id = parent_task_id if root_task_id else ""
        self.save()


class CharacterMiningLedgerEntryQueryset(models.QuerySet):
    def annotate_pricing(self) -> models.QuerySet:
        """Annotate price and total columns."""
        return


class CharacterMiningLedgerEntryManagerBase(models.Manager):
    pass


CharacterMiningLedgerEntryManager = CharacterMiningLedgerEntryManagerBase.from_queryset(
    CharacterMiningLedgerEntryQueryset
)


class CharacterMiningLedgerEntry(models.Model):
    """Mining ledger entry of a character."""

    character = models.ForeignKey(
        Character, on_delete=models.CASCADE, related_name="mining_ledger"
    )
    date = models.DateField(db_index=True)
    quantity = models.PositiveIntegerField()
    eve_solar_system = models.ForeignKey(
        EveSolarSystem, on_delete=models.CASCADE, related_name="+"
    )
    eve_type = models.ForeignKey(EveType, on_delete=models.CASCADE, related_name="+")
    raw_price = models.FloatField(default=0.0)
    refined_price = models.FloatField(default=0.0)
    taxed_value = models.FloatField(default=0.0)
    taxes_owed = models.FloatField(default=0.0)

    objects = CharacterMiningLedgerEntryManager()

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=["character", "date", "eve_solar_system", "eve_type"],
                name="functional_pk_mt_characterminingledgerentry",
            )
        ]

    def __str__(self) -> str:
        return f"{self.character} {self.id}"

    def calc_prices(self):
        if self.raw_price != 0.0:
            return
        self.raw_price, self.refined_price, self.taxed_value = ore_calc_prices(
            self.eve_type, self.quantity
        )
        self.taxes_owed = get_tax(self.eve_type) * self.taxed_value
        self.raw_price = round(self.raw_price, 2)
        self.refined_price = round(self.refined_price, 2)
        self.taxed_value = round(self.taxed_value, 2)
        self.taxes_owed = round(self.taxes_owed, 2)
        self.save()
