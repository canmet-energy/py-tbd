"""Shared parity helpers (importable by test modules).

Golden reference outputs are generated from the Ruby TBD gem (tools/gen_golden*.rb)
into tests/fixtures/golden/*.json; Python results are compared with
`assert_json_close` (tolerant on floats).
"""
import json
import math
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
OSMS_IN = FIXTURES / "osms" / "in"
JSON_DIR = FIXTURES / "json"
GOLDEN = FIXTURES / "golden"
SCHEMA = FIXTURES / "tbd.schema.json"

# Pure IEEE-754 arithmetic should match Ruby to ~machine epsilon; geometry routed
# through osut/py-topolys may accumulate to ~TBD::TOL (0.01 m).
REL_TOL = 1e-9
ABS_TOL = 1e-9


def load_osm(name):
    """Load an .osm fixture via the OpenStudio VersionTranslator (pyOSut pattern)."""
    import openstudio

    path = openstudio.path(str(OSMS_IN / name))
    translator = openstudio.osversion.VersionTranslator()
    m = translator.loadModel(path)
    assert not m.isNull(), f"could not load fixture {name}"
    return m.get()


def load_golden(name):
    with open(GOLDEN / name) as f:
        return json.load(f)


def assert_json_close(golden, actual, rel_tol=REL_TOL, abs_tol=ABS_TOL, path="$"):
    """Recursively compare two JSON-like structures (floats via math.isclose)."""
    if isinstance(golden, dict):
        assert isinstance(actual, dict), f"{path}: expected dict, got {type(actual).__name__}"
        assert set(golden) == set(actual), (
            f"{path}: key mismatch\n  only in golden: {set(golden) - set(actual)}"
            f"\n  only in actual: {set(actual) - set(golden)}"
        )
        for k in golden:
            assert_json_close(golden[k], actual[k], rel_tol, abs_tol, f"{path}.{k}")
    elif isinstance(golden, list):
        assert isinstance(actual, list), f"{path}: expected list, got {type(actual).__name__}"
        assert len(golden) == len(actual), f"{path}: length {len(golden)} != {len(actual)}"
        for i, (g, a) in enumerate(zip(golden, actual)):
            assert_json_close(g, a, rel_tol, abs_tol, f"{path}[{i}]")
    elif isinstance(golden, bool) or isinstance(actual, bool):
        assert golden == actual, f"{path}: {golden!r} != {actual!r}"
    elif isinstance(golden, (int, float)) and isinstance(actual, (int, float)):
        assert math.isclose(golden, actual, rel_tol=rel_tol, abs_tol=abs_tol), (
            f"{path}: {golden!r} != {actual!r} (rel={rel_tol}, abs={abs_tol})"
        )
    else:
        assert golden == actual, f"{path}: {golden!r} != {actual!r}"
