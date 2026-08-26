# Changelog

All notable changes to `py-tbd` are documented here.

## [Unreleased]

### Added
- Project scaffold: package layout, `pyproject.toml`, dependency pins, upstream
  tracking (`UPSTREAM.md`, `version.py` SHA pin).
- Port targets Ruby TBD `3.6.0` (commit `dd6f12f8`).
- **psi.py pure-data core**: `KHI` and `PSI` classes fully ported —
  `KHI(point/append)`, `PSI(set/has/val/gen/append/shorthands/is_complete/safe)`.
- Golden generator `tools/gen_golden_psi.rb` (runs the Ruby gem against oslg/osut
  with an OpenStudio stub) + `tests/unit/test_psi.py`: 84 tests, per-set golden
  parity for all 16 PSI sets and 14 KHI factors. All passing.
- Seven upstream bugs/warnings catalogued in `UPSTREAM.md` for reporting to authors.

- **geo.py (complete)**: all 11 methods ported — `matches`, `objects`, `faces`,
  `tru_normal`, `is_concave`, `is_convex`, `reset_kiva`, `properties`, `kids`,
  `dads`, `kiva`.
  - Pure-topology parity (`matches`/`is_concave`/`is_convex`) via
    `tools/gen_golden_geo_pure.rb`.
  - **Docker golden generators** (`tools/gen_golden_geo.rb`,
    `gen_golden_edges.rb`, run via `tools/run_golden.sh`) execute the full Ruby
    TBD gem with real OpenStudio 3.11.0.
  - `test_geo_properties.py`: `properties` parity for **439 surfaces across all 9
    fixtures** — exact match.
  - `test_geo_edges.py`: `objects`/`kids`/`dads`/`faces` parity via the geometry-
    keyed **edge graph across all 9 fixtures** (up to 356 edges) — exact match.
  - `kiva` ported; full parity is exercised via `process()` in Phase 4.
- **Dependency compatibility shim** (`src/tbd/_compat.py`): corrects two pyOSut
  0.9.0 bugs in `insulatingLayer` (D1 NameError, D2 wrong RMIN/DMIN/KMAX
  thresholds) so the port matches the canonical Ruby osut. Version/behaviour
  guarded. Both documented in `UPSTREAM.md` "Dependency bugs".
- Full suite: **128 tests passing**. Upstream findings: 10 TBD + 2 pyOSut.

- **ua.py (complete)**: `uo`, `uprate`, `qc33`, `ua_summary`, `ua_md` ported
  (bilingual EN/FR reporting). `uo` numeric core verified against a Ruby golden
  (`tools/gen_golden_uo.rb` + `test_ua_uo.py`, 5 cases). `uprate`/`qc33`/
  `ua_summary`/`ua_md` are validated end-to-end via `process`/`exit` in Phase 4.
- **Third pyOSut shim** (`_compat.py::_rsi_fixed`): corrects `osut.rsi` (D3), which
  crashed on any massless layer. Documented in `UPSTREAM.md`.
- Full suite: **133 tests passing**. Upstream findings: 10 TBD + 3 pyOSut.

- **Engine (complete)**: `inputs`, `derate`, `process` (~1600-line core) and
  `exit` ported. `process` classifies edges, distributes bridge heat loss,
  optionally uprates then derates constructions; `exit` writes `tbd.out.json` and
  the bilingual UA' reports (library mode: the OpenStudio runner is optional).
  - **Docker golden generators** `gen_golden_process.rb`, `gen_golden_process_json.rb`,
    `gen_golden_ua_report.rb`, `gen_golden_uo.rb`.
  - `test_process.py`: exact parity across **all 9 fixtures** (per-surface heat
    loss / ratio / U and every serialized edge).
  - `test_process_json.py`: **7 JSON-override cases + 1 uprate case** — validates
    `inputs`, the surface/subsurface/edge/KHI overrides, and `uprate`+`uo`.
  - `test_ua_report.py`: bilingual UA' Markdown parity across 3 fixtures
    (validates `qc33`/`ua_summary`/`ua_md`).
  - `test_exit.py`: `tbd.out.json` + UA report emission.
- One more preserved upstream bug: `psi.rb:1741` `fathest_mag` typo (edge polar-
  angle search picks the last, not farthest, wire point) — reproduced for parity.
- **Hardening**: GitHub Actions CI (`ci.yml`, Python 3.11/3.12) running the full
  parity suite; a weekly `upstream-drift.yml` job that opens a tracking issue when
  the pinned rd2/tbd revision falls behind `develop`; editable install support
  (`pip install -e .`); coverage config.
- Full suite: **156 tests passing, 76% line coverage** (uncovered lines are almost
  entirely defensive input-guard branches). Upstream findings: 11 TBD + 3 pyOSut.
