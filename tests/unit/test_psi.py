"""Per-method parity tests for tbd.psi (KHI + PSI pure-data layer).

Golden values in tests/fixtures/golden/psi.json are generated from the Ruby TBD
gem at the pinned upstream SHA by tools/gen_golden_psi.rb. Each PSI set's `set`,
`has`, and `val` dicts (and KHI.point, complete?, safe) must reproduce exactly.
"""
import json

import pytest

import tbd
from tbd import psi as psimod

from parity import GOLDEN, assert_json_close

with open(GOLDEN / "psi.json") as _f:
    GOLD = json.load(_f)

PSI_IDS = sorted(GOLD["psi"].keys())


# --- KHI ---------------------------------------------------------------------

def test_khi_defaults_match_golden():
    k = tbd.KHI()
    assert_json_close(GOLD["khi_point"], k.point)


def test_khi_append_valid():
    k = tbd.KHI()
    assert k.append({"id": "custom", "point": 0.42}) is True
    assert k.point["custom"] == pytest.approx(0.42)


def test_khi_append_rejects_non_hash():
    k = tbd.KHI()
    assert k.append(42) is False


def test_khi_append_rejects_missing_keys():
    k = tbd.KHI()
    assert k.append({"id": "x"}) is False          # no :point
    assert k.append({"point": 0.1}) is False        # no :id


def test_khi_append_rejects_empty_id():
    k = tbd.KHI()
    assert k.append({"id": "  ", "point": 0.1}) is False


def test_khi_append_rejects_duplicate():
    k = tbd.KHI()
    assert k.append({"id": "poor (BETBG)", "point": 0.1}) is False


# --- PSI defaults / gen / shorthands (golden parity per set) -----------------

def test_psi_default_set_ids():
    p = tbd.PSI()
    assert sorted(p.set.keys()) == PSI_IDS


@pytest.mark.parametrize("sid", PSI_IDS)
def test_psi_set_raw_matches_golden(sid):
    p = tbd.PSI()
    assert_json_close(GOLD["psi"][sid]["set"], p.set[sid])


@pytest.mark.parametrize("sid", PSI_IDS)
def test_psi_has_matches_golden(sid):
    """The `has` shorthand — exercises the gen() presence cascade + parity bugs."""
    p = tbd.PSI()
    assert_json_close(GOLD["psi"][sid]["has"], p.shorthands(sid)["has"])


@pytest.mark.parametrize("sid", PSI_IDS)
def test_psi_val_matches_golden(sid):
    """The `val` shorthand — exercises the full gen() inheritance + parity bugs."""
    p = tbd.PSI()
    assert_json_close(GOLD["psi"][sid]["val"], p.shorthands(sid)["val"])


@pytest.mark.parametrize("sid", PSI_IDS)
def test_psi_is_complete_matches_golden(sid):
    p = tbd.PSI()
    assert p.is_complete(sid) == GOLD["psi"][sid]["complete"]


# --- PSI.safe inheritance ----------------------------------------------------

@pytest.mark.parametrize("case", GOLD["safe"], ids=lambda c: f"{c['id']}:{c['type']}")
def test_psi_safe_matches_golden(case):
    p = tbd.PSI()
    assert p.safe(case["id"], case["type"]) == case["result"]


# --- PSI.append --------------------------------------------------------------

def test_psi_append_valid_then_gen():
    p = tbd.PSI()
    ok = p.append({"id": "custom", "rimjoist": 0.6, "parapet": 0.7})
    assert ok is True
    assert "custom" in p.set
    # gen() ran: defaulted joint/transition/ceiling to 0, derived variants.
    assert p.set["custom"]["joint"] == pytest.approx(0.0)
    assert p.shorthands("custom")["val"]["rimjoistconcave"] == pytest.approx(0.6)


def test_psi_append_rejects_duplicate():
    p = tbd.PSI()
    assert p.append({"id": "poor (BETBG)", "rimjoist": 0.1}) is False


def test_psi_append_rejects_missing_id():
    p = tbd.PSI()
    assert p.append({"rimjoist": 0.1}) is False


# --- parity-bug anchors (documented in UPSTREAM.md) --------------------------

def test_parity_bug_partyconcave_reads_parapet():
    """psi.rb:545 — has['partyconcave'] mirrors presence of 'parapetconcave'."""
    p = tbd.PSI()
    for sid in PSI_IDS:
        h = p.shorthands(sid)["has"]
        # No built-in set defines parapetconcave, so partyconcave is always False
        # despite 'party' being present — this is the preserved bug.
        assert h["partyconcave"] is False


def test_engine_functions_are_ported():
    # The engine (inputs/derate/process/exit) is ported; assert they are callable
    # and validate input (full parity lives in the e2e process/UA tests).
    assert callable(psimod.inputs)
    assert callable(psimod.derate)
    assert callable(psimod.process)
    assert callable(psimod.exit)
    # process rejects a non-Model argument (returns the sentinel, not raises).
    res = psimod.process(None, {"option": "poor (BETBG)"})
    assert res == {"io": None, "surfaces": {}}
