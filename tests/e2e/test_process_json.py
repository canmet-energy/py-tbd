"""End-to-end parity for process() driven by TBD JSON inputs and by uprating.

Golden (tests/fixtures/golden/process_json.json) is produced by the Docker
generator tools/gen_golden_process_json.rb. These cases exercise the paths the
plain process golden does not: JSON input parsing, per-surface/subsurface/edge/
KHI overrides, and construction uprating (uprate + uo) before derating.
"""
import json

import openstudio
import pytest

import tbd
from parity import GOLDEN, OSMS_IN, JSON_DIR, assert_json_close

with open(GOLDEN / "process_json.json") as _f:
    CASES = json.load(_f)

REL = 1e-6
ABS = 1e-6

# label -> (model file, argh). Mirrors the Ruby harness exactly.
CONFIG = {
    "warehouse10": ("warehouse.osm", {"option": "poor (BETBG)", "io_path": "tbd_warehouse10.json"}),
    "warehouse4": ("warehouse.osm", {"option": "poor (BETBG)", "io_path": "tbd_warehouse4.json"}),
    "warehouse17": ("warehouse.osm", {"option": "poor (BETBG)", "io_path": "tbd_warehouse17.json"}),
    "warehouse18": ("warehouse.osm", {"option": "poor (BETBG)", "io_path": "tbd_warehouse18.json"}),
    "seb_n2": ("seb.osm", {"option": "poor (BETBG)", "io_path": "tbd_seb_n2.json"}),
    "seb_n4": ("seb.osm", {"option": "poor (BETBG)", "io_path": "tbd_seb_n4.json"}),
    "5zone": ("5ZoneNoHVAC.osm", {"option": "poor (BETBG)", "io_path": "tbd_5ZoneNoHVAC.json"}),
    "uprate_walls": ("warehouse.osm", {
        "option": "poor (BETBG)", "uprate_walls": True,
        "wall_ut": 0.210, "wall_option": "all wall constructions",
    }),
}


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
        "psi": e["psi"], "type": e["type"], "length": _rnd(e["length"]),
        "surfaces": sorted(e["surfaces"]),
        "v0": [_rnd(e["v0x"], 4), _rnd(e["v0y"], 4), _rnd(e["v0z"], 4)],
        "v1": [_rnd(e["v1x"], 4), _rnd(e["v1y"], 4), _rnd(e["v1z"], 4)],
    }


def _load(name):
    path = openstudio.path(str(OSMS_IN / name))
    m = openstudio.osversion.VersionTranslator().loadModel(path)
    assert not m.isNull(), name
    return m.get()


@pytest.mark.parametrize("label", sorted(CASES.keys()))
def test_process_json_parity(label):
    golden = CASES[label]
    model_file, argh = CONFIG[label]
    argh = dict(argh)
    if "io_path" in argh:
        argh["io_path"] = str(JSON_DIR / argh["io_path"])

    tbd.oslg.clean()
    res = tbd.process(_load(model_file), argh)

    actual_surfaces = {k: _norm_surf(v) for k, v in res["surfaces"].items()}
    assert set(actual_surfaces) == set(golden["surfaces"]), f"{label}: surface set differs"
    for sid, gs in golden["surfaces"].items():
        assert_json_close(gs, actual_surfaces[sid], rel_tol=REL, abs_tol=ABS, path=f"{label}.{sid}")

    io_edges = (res["io"] or {}).get("edges", [])
    actual_edges = sorted((_norm_edge(e) for e in io_edges), key=lambda e: (e["v0"], e["v1"], e["type"]))
    assert len(actual_edges) == len(golden["edges"]), f"{label}: edge count differs"
    for i, (ge, ae) in enumerate(zip(golden["edges"], actual_edges)):
        assert_json_close(ge, ae, rel_tol=REL, abs_tol=ABS, path=f"{label}.edge[{i}]")

    # Uprated area-weighted Uo, when applicable.
    for key in ("wall_uo", "roof_uo", "floor_uo"):
        if key in golden:
            assert argh.get(key) == pytest.approx(golden[key], rel=REL, abs=ABS), f"{label}.{key}"
