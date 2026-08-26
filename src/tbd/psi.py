# MIT License
#
# Copyright (c) 2020-2026 Denis Bourgeois & Dan Macumber
#
# Native Python port of lib/tbd/psi.rb from the TBD Ruby gem.
# Sources for thermal bridge types and default KHI-/PSI-factor sets:
#   a) BETBG  = Building Envelope Thermal Bridging Guide v1.4 (or newer)
#   b) ISO 14683 (Appendix C)
#   c) NECB-QC = Quebec's energy code for new commercial buildings
#
# Ruby symbol keys are ported as plain Python str keys. Ruby's `extend OSut`
# mixin is replaced by explicit `oslg.`/`osut.` calls (see _helpers.py).

import json
import os

import openstudio
import py_topolys

from . import geo
from ._helpers import oslg, osut, DBG, INF, WRN, ERR, FTL, TOL, NS
from ._helpers import RMIN, KMIN, KMAX, DMIN, DMAX, UMAX

# Built-in KHI point-thermal-bridge factors (W/K). Mirrors KHI#initialize.
_KHI_POINT = {
    "poor (BETBG)":                0.900,  # detail 5.7.2 BETBG
    "regular (BETBG)":             0.500,  # detail 5.7.4 BETBG
    "efficient (BETBG)":           0.150,  # detail 5.7.3 BETBG
    "code (Quebec)":               0.500,  # art. 3.3.1.3. NECB-QC
    "uncompliant (Quebec)":        1.000,  # NECB-QC Guide
    "90.1.22|steel.m|default":     0.480,  # steel/metal, compliant
    "90.1.22|steel.m|unmitigated": 0.920,  # steel/metal, non-compliant
    "90.1.22|mass.ex|default":     0.330,  # ext/integral, compliant
    "90.1.22|mass.ex|unmitigated": 0.460,  # ext/integral, non-compliant
    "90.1.22|mass.in|default":     0.330,  # interior mass, compliant
    "90.1.22|mass.in|unmitigated": 0.460,  # interior, non-compliant
    "90.1.22|wood.fr|default":     0.040,  # compliant
    "90.1.22|wood.fr|unmitigated": 0.330,  # non-compliant
    "(non thermal bridging)":      0.000,  # defaults to 0
}


class KHI:
    """Library of point thermal bridges (e.g. columns), keyed by id, in W/K."""

    def __init__(self):
        # @point — built-in KHI-factors. Users may append new id:value pairs,
        # preferably through a TBD JSON input file. Units are in W/K.
        self._point = dict(_KHI_POINT)

    @property
    def point(self):
        """dict: the KHI library {id: conductance W/K} (read-only)."""
        return self._point

    def append(self, k=None):
        """Append a new KHI entry {"id": <str>, "point": <float>}.

        Returns True on success, False on invalid input (logged). Ruby: KHI#append.
        """
        mth = "TBD::append"
        a = False
        if k is None:
            k = {}
        if not hasattr(k, "get") or not hasattr(k, "__contains__"):
            return oslg.mismatch("KHI", k, dict, mth, DBG, a)
        if "id" not in k:
            return oslg.hashkey("KHI id", k, "id", mth, DBG, a)
        if "point" not in k:
            return oslg.hashkey("KHI point", k, "point", mth, DBG, a)

        id = oslg.trim(k["id"])
        ck1 = id == ""
        ck2 = _to_f_ok(k["point"])
        if ck1:
            return oslg.mismatch("KHI id", k["id"], str, mth, ERR, a)
        if not ck2:
            return oslg.mismatch("KHI point", k["point"], float, mth, ERR, a)

        if id in self._point:
            oslg.log(ERR, "Skipping '%s': existing KHI entry (%s)" % (id, mth))
            return False

        self._point[id] = float(k["point"])
        return True


# Built-in PSI-factor sets (W/K per linear meter). Mirrors PSI#initialize.
# Each set carries only the *base* PSI types; PSI.gen() derives the concave/
# convex/head/sill/jamb variants. Ordered exactly as in psi.rb.
_PSI_SETS = {
    # Based on INTERIOR dimensioning (p.15 BETBG).
    "poor (BETBG)": {
        "rimjoist": 1.000000, "parapet": 0.800000, "roof": 0.800000,
        "ceiling": 0.000000, "fenestration": 0.500000, "door": 0.500000,
        "skylight": 0.500000, "spandrel": 0.155000, "corner": 0.850000,
        "balcony": 1.000000, "balconysill": 1.000000, "balconydoorsill": 1.000000,
        "party": 0.850000, "grade": 0.850000, "joint": 0.300000,
        "transition": 0.000000,
    },
    # Based on INTERIOR dimensioning (p.15 BETBG).
    "regular (BETBG)": {
        "rimjoist": 0.500000, "parapet": 0.450000, "roof": 0.450000,
        "ceiling": 0.000000, "fenestration": 0.350000, "door": 0.350000,
        "skylight": 0.350000, "spandrel": 0.155000, "corner": 0.450000,
        "balcony": 0.500000, "balconysill": 0.500000, "balconydoorsill": 0.500000,
        "party": 0.450000, "grade": 0.450000, "joint": 0.200000,
        "transition": 0.000000,
    },
    # Based on INTERIOR dimensioning (p.15 BETBG).
    "efficient (BETBG)": {
        "rimjoist": 0.200000, "parapet": 0.200000, "roof": 0.200000,
        "ceiling": 0.000000, "fenestration": 0.199999, "door": 0.199999,
        "skylight": 0.199999, "spandrel": 0.155000, "corner": 0.200000,
        "balcony": 0.200000, "balconysill": 0.200000, "balconydoorsill": 0.200000,
        "party": 0.200000, "grade": 0.200000, "joint": 0.100000,
        "transition": 0.000000,
    },
    # "Conventional", closer to window wall spandrels.
    "spandrel (BETBG)": {
        "rimjoist": 0.615000, "parapet": 1.000000, "roof": 1.000000,
        "ceiling": 0.000000, "fenestration": 0.000000, "door": 0.000000,
        "skylight": 0.350000, "spandrel": 0.155000, "corner": 0.425000,
        "balcony": 1.110000, "balconysill": 1.110000, "balconydoorsill": 1.110000,
        "party": 0.990000, "grade": 0.880000, "joint": 0.500000,
        "transition": 0.000000,
    },
    # "GoodHigh performance" curtainwall spandrels.
    "spandrel HP (BETBG)": {
        "rimjoist": 0.170000, "parapet": 0.660000, "roof": 0.660000,
        "ceiling": 0.000000, "fenestration": 0.000000, "door": 0.000000,
        "skylight": 0.350000, "spandrel": 0.155000, "corner": 0.200000,
        "balcony": 0.400000, "balconysill": 0.400000, "balconydoorsill": 0.400000,
        "party": 0.500000, "grade": 0.880000, "joint": 0.140000,
        "transition": 0.000000,
    },
    # CCQ, Chapitre I1, code-compliant defaults.
    "code (Quebec)": {
        "rimjoist": 0.300000, "parapet": 0.325000, "roof": 0.325000,
        "ceiling": 0.000000, "fenestration": 0.200000, "door": 0.200000,
        "skylight": 0.200000, "spandrel": 0.155000, "corner": 0.300000,
        "balcony": 0.500000, "balconysill": 0.500000, "balconydoorsill": 0.500000,
        "party": 0.450000, "grade": 0.450000, "joint": 0.200000,
        "transition": 0.000000,
    },
    # CCQ, Chapitre I1, non-code-compliant defaults.
    "uncompliant (Quebec)": {
        "rimjoist": 0.850000, "parapet": 0.800000, "roof": 0.800000,
        "ceiling": 0.000000, "fenestration": 0.500000, "door": 0.500000,
        "skylight": 0.500000, "spandrel": 0.155000, "corner": 0.850000,
        "balcony": 1.000000, "balconysill": 1.000000, "balconydoorsill": 1.000000,
        "party": 0.850000, "grade": 0.850000, "joint": 0.500000,
        "transition": 0.000000,
    },
    # ASHRAE 90.1 2022 (A10) "default" steel-framed and metal buildings.
    "90.1.22|steel.m|default": {
        "rimjoist": 0.307000, "parapet": 0.260000, "roof": 0.020000,
        "ceiling": 0.000000, "fenestration": 0.194000, "door": 0.000000,
        "skylight": 0.000000, "spandrel": 0.000001, "corner": 0.000002,
        "balcony": 0.307000, "balconysill": 0.307000, "balconydoorsill": 0.307000,
        "party": 0.000001, "grade": 0.000001, "joint": 0.376000,
        "transition": 0.000000,
    },
    # ASHRAE 90.1 2022 (A10) "unmitigated" steel-framed and metal buildings.
    "90.1.22|steel.m|unmitigated": {
        "rimjoist": 0.842000, "parapet": 0.500000, "roof": 0.650000,
        "ceiling": 0.000000, "fenestration": 0.505000, "door": 0.000000,
        "skylight": 0.000000, "spandrel": 0.000001, "corner": 0.000002,
        "balcony": 0.842000, "balconysill": 1.686000, "balconydoorsill": 0.842000,
        "party": 0.000001, "grade": 0.000001, "joint": 0.554000,
        "transition": 0.000000,
    },
    # ASHRAE 90.1 2022 (A10) "default" exterior/integral mass walls.
    "90.1.22|mass.ex|default": {
        "rimjoist": 0.205000, "parapet": 0.217000, "roof": 0.150000,
        "ceiling": 0.000000, "fenestration": 0.226000, "door": 0.000000,
        "skylight": 0.000000, "spandrel": 0.000001, "corner": 0.000002,
        "balcony": 0.205000, "balconysill": 0.307000, "balconydoorsill": 0.205000,
        "party": 0.000001, "grade": 0.000001, "joint": 0.322000,
        "transition": 0.000000,
    },
    # ASHRAE 90.1 2022 (A10) "unmitigated" exterior/integral mass walls.
    "90.1.22|mass.ex|unmitigated": {
        "rimjoist": 0.824000, "parapet": 0.412000, "roof": 0.750000,
        "ceiling": 0.000000, "fenestration": 0.325000, "door": 0.000000,
        "skylight": 0.000000, "spandrel": 0.000001, "corner": 0.000002,
        "balcony": 0.824000, "balconysill": 1.686000, "balconydoorsill": 0.824000,
        "party": 0.000001, "grade": 0.000001, "joint": 0.476000,
        "transition": 0.000000,
    },
    # ASHRAE 90.1 2022 (A10) "default" interior mass walls.
    "90.1.22|mass.in|default": {
        "rimjoist": 0.495000, "parapet": 0.393000, "roof": 0.150000,
        "ceiling": 0.000000, "fenestration": 0.143000, "door": 0.000000,
        "skylight": 0.000000, "spandrel": 0.000000, "corner": 0.000001,
        "balcony": 0.495000, "balconysill": 0.307000, "balconydoorsill": 0.495000,
        "party": 0.000001, "grade": 0.000001, "joint": 0.322000,
        "transition": 0.000000,
    },
    # ASHRAE 90.1 2022 (A10) "unmitigated" interior mass walls.
    "90.1.22|mass.in|unmitigated": {
        "rimjoist": 0.824000, "parapet": 0.884000, "roof": 0.750000,
        "ceiling": 0.000000, "fenestration": 0.543000, "door": 0.000000,
        "skylight": 0.000000, "spandrel": 0.000000, "corner": 0.000001,
        "balcony": 0.824000, "balconysill": 1.686000, "balconydoorsill": 0.824000,
        "party": 0.000001, "grade": 0.000001, "joint": 0.476000,
        "transition": 0.000000,
    },
    # ASHRAE 90.1 2022 (A10) "default" wood-framed (and other) walls.
    "90.1.22|wood.fr|default": {
        "rimjoist": 0.084000, "parapet": 0.056000, "roof": 0.020000,
        "ceiling": 0.000000, "fenestration": 0.171000, "door": 0.000000,
        "skylight": 0.000000, "spandrel": 0.000000, "corner": 0.000001,
        "balcony": 0.084000, "balconysill": 0.171001, "balconydoorsill": 0.084000,
        "party": 0.000001, "grade": 0.000001, "joint": 0.074000,
        "transition": 0.000000,
    },
    # ASHRAE 90.1 2022 (A10) "unmitigated" wood-framed (and other) walls.
    "90.1.22|wood.fr|unmitigated": {
        "rimjoist": 0.582000, "parapet": 0.056000, "roof": 0.150000,
        "ceiling": 0.000000, "fenestration": 0.260000, "door": 0.000000,
        "skylight": 0.000000, "spandrel": 0.000000, "corner": 0.000001,
        "balcony": 0.582000, "balconysill": 0.582000, "balconydoorsill": 0.582000,
        "party": 0.000001, "grade": 0.000001, "joint": 0.322000,
        "transition": 0.000000,
    },
    "(non thermal bridging)": {
        "rimjoist": 0.000000, "parapet": 0.000000, "roof": 0.000000,
        "ceiling": 0.000000, "fenestration": 0.000000, "door": 0.000000,
        "skylight": 0.000000, "spandrel": 0.000000, "corner": 0.000000,
        "balcony": 0.000000, "balconysill": 0.000000, "balconydoorsill": 0.000000,
        "party": 0.000000, "grade": 0.000000, "joint": 0.000000,
        "transition": 0.000000,
    },
}


class PSI:
    """Library of linear thermal bridges (corners, balconies, parapets, ...).

    Each set (keyed by id) holds PSI-factors in W/K per linear meter. Mirrors
    the Ruby TBD::PSI class. `gen()` derives the concave/convex/head/sill/jamb
    variants from the base types.
    """

    def __init__(self):
        self._set = {}   # raw PSI-factor sets {id: {type: float}}
        self._has = {}   # {id: {type: bool}} which PSI types a set defines
        self._val = {}   # {id: {type: float}} expanded factor for every type

        for k, v in _PSI_SETS.items():
            self._set[k] = dict(v)

        for k in list(self._set.keys()):
            self.gen(k)

    @property
    def set(self):
        """dict: raw PSI-factor sets (read-only)."""
        return self._set

    @property
    def has(self):
        """dict: per-set listing of which PSI types are defined (read-only)."""
        return self._has

    @property
    def val(self):
        """dict: per-set expanded PSI-factors for every admissible type."""
        return self._val

    def gen(self, id=""):
        """Generate the shorthand `has`/`val` listings for PSI set `id`.

        Faithful port of PSI#gen. Returns True on success, False if the set is
        unknown (logged). NOTE: several upstream typo-bugs are preserved verbatim
        for parity — see the `# PARITY:` markers below and UPSTREAM.md.
        """
        mth = "TBD::gen"
        if id not in self._set:
            return oslg.hashkey(id, self._set, id, mth, ERR, False)

        st = self._set[id]

        h = {}  # true/false if PSI set has PSI type
        h["joint"] = "joint" in st
        h["transition"] = "transition" in st
        h["fenestration"] = "fenestration" in st
        h["head"] = "head" in st
        h["headconcave"] = "headconcave" in st
        h["headconvex"] = "headconvex" in st
        h["sill"] = "sill" in st
        h["sillconcave"] = "sillconcave" in st
        h["sillconvex"] = "sillconvex" in st
        h["jamb"] = "jamb" in st
        h["jambconcave"] = "jambconcave" in st
        h["jambconvex"] = "jambconvex" in st
        h["door"] = "door" in st
        h["doorhead"] = "doorhead" in st
        h["doorheadconcave"] = "doorheadconcave" in st
        h["doorheadconvex"] = "doorheadconvex" in st
        h["doorsill"] = "doorsill" in st
        h["doorsillconcave"] = "doorsillconcave" in st
        h["doorsillconvex"] = "doorsillconvex" in st
        h["doorjamb"] = "doorjamb" in st
        h["doorjambconcave"] = "doorjambconcave" in st
        h["doorjambconvex"] = "doorjambconvex" in st
        h["skylight"] = "skylight" in st
        h["skylighthead"] = "skylighthead" in st
        h["skylightheadconcave"] = "skylightheadconcave" in st
        h["skylightheadconvex"] = "skylightheadconvex" in st
        h["skylightsill"] = "skylightsill" in st
        h["skylightsillconcave"] = "skylightsillconcave" in st
        h["skylightsillconvex"] = "skylightsillconvex" in st
        h["skylightjamb"] = "skylightjamb" in st
        h["skylightjambconcave"] = "skylightjambconcave" in st
        h["skylightjambconvex"] = "skylightjambconvex" in st
        h["spandrel"] = "spandrel" in st
        h["spandrelconcave"] = "spandrelconcave" in st
        h["spandrelconvex"] = "spandrelconvex" in st
        h["corner"] = "corner" in st
        h["cornerconcave"] = "cornerconcave" in st
        h["cornerconvex"] = "cornerconvex" in st
        h["party"] = "party" in st
        h["partyconcave"] = "partyconcave" in st
        h["partyconvex"] = "partyconvex" in st
        h["parapet"] = "parapet" in st
        # PARITY: upstream bug psi.rb:545 — party-concave written from parapet,
        # overwriting the correct h["partyconcave"] set just above.
        h["partyconcave"] = "parapetconcave" in st
        h["parapetconvex"] = "parapetconvex" in st
        h["roof"] = "roof" in st
        h["roofconcave"] = "roofconcave" in st
        h["roofconvex"] = "roofconvex" in st
        h["ceiling"] = "ceiling" in st
        h["ceilingconcave"] = "ceilingconcave" in st
        h["ceilingconvex"] = "ceilingconvex" in st
        h["grade"] = "grade" in st
        h["gradeconcave"] = "gradeconcave" in st
        h["gradeconvex"] = "gradeconvex" in st
        h["balcony"] = "balcony" in st
        h["balconyconcave"] = "balconyconcave" in st
        h["balconyconvex"] = "balconyconvex" in st
        h["balconysill"] = "balconysill" in st
        # PARITY: upstream bug psi.rb:560 — concave presence read from convex.
        h["balconysillconcave"] = "balconysillconvex" in st
        h["balconysillconvex"] = "balconysillconvex" in st
        h["balconydoorsill"] = "balconydoorsill" in st
        # PARITY: upstream bug psi.rb:563 — concave presence read from convex.
        h["balconydoorsillconcave"] = "balconydoorsillconvex" in st
        h["balconydoorsillconvex"] = "balconydoorsillconvex" in st
        h["rimjoist"] = "rimjoist" in st
        h["rimjoistconcave"] = "rimjoistconcave" in st
        h["rimjoistconvex"] = "rimjoistconvex" in st
        self._has[id] = h

        v = {}  # PSI-value (W/K per linear meter)
        # Initial zero-fill (mirrors psi.rb:571-592, including the upstream typo
        # keys :doorconvex and :skylightconvex, preserved for exact val parity).
        v["door"] = 0; v["fenestration"] = 0; v["skylight"] = 0
        v["head"] = 0; v["headconcave"] = 0; v["headconvex"] = 0
        v["sill"] = 0; v["sillconcave"] = 0; v["sillconvex"] = 0
        v["jamb"] = 0; v["jambconcave"] = 0; v["jambconvex"] = 0
        v["doorhead"] = 0; v["doorheadconcave"] = 0; v["doorconvex"] = 0
        v["doorsill"] = 0; v["doorsillconcave"] = 0; v["doorsillconvex"] = 0
        v["doorjamb"] = 0; v["doorjambconcave"] = 0; v["doorjambconvex"] = 0
        v["skylighthead"] = 0; v["skylightheadconcave"] = 0; v["skylightconvex"] = 0
        v["skylightsill"] = 0; v["skylightsillconcave"] = 0; v["skylightsillconvex"] = 0
        v["skylightjamb"] = 0; v["skylightjambconcave"] = 0; v["skylightjambconvex"] = 0
        v["spandrel"] = 0; v["spandrelconcave"] = 0; v["spandrelconvex"] = 0
        v["corner"] = 0; v["cornerconcave"] = 0; v["cornerconvex"] = 0
        v["parapet"] = 0; v["parapetconcave"] = 0; v["parapetconvex"] = 0
        v["roof"] = 0; v["roofconcave"] = 0; v["roofconvex"] = 0
        v["ceiling"] = 0; v["ceilingconcave"] = 0; v["ceilingconvex"] = 0
        v["party"] = 0; v["partyconcave"] = 0; v["partyconvex"] = 0
        v["grade"] = 0; v["gradeconcave"] = 0; v["gradeconvex"] = 0
        v["balcony"] = 0; v["balconyconcave"] = 0; v["balconyconvex"] = 0
        v["balconysill"] = 0; v["balconysillconcave"] = 0; v["balconysillconvex"] = 0
        v["balconydoorsill"] = 0; v["balconydoorsillconcave"] = 0; v["balconydoorsillconvex"] = 0
        v["rimjoist"] = 0; v["rimjoistconcave"] = 0; v["rimjoistconvex"] = 0
        v["joint"] = 0; v["transition"] = 0

        if h.get("joint"): v["joint"] = st.get("joint")
        if h.get("transition"): v["transition"] = st.get("transition")
        if h.get("fenestration"): v["fenestration"] = st.get("fenestration")
        if h.get("fenestration"): v["head"] = st.get("fenestration")
        if h.get("fenestration"): v["headconcave"] = st.get("fenestration")
        if h.get("fenestration"): v["headconvex"] = st.get("fenestration")
        if h.get("fenestration"): v["sill"] = st.get("fenestration")
        if h.get("fenestration"): v["sillconcave"] = st.get("fenestration")
        if h.get("fenestration"): v["sillconvex"] = st.get("fenestration")
        if h.get("fenestration"): v["jamb"] = st.get("fenestration")
        if h.get("fenestration"): v["jambconcave"] = st.get("fenestration")
        if h.get("fenestration"): v["jambconvex"] = st.get("fenestration")
        if h.get("fenestration"): v["door"] = st.get("fenestration")
        if h.get("fenestration"): v["doorhead"] = st.get("fenestration")
        if h.get("fenestration"): v["doorheadconcave"] = st.get("fenestration")
        if h.get("fenestration"): v["doorheadconvex"] = st.get("fenestration")
        if h.get("fenestration"): v["doorsill"] = st.get("fenestration")
        if h.get("fenestration"): v["doorsillconcave"] = st.get("fenestration")
        if h.get("fenestration"): v["doorsillconvex"] = st.get("fenestration")
        if h.get("fenestration"): v["doorjamb"] = st.get("fenestration")
        if h.get("fenestration"): v["doorjambconcave"] = st.get("fenestration")
        if h.get("fenestration"): v["doorjambconvex"] = st.get("fenestration")
        if h.get("fenestration"): v["skylight"] = st.get("fenestration")
        if h.get("fenestration"): v["skylighthead"] = st.get("fenestration")
        if h.get("fenestration"): v["skylightheadconcave"] = st.get("fenestration")
        if h.get("fenestration"): v["skylightheadconvex"] = st.get("fenestration")
        if h.get("fenestration"): v["skylightsill"] = st.get("fenestration")
        if h.get("fenestration"): v["skylightsillconcave"] = st.get("fenestration")
        if h.get("fenestration"): v["skylightsillconvex"] = st.get("fenestration")
        if h.get("fenestration"): v["skylightjamb"] = st.get("fenestration")
        if h.get("fenestration"): v["skylightjambconcave"] = st.get("fenestration")
        if h.get("fenestration"): v["skylightjambconvex"] = st.get("fenestration")
        if h.get("door"): v["door"] = st.get("door")
        if h.get("door"): v["doorhead"] = st.get("door")
        if h.get("door"): v["doorheadconcave"] = st.get("door")
        if h.get("door"): v["doorheadconvex"] = st.get("door")
        if h.get("door"): v["doorsill"] = st.get("door")
        if h.get("door"): v["doorsillconcave"] = st.get("door")
        if h.get("door"): v["doorsillconvex"] = st.get("door")
        if h.get("door"): v["doorjamb"] = st.get("door")
        if h.get("door"): v["doorjambconcave"] = st.get("door")
        if h.get("door"): v["doorjambconvex"] = st.get("door")
        if h.get("skylight"): v["skylight"] = st.get("skylight")
        if h.get("skylight"): v["skylighthead"] = st.get("skylight")
        if h.get("skylight"): v["skylightheadconcave"] = st.get("skylight")
        if h.get("skylight"): v["skylightheadconvex"] = st.get("skylight")
        if h.get("skylight"): v["skylightsill"] = st.get("skylight")
        if h.get("skylight"): v["skylightsillconcave"] = st.get("skylight")
        if h.get("skylight"): v["skylightsillconvex"] = st.get("skylight")
        if h.get("skylight"): v["skylightjamb"] = st.get("skylight")
        if h.get("skylight"): v["skylightjambconcave"] = st.get("skylight")
        if h.get("skylight"): v["skylightjambconvex"] = st.get("skylight")
        if h.get("head"): v["head"] = st.get("head")
        if h.get("head"): v["headconcave"] = st.get("head")
        if h.get("head"): v["headconvex"] = st.get("head")
        if h.get("sill"): v["sill"] = st.get("sill")
        if h.get("sill"): v["sillconcave"] = st.get("sill")
        if h.get("sill"): v["sillconvex"] = st.get("sill")
        if h.get("jamb"): v["jamb"] = st.get("jamb")
        if h.get("jamb"): v["jambconcave"] = st.get("jamb")
        if h.get("jamb"): v["jambconvex"] = st.get("jamb")
        if h.get("doorhead"): v["doorhead"] = st.get("doorhead")
        if h.get("doorhead"): v["doorheadconcave"] = st.get("doorhead")
        if h.get("doorhead"): v["doorheadconvex"] = st.get("doorhead")
        if h.get("doorsill"): v["doorsill"] = st.get("doorsill")
        if h.get("doorsill"): v["doorsillconcave"] = st.get("doorsill")
        if h.get("doorsill"): v["doorsillconvex"] = st.get("doorsill")
        if h.get("doorjamb"): v["doorjamb"] = st.get("doorjamb")
        if h.get("doorjamb"): v["doorjambconcave"] = st.get("doorjamb")
        if h.get("doorjamb"): v["doorjambconvex"] = st.get("doorjamb")
        if h.get("skylighthead"): v["skylighthead"] = st.get("skylighthead")
        if h.get("skylighthead"): v["skylightheadconcave"] = st.get("skylighthead")
        if h.get("skylighthead"): v["skylightheadconvex"] = st.get("skylighthead")
        if h.get("skylightsill"): v["skylightsill"] = st.get("skylightsill")
        if h.get("skylightsill"): v["skylightsillconcave"] = st.get("skylightsill")
        if h.get("skylightsill"): v["skylightsillconvex"] = st.get("skylightsill")
        if h.get("skylightjamb"): v["skylightjamb"] = st.get("skylightjamb")
        if h.get("skylightjamb"): v["skylightjambconcave"] = st.get("skylightjamb")
        if h.get("skylightjamb"): v["skylightjambconvex"] = st.get("skylightjamb")
        if h.get("headconcave"): v["headconcave"] = st.get("headconcave")
        if h.get("headconvex"): v["headconvex"] = st.get("headconvex")
        if h.get("sillconcave"): v["sillconcave"] = st.get("sillconcave")
        if h.get("sillconvex"): v["sillconvex"] = st.get("sillconvex")
        if h.get("jambconcave"): v["jambconcave"] = st.get("jambconcave")
        if h.get("jambconvex"): v["jambconvex"] = st.get("jambconvex")
        if h.get("doorheadconcave"): v["doorheadconcave"] = st.get("doorheadconcave")
        if h.get("doorheadconvex"): v["doorheadconvex"] = st.get("doorheadconvex")
        if h.get("doorsillconcave"): v["doorsillconcave"] = st.get("doorsillconcave")
        if h.get("doorsillconvex"): v["doorsillconvex"] = st.get("doorsillconvex")
        if h.get("doorjambconcave"): v["doorjambconcave"] = st.get("doorjambconcave")
        if h.get("doorjambconvex"): v["doorjambconvex"] = st.get("doorjambconvex")
        if h.get("skylightheadconcave"): v["skylightheadconcave"] = st.get("skylightheadconcave")
        if h.get("skylightheadconvex"): v["skylightheadconvex"] = st.get("skylightheadconvex")
        if h.get("skylightsillconcave"): v["skylightsillconcave"] = st.get("skylightsillconcave")
        if h.get("skylightsillconvex"): v["skylightsillconvex"] = st.get("skylightsillconvex")
        if h.get("skylightjambconcave"): v["skylightjambconcave"] = st.get("skylightjambconcave")
        if h.get("skylightjambconvex"): v["skylightjambconvex"] = st.get("skylightjambconvex")
        if h.get("spandrel"): v["spandrel"] = st.get("spandrel")
        if h.get("spandrel"): v["spandrelconcave"] = st.get("spandrel")
        if h.get("spandrel"): v["spandrelconvex"] = st.get("spandrel")
        if h.get("spandrelconcave"): v["spandrelconcave"] = st.get("spandrelconcave")
        if h.get("spandrelconvex"): v["spandrelconvex"] = st.get("spandrelconvex")
        if h.get("corner"): v["corner"] = st.get("corner")
        if h.get("corner"): v["cornerconcave"] = st.get("corner")
        if h.get("corner"): v["cornerconvex"] = st.get("corner")
        if h.get("cornerconcave"): v["cornerconcave"] = st.get("cornerconcave")
        if h.get("cornerconvex"): v["cornerconvex"] = st.get("cornerconvex")
        if h.get("roof"): v["parapet"] = st.get("roof")
        if h.get("roof"): v["parapetconcave"] = st.get("roof")
        if h.get("roof"): v["parapetconvex"] = st.get("roof")
        if h.get("roofconcave"): v["parapetconcave"] = st.get("roofconcave")
        if h.get("roofconvex"): v["parapetconvex"] = st.get("roofconvex")
        if h.get("parapet"): v["parapet"] = st.get("parapet")
        if h.get("parapet"): v["parapetconcave"] = st.get("parapet")
        if h.get("parapet"): v["parapetconvex"] = st.get("parapet")
        if h.get("parapetconcave"): v["parapetconcave"] = st.get("parapetconcave")
        if h.get("parapetconvex"): v["parapetconvex"] = st.get("parapetconvex")
        if h.get("parapet"): v["roof"] = st.get("parapet")
        if h.get("parapet"): v["roofconcave"] = st.get("parapet")
        if h.get("parapet"): v["roofconvex"] = st.get("parapet")
        if h.get("parapetconcave"): v["roofconcave"] = st.get("parapetconcave")
        # PARITY: upstream bug psi.rb:715 — RHS key ':parapetxonvex' is a typo
        # that never exists, so this assigns None when the guard is truthy.
        if h.get("parapetconvex"): v["roofconvex"] = st.get("parapetxonvex")
        if h.get("roof"): v["roof"] = st.get("roof")
        if h.get("roof"): v["roofconcave"] = st.get("roof")
        if h.get("roof"): v["roofconvex"] = st.get("roof")
        if h.get("roofconcave"): v["roofconcave"] = st.get("roofconcave")
        if h.get("roofconvex"): v["roofconvex"] = st.get("roofconvex")
        if h.get("ceiling"): v["ceiling"] = st.get("ceiling")
        if h.get("ceiling"): v["ceilingconcave"] = st.get("ceiling")
        if h.get("ceiling"): v["ceilingconvex"] = st.get("ceiling")
        if h.get("ceilingconcave"): v["ceilingconcave"] = st.get("ceilingconcave")
        if h.get("ceilingconvex"): v["ceilingconvex"] = st.get("ceilingconvex")
        if h.get("party"): v["party"] = st.get("party")
        if h.get("party"): v["partyconcave"] = st.get("party")
        if h.get("party"): v["partyconvex"] = st.get("party")
        if h.get("partyconcave"): v["partyconcave"] = st.get("partyconcave")
        if h.get("partyconvex"): v["partyconvex"] = st.get("partyconvex")
        if h.get("grade"): v["grade"] = st.get("grade")
        if h.get("grade"): v["gradeconcave"] = st.get("grade")
        if h.get("grade"): v["gradeconvex"] = st.get("grade")
        if h.get("gradeconcave"): v["gradeconcave"] = st.get("gradeconcave")
        if h.get("gradeconvex"): v["gradeconvex"] = st.get("gradeconvex")
        if h.get("balcony"): v["balcony"] = st.get("balcony")
        if h.get("balcony"): v["balconyconcave"] = st.get("balcony")
        if h.get("balcony"): v["balconyconvex"] = st.get("balcony")
        if h.get("balconyconcave"): v["balconyconcave"] = st.get("balconyconcave")
        if h.get("balconyconvex"): v["balconyconvex"] = st.get("balconyconvex")
        if h.get("fenestration"): v["balconysill"] = st.get("fenestration")
        if h.get("fenestration"): v["balconysillconcave"] = st.get("fenestration")
        if h.get("fenestration"): v["balconysillconvex"] = st.get("fenestration")
        if h.get("fenestration"): v["balconydoorsill"] = st.get("fenestration")
        if h.get("fenestration"): v["balconydoorsillconcave"] = st.get("fenestration")
        if h.get("fenestration"): v["balconydoorsillconvex"] = st.get("fenestration")
        if h.get("sill"): v["balconysill"] = st.get("sill")
        if h.get("sill"): v["balconysillconcave"] = st.get("sill")
        if h.get("sill"): v["balconysillconvex"] = st.get("sill")
        if h.get("sillconcave"): v["balconysillconcave"] = st.get("sillconcave")
        if h.get("sillconvex"): v["balconysillconvex"] = st.get("sillconvex")
        if h.get("sill"): v["balconydoorsill"] = st.get("sill")
        if h.get("sill"): v["balconydoorsillconcave"] = st.get("sill")
        if h.get("sill"): v["balconydoorsillconvex"] = st.get("sill")
        if h.get("sillconcave"): v["balconydoorsillconcave"] = st.get("sillconcave")
        if h.get("sillconvex"): v["balconydoorsillconvex"] = st.get("sillconvex")
        if h.get("balcony"): v["balconysill"] = st.get("balcony")
        if h.get("balcony"): v["balconysillconcave"] = st.get("balcony")
        if h.get("balcony"): v["balconysillconvex"] = st.get("balcony")
        if h.get("balconyconcave"): v["balconysillconcave"] = st.get("balconyconcave")
        # PARITY: upstream bug psi.rb:761 — guard key ':balconycinvex' is a typo
        # that is never present in `h`, so this branch is dead.
        if h.get("balconycinvex"): v["balconysillconvex"] = st.get("balconyconvex")
        if h.get("balcony"): v["balconydoorsill"] = st.get("balcony")
        if h.get("balcony"): v["balconydoorsillconcave"] = st.get("balcony")
        if h.get("balcony"): v["balconydoorsillconvex"] = st.get("balcony")
        if h.get("balconyconcave"): v["balconydoorsillconcave"] = st.get("balconyconcave")
        # PARITY: upstream bug psi.rb:766 — same ':balconycinvex' typo, dead branch.
        if h.get("balconycinvex"): v["balconydoorsillconvex"] = st.get("balconyconvex")
        if h.get("balconysill"): v["balconysill"] = st.get("balconysill")
        if h.get("balconysill"): v["balconysillconcave"] = st.get("balconysill")
        if h.get("balconysill"): v["balconysillconvex"] = st.get("balconysill")
        if h.get("balconysillconcave"): v["balconysillconcave"] = st.get("balconysillconcave")
        if h.get("balconysillconvex"): v["balconysillconvex"] = st.get("balconysillconvex")
        if h.get("balconysill"): v["balconydoorsill"] = st.get("balconysill")
        if h.get("balconysill"): v["balconydoorsillconcave"] = st.get("balconysill")
        if h.get("balconysill"): v["balconydoorsillconvex"] = st.get("balconysill")
        if h.get("balconysillconcave"): v["balconydoorsillconcave"] = st.get("balconysillconcave")
        if h.get("balconysillconvex"): v["balconydoorsillconvex"] = st.get("balconysillconvex")
        if h.get("balconydoorsill"): v["balconydoorsill"] = st.get("balconydoorsill")
        if h.get("balconydoorsill"): v["balconydoorsillconcave"] = st.get("balconydoorsill")
        if h.get("balconydoorsill"): v["balconydoorsillconvex"] = st.get("balconydoorsill")
        if h.get("balconydoorsillconcave"): v["balconydoorsillconcave"] = st.get("balconydoorsillconcave")
        if h.get("balconydoorsillconvex"): v["balconydoorsillconvex"] = st.get("balconydoorsillconvex")
        if h.get("rimjoist"): v["rimjoist"] = st.get("rimjoist")
        if h.get("rimjoist"): v["rimjoistconcave"] = st.get("rimjoist")
        if h.get("rimjoist"): v["rimjoistconvex"] = st.get("rimjoist")
        if h.get("rimjoistconcave"): v["rimjoistconcave"] = st.get("rimjoistconcave")
        if h.get("rimjoistconvex"): v["rimjoistconvex"] = st.get("rimjoistconvex")

        mx = max(v["parapetconcave"], v["parapetconvex"])
        # PARITY: upstream psi.rb:789 guards on @has[:parapet] (a set named
        # "parapet"), never @has[id][:parapet]; that lookup is always falsy.
        if not self._has.get("parapet"):
            v["parapet"] = mx

        mx = max(v["roofconcave"], v["roofconvex"])
        if not self._has.get("roof"):
            v["roof"] = mx

        self._val[id] = v
        return True

    def append(self, set=None):
        """Append a new PSI set {"id": <str>, <psi_type>: <float>, ...}.

        Returns True on success, False on invalid input (logged). Ruby: PSI#append.
        """
        mth = "TBD::append"
        a = False
        s = {}
        if set is None:
            set = {}
        if not isinstance(set, dict):
            return oslg.mismatch("set", set, dict, mth, DBG, a)
        if "id" not in set:
            return oslg.hashkey("set id", set, "id", mth, DBG, a)

        id = oslg.trim(set["id"])
        if id == "":
            return oslg.mismatch("set ID", set["id"], str, mth, ERR, a)

        if id in self._set:
            oslg.log(ERR, "'%s': existing PSI set (%s)" % (id, mth))
            return a

        # Copy only recognized PSI types (all base + concave/convex + families).
        for key in _APPEND_KEYS:
            if key in set:
                s[key] = set[key]

        if "joint" not in set:
            s["joint"] = 0.000
        if "transition" not in set:
            s["transition"] = 0.000
        if "ceiling" not in set:
            s["ceiling"] = 0.000

        self._set[id] = s
        self.gen(id)
        return True

    def shorthands(self, id=""):
        """Return {"has": <dict bool>, "val": <dict float>} for PSI set `id`.

        Ruby: PSI#shorthands. Returns {"has": {}, "val": {}} on failure.
        """
        mth = "TBD::shorthands"
        sh = {"has": {}, "val": {}}
        id = oslg.trim(id)
        if id == "":
            # PARITY: upstream psi.rb:985 references an undefined `a` here; the
            # empty-id branch is effectively an error path.
            return oslg.mismatch("set ID", id, str, mth, ERR, sh)
        if id not in self._set:
            return oslg.hashkey(id, self._set, id, mth, ERR, sh)
        if id not in self._has:
            return oslg.hashkey(id, self._has, id, mth, ERR, sh)
        if id not in self._val:
            return oslg.hashkey(id, self._val, id, mth, ERR, sh)

        sh["has"] = self._has[id]
        sh["val"] = self._val[id]
        return sh

    def is_complete(self, id=""):
        """Whether PSI set `id` defines a complete, usable list of PSI types.

        Ruby: PSI#complete?. Returns False on invalid input (logged).
        """
        mth = "TBD::is_complete"
        a = False
        id = oslg.trim(id)
        if id == "":
            return oslg.mismatch("set ID", id, str, mth, ERR, a)
        if id not in self._set:
            return oslg.hashkey(id, self._set, id, mth, ERR, a)
        if id not in self._has:
            return oslg.hashkey(id, self._has, id, mth, ERR, a)
        if id not in self._val:
            return oslg.hashkey(id, self._val, id, mth, ERR, a)

        hid = self._has[id]
        holes = []
        if hid.get("head"): holes.append("head")
        if hid.get("sill"): holes.append("sill")
        if hid.get("jamb"): holes.append("jamb")
        ok = len(holes) == 3
        if hid.get("fenestration"): ok = True
        if not ok:
            return False

        corners = []
        if hid.get("cornerconcave"): corners.append("concave")
        if hid.get("cornerconvex"): corners.append("convex")
        ok = len(corners) == 2
        if hid.get("corner"): ok = True
        if not ok:
            return False

        parapets = []
        roofs = []
        if hid.get("parapetconcave"): parapets.append("concave")
        if hid.get("parapetconvex"): parapets.append("convex")
        if hid.get("roofconcave"): roofs.append("concave")
        if hid.get("roofconvex"): parapets.append("convex")
        ok = len(parapets) == 2 or len(roofs) == 2
        if hid.get("parapet"): ok = True
        if hid.get("roof"): ok = True
        if not ok:
            return False
        if not hid.get("party"):
            return False
        if not hid.get("grade"):
            return False
        if not hid.get("balcony"):
            return False
        if not hid.get("rimjoist"):
            return False

        return ok

    def safe(self, id="", type=None):
        """Return the nearest defined PSI type for `type` via inheritance.

        Ruby: PSI#safe. Returns a PSI-type str, or None on invalid input (logged).
        """
        mth = "TBD::safe"
        id = oslg.trim(id)
        ck1 = id == ""
        ck2 = type is not None and (isinstance(type, str) or hasattr(type, "__str__"))
        if ck1:
            return oslg.mismatch("set ID", id, str, mth)
        if not ck2:
            return oslg.mismatch("type", type, str, mth)
        if id not in self._set:
            return oslg.hashkey(id, self._set, id, mth, ERR)
        if id not in self._has:
            return oslg.hashkey(id, self._has, id, mth, ERR)

        hid = self._has[id]
        safer = str(type)

        if not hid.get(safer):
            concave = "concave" in safer
            convex = "convex" in safer
            if concave:
                safer = _chomp(safer, "concave")
            if convex:
                safer = _chomp(safer, "convex")

        if not hid.get(safer):
            if safer == "head": safer = "fenestration"
            if safer == "sill": safer = "fenestration"
            if safer == "jamb": safer = "fenestration"
            if safer == "doorhead": safer = "door"
            if safer == "doorsill": safer = "door"
            if safer == "doorjamb": safer = "door"
            if safer == "skylighthead": safer = "skylight"
            if safer == "skylightsill": safer = "skylight"
            if safer == "skylightjamb": safer = "skylight"

        if not hid.get(safer):
            if safer == "skylight": safer = "fenestration"
            if safer == "door": safer = "fenestration"

        if hid.get(safer):
            return safer

        return None


def _chomp(s, suffix):
    """Return s without a trailing `suffix` (mirrors Ruby String#chomp)."""
    if suffix and s.endswith(suffix):
        return s[: -len(suffix)]
    return s


# Recognized keys copied by PSI.append (all base + concave/convex + families),
# in the exact order of psi.rb:894-958.
_APPEND_KEYS = [
    "rimjoist", "rimjoistconcave", "rimjoistconvex",
    "parapet", "parapetconcave", "parapetconvex",
    "roof", "roofconcave", "roofconvex",
    "ceiling", "ceilingconcave", "ceilingconvex",
    "fenestration",
    "head", "headconcave", "headconvex",
    "sill", "sillconcave", "sillconvex",
    "jamb", "jambconcave", "jambconvex",
    "door",
    "doorhead", "doorheadconcave", "doorheadconvex",
    "doorsill", "doorsillconcave", "doorsillconvex",
    "doorjamb", "doorjambconcave", "doorjambconvex",
    "skylight",
    "skylighthead", "skylightheadconcave", "skylightheadconvex",
    "skylightsill", "skylightsillconcave", "skylightsillconvex",
    "skylightjamb", "skylightjambconcave", "skylightjambconvex",
    "spandrel", "spandrelconcave", "spandrelconvex",
    "corner", "cornerconcave", "cornerconvex",
    "balcony", "balconyconcave", "balconyconvex",
    "balconysill", "balconysillconcave", "balconysillconvex",
    "balconydoorsill", "balconydoorsillconcave", "balconydoorsillconvex",
    "party", "partyconcave", "partyconvex",
    "grade", "gradeconcave", "gradeconvex",
    "joint", "transition",
]


# ---------------------------------------------------------------------------
# Module-level engine functions (Ruby: TBD.inputs/derate/process/exit).
# Ported in Phase 4; declared here so `import tbd` exposes the full surface.
# ---------------------------------------------------------------------------
def _is_num(x):
    """True for real numbers (excludes bool), mirroring Ruby is_a?(Numeric)."""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _clamp(x, lo, hi):
    """Ruby Numeric#clamp(lo, hi)."""
    return lo if x < lo else (hi if x > hi else x)


def inputs(s=None, e=None, argh=None):
    """Parse/validate the TBD JSON input and prime the PSI/KHI libraries.

    Faithful port of TBD.inputs. Returns {"io": <dict>, "psi": PSI, "khi": KHI}.
    `s` are in-memory TBD surfaces, `e` in-memory TBD edges; `argh["option"]` is
    the selected building PSI set, `argh["io_path"]` an optional tbd.json path (or
    a pre-parsed dict), `argh["schema_path"]` an optional JSON schema path.
    """
    mth = "TBD::inputs"
    opt = "option"
    ipt = {"io": {}, "psi": PSI(), "khi": KHI()}
    io = {}
    if s is None:
        s = {}
    if e is None:
        e = {}
    if argh is None:
        argh = {}
    if not isinstance(s, dict):
        return oslg.mismatch("s", s, dict, mth, DBG, ipt)
    if not isinstance(e, dict):
        return oslg.mismatch("e", e, dict, mth, DBG, ipt)
    if not isinstance(argh, dict):
        return oslg.mismatch("argh", argh, dict, mth, DBG, ipt)
    if opt not in argh:
        return oslg.hashkey("argh", argh, opt, mth, DBG, ipt)

    argh.setdefault("io_path", None)
    argh.setdefault("schema_path", None)
    pth = argh["io_path"]
    sch = argh["schema_path"]

    if pth is not None and isinstance(pth, (str, dict)):
        if isinstance(pth, dict):
            io = pth
        else:
            if not (os.path.isfile(pth) and os.path.getsize(pth) > 0):
                return oslg.empty("JSON file", mth, FTL, ipt)
            with open(pth) as f:
                io = json.load(f)
            if not isinstance(io, dict):
                return oslg.mismatch("io", io, dict, mth, FTL, ipt)

        # Optional JSON-schema validation (draft-04) against tbd.schema.json.
        if sch:
            import jsonschema
            if not os.path.exists(sch):
                return oslg.invalid("JSON schema", mth, 3, FTL, ipt)
            if os.path.getsize(sch) == 0:
                return oslg.empty("JSON schema", mth, FTL, ipt)
            with open(sch) as f:
                schema = json.load(f)
            try:
                jsonschema.Draft4Validator(schema).validate(io)
            except jsonschema.ValidationError:
                return oslg.invalid("JSON schema validation", mth, 3, FTL, ipt)

        # Append file-defined linear (PSI) and point (KHI) bridge libraries.
        if "psis" in io:
            for psi in io["psis"]:
                ipt["psi"].append(psi)
        if "khis" in io:
            for khi in io["khis"]:
                ipt["khi"].append(khi)

        # The building-wide PSI set (JSON-defined or argh-selected) must be complete.
        if "building" not in io:
            io["building"] = {"psi": argh[opt]}
        bdg = io["building"]
        if "psi" not in bdg:
            return oslg.hashkey("Building PSI", bdg, "psi", mth, FTL, ipt)
        if not ipt["psi"].is_complete(bdg["psi"]):
            return oslg.invalid("Complete building PSI", mth, 3, FTL, ipt)

        # Validate optional story/spacetype/space overrides against the model.
        for types in ("stories", "spacetypes", "spaces"):
            key = "story"
            if types == "spacetypes":
                key = "stype"
            if types == "spaces":
                key = "space"
            if types in io:
                for type in io[types]:
                    if "psi" not in type or "id" not in type:
                        continue
                    s1 = "JSON/OSM '%s' (%s)" % (type["id"], mth)
                    s2 = "JSON/PSI '%s' set (%s)" % (type["id"], mth)
                    match = False
                    for props in s.values():
                        if match:
                            break
                        if key not in props:
                            continue
                        match = type["id"] == props[key].nameString()
                    if not match:
                        oslg.log(ERR, s1)
                    if type["psi"] not in ipt["psi"].set:
                        oslg.log(ERR, s2)

        # Validate optional surface overrides (and their custom PSI/KHI).
        if "surfaces" in io:
            for surface in io["surfaces"]:
                if "id" not in surface:
                    continue
                if surface["id"] not in s:
                    oslg.log(ERR, "JSON/OSM surface '%s' (%s)" % (surface["id"], mth))
                if "psi" in surface:
                    if surface["psi"] not in ipt["psi"].set:
                        oslg.log(ERR, "JSON/OSM surface/set '%s' (%s)" % (surface["id"], mth))
                if "khis" in surface:
                    for khi in surface["khis"]:
                        if "id" not in khi:
                            continue
                        if khi["id"] not in ipt["khi"].point:
                            oslg.log(ERR, "JSON/KHI surface '%s' '%s' (%s)" % (surface["id"], khi["id"], mth))

        # Validate optional subsurface overrides.
        if "subsurfaces" in io:
            for sub in io["subsurfaces"]:
                if "id" not in sub or "usi" not in sub:
                    continue
                match = False
                for id, surface in s.items():
                    if match:
                        break
                    for holes in ("windows", "doors", "skylights"):
                        if holes in surface:
                            for hid in surface[holes].keys():
                                if match:
                                    break
                                match = sub["id"] == hid
                if not match:
                    oslg.log(ERR, "JSON/OSM subsurface '%s' (%s)" % (sub["id"], mth))

        # Validate + tag optional per-edge overrides against in-memory edges.
        if "edges" in io:
            for edge in io["edges"]:
                if "type" not in edge or "surfaces" not in edge:
                    continue
                surfaces = edge["surfaces"]
                type = edge["type"]
                safer = ipt["psi"].safe(bdg["psi"], type)  # fallback must exist
                if not safer:
                    oslg.log(ERR, "Skipping invalid edge PSI '%s' (%s)" % (type, mth))
                    continue

                valid = True
                for surface in surfaces:
                    for ee in e.values():
                        if not valid:
                            break
                        if "io_type" in ee:  # already matched in a previous pass
                            continue
                        if "surfaces" not in ee:
                            continue
                        surfs = ee["surfaces"]
                        if surface not in surfs:
                            continue

                        # A filed edge matches if ALL its listed surfaces connect
                        # this in-memory edge (which may touch even more surfaces).
                        match = True
                        for sid in surfaces:
                            if sid not in surfs:
                                match = False
                        if not match:
                            continue

                        if "length" in edge:  # optional length narrowing
                            if not abs(ee["length"] - edge["length"]) < TOL:
                                continue

                        # Optional vertex-coordinate narrowing.
                        vkeys = ("v0x", "v0y", "v0z", "v1x", "v1y", "v1z")
                        if any(k in edge for k in vkeys):
                            if not all(k in edge for k in vkeys):
                                oslg.log(ERR, "Mismatch '%s' edge vertices (%s)" % (surface, mth))
                                valid = False
                                continue
                            e1 = {
                                "v0": py_topolys.Point3D(float(edge["v0x"]), float(edge["v0y"]), float(edge["v0z"])),
                                "v1": py_topolys.Point3D(float(edge["v1x"]), float(edge["v1y"]), float(edge["v1z"])),
                            }
                            e2 = {"v0": ee["v0"].point, "v1": ee["v1"].point}
                            if not geo.matches(e1, e2):
                                continue

                        if "psi" in edge:  # optional explicit set on the edge
                            st = edge["psi"]
                            if st in ipt["psi"].set:
                                saferr = ipt["psi"].safe(st, type)
                                if saferr:
                                    ee["io_set"] = st
                                    ee["io_type"] = type
                                else:
                                    oslg.log(ERR, "Invalid %s: %s (%s)" % (st, type, mth))
                                    valid = False
                            else:
                                oslg.log(ERR, "Missing edge PSI %s (%s)" % (st, mth))
                                valid = False
                        else:
                            ee["io_type"] = type  # success: tag the matched edge
    else:
        # No JSON file: argh[:option] alone must name a complete PSI set; every
        # edge then inherits that default set (no KHI entries).
        ok = ipt["psi"].is_complete(argh[opt])
        if ok:
            io["building"] = {"psi": argh[opt]}
        else:
            oslg.log(FTL, "Incomplete building PSI set '%s' (%s)" % (argh[opt], mth))
            return ipt

    ipt["io"] = io
    return ipt


def derate(id="", s=None, lc=None):
    """Thermally derate a construction's insulating layer (returns a cloned material).

    Faithful port of TBD.derate. Clones the target layer material, renames it
    "<id> [uprated ]m tbd", and reduces its resistance/conductivity to absorb the
    surface's major-thermal-bridge heat loss. Returns the derated OpaqueMaterial,
    or None on invalid input / already-derated construction (logged).
    """
    mth = "TBD::derate"
    m = None
    kys = ["heatloss", "net", "ltype", "index", "r"]
    cl = openstudio.model.LayeredConstruction
    if not hasattr(lc, NS):
        return oslg.mismatch("lc", lc, cl, mth)
    if not isinstance(id, str):
        return oslg.mismatch("id", id, str, mth)

    id = oslg.trim(id)
    nom = lc.nameString()
    if id == "":
        return oslg.invalid("id", mth, 1)
    if not isinstance(lc, cl):
        return oslg.mismatch(nom, lc, cl, mth)
    if not isinstance(s, dict):
        return oslg.mismatch("%s surface" % nom, s, dict, mth)

    # Never re-derate a construction already tagged " tbd".
    if " tbd" in nom.lower():
        oslg.log(WRN, "Won't derate '%s': tagged as derated (%s)" % (nom, mth))
        return m

    # Validate the surface parameters uo/derate rely on.
    for k in kys:
        tag = "%s %s" % (id, k)
        if k not in s:
            return oslg.hashkey(tag, s, k, mth)
        if k == "ltype":
            if s[k] in ("massless", "standard"):
                continue
            return oslg.invalid(tag, mth, 2)
        elif k == "index":
            if not (isinstance(s[k], int) and not isinstance(s[k], bool)):
                return oslg.mismatch(tag, s[k], int, mth)
            if not (0 <= s[k] <= lc.numLayers() - 1):
                return oslg.invalid(tag, mth, 2)
        else:
            if not _is_num(s[k]):
                return oslg.mismatch(tag, s[k], float, mth)
            if k == "heatloss":
                continue
            if s[k] < 0:
                return oslg.negative(tag, mth, 2)
            if abs(s[k]) < 0.001:
                return oslg.zero(tag, mth)

    model = lc.model()
    ltype = s["ltype"]
    index = s["index"]
    net = s["net"]
    r = s["r"]
    u = s["heatloss"] / net
    loss = 0
    de_u = 1 / r + u   # derated insulating material U
    de_r = 1 / de_u    # derated insulating material R

    if ltype == "massless":
        m = lc.getLayer(index).to_MasslessOpaqueMaterial()
        if m.empty():
            return oslg.invalid("%s massless layer?" % id, mth, 0)
        m = m.get()
        up = "uprated " if " uprated" in m.nameString().lower() else ""
        m = m.clone(model).to_MasslessOpaqueMaterial().get()
        m.setName("%s %sm tbd" % (id, up))

        if de_r < RMIN:
            de_r = RMIN
            loss = (de_u - 1 / de_r) * net

        if not m.setThermalResistance(de_r):
            return oslg.invalid("Can't derate %s: RSi%s" % (id, round(de_r, 2)), mth)
    else:
        m = lc.getLayer(index).to_StandardOpaqueMaterial()
        if m.empty():
            return oslg.invalid("%s standard layer?" % id, mth, 0)
        m = m.get()
        up = "uprated " if " uprated" in m.nameString().lower() else ""
        m = m.clone(model).to_StandardOpaqueMaterial().get()
        m.setName("%s %sm tbd" % (id, up))

        d = m.thickness()
        k = _clamp(d / de_r, KMIN, KMAX)
        d = _clamp(k * de_r, DMIN, DMAX)

        if not d / k > RMIN:
            loss = (de_u - k / d) * net

        if not m.setThermalConductivity(k):
            return oslg.invalid("Can't derate %s: K%s" % (id, round(k, 3)), mth)
        if not m.setThickness(d):
            return oslg.invalid("Can't derate %s: %dmm" % (id, int(d * 1000)), mth)

    if m and loss > TOL:
        s["r_heatloss"] = loss
        oslg.log(WRN, "Won't assign %s W/K to '%s': too conductive (%s)" % ("%.3f" % s["r_heatloss"], id, mth))

    return m


def _keys_include(d, sub):
    """Mirror Ruby `hash.keys.to_s.include?(sub)`: any key contains `sub`."""
    return any(sub in k for k in d)


def _max_key(d):
    """Return the first key holding the maximum value (Ruby Hash#key(max))."""
    mx = max(d.values())
    for k, v in d.items():
        if v == mx:
            return k
    return None


def process(model=None, argh=None):
    """Detect major thermal bridges and derate opaque constructions.

    Faithful port of TBD.process — the core engine. Builds a Topolys model from
    the OpenStudio surfaces, classifies every edge as a thermal-bridge type,
    distributes the resulting heat loss onto deratable surfaces, optionally
    uprates then derates their constructions, and returns
    {"io": <dict|None>, "surfaces": <dict>}.
    """
    import math

    from . import geo
    mth = "TBD::process"
    cl = openstudio.model.Model
    tbd = {"io": None, "surfaces": {}}
    if not isinstance(model, cl):
        return oslg.mismatch("model", model, cl, mth, DBG, tbd)
    if not isinstance(argh, dict):
        if argh is None:
            argh = {}
        else:
            return oslg.mismatch("argh", argh, dict, mth, DBG, tbd)

    if not argh:
        argh = {}
    argh.setdefault("option", "")
    argh.setdefault("io_path", None)
    argh.setdefault("schema_path", None)
    argh.setdefault("parapet", True)
    argh.setdefault("uprate_walls", False)
    argh.setdefault("uprate_roofs", False)
    argh.setdefault("uprate_floors", False)
    argh.setdefault("wall_ut", 0)
    argh.setdefault("roof_ut", 0)
    argh.setdefault("floor_ut", 0)
    argh.setdefault("wall_option", "")
    argh.setdefault("roof_option", "")
    argh.setdefault("floor_option", "")
    argh.setdefault("gen_ua", False)
    argh.setdefault("ua_ref", "")
    argh.setdefault("gen_kiva", False)
    argh.setdefault("reset_kiva", False)
    argh.setdefault("sub_tol", TOL)

    if argh["gen_kiva"] not in (True, False):
        return oslg.invalid("generate KIVA option", mth, 0, DBG, tbd)
    if argh["reset_kiva"] not in (True, False):
        return oslg.invalid("reset KIVA option", mth, 0, DBG, tbd)

    t_model = py_topolys.Model()

    # A model "holds setpoints" if any zone has valid heating/cooling setpoints.
    heated = osut.hasHeatingTemperatureSetpoints(model)
    cooled = osut.hasCoolingTemperatureSetpoints(model)
    argh["setpoints"] = heated or cooled

    # 1. Fetch key attributes of every opaque surface (+ its subsurfaces).
    for s in sorted(model.getSurfaces(), key=lambda x: x.nameString()):
        surface = geo.properties(s, argh)
        if surface is not None:
            tbd["surfaces"][s.nameString()] = surface

    if not tbd["surfaces"]:
        return oslg.empty("TBD surfaces", mth, ERR, tbd)

    # 2. Mark which surfaces are deratable: conditioned, non-ground, facing
    #    outdoors or an unconditioned/unenclosed space, with an insulating layer.
    for id, surface in tbd["surfaces"].items():
        surface["deratable"] = False
        if not surface["conditioned"]:
            continue
        if surface["ground"]:
            continue
        if surface["boundary"] != "outdoors":
            if surface["boundary"] not in tbd["surfaces"]:
                continue
            if tbd["surfaces"][surface["boundary"]]["conditioned"]:
                continue
        if "index" in surface:
            surface["deratable"] = True
        else:
            oslg.log(ERR, "Skipping '%s': insulating layer? (%s)" % (id, mth))

    # Sort subsurfaces (by min Z) before processing.
    for holes in ("windows", "doors", "skylights"):
        for surface in tbd["surfaces"].values():
            if holes in surface:
                surface[holes] = dict(sorted(surface[holes].items(), key=lambda kv: kv[1]["minz"]))

    # Split into floors / ceilings / walls, sorted by (minz, space).
    def _by_minz_space(kv):
        return (kv[1]["minz"], kv[1]["space"].nameString())

    floors = {k: v for k, v in tbd["surfaces"].items() if v["type"] == "floor"}
    ceilings = {k: v for k, v in tbd["surfaces"].items() if v["type"] == "ceiling"}
    walls = {k: v for k, v in tbd["surfaces"].items() if v["type"] == "wall"}
    floors = dict(sorted(floors.items(), key=_by_minz_space))
    ceilings = dict(sorted(ceilings.items(), key=_by_minz_space))
    walls = dict(sorted(walls.items(), key=_by_minz_space))

    # Shading surfaces (their edges may become e.g. balcony thermal bridges).
    shades = {}
    for s in model.getShadingSurfaces():
        id = s.nameString()
        group = s.shadingSurfaceGroup()
        if group.empty():
            oslg.log(ERR, "Can't process '%s' transformation (%s)" % (id, mth))
            continue
        group = group.get()
        tr = osut.transforms(group)
        t = tr["t"] if (tr["t"] is not None and tr["r"] is not None) else None
        if not t:
            oslg.log(ERR, "Can't process '%s' transformation (%s)" % (id, mth))
            continue
        space = group.space()
        r = tr["r"]
        if not space.empty():
            r += space.get().directionofRelativeNorth()
        n = geo.tru_normal(s, r)
        if not n:
            oslg.log(ERR, "Can't process '%s' true normal (%s)" % (id, mth))
            continue
        points = [py_topolys.Point3D(v.x(), v.y(), v.z()) for v in (t * s.vertices())]
        minz = min(p.z for p in points)
        shades[id] = {"group": group, "points": points, "minz": minz, "n": n}

    # 3. Build the Topolys model: add all base surfaces (dads) + subsurface holes.
    holes = {}
    holes.update(geo.dads(t_model, floors))
    holes.update(geo.dads(t_model, ceilings))
    holes.update(geo.dads(t_model, walls))
    geo.dads(t_model, shades)

    # 4. Collect edges. Start with hole edges, then surface/shade faces.
    edges = {}
    for id, wire in holes.items():
        for e in wire.edges:
            i = e.id
            if i not in edges:
                edges[i] = {"length": e.length, "v0": e.v0, "v1": e.v1, "surfaces": {}}
            if wire.attributes["id"] not in edges[i]["surfaces"]:
                edges[i]["surfaces"][wire.attributes["id"]] = {"wire": wire.id}

    geo.faces(floors, edges)
    geo.faces(ceilings, edges)
    geo.faces(walls, edges)
    geo.faces(shades, edges)

    # Optional: purge existing KIVA objects, and/or generate new ones.
    if argh["reset_kiva"]:
        kva = False
        if len(model.getSurfacePropertyExposedFoundationPerimeters()) > 0:
            kva = True
        if len(model.getFoundationKivas()) > 0:
            kva = True
        if kva:
            geo.reset_kiva(model, "Foundation" if argh["gen_kiva"] else "Ground")

    if argh["gen_kiva"]:
        geo.kiva(model, walls, floors, edges)

    # 5. Compute each edge-linked surface's polar angle about the edge (this is
    #    what distinguishes concave from convex intersections).
    zenith = py_topolys.Vector3D(0, 0, 1)
    north = py_topolys.Vector3D(0, 1, 0)
    east = py_topolys.Vector3D(1, 0, 0)

    for edge in edges.values():
        origin = edge["v0"].point
        terminal = edge["v1"].point
        dx = abs(origin.x - terminal.x)
        dy = abs(origin.y - terminal.y)
        dz = abs(origin.z - terminal.z)
        horizontal = dz < TOL
        vertical = dx < TOL and dy < TOL
        edge_V = terminal - origin
        if edge_V.magnitude < TOL:
            continue

        edge_plane = py_topolys.Plane3D(origin, edge_V)

        if vertical:
            reference_V = py_topolys.Vector3D(north.x, north.y, north.z)
        elif horizontal:
            reference_V = py_topolys.Vector3D(zenith.x, zenith.y, zenith.z)
        else:  # project the zenith vector onto the edge plane
            reference = edge_plane.project(origin + zenith)
            reference_V = reference - origin

        for id, surface in edge["surfaces"].items():
            # Match the surface's wire and find its point farthest from the edge.
            for wire in t_model.wires:
                if surface["wire"] != wire.id:
                    continue

                normal = None
                if id in tbd["surfaces"]:
                    normal = tbd["surfaces"][id]["n"]
                if id in holes:
                    normal = holes[id].attributes["n"]
                if id in shades:
                    normal = shades[id]["n"]
                farthest = py_topolys.Point3D(origin.x, origin.y, origin.z)
                farthest_V = farthest - origin  # zero magnitude initially
                farthest_mag = 0

                for point in wire.points:
                    if point == origin:
                        continue
                    if point == terminal:
                        continue
                    point_on_plane = edge_plane.project(point)
                    origin_point_V = point_on_plane - origin
                    point_V_mag = origin_point_V.magnitude
                    if not point_V_mag > TOL:
                        continue
                    if not point_V_mag > farthest_mag:
                        continue
                    farthest = point
                    farthest_V = origin_point_V
                    # PARITY: upstream bug psi.rb:1741 assigns to a misspelled
                    # `fathest_mag`, so `farthest_mag` never updates (stays 0).
                    # The guard above is therefore effectively `> 0`, making
                    # `farthest` the LAST qualifying wire point, not the farthest.
                    # Reproduced verbatim (assign to a dead variable) for parity.
                    fathest_mag = point_V_mag  # noqa: F841

                angle = reference_V.angle(farthest_V)
                if angle is None:
                    angle = 0
                adjust = False  # adjust into [180deg, 360deg] if needed

                if vertical:
                    if east.dot(farthest_V) < -TOL:
                        adjust = True
                else:
                    dN = north.dot(farthest_V)
                    dN1 = abs(north.dot(farthest_V)) - 1
                    if abs(dN) < TOL or abs(dN1) < TOL:
                        if east.dot(farthest_V) < -TOL:
                            adjust = True
                    else:
                        if dN < -TOL:
                            adjust = True

                if adjust:
                    angle = 2 * math.pi - angle
                if abs(angle - 2 * math.pi) < TOL:
                    angle -= 2 * math.pi
                surface["angle"] = angle
                farthest_V.normalize_in_place()
                surface["polar"] = farthest_V
                surface["normal"] = normal

        edge["horizontal"] = horizontal
        edge["vertical"] = vertical
        edge["surfaces"] = dict(sorted(edge["surfaces"].items(), key=lambda kv: kv[1]["angle"]))

    # 6. Load JSON inputs (or the default building PSI set) and validate.
    json = inputs(tbd["surfaces"], edges, argh)
    if oslg.is_fatal():
        return tbd

    psi = json["io"]["building"]["psi"]
    shorts = json["psi"].shorthands(psi)
    if not shorts["has"] or not shorts["val"]:
        oslg.log(FTL, "Invalid or incomplete building PSI set (%s)" % mth)
        return tbd
    val = shorts["val"]

    # 7. Classify each edge as a thermal-bridge type, assembling its PSI set.
    _classify_edges(model, tbd, edges, holes, shades, floors, ceilings, walls,
                    json, psi, shorts, val, argh, zenith)

    # 8. Apply JSON overrides (subsurface U, parapet/roof, group/surface/edge PSI).
    _apply_json_overrides(model, tbd, edges, holes, json, shorts, argh)

    # 9. Demote near-coincident subsurface edges to transitions.
    _demote_transitions(model, tbd, edges, holes, json, argh)

    # 10. Distribute each edge's heat loss onto its deratable surfaces.
    for identifier, edge in edges.items():
        if "psi" not in edge:
            continue
        rsi = 0
        mx = max(edge["psi"].values())
        etype = _max_key(edge["psi"])
        length = edge["length"]
        if "mult" in edge:
            length *= edge["mult"]
        deratables = {}
        apertures = {}

        if "sets" in edge and etype in edge["sets"]:
            if "io_set" not in edge:
                edge["set"] = edge["sets"][etype]

        for id, sdata in edge["surfaces"].items():
            if id not in tbd["surfaces"]:
                continue
            if not tbd["surfaces"][id]["deratable"]:
                continue
            deratables[id] = sdata

        for id, sdata in edge["surfaces"].items():
            if id in holes:
                apertures[id] = sdata
        if len(apertures) > 1:
            continue  # edge links 2 openings

        # Prune the "dad" if the edge links an opening, its dad and an uncle.
        if len(deratables) > 1 and len(apertures) > 0:
            for id in list(deratables.keys()):
                for types in ("windows", "doors", "skylights"):
                    if types not in tbd["surfaces"][id]:
                        continue
                    for sub in tbd["surfaces"][id][types].keys():
                        if sub in apertures:
                            deratables.pop(id, None)

        if not deratables:
            continue

        for id in deratables:
            if "r" in tbd["surfaces"][id]:
                rsi += tbd["surfaces"][id]["r"]

        # Distribute in proportion to each surface's insulating-layer RSi.
        for id in deratables:
            ratio = 0
            if rsi > 0.001:
                ratio = tbd["surfaces"][id]["r"] / rsi
            loss = mx * ratio
            b = {"psi": loss, "type": etype, "length": length, "ratio": ratio}
            tbd["surfaces"][id].setdefault("edges", {})
            tbd["surfaces"][id]["edges"][identifier] = b

    # 11. Sum linear heat loss per surface.
    for id, surface in tbd["surfaces"].items():
        if "edges" not in surface:
            continue
        surface["heatloss"] = 0
        for edge in surface["edges"].values():
            surface["heatloss"] += edge["psi"] * edge["length"]

    # 12. Add JSON point conductances (KHI x count) to deratable surfaces.
    for id, sdata in tbd["surfaces"].items():
        if not sdata["deratable"]:
            continue
        if not json["io"]:
            continue
        if "surfaces" not in json["io"]:
            continue
        for surface in json["io"]["surfaces"]:
            if "khis" not in surface or "id" not in surface:
                continue
            if surface["id"] != id:
                continue
            for k in surface["khis"]:
                if "id" not in k or "count" not in k:
                    continue
                if k["id"] not in json["khi"].point:
                    continue
                if not json["khi"].point[k["id"]] > 0.001:
                    continue
                sdata.setdefault("heatloss", 0)
                sdata["heatloss"] += json["khi"].point[k["id"]] * k["count"]
                sdata.setdefault("pts", {})
                sdata["pts"][k["id"]] = {"val": json["khi"].point[k["id"]], "n": k["count"]}

    # 13. Optionally uprate targeted insulation before derating.
    up = argh["uprate_walls"] or argh["uprate_roofs"] or argh["uprate_floors"]
    if up:
        from . import ua
        ua.uprate(model, tbd["surfaces"], argh)

    # 14. Derate constructions: clone + rewrite the insulating layer per surface.
    for id, surface in tbd["surfaces"].items():
        if not all(k in surface for k in ("construction", "filmRSI", "index", "ltype", "r", "edges", "heatloss")):
            continue
        if not abs(surface["heatloss"]) > TOL:
            continue
        s = model.getSurfaceByName(id)
        if s.empty():
            continue
        s = s.get()
        index = surface["index"]
        current_c = surface["construction"]
        c = current_c.clone(model).to_LayeredConstruction().get()
        m = None
        if index is not None:
            m = derate(id, surface, c)
        if m:
            c.setLayer(index, m)
            c.setName("%s c tbd" % id)
            current_R = osut.rsi(current_c, surface["filmRSI"])
            s.setConstruction(c)

            # Derate a defaulted adjacent surface (conditioned/unconditioned split).
            if s.outsideBoundaryCondition().lower() == "surface":
                if not s.adjacentSurface().empty():
                    adjacent = s.adjacentSurface().get()
                    nom = adjacent.nameString()
                    default = adjacent.isConstructionDefaulted() is False
                    if default and nom in tbd["surfaces"]:
                        current_cc = tbd["surfaces"][nom]["construction"]
                        cc = current_cc.clone(model).to_LayeredConstruction().get()
                        cc.setLayer(tbd["surfaces"][nom]["index"], m)
                        cc.setName("%s c tbd" % nom)
                        adjacent.setConstruction(cc)

            updated_c = s.construction().get().to_LayeredConstruction().get()
            updated_R = osut.rsi(updated_c, surface["filmRSI"])
            ratio = -(current_R - updated_R) * 100 / current_R
            if abs(ratio) > TOL:
                surface["ratio"] = ratio
            surface["u"] = 1 / current_R  # un-derated U (for UA')

    # 15. Ensure all deratable surfaces carry a U-factor (even if not derated).
    for id, surface in tbd["surfaces"].items():
        if not surface["deratable"]:
            continue
        if "construction" not in surface or "filmRSI" not in surface:
            continue
        if "u" in surface:
            continue
        surface["u"] = 1.0 / osut.rsi(surface["construction"], surface["filmRSI"])

    # 16. Serialize edges into io for JSON output.
    json["io"]["edges"] = []
    for e in edges.values():
        if "psi" not in e or "set" not in e:
            continue
        v = max(e["psi"].values())
        set_ = e["set"]
        t = _max_key(e["psi"])
        l = e["length"]
        if "mult" in e:
            l *= e["mult"]
        edge = {"psi": set_, "type": t, "length": l, "surfaces": list(e["surfaces"].keys())}
        edge["v0x"] = e["v0"].point.x
        edge["v0y"] = e["v0"].point.y
        edge["v0z"] = e["v0"].point.z
        edge["v1x"] = e["v1"].point.x
        edge["v1y"] = e["v1"].point.y
        edge["v1z"] = e["v1"].point.z
        json["io"]["edges"].append(edge)

    if not json["io"]["edges"]:
        del json["io"]["edges"]
    else:
        json["io"]["edges"].sort(key=lambda e: (e["v0x"], e["v0y"], e["v0z"], e["v1x"], e["v1y"], e["v1z"]))

    # 17. Optional UA' reference values.
    if argh["gen_ua"] and argh["ua_ref"]:
        if argh["ua_ref"] == "code (Quebec)":
            from . import ua
            ua.qc33(tbd["surfaces"], json["psi"], argh["setpoints"])

    tbd["io"] = json["io"]
    argh["io"] = tbd["io"]
    argh["surfaces"] = tbd["surfaces"]
    argh["version"] = model.getVersion().versionIdentifier()

    return tbd


def _classify_edges(model, tbd, edges, holes, shades, floors, ceilings, walls,
                    json, psi, shorts, val, argh, zenith):
    """Assign a thermal-bridge PSI set to each edge (port of process lines ~1827-2434).

    For every edge linked to at least one deratable surface, walk an ordered
    cascade of tests (subsurface head/sill/jamb, spandrel, corner, ceiling,
    parapet/roof, party, grade, rimjoist/balcony) and record the matching PSI
    types/values into edge["psi"]. Untagged deratable edges become transitions.
    """
    surfaces = tbd["surfaces"]

    for edge in edges.values():
        if "surfaces" not in edge:
            continue
        deratables = []
        set_ = {}
        for id in edge["surfaces"].keys():
            if id not in surfaces:
                continue
            if surfaces[id]["deratable"]:
                deratables.append(id)
        if not deratables:
            continue

        match = False
        if "io_type" in edge:
            # A JSON-forced edge type: use the building set's safe fallback value.
            bdg = json["psi"].safe(psi, edge["io_type"])
            edge.setdefault("sets", {})
            edge["sets"][edge["io_type"]] = val[bdg]
            set_[edge["io_type"]] = val[bdg]
            edge["psi"] = set_
            if "io_set" in edge and edge["io_set"] in json["psi"].set:
                ty = json["psi"].safe(edge["io_set"], edge["io_type"])
                if ty:
                    edge["set"] = edge["io_set"]
            match = True

        for id in list(edge["surfaces"].keys()):
            if match:
                break
            if id not in surfaces:
                continue
            if id not in deratables:
                continue

            # What PSI types has this edge accumulated so far?
            iss = {}
            for key in ("doorhead", "doorsill", "doorjamb", "skylighthead",
                        "skylightsill", "skylightjamb", "spandrel", "corner",
                        "parapet", "roof", "ceiling", "party", "grade", "balcony",
                        "balconysill", "balconydoorsill", "rimjoist"):
                iss[key] = _keys_include(set_, key)
            # (Upstream's `is.empty?` head/sill/jamb block is dead code: `is` is
            #  always populated above, so it never runs.)

            # --- subsurface head / sill / jamb ---
            for i in list(edge["surfaces"].keys()):
                if any(iss.get(k) for k in ("head", "sill", "jamb", "doorhead",
                                            "doorsill", "doorjamb", "skylighthead",
                                            "skylightsill", "skylightjamb")):
                    break
                if i in deratables:
                    continue
                if i not in holes:
                    continue

                gardian = id if len(deratables) == 1 else ""
                target = gardian
                ids = _sub_ids(surfaces, id)

                if gardian == "":
                    other = deratables[-1] if deratables[0] == id else deratables[0]
                    gardian = id if i in ids else other
                    target = other if i in ids else id
                    ids = _sub_ids(surfaces, gardian)

                adj = None
                if i not in ids:  # adjacent subsurface?
                    sb = model.getSubSurfaceByName(i)
                    if sb.empty():
                        oslg.log(DBG, "Orphaned subsurface %s (%s)?" % (i, "TBD::process"))
                    else:
                        sb = sb.get()
                        adj = sb.adjacentSubSurface()
                        if adj.empty():
                            oslg.log(DBG, "Orphaned sub %s (%s)?" % (i, "TBD::process"))
                    continue

                sub = _sub_lookup(surfaces, gardian, i)
                window = sub["type"] == "window"
                door = sub["type"] == "door"
                glazed = door and sub.get("glazed", False)

                s1 = edge["surfaces"][target]
                s2 = edge["surfaces"][i]
                concave = geo.is_concave(s1, s2)
                convex = geo.is_convex(s1, s2)
                flat = not concave and not convex

                horizontal_surface = abs(abs(s2["normal"].dot(zenith)) - 1) < TOL
                if horizontal_surface:
                    if glazed or window:
                        _set_variants(set_, val, "jamb", flat, concave, convex)
                        iss["jamb"] = True
                    elif door:
                        _set_variants(set_, val, "doorjamb", flat, concave, convex)
                        iss["doorjamb"] = True
                    else:
                        _set_variants(set_, val, "skylightjamb", flat, concave, convex)
                        iss["skylightjamb"] = True
                else:
                    if glazed or window:
                        if edge["horizontal"]:
                            if s2["polar"].dot(zenith) < 0:
                                _set_variants(set_, val, "head", flat, concave, convex)
                                iss["head"] = True
                            else:
                                _set_variants(set_, val, "sill", flat, concave, convex)
                                iss["sill"] = True
                        else:
                            _set_variants(set_, val, "jamb", flat, concave, convex)
                            iss["jamb"] = True
                    elif door:
                        if edge["horizontal"]:
                            if s2["polar"].dot(zenith) < 0:
                                _set_variants(set_, val, "doorhead", flat, concave, convex)
                                iss["doorhead"] = True
                            else:
                                _set_variants(set_, val, "doorsill", flat, concave, convex)
                                iss["doorsill"] = True
                        else:
                            _set_variants(set_, val, "doorjamb", flat, concave, convex)
                            iss["doorjamb"] = True
                    else:
                        if edge["horizontal"]:
                            if s2["polar"].dot(zenith) < 0:
                                _set_variants(set_, val, "skylighthead", flat, concave, convex)
                                iss["skylighthead"] = True
                            else:
                                _set_variants(set_, val, "skylightsill", flat, concave, convex)
                                iss["skylightsill"] = True
                        else:
                            _set_variants(set_, val, "skylightjamb", flat, concave, convex)
                            iss["skylightjamb"] = True

            # --- spandrel (non-spandrel wall meets spandrel wall) ---
            for i in list(edge["surfaces"].keys()):
                if iss["spandrel"]:
                    break
                if len(deratables) != 2:
                    break
                if id not in walls or not walls[id]["spandrel"]:
                    break
                if i == id:
                    continue
                if i not in deratables or i not in walls:
                    continue
                if walls[i]["spandrel"]:
                    continue
                s1 = edge["surfaces"][id]
                s2 = edge["surfaces"][i]
                concave = geo.is_concave(s1, s2)
                convex = geo.is_convex(s1, s2)
                flat = not concave and not convex
                _set_variants(set_, val, "spandrel", flat, concave, convex)
                iss["spandrel"] = True

            # --- corner (2 deratable walls) ---
            for i in list(edge["surfaces"].keys()):
                if iss["corner"]:
                    break
                if len(deratables) != 2:
                    break
                if id not in walls:
                    break
                if i == id:
                    continue
                if i not in deratables or i not in walls:
                    continue
                s1 = edge["surfaces"][id]
                s2 = edge["surfaces"][i]
                concave = geo.is_concave(s1, s2)
                convex = geo.is_convex(s1, s2)
                if concave:
                    set_["cornerconcave"] = val["cornerconcave"]
                if convex:
                    set_["cornerconvex"] = val["cornerconvex"]
                iss["corner"] = True

            # --- ceiling (uninsulated plenum floor / occupied ceiling split) ---
            for i in list(edge["surfaces"].keys()):
                if iss["ceiling"]:
                    break
                if not len(deratables) > 0:
                    break
                if id in floors:
                    break
                if i == id:
                    continue
                if i not in floors:
                    continue
                if floors[i]["ground"] or not floors[i]["conditioned"] or floors[i]["occupied"]:
                    continue
                ceiling = floors[i]["boundary"]
                if ceiling not in ceilings:
                    continue
                if not ceilings[ceiling]["conditioned"] or not ceilings[ceiling]["occupied"]:
                    continue
                other = _other_deratable(deratables, id)
                s1 = edge["surfaces"][id]
                s2 = edge["surfaces"][other]
                concave = geo.is_concave(s1, s2)
                convex = geo.is_convex(s1, s2)
                flat = not concave and not convex
                _set_variants(set_, val, "ceiling", flat, concave, convex)
                iss["ceiling"] = True

            # --- parapet / roof (deratable wall meets deratable ceiling) ---
            for i in list(edge["surfaces"].keys()):
                if iss["parapet"] or iss["roof"]:
                    break
                if len(deratables) != 2:
                    break
                if id not in ceilings:
                    break
                if i == id:
                    continue
                if i not in deratables or i not in walls:
                    continue
                s1 = edge["surfaces"][id]
                s2 = edge["surfaces"][i]
                concave = geo.is_concave(s1, s2)
                convex = geo.is_convex(s1, s2)
                flat = not concave and not convex
                if argh["parapet"]:
                    _set_variants(set_, val, "parapet", flat, concave, convex)
                    iss["parapet"] = True
                else:
                    _set_variants(set_, val, "roof", flat, concave, convex)
                    iss["roof"] = True

            # --- party (OtherSideCoefficients surface) ---
            for i in list(edge["surfaces"].keys()):
                if iss["party"]:
                    break
                if len(deratables) != 1:
                    break
                if i == id:
                    continue
                if i not in surfaces:
                    continue
                if i in holes or i in shades:
                    continue
                if surfaces[i]["boundary"] != "othersidecoefficients":
                    continue
                s1 = edge["surfaces"][id]
                s2 = edge["surfaces"][i]
                concave = geo.is_concave(s1, s2)
                convex = geo.is_convex(s1, s2)
                flat = not concave and not convex
                _set_variants(set_, val, "party", flat, concave, convex)
                iss["party"] = True

            # --- grade (ground-facing meets outdoor) ---
            for i in list(edge["surfaces"].keys()):
                if iss["grade"]:
                    break
                if len(deratables) != 1:
                    break
                if i == id:
                    continue
                if i not in surfaces:
                    continue
                if "ground" not in surfaces[i] or not surfaces[i]["ground"]:
                    continue
                s1 = edge["surfaces"][id]
                s2 = edge["surfaces"][i]
                concave = geo.is_concave(s1, s2)
                convex = geo.is_convex(s1, s2)
                flat = not concave and not convex
                _set_variants(set_, val, "grade", flat, concave, convex)
                iss["grade"] = True

            # --- rimjoist / balcony / balconysill / balconydoorsill ---
            balcony = False
            balconysill = False
            balconydoorsill = False
            for i in list(edge["surfaces"].keys()):
                if iss["ceiling"]:
                    break
                if balcony:
                    break
                if i == id:
                    continue
                balcony = i in shades

            for i in list(edge["surfaces"].keys()):
                if not balcony:
                    break
                if balconysill or balconydoorsill:
                    break
                if i == id:
                    continue
                if i not in holes:
                    continue
                gardian = id if len(deratables) == 1 else ""
                ids = _sub_ids(surfaces, id)
                if gardian == "":
                    other = deratables[-1] if deratables[0] == id else deratables[0]
                    gardian = id if i in ids else other
                    ids = _sub_ids(surfaces, gardian)
                if i not in ids:
                    oslg.log(ERR, "Balcony sill: orphaned subsurface %s (mth)" % i)
                    continue
                sub = _sub_lookup(surfaces, gardian, i)
                window = sub["type"] == "window"
                door = sub["type"] == "door"
                glazed = door and sub.get("glazed", False)
                if window or glazed:
                    balconysill = True
                elif door:
                    balconydoorsill = True

            for i in list(edge["surfaces"].keys()):
                if any(iss[k] for k in ("ceiling", "rimjoist", "balcony", "balconysill", "balconydoorsill")):
                    break
                if not len(deratables) > 0:
                    break
                if id in floors:
                    break
                if i == id:
                    continue
                if i not in floors:
                    continue
                if floors[i]["ground"] or not floors[i]["conditioned"]:
                    continue
                other = _other_deratable(deratables, id)
                s1 = edge["surfaces"][id]
                s2 = edge["surfaces"][other]
                concave = geo.is_concave(s1, s2)
                convex = geo.is_convex(s1, s2)
                flat = not concave and not convex
                if balconydoorsill:
                    _set_variants(set_, val, "balconydoorsill", flat, concave, convex)
                    iss["balconydoorsill"] = True
                elif balconysill:
                    _set_variants(set_, val, "balconysill", flat, concave, convex)
                    iss["balconysill"] = True
                elif balcony:
                    _set_variants(set_, val, "balcony", flat, concave, convex)
                    iss["balcony"] = True
                else:
                    _set_variants(set_, val, "rimjoist", flat, concave, convex)
                    iss["rimjoist"] = True

        if set_:
            edge["psi"] = set_
            edge["set"] = psi

    # Untagged edges between deratable surfaces become (mild) transitions.
    for edge in edges.values():
        if "psi" in edge or "surfaces" not in edge:
            continue
        deratable = False
        for id in edge["surfaces"].keys():
            if id not in tbd["surfaces"]:
                continue
            if tbd["surfaces"][id]["deratable"]:
                deratable = tbd["surfaces"][id]["deratable"]
        if not deratable:
            continue
        edge["psi"] = {"transition": 0.000}
        edge["set"] = json["io"]["building"]["psi"]

    # 'Unhinged' subsurface edges (e.g. TDD domes) inherit their parent's :jamb.
    for edge in edges.values():
        if "psi" in edge or "surfaces" not in edge:
            continue
        if len(edge["surfaces"]) != 1:
            continue
        id = next(iter(edge["surfaces"]))
        if id not in holes:
            continue
        if "unhinged" not in holes[id].attributes or not holes[id].attributes["unhinged"]:
            continue
        subsurface = model.getSubSurfaceByName(id)
        if subsurface.empty():
            continue
        subsurface = subsurface.get()
        surface = subsurface.surface()
        if surface.empty():
            continue
        nom = surface.get().nameString()
        if nom not in tbd["surfaces"]:
            continue
        if "conditioned" not in tbd["surfaces"][nom] or not tbd["surfaces"][nom]["conditioned"]:
            continue
        edge["surfaces"][nom] = {}
        edge["psi"] = {"jamb": shorts["val"]["jamb"]}
        edge["set"] = json["io"]["building"]["psi"]


# --- classification helpers --------------------------------------------------

def _sub_ids(surfaces, id):
    """All subsurface ids (windows + doors + skylights) of base surface `id`."""
    out = []
    for holes in ("windows", "doors", "skylights"):
        if holes in surfaces[id]:
            out += list(surfaces[id][holes].keys())
    return out


def _sub_lookup(surfaces, gardian, i):
    """Return subsurface `i`'s descriptor from its gardian base surface."""
    for holes in ("windows", "doors", "skylights"):
        if holes in surfaces[gardian] and i in surfaces[gardian][holes]:
            return surfaces[gardian][holes][i]
    return {}


def _other_deratable(deratables, id):
    """The 'other' deratable id (or `id` itself if the edge has just one)."""
    if len(deratables) == 1:
        return id
    other = id
    if deratables[0] != id:
        other = deratables[0]
    if deratables[-1] != id:
        other = deratables[-1]
    return other


def _set_variants(set_, val, base, flat, concave, convex):
    """Assign a base PSI type's flat/concave/convex variant into `set_`."""
    if flat:
        set_[base] = val[base]
    if concave:
        set_[base + "concave"] = val[base + "concave"]
    if convex:
        set_[base + "convex"] = val[base + "convex"]


def _apply_json_overrides(model, tbd, edges, holes, json, shorts, argh):
    """Apply TBD-JSON overrides in precedence order (port of ~2436-2751)."""
    surfaces = tbd["surfaces"]
    if not json["io"]:
        return

    io = json["io"]

    # Reset subsurface U-factors from file.
    if "subsurfaces" in io:
        for sub in io["subsurfaces"]:
            if "id" not in sub or "usi" not in sub:
                continue
            match = False
            for surface in surfaces.values():
                if match:
                    break
                for types in ("windows", "doors", "skylights"):
                    if match:
                        break
                    if types not in surface:
                        continue
                    for sid, opening in surface[types].items():
                        if match:
                            break
                        if "u" not in opening:
                            continue
                        if sub["id"] != sid:
                            continue
                        opening["u"] = sub["usi"]
                        match = True

    # Reset wall-to-roof intersection type (parapet vs roof), per group.
    for groups in ("stories", "spacetypes", "spaces"):
        key = {"stories": "story", "spacetypes": "stype", "spaces": "space"}[groups]
        if groups not in io:
            continue
        for group in io[groups]:
            if "id" not in group or "parapet" not in group:
                continue
            for edge in edges.values():
                if "psi" not in edge or "surfaces" not in edge or "io_type" in edge:
                    continue
                match = False
                for id in edge["surfaces"].keys():
                    if match:
                        break
                    if id not in surfaces or key not in surfaces[id]:
                        continue
                    match = group["id"] == surfaces[id][key].nameString()
                if not match:
                    continue
                _swap_parapet_roof(edge, shorts, group["parapet"])

    # Reset parapet/roof type, per individual surface.
    if "surfaces" in io:
        for surface in io["surfaces"]:
            if "parapet" not in surface or "id" not in surface:
                continue
            for edge in edges.values():
                if "io_type" in edge or "psi" not in edge or "surfaces" not in edge:
                    continue
                if surface["id"] not in edge["surfaces"]:
                    continue
                _swap_parapet_roof(edge, shorts, surface["parapet"])

    # Custom PSI sets: stories < spacetypes < spaces (each trumps the prior).
    for groups in ("stories", "spacetypes", "spaces"):
        key = {"stories": "story", "spacetypes": "stype", "spaces": "space"}[groups]
        if groups in io:
            for group in io[groups]:
                if "id" not in group or "psi" not in group:
                    continue
                if group["psi"] not in json["psi"].set:
                    continue
                sh = json["psi"].shorthands(group["psi"])
                if not sh["val"]:
                    continue
                for edge in edges.values():
                    if "psi" not in edge or "surfaces" not in edge or "io_set" in edge:
                        continue
                    match = False
                    for id in edge["surfaces"].keys():
                        if match:
                            break
                        if id not in surfaces or key not in surfaces[id]:
                            continue
                        match = group["id"] == surfaces[id][key].nameString()
                    if not match:
                        continue
                    st = {}
                    edge.setdefault(groups, {})
                    edge[groups][group["psi"]] = {}
                    if "io_type" in edge:
                        safer = json["psi"].safe(group["psi"], edge["io_type"])
                        if safer:
                            st[edge["io_type"]] = sh["val"][safer]
                    else:
                        for ty in list(edge["psi"].keys()):
                            safer = json["psi"].safe(group["psi"], ty)
                            if safer:
                                st[ty] = sh["val"][safer]
                    if st:
                        edge[groups][group["psi"]] = st

        # When multiple group sets target a shared edge, keep the most conductive.
        for edge in edges.values():
            if "psi" not in edge or groups not in edge:
                continue
            for ty in list(edge["psi"].keys()):
                vals = {}
                for st in edge[groups].keys():
                    sh = json["psi"].shorthands(st)
                    if not sh["val"]:
                        continue
                    safer = json["psi"].safe(st, ty)
                    if safer:
                        vals[st] = sh["val"][safer]
                if not vals:
                    continue
                mx = max(vals.values())
                edge["psi"][ty] = mx
                edge.setdefault("sets", {})
                edge["sets"][ty] = _dict_key_for_value(vals, mx)

    # Custom per-surface PSI sets.
    if "surfaces" in io:
        for surface in io["surfaces"]:
            if "psi" not in surface or "id" not in surface:
                continue
            if surface["id"] not in surfaces:
                continue
            if surface["psi"] not in json["psi"].set:
                continue
            sh = json["psi"].shorthands(surface["psi"])
            if not sh["val"]:
                continue
            for edge in edges.values():
                if "io_set" in edge or "psi" not in edge or "surfaces" not in edge:
                    continue
                if surface["id"] not in edge["surfaces"]:
                    continue
                sdata = edge["surfaces"][surface["id"]]
                st = {}
                if "io_type" in edge:
                    safer = json["psi"].safe(surface["psi"], edge["io_type"])
                    if safer:
                        st["io_type"] = sh["val"][safer]
                else:
                    for ty in list(edge["psi"].keys()):
                        safer = json["psi"].safe(surface["psi"], ty)
                        if safer:
                            st[ty] = sh["val"][safer]
                if not st:
                    continue
                sdata["psi"] = st
                sdata["set"] = surface["psi"]

        for edge in edges.values():
            if "psi" not in edge or "surfaces" not in edge:
                continue
            for ty in list(edge["psi"].keys()):
                vals = {}
                for id, sdata in edge["surfaces"].items():
                    if "psi" not in sdata or "set" not in sdata or not sdata["set"]:
                        continue
                    sh = json["psi"].shorthands(sdata["set"])
                    if not sh["val"]:
                        continue
                    safer = json["psi"].safe(sdata["set"], ty)
                    if safer:
                        vals[sdata["set"]] = sh["val"][safer]
                if not vals:
                    continue
                mx = max(vals.values())
                edge["psi"][ty] = mx
                edge.setdefault("sets", {})
                edge["sets"][ty] = _dict_key_for_value(vals, mx)

    # Customized edges on file (with/without a custom PSI set).
    for edge in edges.values():
        if "psi" not in edge or "io_type" not in edge or "surfaces" not in edge:
            continue
        if "io_set" in edge:
            if edge["io_set"] not in json["psi"].set:
                continue
            st = edge["io_set"]
        else:
            if "sets" not in edge or edge["io_type"] not in edge["sets"]:
                continue
            if edge["sets"][edge["io_type"]] not in json["psi"].set:
                continue
            st = edge["sets"][edge["io_type"]]
        sh = json["psi"].shorthands(st)
        if not sh["val"]:
            continue
        safer = json["psi"].safe(st, edge["io_type"])
        if not safer:
            continue
        if "io_set" in edge:
            edge["psi"] = {}
            edge["set"] = edge["io_set"]
        else:
            edge.setdefault("sets", {})
            edge["sets"][edge["io_type"]] = sh["val"][safer]
        edge["psi"][edge["io_type"]] = sh["val"][safer]


def _swap_parapet_roof(edge, shorts, want_parapet):
    """Swap an edge's parapet<->roof PSI keys per a JSON `parapet` flag."""
    parapets = [ty for ty in edge["psi"] if "parapet" in ty]
    roofs = [ty for ty in edge["psi"] if "roof" in ty]
    if want_parapet:
        if parapets or not roofs:
            return
        ty = "parapet"
        if "concave" in roofs[0]:
            ty = "parapetconcave"
        if "convex" in roofs[0]:
            ty = "parapetconvex"
        edge["psi"][ty] = shorts["val"][ty]
        for t in roofs:
            edge["psi"].pop(t, None)
    else:
        if roofs or not parapets:
            return
        ty = "roof"
        if "concave" in parapets[0]:
            ty = "roofconcave"
        if "convex" in parapets[0]:
            ty = "roofconvex"
        edge["psi"][ty] = shorts["val"][ty]
        for t in parapets:
            edge["psi"].pop(t, None)


def _dict_key_for_value(d, value):
    """First key whose value equals `value` (Ruby Hash#key)."""
    for k, v in d.items():
        if v == value:
            return k
    return None


def _demote_transitions(model, tbd, edges, holes, json, argh):
    """Edge multipliers + proximity-based transition demotion (port ~2753-2858)."""
    # Fetch subsurface edge multipliers (>1) onto their head/sill/jamb edges.
    for edge in edges.values():
        if "mult" in edge or "surfaces" not in edge or "psi" not in edge:
            continue
        ok = False
        for k in edge["psi"].keys():
            if ok:
                break
            ok = ("jamb" in k) or ("sill" in k) or ("head" in k)
        if not ok:
            continue
        for id, surface in edge["surfaces"].items():
            if id not in tbd["surfaces"]:
                continue
            for subtypes in ("windows", "doors", "skylights"):
                if subtypes not in tbd["surfaces"][id]:
                    continue
                for nom, sub in tbd["surfaces"][id][subtypes].items():
                    if nom not in edge["surfaces"]:
                        continue
                    if not sub["mult"] > 1:
                        continue
                    if "mult" not in edge:
                        edge["mult"] = sub["mult"]
                    if sub["mult"] > edge["mult"]:
                        edge["mult"] = sub["mult"]

    # Demote a lone subsurface edge to a transition when it nearly coincides with
    # another lone subsurface edge (both endpoints within sub_tol).
    for id, edge in edges.items():
        nb = 0
        match = False
        if "io_type" in edge or "v0" not in edge or "v1" not in edge:
            continue
        if "psi" not in edge or "surfaces" not in edge:
            continue
        for identifier in edge["surfaces"].keys():
            if match:
                break
            if identifier not in holes:
                continue
            if "unhinged" in holes[identifier].attributes:
                if holes[identifier].attributes["unhinged"]:
                    nb = 0
                    break
            nb += 1
            if nb > 1:
                match = True

        if nb == 1:
            e1 = {"v0": edge["v0"].point, "v1": edge["v1"].point}
            for nom, e in edges.items():
                nb = 0
                if match:
                    break
                if nom == id or "io_type" in e or "psi" not in e or "surfaces" not in e:
                    continue
                for identifier in e["surfaces"].keys():
                    if identifier not in holes:
                        continue
                    if "unhinged" in holes[identifier].attributes:
                        if holes[identifier].attributes["unhinged"]:
                            nb = 0
                            break
                    nb += 1
                if nb != 1:
                    continue
                e2 = {"v0": e["v0"].point, "v1": e["v1"].point}
                match = geo.matches(e1, e2, argh["sub_tol"])

        if not match:
            continue
        edge["psi"] = {"transition": 0.000}
        edge["set"] = json["io"]["building"]["psi"]


def exit(runner=None, argh=None, out_dir=None):
    """Finalize a TBD run: assemble io["log"], write tbd.out.json + UA reports.

    Faithful port of TBD.exit, adapted for library use: `runner` (an OpenStudio
    Measure OSRunner) is OPTIONAL — when None, the runner.register* calls are
    skipped and files are written to `out_dir` (default: current directory).
    Returns False on a fatal state, True otherwise.
    """
    import datetime

    from . import ua as ua_mod
    groups = {"wall": {}, "roof": {}, "floor": {}}
    status = oslg.status()
    state = oslg.msg(status)
    if status == 0:
        state = oslg.msg(INF)
    if not isinstance(argh, dict):
        argh = {}
    argh.setdefault("io", None)
    argh.setdefault("surfaces", None)

    if not (argh["io"] and argh["surfaces"]):
        state = "Halting all TBD processes, yet running OpenStudio"
        if oslg.is_fatal():
            state = "Halting all TBD processes, and halting OpenStudio"

    if not argh["io"]:
        argh["io"] = {}
    argh.setdefault("seed", "")
    argh.setdefault("version", "")
    argh.setdefault("gen_ua", False)
    argh.setdefault("ua_ref", "")
    argh.setdefault("setpoints", False)
    argh.setdefault("write_tbd", False)
    argh.setdefault("uprate_walls", False)
    argh.setdefault("uprate_roofs", False)
    argh.setdefault("uprate_floors", False)
    argh.setdefault("wall_ut", UMAX)
    argh.setdefault("roof_ut", UMAX)
    argh.setdefault("floor_ut", UMAX)
    argh.setdefault("wall_option", "")
    argh.setdefault("roof_option", "")
    argh.setdefault("floor_option", "")
    argh.setdefault("wall_uo", None)
    argh.setdefault("roof_uo", None)
    argh.setdefault("floor_uo", None)

    groups["wall"]["up"] = argh["uprate_walls"]
    groups["roof"]["up"] = argh["uprate_roofs"]
    groups["floor"]["up"] = argh["uprate_floors"]
    groups["wall"]["ut"] = argh["wall_ut"]
    groups["roof"]["ut"] = argh["roof_ut"]
    groups["floor"]["ut"] = argh["floor_ut"]
    groups["wall"]["op"] = argh["wall_option"]
    groups["roof"]["op"] = argh["roof_option"]
    groups["floor"]["op"] = argh["floor_option"]
    groups["wall"]["uo"] = argh["wall_uo"]
    groups["roof"]["uo"] = argh["roof_uo"]
    groups["floor"]["uo"] = argh["floor_uo"]

    io = argh["io"]
    out = argh["write_tbd"]
    descr = ""
    if argh["seed"]:
        descr = argh["seed"]
    if "description" not in io:
        io["description"] = descr
    descr = io["description"]

    schema_pth = "https://github.com/rd2/tbd/blob/master/tbd.schema.json"
    if "schema" not in io:
        io["schema"] = schema_pth
    tbd_log = {"date": datetime.datetime.now(), "status": state}
    u_t = []

    for label, g in groups.items():
        if oslg.is_fatal():
            continue
        if not g["uo"]:
            continue
        if not _is_num(g["uo"]):
            continue
        uo_s = "%.3f" % g["uo"]
        ut_s = "%.3f" % g["ut"]
        output = ("An area-weighted %s Uo of %s W/m2•K is required to meet an "
                  "overall Ut of %s W/m2•K for %s" % (label, uo_s, ut_s, g["op"]))
        u_t.append(output)
        if runner is not None:
            runner.registerInfo(output)

    if u_t:
        tbd_log["ut"] = u_t
    ua_md_en = None
    ua_md_fr = None
    ua = None
    ok = argh["surfaces"] and argh["gen_ua"]
    if ok:
        ua = ua_mod.ua_summary(tbd_log["date"], argh)

    if not (oslg.is_fatal() or ua is None or not ua):
        if "en" in ua:
            if "b1" in ua["en"] or "b2" in ua["en"]:
                tbd_log["ua"] = {}
                if runner is not None:
                    runner.registerInfo("-")
                    runner.registerInfo(ua["model"])
                ua_md_en = ua_mod.ua_md(ua, "en")
                ua_md_fr = ua_mod.ua_md(ua, "fr")
            if "b1" in ua["en"] and "summary" in ua["en"]["b1"]:
                if runner is not None:
                    runner.registerInfo(" - %s" % ua["en"]["b1"]["summary"])
                    for k, v in ua["en"]["b1"].items():
                        if k != "summary":
                            runner.registerInfo(" --- %s" % v)
                tbd_log["ua"]["bloc1"] = ua["en"]["b1"]
            if "b2" in ua["en"] and "summary" in ua["en"]["b2"]:
                if runner is not None:
                    runner.registerInfo(" - %s" % ua["en"]["b2"]["summary"])
                    for k, v in ua["en"]["b2"].items():
                        if k != "summary":
                            runner.registerInfo(" --- %s" % v)
                tbd_log["ua"]["bloc2"] = ua["en"]["b2"]
        if runner is not None:
            runner.registerInfo(" -")

    results = []
    if argh["surfaces"]:
        for id, surface in argh["surfaces"].items():
            if oslg.is_fatal():
                continue
            if "ratio" not in surface:
                continue
            ratio = "%4.1f" % surface["ratio"]
            output = "RSi derated by %s%% : %s" % (ratio, id)
            results.append(output)
            if runner is not None:
                runner.registerInfo(output)

    if results:
        tbd_log["results"] = results
    tbd_msgs = []
    for l in oslg.logs():
        tbd_msgs.append({"level": oslg.tag(l["level"]), "message": l["message"]})
        if runner is not None:
            if l["level"] > INF:
                runner.registerWarning(l["message"])
            else:
                runner.registerInfo(l["message"])

    if tbd_msgs:
        tbd_log["messages"] = tbd_msgs
    io["log"] = tbd_log

    # Prune non-essential io keys unless detailed output was requested.
    if not out:
        for k in ("psis", "khis", "building", "stories", "spacetypes", "spaces", "surfaces", "edges"):
            io.pop(k, None)

    # Deterministic key ordering (pop + re-add moves each key to the end).
    for k in ("schema", "description", "log", "psis", "khis", "building",
              "stories", "spacetypes", "spaces", "surfaces", "edges"):
        if k in io:
            io[k] = io.pop(k)

    # Resolve the output directory (from the runner's workflow, else out_dir/cwd).
    resolved = out_dir if out_dir else "."
    if runner is not None:
        try:
            file_paths = list(runner.workflow().absoluteFilePaths())
            import re as _re
            if len(file_paths) >= 2 and os.path.exists(str(file_paths[1]).strip()) and \
               (_re.search("WorkingFiles", str(file_paths[1]).strip()) or _re.search("files", str(file_paths[1]).strip())):
                resolved = str(file_paths[1]).strip()
            elif file_paths and os.path.exists(str(file_paths[0]).strip()):
                resolved = str(file_paths[0]).strip()
        except Exception:
            pass

    out_path = os.path.join(resolved, "tbd.out.json")
    with open(out_path, "w") as f:
        f.write(json.dumps(io, indent=2, default=str))
        f.write("\n")

    if not (oslg.is_fatal() or ua is None or not ua):
        if ua_md_en:
            with open(os.path.join(resolved, "ua_en.md"), "w") as f:
                f.write("\n".join(ua_md_en) + "\n")
        if ua_md_fr:
            with open(os.path.join(resolved, "ua_fr.md"), "w") as f:
                f.write("\n".join(ua_md_fr) + "\n")

    if oslg.is_fatal():
        if runner is not None:
            runner.registerError("%s - see 'tbd.out.json'" % state)
        return False
    elif oslg.is_error() or oslg.is_warn():
        if runner is not None:
            runner.registerWarning("%s - see 'tbd.out.json'" % state)
        return True
    else:
        if runner is not None:
            runner.registerInfo("%s - see 'tbd.out.json'" % state)
        return True


def _to_f_ok(x):
    """True if x is coercible to float (mirrors Ruby respond_to?(:to_f))."""
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False
