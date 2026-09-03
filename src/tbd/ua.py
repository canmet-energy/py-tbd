# Native Python port of lib/tbd/ua.rb from the TBD Ruby gem: construction
# uprating (uo/uprate), the Quebec 3.3 reference-value pass (qc33), and the
# bilingual (EN/FR) UA' summary/report (ua_summary/ua_md).
#
# Ruby symbol keys -> Python str keys. Ruby's `extend OSut` mixin -> explicit
# osut./oslg. calls. `format(...)` -> Python `%` formatting (identical for the
# `%.1f`/`%.3f` specifiers used here). Bilingual strings are copied verbatim.

import datetime

from ._helpers import oslg, osut, DBG, INF, WRN, ERR, TOL, UMIN, UMAX
from ._helpers import RMIN, KMIN, KMAX, DMIN, DMAX
from .psi import PSI


def _clamp(x, lo, hi):
    """Ruby Numeric#clamp(lo, hi): bound x to the [lo, hi] range."""
    return lo if x < lo else (hi if x > hi else x)


def _is_num(x):
    """True for real numbers (excludes bool), mirroring Ruby is_a?(Numeric)."""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def uo(id="", lc=None, area=0, film=0, hloss=0, ut=0):
    """Compute (and apply) the nominal Uo a construction needs to meet a target Ut.

    Faithful port of TBD.uo. Clones and rewrites the construction's insulating
    layer so the assembly meets `ut` [W/m2K] while offsetting `hloss` [W/K] of
    thermal-bridge heat loss over `area` [m2], given target film resistance
    `film`. Returns the achieved Uo (0 on error, UMIN if it can't be met).
    """
    mth = "TBD::uo"
    cl1 = _lc_class()
    id = oslg.trim(id)
    if id == "":
        return oslg.mismatch("id", id, str, mth, DBG, 0)
    if not isinstance(lc, cl1):
        return oslg.mismatch("lc", lc, cl1, mth, DBG, 0)
    if not _is_num(area):
        return oslg.mismatch("area", area, float, mth, DBG, 0)
    if not _is_num(film):
        return oslg.mismatch("film", film, float, mth, DBG, 0)
    if not _is_num(hloss):
        return oslg.mismatch("hloss", hloss, float, mth, DBG, 0)
    if not _is_num(ut):
        return oslg.mismatch("Ut", ut, float, mth, DBG, 0)

    model = lc.model()
    loss = 0
    lyr = osut.insulatingLayer(lc)

    # Validate the insulating-layer index. (Upstream chains `nil >= 0` guards
    # that would raise on a nil index; here we short-circuit to the same
    # invalid-layer outcome without the exception.)
    idx = lyr["index"]
    if not _is_num(idx):
        idx = None
    if idx is not None and not (idx >= 0):
        idx = None
    if idx is not None and not (idx < len(lc.layers())):
        idx = None
    if idx is None:
        return oslg.invalid("%s layer index" % id, mth, 3, DBG, 0)
    if not (area > TOL):
        return oslg.zero("%s: net area (m2)" % id, mth, DBG, 0)
    if film < 0:
        return oslg.negative("%s: film RSI" % id, mth, DBG, 0)
    if hloss < TOL:
        return oslg.zero("%s: heatloss" % id, mth, DBG, 0)
    if not (ut > UMIN):
        return oslg.zero("%s: Ut" % id, mth, DBG, 0)
    if not (ut < UMAX):
        return oslg.invalid("%s: Ut" % id, mth, 4, DBG, 0)

    # Initial (un-derated) layer RSi that would meet Ut before bridging.
    rt = 1 / ut            # target construction Rt
    r0 = osut.rsi(lc, film)  # current construction R0
    r = lyr["r"] + rt - r0  # new layer RSi

    if r < 0:
        oslg.zero("%s: layer RSI" % id, mth, INF)
        r = RMIN

    # Uprate further to counter the thermal-bridge heat loss.
    u = 1 / r
    u -= hloss / area

    if u < UMIN:
        oslg.negative("%s: new Uo" % id, mth, INF)
        u = UMIN

    r = 1 / u

    if lyr["type"] == "massless":
        m = lc.getLayer(idx).to_MasslessOpaqueMaterial()
        if m.empty():
            return oslg.invalid("%s massless layer?" % id, mth, 0, DBG, 0)
        m = m.get().clone(model).to_MasslessOpaqueMaterial().get()
        m.setName("%s uprated" % id)

        if r < RMIN:
            r = RMIN
            loss = (u - 1 / r) * area  # residual heat loss we couldn't place

        if not m.setThermalResistance(r):
            return oslg.invalid("Can't uprate %s: RSi%s" % (id, round(r, 2)), mth, 0, DBG, 0)
    else:
        m = lc.getLayer(idx).to_StandardOpaqueMaterial()
        if m.empty():
            return oslg.invalid("%s standard layer?" % id, mth, 0, DBG, 0)
        m = m.get().clone(model).to_StandardOpaqueMaterial().get()
        m.setName("%s uprated" % id)

        d = m.thickness()
        k = _clamp(d / r, KMIN, KMAX)
        d = _clamp(k * r, DMIN, DMAX)

        if d / k < RMIN:
            loss = (u - k / d) * area

        if not m.setThermalConductivity(k):
            return oslg.invalid("Can't uprate %s: K%s" % (id, round(k, 3)), mth, 0, DBG, 0)
        if not m.setThickness(d):
            return oslg.invalid("Can't uprate %s: %dmm" % (id, int(d * 1000)), mth, 0, DBG, 0)

    if not m:
        return oslg.invalid("Can't ID insulating layer", mth, 0, DBG, 0)

    lc.setLayer(idx, m)
    ro = osut.rsi(lc, film)
    uo_val = UMIN if ro < RMIN else 1 / ro

    if loss > TOL:
        oslg.log(INF, "Can't set %s W/K to %s %s" % ("%.3f" % loss, id, mth))

    return uo_val


def uprate(model=None, s=None, argh=None):
    """Uprate wall/roof/floor insulation layers to user-selected Ut targets.

    Faithful port of TBD.uprate. Groups deratable surfaces by construction,
    clones shared constructions that also span non-targeted surfaces, computes
    an area-weighted film resistance per construction and calls uo(), then writes
    back area-weighted uprated Uo per type into argh (wall_uo/roof_uo/floor_uo).
    Returns True (False on invalid input, logged).
    """
    mth = "TBD::uprate"
    cl1 = _model_class()
    cl3 = _lc_class()
    # The three "all X constructions" sentinels that mean "uprate every one".
    tout = ["all wall constructions", "all roof constructions", "all floor constructions"]
    a = False
    groups = {"wall": {}, "roof": {}, "floor": {}}
    if s is None:
        s = {}
    if argh is None:
        argh = {}
    if not isinstance(model, cl1):
        return oslg.mismatch("model", model, cl1, mth, DBG, a)
    if not isinstance(s, dict):
        return oslg.mismatch("surfaces", s, dict, mth, DBG, a)
    if not isinstance(argh, dict):
        return oslg.mismatch("argh", argh, dict, mth, DBG, a)

    argh.setdefault("uprate_walls", False)
    argh.setdefault("uprate_roofs", False)
    argh.setdefault("uprate_floors", False)
    argh.setdefault("wall_ut", UMAX)
    argh.setdefault("roof_ut", UMAX)
    argh.setdefault("floor_ut", UMAX)
    argh.setdefault("wall_option", "")
    argh.setdefault("roof_option", "")
    argh.setdefault("floor_option", "")

    argh["wall_option"] = oslg.trim(argh["wall_option"])
    argh["roof_option"] = oslg.trim(argh["roof_option"])
    argh["floor_option"] = oslg.trim(argh["floor_option"])

    groups["wall"]["up"] = argh["uprate_walls"]
    groups["roof"]["up"] = argh["uprate_roofs"]
    groups["floor"]["up"] = argh["uprate_floors"]
    groups["wall"]["ut"] = argh["wall_ut"]
    groups["roof"]["ut"] = argh["roof_ut"]
    groups["floor"]["ut"] = argh["floor_ut"]
    groups["wall"]["op"] = oslg.trim(argh["wall_option"])
    groups["roof"]["op"] = oslg.trim(argh["roof_option"])
    groups["floor"]["op"] = oslg.trim(argh["floor_option"])

    # Walls, roofs and floors are uprated sequentially and independently.
    for type, g in groups.items():
        if not g["up"]:
            continue
        if not _is_num(g["ut"]):
            continue
        if not (g["ut"] < UMAX):
            continue
        if not (g["ut"] > UMIN):
            continue

        typ = type
        if typ == "roof":
            typ = "ceiling"  # TBD surface type for roofs

        coll = {}       # construction id -> aggregation state
        op = g["op"]

        if op.lower() in tout:
            # Uprate ALL constructions of this type.
            for nom, surface in s.items():
                if not _uprate_surface_ok(surface, cl3):
                    continue
                if surface["type"] != typ:
                    continue
                lc = surface["construction"]
                id = lc.nameString()
                _coll_init(coll, id, lc)
                coll[id].setdefault("idx", surface["index"])
                coll[id].setdefault("ltp", surface["ltype"])
                _coll_add_surface(coll[id], nom, surface)
        else:
            # Uprate a single, user-named construction.
            id = op
            lc = model.getConstructionByName(id)
            if lc.empty():
                oslg.log(WRN, "Construction '%s'? (%s)" % (id, mth))
                continue
            lc = lc.get().to_LayeredConstruction()
            if lc.empty():
                oslg.log(WRN, "'%s' layered construction? (%s)" % (id, mth))
                continue
            lc = lc.get()

            _coll_init(coll, id, lc)
            for nom, surface in s.items():
                if not _uprate_surface_ok(surface, cl3):
                    continue
                if surface["type"] != typ:
                    continue
                if surface["construction"].nameString() != id:
                    continue
                coll[id].setdefault("idx", surface["index"])
                coll[id].setdefault("ltp", surface["ltype"])
                _coll_add_surface(coll[id], nom, surface)

        if not coll:
            oslg.log(WRN, "Unable to uprate %s construction - skipping (%s)" % (type, mth))
            continue

        # Ensure each construction is exclusive to deratable, targeted surfaces;
        # otherwise clone it onto the non-targeted surfaces that share it.
        for id, col in coll.items():
            lc = col["lc"]
            for nom, surface in s.items():
                if not _uprate_surface_ok(surface, cl3, require_deratable=True, require_type=False):
                    continue
                if surface["construction"] is not lc:
                    continue
                if surface["index"] is None:
                    continue
                if surface["type"] == typ:
                    continue
                if nom in coll[id]["s"]:
                    continue
                oslg.log(INF, "Cloning '%s' construction - not '%s' (%s)" % (nom, id, mth))
                srf = model.getSurfaceByName(nom)
                if srf.empty():
                    continue
                srf = srf.get()
                cloned = lc.clone(model).to_LayeredConstruction().get()
                cloned.setName("%s - cloned" % nom)
                srf.setConstruction(cloned)
                surface["construction"] = cloned

        for id, col in coll.items():
            for item in col["s"].values():
                col["hloss"] += item["h"]
                col["area"] += item["a"]
                if not item["f"] < 0:
                    col["fA"] += item["a"] / item["f"]

            if col["area"] < TOL:
                oslg.empty("%s area" % id, mth, WRN)
                continue

            # Area-weighted air-film resistance for the whole construction.
            col["film"] = 1 / (col["fA"] / col["area"])

            u = uo(id, col["lc"], col["area"], col["film"], col["hloss"], g["ut"])
            if not (u > UMIN):
                oslg.log(WRN, "Unable to completely uprate '%s' (%s)" % (id, mth))
                u = UMIN

            col["u"] = u
            col["uA"] = u * col["area"]

            # Reset each surface's :r to the uprated (pre-derating) insulation RSi.
            lc = col["lc"]
            lyr = osut.insulatingLayer(lc)
            for nom in col["s"].keys():
                if nom not in s:
                    continue
                if "r" not in s[nom]:
                    continue
                s[nom]["r"] = lyr["r"]

        # Area-weighted uprated Uo for this type, back into argh.
        area = sum(col["area"] for col in coll.values())
        uA = sum(col["uA"] for col in coll.values() if "uA" in col)
        if area > TOL:
            if typ == "wall":
                argh["wall_uo"] = uA / area
            if typ == "ceiling":
                argh["roof_uo"] = uA / area
            if typ == "floor":
                argh["floor_uo"] = uA / area

    return True


# --- uprate helpers ----------------------------------------------------------

def _uprate_surface_ok(surface, cl3, require_deratable=True, require_type=True):
    """The long guard shared by uprate's surface loops (keys + deratable + type)."""
    for key in ("deratable", "type", "construction", "filmRSI", "ltype", "r", "index", "net"):
        if key not in surface:
            return False
    if require_deratable and not surface["deratable"]:
        return False
    if not isinstance(surface["construction"], cl3):
        return False
    if surface["index"] is None:
        return False
    return True


def _coll_init(coll, id, lc):
    """Initialize the per-construction aggregation record (once)."""
    if id in coll:
        return
    coll[id] = {"lc": lc, "s": {}, "hloss": 0, "area": 0, "film": 0, "fA": 0, "uA": 0, "u0": 0}


def _coll_add_surface(col, nom, surface):
    """Record a surface's net area, film resistance and (major-TB) heat loss."""
    if nom in col["s"]:
        return
    col["s"][nom] = {"a": surface["net"], "f": surface["filmRSI"], "h": 0}
    if "heatloss" not in surface:
        return
    if not abs(surface["heatloss"]) > TOL:
        return
    col["s"][nom]["h"] = surface["heatloss"]


def qc33(s=None, sets=None, spts=True):
    """Set Quebec-code (Section 3.3) reference U/PSI values on surfaces & bridges.

    Faithful port of TBD.qc33. Writes a "ref" value onto each deratable surface,
    its subsurfaces, its point bridges (pts) and linear bridges (edges), for the
    UA' trade-off comparison. Returns True (False on invalid input, logged).
    """
    mth = "TBD::qc33"
    if s is None:
        s = {}
    if not isinstance(s, dict):
        return oslg.mismatch("surfaces", s, dict, mth, DBG, False)
    if not isinstance(sets, PSI):
        return oslg.mismatch("sets", sets, dict, mth, DBG, False)

    shorts = sets.shorthands("code (Quebec)")
    if not shorts["has"] or not shorts["val"]:
        oslg.log(DBG, "Missing QC PSI set for 3.3 UA' tradeoff (%s)" % mth)
        return False

    if spts not in (True, False):
        oslg.log(DBG, "setpoints must be true or false for 3.3 UA' tradeoff")
        return False

    for id, surface in s.items():
        if "deratable" not in surface or not surface["deratable"]:
            continue
        if "type" not in surface:
            continue

        # Default setpoints assume -25C design conditions when the model has none.
        htng = -24 if spts else 21
        clng = 50 if spts else 24
        if "heating" in surface:
            htng = surface["heating"]
        if "cooling" in surface:
            clng = surface["cooling"]

        if htng < -24:  # avoid divide-by-zero in the adjustment below
            htng = -24

        # Reference U-factor, adjusted upward for low heating setpoints.
        ref = (1 / 3.60) if surface["type"] == "wall" else (1 / 5.46)
        if htng > -25 and htng < 18 and clng > 40:
            ref *= 43 / (htng + 25)
        surface["ref"] = ref

        if "skylights" in surface:
            ref = 2.85
            if htng > -25 and htng < 18 and clng > 40:
                ref *= 43 / (htng + 25)
            for skylight in surface["skylights"].values():
                skylight["ref"] = ref

        if "windows" in surface:
            ref = 2.0
            if htng > -25 and htng < 18 and clng > 40:
                ref *= 43 / (htng + 25)
            for window in surface["windows"].values():
                window["ref"] = ref

        if "doors" in surface:
            for door in surface["doors"].values():
                ref = 2.0 if door.get("glazed") else 0.9
                if htng > -25 and htng < 18 and clng > 40:
                    ref *= 43 / (htng + 25)
                door["ref"] = ref

        if "pts" in surface:
            for pt in surface["pts"].values():
                pt["ref"] = 0.5

        if "edges" in surface:
            for edge in surface["edges"].values():
                if "type" not in edge or "ratio" not in edge:
                    continue
                safe = sets.safe("code (Quebec)", edge["type"])
                if safe:
                    edge["ref"] = shorts["val"][safe] * edge["ratio"]

    return True


# Category keys of a UA' block, in the exact order used to seed the bins.
_BLC_KEYS = [
    "walls", "roofs", "floors", "doors", "windows", "skylights",
    "rimjoists", "parapets", "trim", "corners", "balconies", "grade", "other",
]

# EN/FR labels per block category (used when emitting the summary strings).
_CAT_LABELS = {
    "walls": ("walls", "murs"), "roofs": ("roofs", "toits"),
    "floors": ("floors", "planchers"), "doors": ("doors", "portes"),
    "windows": ("windows", "fenêtres"), "skylights": ("skylights", "lanterneaux"),
    "rimjoists": ("rimjoists", "rives"), "parapets": ("parapets", "parapets"),
    "trim": ("trim", "chassis"), "corners": ("corners", "coins"),
    "balconies": ("balconies", "balcons"), "grade": ("grade", "tracé"),
    "other": ("other", "autres"),
}


def _edge_category(edge_type):
    """Map an edge type string to its UA' bin (matches the Ruby include? chain)."""
    t = str(edge_type).lower()
    if "balcony" in t:
        return "balconies"
    for key in ("door", "skylight", "fenestration", "head", "sill", "jamb"):
        if key in t:
            return "trim"
    if "rimjoist" in t:
        return "rimjoists"
    if "parapet" in t or "roof" in t:
        return "parapets"
    if "corner" in t:
        return "corners"
    if "grade" in t:
        return "grade"
    return "other"


def ua_summary(date=None, argh=None):
    """Aggregate proposed-vs-reference UA' totals into bilingual summary data.

    Faithful port of TBD.ua_summary. Bins surfaces/subsurfaces/edges/points into
    two heating blocks (b1: HSTP >= 18C, b2: < 18C), builds EN/FR summary strings,
    and returns the `ua` dict consumed by ua_md. Empty on failure (logged).

    `date` should be a datetime (defaults to now); pass a fixed value for
    deterministic output.
    """
    mth = "TBD::ua_summary"
    ua = {}
    if date is None:
        date = datetime.datetime.now()
    if not isinstance(date, datetime.datetime):
        return oslg.mismatch("date", date, datetime.datetime, mth, DBG, ua)
    if argh is None:
        argh = {}
    if not isinstance(argh, dict):
        return oslg.mismatch("argh", argh, dict, mth, DBG, ua)

    argh.setdefault("seed", "")
    argh.setdefault("ua_ref", "")
    argh.setdefault("surfaces", None)
    argh.setdefault("version", "")
    argh.setdefault("io", {})

    file = argh["seed"]
    ref = argh["ua_ref"]
    s = argh["surfaces"]
    v = argh["version"]
    io = argh["io"]
    if not isinstance(file, str):
        return oslg.mismatch("seed", file, str, mth, DBG, ua)
    if not isinstance(ref, str):
        return oslg.mismatch("UA' ref", ref, str, mth, DBG, ua)
    if not isinstance(v, str):
        return oslg.mismatch("version", v, str, mth, DBG, ua)
    if not isinstance(s, dict):
        return oslg.mismatch("surfaces", s, dict, mth, DBG, ua)
    if not isinstance(io, dict):
        return oslg.mismatch("io", io, dict, mth, DBG, ua)
    if not s:
        return oslg.empty("surfaces", mth, WRN, ua)

    io.setdefault("description", "")
    descr = io["description"]

    ua["descr"] = ""
    ua["file"] = ""
    ua["version"] = ""
    ua["model"] = "∑U•A + ∑PSI•L + ∑KHI•n"
    ua["date"] = date
    if descr:
        ua["descr"] = descr
    if file:
        ua["file"] = file
    if v:
        ua["version"] = v

    for lang in ("en", "fr"):
        ua[lang] = {}

    ua["en"]["notes"] = (
        "Automated assessment from the OpenStudio Measure, "
        "Thermal Bridging and Derating (TBD). Open source and MIT-licensed, "
        "TBD is provided as is (without warranty). Procedures are documented "
        "in the source code: https://github.com/rd2/tbd. "
    )
    ua["fr"]["notes"] = (
        "Analyse automatisée à partir de la measure "
        "OpenStudio, 'Thermal Bridging and Derating' (ou TBD). Distribuée "
        "librement (licence MIT), TBD est offerte telle quelle (sans "
        "garantie). L'approche est documentée au sein du code source : "
        "https://github.com/rd2/tbd."
    )

    walls = {"net": 0, "gross": 0, "subs": 0}
    roofs = {"net": 0, "gross": 0, "subs": 0}
    floors = {"net": 0, "gross": 0, "subs": 0}
    areas = {"walls": walls, "roofs": roofs, "floors": floors}
    has = {}
    val = {}
    psi = PSI()

    if ref:
        shorts = psi.shorthands(ref)
        is_empty = not shorts["has"] and not shorts["val"]
        if not is_empty:
            has = shorts["has"]
            val = shorts["val"]
        if is_empty:
            oslg.log(WRN, "Invalid UA' reference set (%s)" % mth)

        if not is_empty:
            ua["model"] += " : Design vs '%s'" % ref
            if ref == "code (Quebec)":
                ua["en"]["objective"] = "COMPLIANCE ASSESSMENT"
                ua["en"]["details"] = [
                    "Quebec Construction Code, Chapter I.1",
                    "NECB 2015, modified version (2020)",
                    "Division B, Section 3.3",
                    "Building Envelope Trade-off Path",
                ]
                ua["en"]["notes"] += (
                    " Calculations comply with Section 3.3 requirements. Results "
                    "are based on user input not subject to prior validation (see "
                    "DESCRIPTION), and as such the assessment shall not be "
                    "considered as a certification of compliance."
                )
                ua["fr"]["objective"] = "ANALYSE DE CONFORMITÉ"
                ua["fr"]["details"] = [
                    "Code de construction du Québec, Chapitre I.1",
                    "CNÉB 2015, version modifiée (2020)",
                    "Division B, Section 3.3",
                    "Méthode des solutions de remplacement",
                ]
                ua["fr"]["notes"] += (
                    " Les calculs sont conformes aux dispositions de la Section "
                    "3.3. Les résultats sont tributaires d'intrants fournis "
                    "par l'utilisateur, sans validation préalable (voir "
                    "DESCRIPTION). Ce document ne peut constituer une attestation "
                    "de conformité."
                )
            else:
                ua["en"]["objective"] = "UA'"
                ua["fr"]["objective"] = "UA'"

    # Two heating-setpoint blocks: b1 (HSTP >= 18C), b2 (< 18C). Each holds a
    # "proposed" (pro) and "reference" (ref) bin, itself keyed by category.
    def _new_blc():
        return {k: 0 for k in _BLC_KEYS}

    b1 = {"pro": _new_blc(), "ref": _new_blc()}
    b2 = {"pro": _new_blc(), "ref": _new_blc()}

    for id, surface in s.items():
        if "deratable" not in surface or not surface["deratable"]:
            continue
        if "type" not in surface:
            continue
        type = surface["type"]
        if type not in ("wall", "ceiling", "floor"):
            continue
        if "net" not in surface or not surface["net"] > TOL:
            continue
        if "u" not in surface or not surface["u"] > TOL:
            continue

        heating = surface.get("heating", 21.0)
        bloc = b2 if heating < 18 else b1
        reference = "ref" in surface

        # Opaque surface U*A into the matching category (walls/roofs/floors).
        if type == "wall":
            cat, akey = "walls", "walls"
        elif type == "ceiling":
            cat, akey = "roofs", "roofs"
        else:
            cat, akey = "floors", "floors"
        areas[akey]["net"] += surface["net"]
        bloc["pro"][cat] += surface["net"] * surface["u"]
        bloc["ref"][cat] += surface["net"] * (surface["ref"] if reference else surface["u"])

        # Subsurface U*A.
        for subs in ("doors", "windows", "skylights"):
            if subs not in surface:
                continue
            for sub in surface[subs].values():
                if "gross" not in sub or "u" not in sub:
                    continue
                if not sub["gross"] > TOL or not sub["u"] > TOL:
                    continue
                gross = sub["gross"]
                if "mult" in sub:
                    gross *= sub["mult"]
                if type == "wall":
                    areas["walls"]["subs"] += gross
                if type == "ceiling":
                    areas["roofs"]["subs"] += gross
                if type == "floor":
                    areas["floors"]["subs"] += gross
                bloc["pro"][subs] += gross * sub["u"]
                bloc["ref"][subs] += gross * (sub["ref"] if "ref" in sub else sub["u"])

        # Linear thermal bridges (edges): PSI*L into a mapped category.
        if "edges" in surface:
            for edge in surface["edges"].values():
                if "type" not in edge or "length" not in edge:
                    continue
                if not edge["length"] > TOL or "psi" not in edge:
                    continue
                loss = edge["length"] * edge["psi"]
                bloc["pro"][_edge_category(edge["type"])] += loss

                if not val or not ref:
                    continue
                safer = psi.safe(ref, edge["type"])
                if "ref" in edge:
                    loss = edge["length"] * edge["ref"]
                else:
                    loss = edge["length"] * val[safer] * edge["ratio"]
                bloc["ref"][_edge_category(edge["type"])] += loss

        # Point thermal bridges (pts): KHI*n into "other".
        if "pts" in surface:
            for pts in surface["pts"].values():
                if "val" not in pts or "n" not in pts:
                    continue
                bloc["pro"]["other"] += pts["val"] * pts["n"]
                if "ref" in pts:
                    bloc["ref"]["other"] += pts["ref"] * pts["n"]

    # Build the bilingual per-block summary strings.
    for lang in ("en", "fr"):
        for b, bloc in (("b1", b1), ("b2", b2)):
            pro_sum = sum(bloc["pro"].values())
            ref_sum = sum(bloc["ref"].values())
            if not (pro_sum > TOL or ref_sum > TOL):
                continue

            ratio = None
            if ref_sum > TOL:
                ratio = abs(100.0 * (pro_sum - ref_sum) / ref_sum)
            block_str = "%.1f W/K (vs %.1f W/K)" % (pro_sum, ref_sum)
            if ratio is not None and pro_sum > ref_sum:
                block_str += " +%.1f%%" % ratio
            if ratio is not None and pro_sum < ref_sum:
                block_str += " -%.1f%%" % ratio

            entry = {}  # built categories-first, summary appended last
            for k in _BLC_KEYS:
                vv = bloc["pro"][k]
                rf = bloc["ref"][k]
                if vv < TOL and rf < TOL:
                    continue
                r2 = None
                if rf > TOL:
                    r2 = abs(100.0 * (vv - rf) / rf)
                cat_str = "%.1f W/K (vs %.1f W/K)" % (vv, rf)
                if r2 is not None and vv > rf:
                    cat_str += " +%.1f%%" % r2
                if r2 is not None and vv < rf:
                    cat_str += " -%.1f%%" % r2
                label = _CAT_LABELS[k][0 if lang == "en" else 1]
                entry[k] = "%s : %s" % (label, cat_str)

            # Summary is inserted last (matches upstream's deterministic reorder).
            if b == "b1":
                entry["summary"] = ("heated : %s" if lang == "en" else "chauffé : %s") % block_str
            else:
                entry["summary"] = ("semi-heated : %s" if lang == "en" else "semi-chauffé : %s") % block_str
            ua[lang][b] = entry

    # Gross areas and the bilingual AREAS strings.
    areas["walls"]["gross"] = areas["walls"]["net"] + areas["walls"]["subs"]
    areas["roofs"]["gross"] = areas["roofs"]["net"] + areas["roofs"]["subs"]
    areas["floors"]["gross"] = areas["floors"]["net"] + areas["floors"]["subs"]

    ua["en"]["areas"] = {}
    ua["fr"]["areas"] = {}

    def _area_line(word, unit, a):
        return "%s : %.1f m2 (net), %.1f m2 (%s)" % (word, a["net"], a["gross"], unit)

    if not areas["walls"]["gross"] < TOL:
        ua["en"]["areas"]["walls"] = _area_line("walls", "gross", areas["walls"])
        ua["fr"]["areas"]["walls"] = _area_line("murs", "brut", areas["walls"])
    if not areas["roofs"]["gross"] < TOL:
        ua["en"]["areas"]["roofs"] = _area_line("roofs", "gross", areas["roofs"])
        ua["fr"]["areas"]["roofs"] = _area_line("toits", "brut", areas["roofs"])
    if not areas["floors"]["gross"] < TOL:
        ua["en"]["areas"]["floors"] = _area_line("floors", "gross", areas["floors"])
        ua["fr"]["areas"]["floors"] = _area_line("planchers", "brut", areas["floors"])

    return ua


def ua_md(ua=None, lang="en"):
    """Render the `ua` dict (from ua_summary) into Markdown lines for one language.

    Faithful port of TBD.ua_md. Returns a list of Markdown strings (empty on
    failure, logged). `lang` is "en" or "fr". Note: upstream hard-codes the TBD
    version string here (see UPSTREAM.md).
    """
    mth = "TBD::ua_md"
    report = []
    if ua is None:
        ua = {}
    if not hasattr(ua, "keys"):
        return oslg.mismatch("ua", ua, dict, mth, DBG, report)
    if not isinstance(lang, str):
        return oslg.mismatch("lang", lang, str, mth, DBG, report)

    if lang not in ua:
        return oslg.hashkey("language", ua, lang, mth, DBG, report)
    if not ua:
        return oslg.empty("ua", mth, DBG, report)

    if "objective" in ua[lang]:
        report.append("# %s   " % ua[lang]["objective"])
        report.append("   ")

    if "details" in ua[lang]:
        for d in ua[lang]["details"]:
            report.append("%s   " % d)
        report.append("   ")

    if "model" in ua:
        report.append("##### SUMMARY   " if lang == "en" else "##### SOMMAIRE   ")
        report.append("   ")
        report.append("%s   " % ua["model"])
        report.append("   ")

    for b in ("b1", "b2"):
        if b in ua[lang] and "summary" in ua[lang][b]:
            report.append("* %s" % ua[lang][b]["summary"])
            keys = list(ua[lang][b].keys())
            last = keys[-1]
            for k, vv in ua[lang][b].items():
                if k == "summary":
                    continue
                if k != last:
                    report.append("  * %s" % vv)
                if k == last:
                    report.append("  * %s   " % vv)
                    report.append("   ")
            report.append("   ")

    if "date" in ua:
        report.append("##### DESCRIPTION   ")
        report.append("   ")
        if "descr" in ua:
            report.append(("* project : %s" if lang == "en" else "* projet : %s") % ua["descr"])
        model = ""
        if "file" in ua:
            model = ("* model : %s" if lang == "en" else "* modèle : %s") % ua["file"]
        if "version" in ua:
            model += " (v%s)" % ua["version"]
        if model:
            report.append(model)
        report.append("* TBD : v3.6.0")
        report.append("* date : %s" % ua["date"])

        status = oslg.status()
        if lang == "en":
            report.append("* status : %s" % oslg.msg(status) if status != 0 else "* status : success !")
        elif lang == "fr":
            report.append("* statut : %s" % oslg.msg(status) if status != 0 else "* statut : succès !")
        report.append("   ")

    if "areas" in ua[lang]:
        report.append("##### AREAS   " if lang == "en" else "##### AIRES   ")
        report.append("   ")
        if "walls" in ua[lang]["areas"]:
            report.append("* %s" % ua[lang]["areas"]["walls"])
        if "roofs" in ua[lang]["areas"]:
            report.append("* %s" % ua[lang]["areas"]["roofs"])
        if "floors" in ua[lang]["areas"]:
            report.append("* %s" % ua[lang]["areas"]["floors"])
        report.append("   ")

    if "notes" in ua[lang]:
        report.append("##### NOTES   ")
        report.append("   ")
        report.append("%s   " % ua[lang]["notes"])
        report.append("   ")

    return report


# --- lazy OpenStudio class handles (import openstudio only when needed) ------

def _model_class():
    import openstudio
    return openstudio.model.Model


def _lc_class():
    import openstudio
    return openstudio.model.LayeredConstruction
