"""End-to-end parity for the UA' report path (qc33 + ua_summary + ua_md).

Golden (tests/fixtures/golden/ua_report.json) is produced by the Docker generator
tools/gen_golden_ua_report.rb, which runs the Ruby gem's process + ua_summary +
ua_md with a pinned date. The Python port must reproduce every Markdown line.

The single "* date :" line is excluded from the comparison: Ruby renders a Time
and Python a datetime, whose string forms differ by design. Everything else —
section headers, bilingual labels, per-category W/K figures and percentages,
area strings — must match exactly.
"""
import datetime
import json

import openstudio
import pytest

import tbd
from parity import GOLDEN, OSMS_IN

with open(GOLDEN / "ua_report.json") as _f:
    REPORT = json.load(_f)

# Same instant the Ruby harness pinned (Time.utc(2026,1,1)).
PINNED = datetime.datetime(2026, 1, 1, 0, 0, 0)


def _strip_date(lines):
    """Drop the one non-deterministic date line from a report."""
    return [ln for ln in lines if not ln.startswith("* date :")]


def _load(name):
    path = openstudio.path(str(OSMS_IN / name))
    m = openstudio.osversion.VersionTranslator().loadModel(path)
    assert not m.isNull(), name
    return m.get()


@pytest.mark.parametrize("model_name", sorted(REPORT.keys()))
def test_ua_report_parity(model_name):
    tbd.oslg.clean()
    model = _load(model_name)
    argh = {
        "option": "code (Quebec)",
        "gen_ua": True,
        "ua_ref": "code (Quebec)",
        "seed": model_name,
        "version": "",
    }
    tbd.process(model, argh)
    ua = tbd.ua_summary(PINNED, argh)
    assert ua, f"{model_name}: empty ua_summary"

    for lang in ("en", "fr"):
        actual = tbd.ua_md(ua, lang)
        golden = REPORT[model_name][lang]
        assert _strip_date(actual) == _strip_date(golden), (
            f"{model_name}/{lang}: UA' report mismatch"
        )
