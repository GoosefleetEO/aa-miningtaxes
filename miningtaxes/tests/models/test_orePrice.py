from django.utils.timezone import now
from eveuniverse.models import EveType, EveTypeMaterial

from app_utils.testing import NoSocketsTestCase

from ...models import OrePrices, Settings, get_price, get_tax, ore_calc_prices
from ..testdata.load_eveuniverse import load_eveuniverse


class TestOrePrice(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_eveuniverse()

    def test_ore_calc_price(self):
        n = now()
        a = OrePrices(eve_type_id=45511, buy=10, sell=100, updated=n)  # Monazite
        a.calc_prices()
        self.assertEqual(a.buy, 10)
        self.assertEqual(a.sell, 100)
        self.assertEqual(a.raw_price, 10)
        self.assertEqual(a.refined_price, 10)
        self.assertEqual(a.taxed_price, 10)

    def test_ore_calc_prices2(self):
        n = now()
        b = EveType(eve_group_id=1920, id=16635, published=True, portion_size=1)
        b.save()
        EveTypeMaterial(
            eve_type_id=45511, material_eve_type_id=16635, quantity=3
        ).save()
        OrePrices(eve_type_id=16635, buy=20, sell=200, updated=n).save()
        a = OrePrices(eve_type_id=45511, buy=10, sell=100, updated=n)  # Monazite
        a.calc_prices()
        self.assertEqual(get_price(b), 20)
        self.assertEqual(a.buy, 10)
        self.assertEqual(a.sell, 100)
        self.assertEqual(a.raw_price, 10)
        self.assertEqual(a.refined_price, 0.54378)  # 0.9063 x 3 x 20 / 100
        self.assertEqual(a.taxed_price, 10)

    def test_ore_calc_prices3(self):
        n = now()
        b = EveType(eve_group_id=1920, id=16635, published=True, portion_size=1)
        b.save()
        EveTypeMaterial(
            eve_type_id=45511, material_eve_type_id=16635, quantity=3
        ).save()
        OrePrices(eve_type_id=16635, buy=2000, sell=200, updated=n).save()
        a = OrePrices(eve_type_id=45511, buy=10, sell=100, updated=n)  # Monazite
        a.calc_prices()
        self.assertEqual(get_price(b), 2000)
        self.assertEqual(a.buy, 10)
        self.assertEqual(a.sell, 100)
        self.assertEqual(a.raw_price, 10)
        self.assertEqual(a.refined_price, 54.378)  # 0.9063 x 3 x 2000 / 100
        self.assertEqual(a.taxed_price, 54.378)

    def test_calc_prices(self):
        n = now()
        a = OrePrices(eve_type_id=45511, buy=10, sell=100, updated=n)  # Monazite
        a.calc_prices()
        b = EveType.objects.get(id=45511)
        prices = ore_calc_prices(b, 20)
        self.assertEqual(prices[0], 200)
        self.assertEqual(prices[1], 200)
        self.assertEqual(prices[2], 200)

    def test_calc_prices2(self):
        n = now()
        b = EveType(eve_group_id=1920, id=16635, published=True, portion_size=1)
        b.save()
        EveTypeMaterial(
            eve_type_id=45511, material_eve_type_id=16635, quantity=3
        ).save()
        OrePrices(eve_type_id=16635, buy=20, sell=200, updated=n).save()
        a = OrePrices(eve_type_id=45511, buy=10, sell=100, updated=n)  # Monazite
        a.calc_prices()
        b = EveType.objects.get(id=45511)
        prices = ore_calc_prices(b, 20)
        self.assertEqual(prices[0], 200)
        self.assertEqual(prices[1], 10.8756)
        self.assertEqual(prices[2], 200)

    def test_get_tax_rates(self):
        s = Settings.load()
        s.tax_R64 = 90
        s.tax_R32 = 80
        s.tax_R16 = 70
        s.tax_R8 = 60
        s.tax_R4 = 50
        s.tax_Gasses = 40
        s.tax_Ice = 30
        s.tax_Mercoxit = 20
        s.tax_Ores = 15
        s.save()

        a = EveType.objects.get(id=45511)
        self.assertEqual(get_tax(a), 0.9)

        a = EveType.objects.get(id=45503)
        self.assertEqual(get_tax(a), 0.8)

        a = EveType.objects.get(id=45501)
        self.assertEqual(get_tax(a), 0.7)

        a = EveType.objects.get(id=45496)
        self.assertEqual(get_tax(a), 0.6)

        a = EveType.objects.get(id=45492)
        self.assertEqual(get_tax(a), 0.5)

        a = EveType.objects.get(id=28695)
        self.assertEqual(get_tax(a), 0.4)

        a = EveType.objects.get(id=16267)
        self.assertEqual(get_tax(a), 0.3)

        a = EveType.objects.get(id=11396)
        self.assertEqual(get_tax(a), 0.2)

        a = EveType.objects.get(id=1230)
        self.assertEqual(get_tax(a), 0.15)
