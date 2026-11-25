"""A requirement that names a missing test is itself a failure."""
import re
from pathlib import Path

from vmdt.requirements_trace import REQUIREMENTS


def test_every_requirement_names_real_tests():
    source = (Path(__file__).parent / "test_engine.py").read_text()
    defined = set(re.findall(r"^def (test_\w+)", source, flags=re.M))
    for req in REQUIREMENTS:
        assert req["tests"], req["id"]
        missing = set(req["tests"]) - defined
        assert not missing, f"{req['id']} names tests that do not exist: {missing}"
