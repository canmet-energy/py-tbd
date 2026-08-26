"""End-to-end parity for the Topolys graph builders (objects/kids/dads/faces).

For each .osm fixture we reproduce the pre-classification stage of process():
build a per-surface descriptor with tbd.properties, add every surface (and its
subsurfaces) to ONE Topolys model with tbd.dads, then collect edges with
tbd.faces. The resulting edge graph is compared to the Ruby gold produced by
tools/gen_golden_edges.rb.

Topolys edge IDs are non-deterministic UUIDs, so both sides are keyed by edge
GEOMETRY: the pair of endpoint coordinates, rounded and order-independent. Each
edge contributes its length and the sorted set of surfaces it touches.
"""
import json

import openstudio
import pytest
from osut import osut

import tbd
from parity import GOLDEN, OSMS_IN

with open(GOLDEN / "geo_edges.json") as _f:
    EDGES = json.load(_f)


def _norm_coord(c):
    """Round to 0.1 mm and fold -0.0 into 0.0 so keys are canonical."""
    c = round(c, 4)
    return 0.0 if c == 0 else c


def _canon_key(pair):
    """Order-independent tuple key from a [[x,y,z],[x,y,z]] endpoint pair."""
    pts = tuple(tuple(_norm_coord(c) for c in pt) for pt in pair)
    return tuple(sorted(pts))


def _golden_graph(model_name):
    """Re-key the Ruby golden (JSON-string keys) by canonical numeric tuples."""
    out = {}
    for k, v in EDGES[model_name].items():
        out[_canon_key(json.loads(k))] = v
    return out


def _load(name):
    path = openstudio.path(str(OSMS_IN / name))
    m = openstudio.osversion.VersionTranslator().loadModel(path)
    assert not m.isNull(), name
    return m.get()


def _python_graph(model):
    """Run properties -> dads -> faces and key the edges by geometry."""
    import py_topolys

    setpts = osut.hasHeatingTemperatureSetpoints(model) or osut.hasCoolingTemperatureSetpoints(model)

    surfaces = {}
    for s in sorted(model.getSurfaces(), key=lambda x: x.nameString()):
        props = tbd.properties(s, {"setpoints": setpts})
        if props is not None:
            surfaces[s.nameString()] = props

    # One shared Topolys model so coincident edges are deduplicated via vertices.
    t_model = py_topolys.Model()
    tbd.dads(t_model, surfaces)

    edges = {}
    tbd.faces(surfaces, edges)

    graph = {}
    for e in edges.values():
        # edge v0/v1 are py_topolys Vertices; .point gives the Point3D.
        a, b = e["v0"].point, e["v1"].point
        key = _canon_key([[a.x, a.y, a.z], [b.x, b.y, b.z]])
        graph[key] = {
            "length": round(e["length"], 6),
            "surfaces": sorted(e["surfaces"].keys()),
        }
    return graph


@pytest.mark.parametrize("model_name", sorted(EDGES.keys()))
def test_edge_graph_parity(model_name):
    golden = _golden_graph(model_name)
    actual = _python_graph(_load(model_name))

    # Same set of geometric edges.
    assert set(actual.keys()) == set(golden.keys()), (
        f"{model_name}: edge set differs "
        f"(python {len(actual)} vs ruby {len(golden)}); "
        f"only-python={len(set(actual) - set(golden))} "
        f"only-ruby={len(set(golden) - set(actual))}"
    )

    for key, g in golden.items():
        a = actual[key]
        assert a["surfaces"] == g["surfaces"], f"{model_name} edge {key}: surfaces {a['surfaces']} != {g['surfaces']}"
        assert abs(a["length"] - g["length"]) < 1e-6, f"{model_name} edge {key}: length {a['length']} != {g['length']}"
