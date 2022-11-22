import datetime
import hashlib
import json
from unittest.mock import patch

from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter
from app_utils.testing import NoSocketsTestCase

from ...models import OrePrices
from ..testdata.esi_client_stub import esi_client_stub
from ..testdata.load_entities import load_entities
from ..testdata.load_eveuniverse import load_eveuniverse
from ..utils import (
    create_character,
    create_character_update_status,
    create_miningtaxes_character,
)

MODELS_PATH = "miningtaxes.models"


class TestCharacter(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_eveuniverse()
        load_entities()

    def test_user_should_return_user_when_not_orphan(self):
        # given
        character_1001 = create_miningtaxes_character(1001)
        user = character_1001.eve_character.character_ownership.user
        # when/then
        self.assertEqual(character_1001.user, user)

    def test_user_should_be_None_when_orphan(self):
        # given
        character = create_character(EveCharacter.objects.get(character_id=1121))
        # when/then
        self.assertIsNone(character.user)

    def test_should_return_main_when_it_exists_1(self):
        # given
        character_1001 = create_miningtaxes_character(1001)
        user = character_1001.eve_character.character_ownership.user
        main_character = user.profile.main_character
        # when/then
        self.assertEqual(character_1001.main_character, main_character)

    def test_mining_ledger(self):
        n = datetime.date(year=2022, month=1, day=15)
        month_n = datetime.date(year=2022, month=1, day=1)
        character_1001 = create_miningtaxes_character(1001)
        a = OrePrices(eve_type_id=45511, buy=10, sell=100, updated=n)
        a.calc_prices()
        c, _ = character_1001.mining_ledger.update_or_create(
            date=n, quantity=10, eve_type_id=45511, eve_solar_system_id=30000142
        )
        c.calc_prices()
        monthly = character_1001.get_monthly_taxes()
        monthly_k = list(monthly.keys())[0]

        self.assertEqual(c.raw_price, 100)
        self.assertEqual(c.refined_price, 100)
        self.assertEqual(c.taxed_value, 100)
        self.assertEqual(c.taxes_owed, 10)
        self.assertEqual(character_1001.get_lifetime_taxes(), 10)
        self.assertEqual(monthly_k, month_n)
        self.assertEqual(monthly[monthly_k], 10)

    def test_tax_credits(self):
        character_1001 = create_miningtaxes_character(1001)
        n = now()
        character_1001.give_credit(1234, "paid")
        last = character_1001.last_paid()
        month_n = datetime.date(year=n.year, month=n.month, day=1)

        monthly = character_1001.get_monthly_credits()
        monthly_k = list(monthly.keys())[0]

        self.assertEqual(character_1001.get_lifetime_credits(), 1234)
        self.assertEqual(monthly_k, month_n)
        self.assertEqual(monthly[monthly_k], 1234)
        self.assertEqual(last.year, n.year)
        self.assertEqual(last.month, n.month)
        self.assertEqual(last.day, n.day)

    @patch(MODELS_PATH + ".character.esi")
    def test_get_ledger(self, mock_esi):
        mock_esi.client = esi_client_stub
        character_1001 = create_miningtaxes_character(1001)
        character_1001.update_mining_ledger()
        ledger = character_1001.mining_ledger.all()
        self.assertEqual(
            len(ledger), 1
        )  # make sure that moon ore is ignored on import.
        entry = ledger[0]
        self.assertEqual(entry.quantity, 4333)
        self.assertEqual(entry.eve_type_id, 62586)
        self.assertEqual(entry.eve_solar_system_id, 30002537)


class TestCharacterUpdateStatus(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_entities()
        cls.character_1001 = create_miningtaxes_character(1001)
        cls.content = {"alpha": 1, "bravo": 2}

    def test_str(self):
        # given
        status = create_character_update_status(character=self.character_1001)
        # when/then
        self.assertEqual(str(status), f"{self.character_1001}")

    def test_reset_1(self):
        # given
        status = create_character_update_status(
            character=self.character_1001,
            is_success=True,
            last_error_message="abc",
            root_task_id="a",
            parent_task_id="b",
        )
        # when
        status.reset()
        # then
        status.refresh_from_db()
        self.assertIsNone(status.is_success)
        self.assertEqual(status.last_error_message, "")
        self.assertEqual(status.root_task_id, "")
        self.assertEqual(status.parent_task_id, "")

    def test_reset_2(self):
        # given
        status = create_character_update_status(
            character=self.character_1001,
            is_success=True,
            last_error_message="abc",
            root_task_id="a",
            parent_task_id="b",
        )
        # when
        status.reset(root_task_id="1", parent_task_id="2")

        # then
        status.refresh_from_db()
        self.assertIsNone(status.is_success)
        self.assertEqual(status.last_error_message, "")
        self.assertEqual(status.root_task_id, "1")
        self.assertEqual(status.parent_task_id, "2")

    def test_has_changed_1(self):
        """When hash is different, then return True"""
        status = create_character_update_status(
            character=self.character_1001, content_hash_1="abc"
        )
        self.assertTrue(status.has_changed(self.content))

    def test_has_changed_2(self):
        """When no hash exists, then return True"""
        status = create_character_update_status(
            character=self.character_1001, content_hash_1=""
        )
        self.assertTrue(status.has_changed(self.content))

    def test_has_changed_3a(self):
        """When hash is equal, then return False"""
        status = create_character_update_status(
            character=self.character_1001,
            content_hash_1=hashlib.md5(
                json.dumps(self.content).encode("utf-8")
            ).hexdigest(),
        )
        self.assertFalse(status.has_changed(self.content))

    def test_has_changed_3b(self):
        """When hash is equal, then return False"""
        status = create_character_update_status(
            character=self.character_1001,
            content_hash_2=hashlib.md5(
                json.dumps(self.content).encode("utf-8")
            ).hexdigest(),
        )
        self.assertFalse(status.has_changed(content=self.content, hash_num=2))

    def test_has_changed_3c(self):
        """When hash is equal, then return False"""
        status = create_character_update_status(
            character=self.character_1001,
            content_hash_3=hashlib.md5(
                json.dumps(self.content).encode("utf-8")
            ).hexdigest(),
        )
        self.assertFalse(status.has_changed(content=self.content, hash_num=3))

    def test_is_updating_1(self):
        """When started_at exist and finished_at does not exist, return True"""
        status = create_character_update_status(
            character=self.character_1001, started_at=now(), finished_at=None
        )
        self.assertTrue(status.is_updating)

    def test_is_updating_2(self):
        """When started_at and finished_at does not exist, return False"""
        status = create_character_update_status(
            character=self.character_1001, started_at=None, finished_at=None
        )
        self.assertFalse(status.is_updating)
