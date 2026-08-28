# Upstream tracking

`py-tbd` is a line-for-line native Python port of the **TBD** Ruby gem. This file
records exactly which upstream revision the port mirrors and how to advance it.

## Pinned revision — THE `tbd-3.5.2-compat` BRANCH

| | |
|---|---|
| Upstream repo | https://github.com/rd2/tbd |
| Tag | `v3.5.2` |
| **Commit** | **`95156a922f54e45293e1896eba11bc29cd1b5c6d`** |
| Upstream version | `3.5.2` |
| Pinned on | 2026-08-28 |

**Why this branch exists.** `main` ports upstream v3.6.0. The canmet-energy
btap family's verification oracle (D-78/D-79) is FROZEN on the Ruby triplet
TBD 3.5.2 / OSut 0.8.2 / Topolys 0.6.2, and 3.5.2 vs 3.6.0 is a
physical-output difference, not serialization noise: 3.5.2 REFUSES an
infeasible construction uprate outright ("Unable to uprate ...", model left
as-is) where 3.6.0 partially uprates — landing ~43% apart on the same wall.
This branch backports the v3.5.2 semantics so btap can integrate py-tbd
against its frozen baseline (Option A of btap's M7 review); retire it when
the btap family deliberately rebaselines on 3.6.x.

The backported deltas, each verified against the Ruby 3.5.2 gem:

- `ua.py` `uo()`/`uprate()` — 3.5.2 signatures and semantics: `uo(model, lc,
  id, hloss, film, ut) -> {"uo":, "m":}` with hard refusal (the
  "Zero ... new Rsi" warning) instead of 3.6.0's clamp-and-continue;
  `uprate()` merges each surface type onto the LARGEST-area construction
  with the LOWEST film (3.6.0 uprates per construction with area-weighted
  films) and logs 3.5.2's exact warning texts.
- `geo.py` — `surf["boundary"]` keeps the SDK's casing ("Outdoors", not
  "outdoors"); consumers downcase at comparison, as 3.5.2 does. The
  interzone film override (`osut.filmResistances(...)`) is a 3.6.0 addition
  and is removed: films are always `surface.filmResistance()`.
- `ua.py` UA' banner reports the branch version (`v3.5.2`).

Every golden under `tests/fixtures/golden/` on this branch is REGENERATED
from Ruby TBD 3.5.2 + OSut 0.8.2 + Topolys 0.6.2 (`OSUT_VERSION=0.8.2`
through the same `tools/gen_golden_*.rb` harnesses); the full suite passes
against them (156 tests).

The same values are exported programmatically from `src/tbd/version.py`
(`UPSTREAM_SHA`, `UPSTREAM_VERSION`) and asserted by `tests/unit/test_version.py`.

## File mapping (Ruby → Python)

Only TBD's own code is ported. The three dependency gems are replaced by their
existing Python packages (see `pyproject.toml`): `oslg`, `osut` (pyOSut),
`py-topolys`, plus the `openstudio` SDK bindings.

| Ruby (`lib/tbd/`) | Python (`src/tbd/`) | Upstream lines |
|---|---|---|
| `psi.rb` | `psi.py` | 3369 |
| `geo.rb` | `geo.py` | 981 |
| `ua.rb` | `ua.py` | 1040 |
| `version.rb` | `version.py` | 25 |
| `../tbd.rb` (loader/mixin) | `__init__.py` + `_helpers.py` | 76 |

Per-file line counts are a drift signal: a large delta after fetching upstream
flags a method that needs re-porting.

## Upstream bug / warning log (to report to the authors)

A running record of suspected bugs, typos, and questionable code found while
porting. The port **reproduces each one verbatim** to keep golden parity (they
are annotated in the code with `# PARITY: upstream bug psi.rb:NNN (SHA dd6f12f8)`),
but they are collected here so they can be raised upstream. If upstream fixes any,
fix the Python side and regenerate goldens in the same PR.

Status legend: 🔴 changes results · 🟡 latent/benign for built-in sets · ⚪ cosmetic.

### psi.rb — `PSI#gen`

1. 🟡 **`psi.rb:715` — typo key `:parapetxonvex`.**
   `v[:roofconvex] = @set[id][:parapetxonvex] if h[:parapetconvex]`. The RHS key
   should be `:parapetconvex`; as written it is always `nil`. Dead for all 16
   built-in sets (none define `:parapetconvex`), but a user set that defines
   `:parapetconvex` would get `roofconvex = nil` instead of the intended value.

2. 🟡 **`psi.rb:761` & `:766` — typo guard key `:balconycinvex`.**
   `... if h[:balconycinvex]` should read `h[:balconyconvex]`. `:balconycinvex`
   is never a key of `h`, so both branches are dead — `balconysillconvex` /
   `balconydoorsillconvex` never inherit from `:balconyconvex`.

3. 🔴 **`psi.rb:545` — `h[:partyconcave]` overwritten from parapet presence.**
   Line 542 correctly sets `h[:partyconcave] = key?(:partyconcave)`, then line 545
   overwrites it with `key?(:parapetconcave)`. So `has[:partyconcave]` reflects
   the *parapet*, not the party wall. (Benign for built-ins since none define
   either key, but semantically wrong and observable via `shorthands`.)

4. 🔴 **`psi.rb:560` & `:563` — concave presence read from the convex key.**
   `h[:balconysillconcave] = key?(:balconysillconvex)` and
   `h[:balconydoorsillconcave] = key?(:balconydoorsillconvex)`. A set defining
   only the `...convex` variant would be reported as *also* having the `...concave`
   variant (and vice-versa never detected).

5. ⚪ **`psi.rb:575`,`:578` — stray/typo init keys in `v`.**
   The zero-init block writes `v[:doorconvex]` and `v[:skylightconvex]` (which are
   never valid PSI types and never read) instead of, e.g., `:doorheadconvex` /
   `:skylightheadconvex`. Harmless leftover keys in the `val` hash.

6. 🟡 **`psi.rb:789`,`:792` — `@has[:parapet]` / `@has[:roof]` guard.**
   `v[:parapet] = max unless @has[:parapet]` looks up `@has` (the set-keyed
   registry) with a PSI-type symbol, so it is always `nil`/falsy and the
   assignment always runs. Almost certainly intended `@has[id][:parapet]`.

### psi.rb — `PSI#shorthands`

7. 🔴 **`psi.rb:985` — undefined local `a`.**
   The empty-id guard calls `mismatch("set ID", id, String, mth, ERR, a)` but `a`
   is never defined in this method (other methods define `a = false`). In Ruby
   this raises `NameError` when `shorthands("")` is called. The port treats the
   empty-id branch as a logged error path returning the default `{has:{}, val:{}}`.

### geo.rb

8. ⚪ **`geo.rb:40-41` — duplicated guard.** `matches?` checks
   `return mismatch("e2", e2, Hash, ...) unless e2.is_a?(Hash)` twice in a row
   (lines 40 and 41 are identical). Harmless dead line.

9. ⚪ **`geo.rb:648` — wrong label + misaligned args in `concave?`/`convex?`.**
   The second angle check reads
   `mismatch("s1 angle", s1[:angle], Numeric, DBG, false)` — it (a) labels the
   `s2` angle as "s1 angle", (b) passes the value `s1[:angle]` instead of
   `s2[:angle]`, and (c) omits the `mth` argument, so `DBG` lands in the `mth`
   slot and the log level defaults. Only surfaces on invalid (non-numeric) angle
   input; results unaffected for valid input. Same pattern in both methods.

10. ⚪ **`geo.rb` `kiva` — doc/signature param-order mismatch.** The YARD comment
    orders params `(model, floors, walls, edges)` but the signature is
    `(model, walls, floors, edges)`.

### psi.rb — `process`

11. 🔴 **`psi.rb:1741` — misspelled `fathest_mag` in the polar-angle search.**
    Inside the per-edge "farthest point" loop, the update reads
    `fathest_mag = point_V_mag` (missing an `r`), so the real accumulator
    `farthest_mag` never changes from its initial `0`. The guard
    `next unless point_V_mag > farthest_mag` is therefore effectively
    `> 0`, so `farthest` ends up being the LAST qualifying wire point rather than
    the geometrically farthest one. This changes the computed polar angle and
    hence concave/convex/flat classification of some edges (observed as a
    `grade` vs `gradeconvex` label flip on a seb.osm edge — numeric derating was
    unaffected there because the set's grade variants share one value, but other
    sets/edges could differ materially). Reproduced verbatim in the port.

### ua.rb

- `ua_md` hard-codes `"* TBD : v3.6.0"` while `ua_summary` uses the passed-in SDK
  `:version`; two independent version sources.

## Dependency bugs (to report to the dependency authors)

Bugs found in py-tbd's **Python dependencies** (not the TBD Ruby gem). Unlike the
TBD parity bugs above, these are *worked around* by `src/tbd/_compat.py` (a
version- and behaviour-guarded runtime shim that no-ops once the dependency is
fixed) — a port cannot reproduce a dependency's crash and still be useful.

### pyOSut (`osut` on PyPI)

D1. 🔴 **`osut.py:579` (v0.9.0) — `insulatingLayer` NameError on massless layers.**
   In the massless branch, `res["r"] = m.thermalResistance()` uses `m`, but the
   loop variable is `l` (`m` is undefined). Any construction whose insulating
   layer is a `MasslessOpaqueMaterial` — extremely common — raises
   `NameError: name 'm' is not defined`. Fix: `m` → `l`.

D2. 🔴 **`osut.py` (v0.9.0) — `insulatingLayer` uses hardcoded thresholds
   instead of the RMIN/DMIN/KMAX constants.** The Ruby osut qualifies a layer
   with `thermalResistance < RMIN` (0.005), `d < DMIN` (0.01), `k > KMAX` (2.0);
   pyOSut hardcodes `0.001`, `0.003`, and `3.0` respectively. Consequence: a
   different layer is selected as "insulating" than in the Ruby gem — e.g. a
   ~0.15 m normalweight-concrete floor (k≈2.31) is *excluded* by Ruby
   (`k > 2.0`) but *kept* by pyOSut (`k > 3.0`), which then changes every
   downstream derating result for that surface. Detected across the warehouse
   and resto1 fixtures during `properties` parity testing.

D3. 🔴 **`osut.py:536` (v0.9.0) — `rsi` accumulates an Optional, not a resistance.**
   The massless branch reads `rsi += m.to_MasslessOpaqueMaterial()` instead of
   `... .get().thermalResistance()`, so `rsi` raises
   `TypeError: unsupported operand type(s) for +=: 'float' and 'OptionalMassless…'`
   for any construction containing a massless layer. Fix: append
   `.get().thermalResistance()`. Worked around in `_compat.py::_rsi_fixed`.

D1 and D2 are corrected together by `_compat.py::_insulating_layer_fixed`, D3 by
`_compat.py::_rsi_fixed` (drop-in replacements matching Ruby osut 0.9.1),
installed only when the buggy behavior is detected. Report all three to
rd2/pyOSut.

## Update process

1. `git -C <ruby-tbd> fetch && git log dd6f12f8..origin/develop -- lib/tbd/` —
   list changed methods since the pin.
2. `git -C <ruby-tbd> diff dd6f12f8..<new> -- lib/tbd/psi.rb lib/tbd/geo.rb lib/tbd/ua.rb` —
   apply equivalent Python edits method-by-method.
3. Re-run `tools/gen_golden.rb` against `<new>` to regenerate `tests/fixtures/golden/`.
4. Bump `UPSTREAM_SHA` / `UPSTREAM_VERSION` / `VERSION` in `src/tbd/version.py` and
   the table above, in the same PR as the code + golden changes.
