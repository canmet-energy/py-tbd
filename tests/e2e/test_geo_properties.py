"""End-to-end parity for tbd.properties across every .osm fixture.

Golden (tests/fixtures/golden/geo_properties.json) is produced by the Docker
generator tools/gen_golden_geo.rb running the full Ruby TBD gem with OpenStudio
3.11.0. This test runs the Python port over the same surfaces and asserts a
normalized, JSON-able descriptor reproduces the Ruby output.
"""
import json

import openstudio
import pytest
from osut import osut

import tbd
from parity import GOLDEN, OSMS_IN, assert_json_close

with open(GOLDEN / "geo_properties.json") as _f:
    GEO = json.load(_f)

# Geometry flows through OpenStudio + osut (Ruby osut 0.9.1 vs Python 0.9.0);
# both use IEEE-754 doubles and the same SDK, so values match tightly.
REL = 1e-9
ABS = 1e-9


def _xyz(v):
    x = v.x() if callable(getattr(v, "x")) else v.x
    y = v.y() if callable(getattr(v, "y")) else v.y
    z = v.z() if callable(getattr(v, "z")) else v.z
    return [x, y, z]


def _norm_sub(sub):
    h = {
        "type": sub["type"],
        "gross": sub["gross"],
        "area": sub["area"],
        "mult": sub["mult"],
        "u": sub["u"],
        "unhinged": sub["unhinged"],
        "n": _xyz(sub["n"]),
        "minz": sub["minz"],
        "points": [_xyz(p) for p in sub["points"]],
    }
    if sub.get("glazed"):
        h["glazed"] = True
    return h


def _norm_surf(surf):
    h = {
        "type": surf["type"],
        "boundary": surf["boundary"],
        "ground": surf["ground"],
        "conditioned": surf["conditioned"],
        "occupied": surf["occupied"],
        "spandrel": surf["spandrel"],
        "gross": surf["gross"],
        "net": surf["net"],
        "filmRSI": surf["filmRSI"],
        "minz": surf["minz"],
        # r / index / ltype are only set when the surface has a valid insulating
        # layer. When absent, Ruby's hash access yields nil (JSON null), so mirror
        # that with .get() rather than assuming the keys exist.
        "r": surf.get("r"),
        "index": surf.get("index"),
        "ltype": surf.get("ltype"),
        "space": surf["space"].nameString(),
        "n": _xyz(surf["n"]),
        "points": [_xyz(p) for p in surf["points"]],
    }
    if "heating" in surf:
        h["heating"] = surf["heating"]
    if "cooling" in surf:
        h["cooling"] = surf["cooling"]
    if "construction" in surf:
        h["construction"] = surf["construction"].nameString()
    if "stype" in surf:
        h["stype"] = surf["stype"].nameString()
    if "story" in surf:
        h["story"] = surf["story"].nameString()
    for k in ("windows", "doors", "skylights"):
        if k in surf:
            h[k] = {sid: _norm_sub(sub) for sid, sub in surf[k].items()}
    return h


def _load(name):
    path = openstudio.path(str(OSMS_IN / name))
    m = openstudio.osversion.VersionTranslator().loadModel(path)
    assert not m.isNull(), name
    return m.get()


@pytest.mark.parametrize("model_name", sorted(GEO.keys()))
def test_properties_parity(model_name):
    golden = GEO[model_name]
    model = _load(model_name)

    heat = osut.hasHeatingTemperatureSetpoints(model)
    cool = osut.hasCoolingTemperatureSetpoints(model)
    setpts = heat or cool
    assert setpts == golden["setpoints"], f"{model_name}: setpoints flag differs"

    actual = {}
    for s in sorted(model.getSurfaces(), key=lambda x: x.nameString()):
        props = tbd.properties(s, {"setpoints": setpts})
        if props is None:
            continue
        actual[s.nameString()] = _norm_surf(props)

    # Same set of non-None surfaces.
    assert set(actual.keys()) == set(golden["surfaces"].keys()), (
        f"{model_name}: surface set differs\n"
        f"  only python: {set(actual) - set(golden['surfaces'])}\n"
        f"  only ruby:   {set(golden['surfaces']) - set(actual)}"
    )
    for sid, gsurf in golden["surfaces"].items():
        assert_json_close(gsurf, actual[sid], rel_tol=REL, abs_tol=ABS, path=f"{model_name}.{sid}")
