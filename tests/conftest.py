import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "spec"


@pytest.fixture(scope="session")
def vectors():
	return json.loads((SPEC / "vectors.json").read_text())


@pytest.fixture(scope="session")
def field_vectors():
	return json.loads((SPEC / "field_vectors.json").read_text())


@pytest.fixture(scope="session")
def factory_slots():
	return json.loads((SPEC / "device_factory_defaults.json").read_text())["slots"]
