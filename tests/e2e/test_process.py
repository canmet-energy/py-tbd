"""End-to-end parity for TBD.process (the core derating engine).

Golden (tests/fixtures/golden/process.json) is produced by the Docker generator
tools/gen_golden_process.rb running the full Ruby gem with the "poor (BETBG)" PSI
set. This test runs the Python port over the same fixtures and asserts that the
per-surface derating (heat loss / ratio / U) and the serialized edge list match.
"""
import json

import openstudio
import pytest

import tbd
from parity import GOLDEN, OSMS_IN, assert_json_close

with open(GOLDEN / "process.json") as _f:
    PROC = json.load(_f)

REL = 1e-6
ABS = 1e-6


def _rnd(x, n=6):
    return round(x, n) if isinstance(x, (int, float)) and not isinstance(x, bool) else x


def _norm_surf(s):
    h = {"deratable": s["deratable"]}
    if "heatloss" in s:
        h["heatloss"] = _rnd(s["heatloss"])
    if "ratio" in s:
        h["ratio"] = _rnd(s["ratio"])
    if "u" in s:
        h["u"] = _rnd(s["u"])
    return h


def _norm_edge(e):
    return {
        "psi": e["psi"],
        "type": e["type"],
        "length": _rnd(e["length"]),
        "surfaces": sorted(e["surfaces"]),
        "v0": [_rnd(e["v0x"], 4), _rnd(e["v0y"], 4), _rnd(e["v0z"], 4)],
        "v1": [_rnd(e["v1x"], 4), _rnd(e["v1y"], 4), _rnd(e["v1z"], 4)],
    }


def _load(name):
    path = openstudio.path(str(OSMS_IN / name))
    m = openstudio.osversion.VersionTranslator().loadModel(path)
    assert not m.isNull(), name
    return m.get()


@pytest.mark.parametrize("model_name", sorted(PROC.keys()))
def test_process_parity(model_name):
    golden = PROC[model_name]
    model = _load(model_name)
    res = tbd.process(model, {"option": "poor (BETBG)"})

    # --- per-surface derating ---
    actual_surfaces = {k: _norm_surf(v) for k, v in res["surfaces"].items()}
    assert set(actual_surfaces) == set(golden["surfaces"]), f"{model_name}: surface set differs"
    for sid, gs in golden["surfaces"].items():
        assert_json_close(gs, actual_surfaces[sid], rel_tol=REL, abs_tol=ABS, path=f"{model_name}.{sid}")

    # --- serialized edges (sorted by geometry, order-independent) ---
    io_edges = (res["io"] or {}).get("edges", [])
    actual_edges = sorted((_norm_edge(e) for e in io_edges), key=lambda e: (e["v0"], e["v1"], e["type"]))
    assert len(actual_edges) == len(golden["edges"]), (
        f"{model_name}: edge count {len(actual_edges)} != {len(golden['edges'])}"
    )
    for i, (ge, ae) in enumerate(zip(golden["edges"], actual_edges)):
        assert_json_close(ge, ae, rel_tol=REL, abs_tol=ABS, path=f"{model_name}.edge[{i}]")
