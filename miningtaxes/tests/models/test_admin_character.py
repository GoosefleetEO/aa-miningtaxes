from unittest.mock import patch

from allianceauth.eveonline.models import EveCharacter
from app_utils.testing import NoSocketsTestCase, add_new_token

from ...models import AdminCharacter
from ..testdata.esi_client_stub import esi_client_stub
from ..testdata.load_entities import load_entities
from ..testdata.load_eveuniverse import load_eveuniverse
from ..utils import create_character, create_miningtaxes_admincharacter

MODELS_PATH = "miningtaxes.models"


class TestAdminCharacter(NoSocketsTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        load_eveuniverse()
        load_entities()

    def test_user_should_return_user_when_not_orphan(self):
        # given
        character_1001 = create_miningtaxes_admincharacter(1001)
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
        character_1001 = create_miningtaxes_admincharacter(1001)
        user = character_1001.eve_character.character_ownership.user
        main_character = user.profile.main_character
        # when/then
        self.assertEqual(character_1001.main_character, main_character)

    @patch(MODELS_PATH + ".admin.esi")
    def test_corp_ledger(self, mock_esi):
        mock_esi.client = esi_client_stub
        # given
        character_1001 = create_miningtaxes_admincharacter(1001)
        user = character_1001.eve_character.character_ownership.user
        add_new_token(
            user, character_1001.eve_character, AdminCharacter.get_esi_scopes()
        )
        # when/then
        character_1001.update_all()
        ledger = character_1001.corp_ledger.all()
        self.assertEqual(len(ledger), 1)
        entry = ledger[0]
        self.assertEqual(entry.amount, 987654321)
        self.assertEqual(entry.reason, "")
        self.assertEqual(entry.taxed_id, 1001)

        observers = character_1001.mining_obs.all()
        self.assertEqual(len(observers), 1)
        obs = observers[0]
        self.assertEqual(obs.obs_id, 123456789)
        self.assertEqual(obs.name, "Amamake - Test Structure Alpha")
        self.assertEqual(obs.sys_name, "Amamake")

        mining_ledger = obs.mining_log.all()
        self.assertEqual(len(mining_ledger), 1)
        entry = mining_ledger[0]
        self.assertEqual(entry.miner_id, 1001)
        self.assertEqual(entry.quantity, 100)
        self.assertEqual(entry.eve_type_id, 45511)
