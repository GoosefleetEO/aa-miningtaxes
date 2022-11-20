import inspect
import json
import os

from eveuniverse.tools.testdata import load_testdata_from_dict

_currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))


def _load_eveuniverse_from_file():
    with open(_currentdir + "/eveuniverse.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def load_eveuniverse():
    load_testdata_from_dict(_load_eveuniverse_from_file())
