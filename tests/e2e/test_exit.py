"""Integration coverage for tbd.exit (library mode, no OpenStudio runner).

exit() is mostly serialization + runner registration. In library mode the runner
is None, so we drive process() then exit() and assert the on-disk tbd.out.json is
well-formed and reflects the run (log block, schema, and — when requested —
per-surface edges), plus that the bilingual UA reports are emitted.
"""
import json

import openstudio

import tbd
from parity import OSMS_IN


def _load(name):
    path = openstudio.path(str(OSMS_IN / name))
    m = openstudio.osversion.VersionTranslator().loadModel(path)
    assert not m.isNull(), name
    return m.get()


def test_exit_writes_tbd_out_json(tmp_path):
    tbd.oslg.clean()
    argh = {"option": "poor (BETBG)", "seed": "warehouse.osm"}
    tbd.process(_load("warehouse.osm"), argh)
    ok = tbd.exit(None, argh, out_dir=str(tmp_path))
    assert ok is True

    out = tmp_path / "tbd.out.json"
    assert out.exists()
    io = json.loads(out.read_text())
    # Deterministic key order puts schema/description/log first; log carries state.
    assert io["schema"].endswith("tbd.schema.json")
    assert "log" in io and "date" in io["log"] and "status" in io["log"]
    # Non-detailed output prunes the bulky sections by default.
    assert "edges" not in io


def test_exit_write_tbd_keeps_edges(tmp_path):
    tbd.oslg.clean()
    argh = {"option": "poor (BETBG)", "seed": "warehouse.osm", "write_tbd": True}
    tbd.process(_load("warehouse.osm"), argh)
    tbd.exit(None, argh, out_dir=str(tmp_path))
    io = json.loads((tmp_path / "tbd.out.json").read_text())
    assert "edges" in io and len(io["edges"]) > 0


def test_exit_emits_ua_reports(tmp_path):
    tbd.oslg.clean()
    argh = {
        "option": "code (Quebec)", "gen_ua": True,
        "ua_ref": "code (Quebec)", "seed": "seb.osm",
    }
    tbd.process(_load("seb.osm"), argh)
    tbd.exit(None, argh, out_dir=str(tmp_path))
    assert (tmp_path / "ua_en.md").exists()
    assert (tmp_path / "ua_fr.md").exists()
    assert (tmp_path / "ua_en.md").read_text().startswith("# COMPLIANCE ASSESSMENT")
