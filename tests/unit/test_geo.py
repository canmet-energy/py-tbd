"""Per-method parity tests for tbd.geo.

Pure-topology methods (matches/is_concave/is_convex) are checked against golden
outputs generated from the Ruby gem by tools/gen_golden_geo_pure.rb. Each golden
case carries its numeric inputs, which we rebuild as py_topolys objects here so
the Python and Ruby sides evaluate identical geometry.

OpenStudio-backed methods (tru_normal, reset_kiva) are exercised directly against
OpenStudio models; their cross-language golden parity lands with the Docker-based
generator alongside the heavy methods (properties/dads/kids/kiva).
"""
import json

import openstudio
import py_topolys as T
import pytest

import tbd
from tbd import geo as geomod

from parity import GOLDEN

with open(GOLDEN / "geo_pure.json") as _f:
    GEO = json.load(_f)


def _pt(a):
    return T.Point3D(a[0], a[1], a[2])


def _vec(a):
    return T.Vector3D(a[0], a[1], a[2])


def _s(h):
    return {"angle": h["angle"], "normal": _vec(h["normal"]), "polar": _vec(h["polar"])}


# --- matches -----------------------------------------------------------------

@pytest.mark.parametrize("case", GEO["matches"], ids=lambda c: str(c["result"]))
def test_matches_parity(case):
    e1 = {"v0": _pt(case["e1"][0]), "v1": _pt(case["e1"][1])}
    e2 = {"v0": _pt(case["e2"][0]), "v1": _pt(case["e2"][1])}
    assert tbd.matches(e1, e2, case["tol"]) == case["result"]


def test_matches_invalid_inputs():
    assert tbd.matches(42, {}) is False
    assert tbd.matches({"v0": _pt([0, 0, 0])}, {"v0": _pt([0, 0, 0]), "v1": _pt([1, 0, 0])}) is False


# --- is_concave / is_convex --------------------------------------------------

@pytest.mark.parametrize("case", GEO["concave"], ids=lambda c: str(c["result"]))
def test_is_concave_parity(case):
    assert tbd.is_concave(_s(case["s1"]), _s(case["s2"])) == case["result"]


@pytest.mark.parametrize("case", GEO["convex"], ids=lambda c: str(c["result"]))
def test_is_convex_parity(case):
    assert tbd.is_convex(_s(case["s1"]), _s(case["s2"])) == case["result"]


def test_concave_convex_identical_surfaces_false():
    s = _s({"angle": 0.3, "normal": [1, 0, 0], "polar": [0, 1, 0]})
    assert tbd.is_concave(s, dict(s)) is False
    assert tbd.is_convex(s, dict(s)) is False


# --- objects / faces (Topolys wiring) ----------------------------------------

def test_objects_builds_vertices_and_wire():
    m = T.Model()
    pts = [_pt([0, 0, 0]), _pt([1, 0, 0]), _pt([1, 1, 0]), _pt([0, 1, 0])]
    obj = tbd.objects(m, pts)
    assert obj["vx"] is not None and len(obj["vx"]) == 4
    assert obj["w"] is not None


def test_objects_invalid_model():
    obj = tbd.objects(None, [])
    assert obj == {"vx": None, "w": None}


# --- tru_normal (OpenStudio) -------------------------------------------------

def test_tru_normal_flat_roof():
    m = openstudio.model.Model()
    srf = openstudio.model.Surface(
        [openstudio.Point3d(0, 0, 3), openstudio.Point3d(1, 0, 3), openstudio.Point3d(1, 1, 3)], m
    )
    n = tbd.tru_normal(srf, 0)
    assert (round(n.x, 6), round(n.y, 6), round(n.z, 6)) == (0.0, 0.0, 1.0)


def test_tru_normal_invalid():
    assert tbd.tru_normal(None, 0) is None


# --- reset_kiva --------------------------------------------------------------

def test_reset_kiva_empty_model():
    m = openstudio.model.Model()
    assert tbd.reset_kiva(m) is True


def test_reset_kiva_invalid_boundary():
    m = openstudio.model.Model()
    assert tbd.reset_kiva(m, "Zog") is False


# --- not-yet-ported heavy methods --------------------------------------------

def test_kiva_invalid_inputs():
    # Full KIVA parity is exercised via process() in Phase 4 (it needs classified
    # edges + foundation surfaces). Here we cover the input-validation contract.
    assert tbd.kiva(None) is False           # not a model
    m = openstudio.model.Model()
    assert tbd.kiva(m, walls=42) is False     # walls not a dict


def test_kiva_no_foundation_surfaces_is_noop():
    # An empty model has no foundation-facing surfaces, so kiva succeeds trivially
    # (no KIVA objects created).
    m = openstudio.model.Model()
    assert tbd.kiva(m, {}, {}, {}) is True
    assert len(m.getFoundationKivas()) == 0

