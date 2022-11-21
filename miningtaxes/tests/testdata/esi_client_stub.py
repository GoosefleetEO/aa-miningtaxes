import inspect
import json
import os

from app_utils.esi_testing import EsiClientStub, EsiEndpoint

_currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
_FILENAME_ESI_TESTDATA = "esi_testdata.json"


def load_test_data():
    with open(f"{_currentdir}/{_FILENAME_ESI_TESTDATA}", "r", encoding="utf-8") as f:
        return json.load(f)


_endpoints = [
    EsiEndpoint(
        "Industry",
        "get_characters_character_id_mining",
        "character_id",
        needs_token=True,
    ),
    EsiEndpoint(
        "Industry",
        "get_corporation_corporation_id_mining_observers",
        "corporation_id",
        needs_token=True,
    ),
    EsiEndpoint(
        "Industry",
        "get_corporation_corporation_id_mining_observers_observer_id",
        ("corporation_id", "observer_id"),
        needs_token=True,
    ),
    EsiEndpoint(
        "Universe",
        "get_universe_structures_structure_id",
        "structure_id",
        needs_token=True,
    ),
    EsiEndpoint(
        "Wallet",
        "get_corporations_corporation_id_wallets_division_journal",
        ("corporation_id", "division"),
        needs_token=True,
    ),
]

esi_client_stub = EsiClientStub(load_test_data(), endpoints=_endpoints)
esi_client_error_stub = EsiClientStub(
    load_test_data(), endpoints=_endpoints, http_error=True
)
