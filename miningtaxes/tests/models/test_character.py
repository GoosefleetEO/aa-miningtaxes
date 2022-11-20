import datetime

from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter
from app_utils.testing import NoSocketsTestCase

from ...models import OrePrices
from ..testdata.load_entities import load_entities
from ..testdata.load_eveuniverse import load_eveuniverse
from ..utils import create_character, create_miningtaxes_character


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
        character_1001.give_credit(1234)
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
