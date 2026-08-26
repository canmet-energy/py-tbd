"""Parity for TBD.uo (construction uprating numeric core).

Golden (tests/fixtures/golden/uo.json) is generated from the Ruby gem by
tools/gen_golden_uo.rb. Each case defines a construction from explicit material
specs; we rebuild the identical construction here, run tbd.uo, and check that the
returned Uo and the resulting construction RSi match the Ruby result.
"""
import json

import openstudio
import pytest
from osut import osut

import tbd
from parity import GOLDEN

with open(GOLDEN / "uo.json") as _f:
    UO = json.load(_f)["uo"]


def _build(model, name, layers):
    """Rebuild the construction from the same layer specs the Ruby harness used."""
    lc = openstudio.model.Construction(model)
    lc.setName(name)
    mats = []
    for i, ly in enumerate(layers):
        if ly["type"] == "massless":
            m = openstudio.model.MasslessOpaqueMaterial(model, "Smooth", ly["r"])
        else:
            m = openstudio.model.StandardOpaqueMaterial(model)
            m.setThickness(ly["d"])
            m.setConductivity(ly["k"])
        m.setName("%s L%d" % (name, i))
        mats.append(m)
    # OpenStudio Python needs a typed vector for setLayers.
    vec = openstudio.model.MaterialVector()
    for m in mats:
        vec.append(m)
    lc.setLayers(vec)
    return lc


@pytest.mark.parametrize("case", UO, ids=lambda c: c["id"])
def test_uo_parity(case):
    model = openstudio.model.Model()
    lc = _build(model, case["id"], case["layers"])
    u = tbd.uo(case["id"], lc, case["area"], case["film"], case["hloss"], case["ut"])
    assert u == pytest.approx(case["result_uo"], rel=1e-9, abs=1e-9)
    # The final construction RSi captures the layer mutation uo performed.
    assert osut.rsi(lc, case["film"]) == pytest.approx(case["final_rsi"], rel=1e-9, abs=1e-9)
