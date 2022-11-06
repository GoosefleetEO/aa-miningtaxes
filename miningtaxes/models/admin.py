# Shamelessly stolen from Member Audit
from django.db import models
from esi.models import Token
from eveuniverse.models import EveSolarSystem, EveType

from allianceauth.eveonline.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from .. import __title__
from ..app_settings import MININGTAXES_TAX_ONLY_CORP_MOONS
from ..decorators import fetch_token_for_character
from ..providers import esi
from .character import CharacterAbstract

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class AdminCharacter(CharacterAbstract):
    eve_character = models.OneToOneField(
        EveCharacter,
        related_name="miningtaxes_admin_character",
        on_delete=models.CASCADE,
    )

    @classmethod
    def get_esi_scopes(cls) -> list:
        return [
            "esi-industry.read_corporation_mining.v1",
            "esi-wallet.read_corporation_wallets.v1",
            "esi-universe.read_structures.v1",
        ]

    def update_all(self):
        if MININGTAXES_TAX_ONLY_CORP_MOONS:
            self.update_mining_observers()
        self.update_corp_ledger()
        return

    @fetch_token_for_character(
        ("esi-industry.read_corporation_mining.v1", "esi-universe.read_structures.v1")
    )
    def update_mining_observers(self, token: Token):
        logger.info("%s: Fetching mining observers from ESI", self)
        # get_corporation_corporation_id_mining_observers
        entries = esi.client.Industry.get_corporation_corporation_id_mining_observers(
            corporation_id=self.eve_character.corporation_id,
            token=token.valid_access_token(),
        ).results()
        for entry in entries:
            structinfo = esi.client.Universe.get_universe_structures_structure_id(
                structure_id=entry["observer_id"],
                token=token.valid_access_token(),
            ).results()
            structname = ""
            sys = None
            if type(structinfo) == dict:
                structname = structinfo["name"]
                sys, _ = EveSolarSystem.objects.get_or_create_esi(
                    id=structinfo["solar_system_id"]
                )
            else:
                logger.error("Wrong struct info for: %d" % entry["observer_id"])
                logger.error(structinfo)
                continue

            (obs, _) = self.mining_obs.update_or_create(
                obs_id=entry["observer_id"],
                defaults={
                    "obs_type": entry["observer_type"],
                    "sys_name": sys.name,
                    "name": structname,
                },
            )
            ledger = esi.client.Industry.get_corporation_corporation_id_mining_observers_observer_id(
                corporation_id=self.eve_character.corporation_id,
                observer_id=entry["observer_id"],
                token=token.valid_access_token(),
            ).results()
            for line in ledger:
                eve_type, _ = EveType.objects.get_or_create_esi(id=line["type_id"])
                obs.mining_log.update_or_create(
                    miner_id=line["character_id"],
                    date=line["last_updated"],
                    eve_type=eve_type,
                    defaults={
                        "eve_solar_system": sys,
                        "quantity": line["quantity"],
                    },
                )

    @fetch_token_for_character("esi-wallet.read_corporation_wallets.v1")
    def update_corp_ledger(self, token: Token):
        """Update corp ledger from ESI for this character."""
        logger.info("%s: Fetching corp wallet ledger from ESI", self)
        entries = (
            esi.client.Wallet.get_corporations_corporation_id_wallets_division_journal(
                corporation_id=self.eve_character.corporation_id,
                division=1,
                token=token.valid_access_token(),
            ).results()
        )
        for entry in entries:
            if entry["ref_type"] != "player_donation":
                continue
            self.corp_ledger.update_or_create(
                taxed_id=entry["first_party_id"],
                date=entry["date"],
                defaults={
                    "amount": entry["amount"],
                    "reason": entry["reason"][0:32],
                },
            )


class AdminMiningObservers(models.Model):
    """Mining Observers available to a character."""

    character = models.ForeignKey(
        AdminCharacter, on_delete=models.CASCADE, related_name="mining_obs"
    )
    obs_id = models.BigIntegerField()
    obs_type = models.CharField(max_length=32)
    name = models.CharField(max_length=32)
    sys_name = models.CharField(max_length=32)

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=["obs_id"],
                name="functional_pk_mt_adminMiningObs",
            )
        ]

    def __str__(self) -> str:
        return f"{self.character} miningObs {self.id}"


class AdminMiningObsLog(models.Model):
    """Mining Log for a given Observer."""

    observer = models.ForeignKey(
        AdminMiningObservers, on_delete=models.CASCADE, related_name="mining_log"
    )
    date = models.DateField(db_index=True)
    miner_id = models.BigIntegerField()
    eve_type = models.ForeignKey(EveType, on_delete=models.CASCADE, related_name="+")
    quantity = models.PositiveIntegerField()
    observer_type = models.CharField(max_length=32)
    eve_solar_system = models.ForeignKey(
        EveSolarSystem, on_delete=models.CASCADE, related_name="+"
    )

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=["observer", "date", "miner_id", "eve_type"],
                name="functional_pk_mt_adminMiningLog",
            )
        ]

    def __str__(self) -> str:
        return f"{self.observer} miningObs {self.id}"


class AdminMiningCorpLedgerEntry(models.Model):
    """Corp ledger entry of a character."""

    character = models.ForeignKey(
        AdminCharacter, on_delete=models.CASCADE, related_name="corp_ledger"
    )
    date = models.DateTimeField(db_index=True)
    taxed_id = models.BigIntegerField()
    amount = models.FloatField(default=0.0)
    reason = models.CharField(max_length=32)

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=["character", "date", "taxed_id"],
                name="functional_pk_mt_admincorpledger",
            )
        ]

    def __str__(self) -> str:
        return f"{self.character} wallet {self.id}"
