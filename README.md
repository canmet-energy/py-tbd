# py-tbd

**Thermal Bridging & Derating (TBD) for OpenStudio — native Python port.**

`py-tbd` is a line-for-line Python port of the [rd2/tbd](https://github.com/rd2/tbd)
Ruby gem. It autodetects major thermal bridges (balconies, parapets, corners, …)
in an OpenStudio model and derates the outside-facing opaque constructions
(walls, roofs, exposed floors) to account for the added heat loss.

This is the **library** (importable as `tbd`). The OpenStudio *measure* wrapper
that ships with the Ruby gem is out of scope for v1.

## Status

Feature-complete port of TBD `3.6.0` (commit `dd6f12f8` — see [`UPSTREAM.md`](UPSTREAM.md)).
All of `psi.rb`, `geo.rb` and `ua.rb` are ported: the `KHI`/`PSI` libraries, the
geometry/topology layer, the UA' reporting, and the full `inputs`/`derate`/
`process`/`exit` engine.

Parity is enforced by golden fixtures generated from the Ruby gem (OpenStudio
3.11.0) and asserted by 150+ tests, including exact `process` parity across all
nine `.osm` fixtures, JSON-override and uprating cases, and the bilingual UA'
report. The one deliverable intentionally left out of v1 is the OpenStudio
Measure wrapper (this is the importable library).

## Install

`py-tbd` depends on the OpenStudio SDK Python bindings and the Python ports of
TBD's dependency gems:

- [`openstudio`](https://pypi.org/project/openstudio/) — OpenStudio SDK bindings
- [`oslg`](https://pypi.org/project/oslg/) — logging (port of the OSlg gem)
- [`osut`](https://pypi.org/project/osut/) — OpenStudio utilities (port of the OSut gem / pyOSut)
- [`py-topolys`](https://github.com/canmet-energy/py-topolys) — 3D topology (port of the Topolys gem)
- `jsonschema` — validates `tbd.json` inputs against `tbd.schema.json`

```bash
python -m venv .venv
.venv/bin/pip install openstudio oslg osut jsonschema \
    "py-topolys @ git+https://github.com/canmet-energy/py-topolys.git"
.venv/bin/pip install -e .
```

> On Debian/Ubuntu Python (PEP 668), if `python -m venv` cannot bootstrap pip,
> create it with `python3 -m venv --without-pip .venv` and bootstrap pip via
> `curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python`.

## Usage

```python
import openstudio
import tbd

translator = openstudio.osversion.VersionTranslator()
model = translator.loadModel(openstudio.path("model.osm")).get()

argh = {"option": "poor (BETBG)"}
result = tbd.process(model, argh)   # -> {"io": ..., "surfaces": ...}
```

## Tests / parity

Parity with the Ruby gem is enforced by golden reference fixtures generated from
the gem (`tools/gen_golden.rb`) plus a unit test per public method. See the
plan and [`UPSTREAM.md`](UPSTREAM.md).

```bash
.venv/bin/pytest tests/unit    # fast, per-method
.venv/bin/pytest tests/e2e     # end-to-end (ports of the Ruby RSpec suite)
```

## Third-party notices

See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) on licensing.
