# Native Python port of lib/tbd/geo.rb from the TBD Ruby gem: geometry/topology
# bridge between OpenStudio surfaces and the Topolys 3D model.
#
# Naming note — two different vector types are used side by side:
#   * OpenStudio Point3d/Vector3d  -> accessors are METHODS: p.x(), p.y(), p.z()
#   * py_topolys Point3D/Vector3D  -> accessors are ATTRIBUTES: p.x, p.y, p.z
#
# geo.rb defines its OWN matches?/concave?/convex?/truNormal that shadow osut's
# same-named helpers, so those are ported locally here (not delegated to osut).

import math

import openstudio
import py_topolys

from ._helpers import oslg, DBG, INF, WRN, ERR, TOL


def matches(e1=None, e2=None, tol=TOL):
    """Whether two edges share the same Topolys vertex pair (either orientation).

    e1/e2 are dicts with "v0"/"v1" py_topolys.Point3D. Ruby: TBD.matches?.
    Returns False on invalid input (logged).
    """
    mth = "TBD::matches"
    cl = py_topolys.Point3D
    a = False
    if e1 is None:
        e1 = {}
    if e2 is None:
        e2 = {}
    if not isinstance(e1, dict):
        return oslg.mismatch("e1", e1, dict, mth, DBG, a)
    if not isinstance(e2, dict):
        return oslg.mismatch("e2", e2, dict, mth, DBG, a)

    if "v0" not in e1:
        return oslg.hashkey("e1", e1, "v0", mth, DBG, a)
    if "v1" not in e1:
        return oslg.hashkey("e1", e1, "v1", mth, DBG, a)
    if "v0" not in e2:
        return oslg.hashkey("e2", e2, "v0", mth, DBG, a)
    if "v1" not in e2:
        return oslg.hashkey("e2", e2, "v1", mth, DBG, a)

    if not isinstance(e1["v0"], cl):
        return oslg.mismatch("e1:v0", e1["v0"], cl, mth, DBG, a)
    if not isinstance(e1["v1"], cl):
        return oslg.mismatch("e1:v1", e1["v1"], cl, mth, DBG, a)
    if not isinstance(e2["v0"], cl):
        return oslg.mismatch("e2:v0", e2["v0"], cl, mth, DBG, a)
    if not isinstance(e2["v1"], cl):
        return oslg.mismatch("e2:v1", e2["v1"], cl, mth, DBG, a)

    e1_vector = e1["v1"] - e1["v0"]
    e2_vector = e2["v1"] - e2["v0"]

    if e1_vector.magnitude < TOL:
        return oslg.zero("e1", mth, DBG, a)
    if e2_vector.magnitude < TOL:
        return oslg.zero("e2", mth, DBG, a)

    if not isinstance(tol, (int, float)):
        return oslg.mismatch("e1", e1, dict, mth, DBG, a)
    if tol < TOL:
        return oslg.zero("tol", mth, DBG, a)

    v1_0, v1_1 = e1["v0"], e1["v1"]
    v2_0, v2_1 = e2["v0"], e2["v1"]
    if (
        (
            (abs(v1_0.x - v2_0.x) < tol and abs(v1_0.y - v2_0.y) < tol and abs(v1_0.z - v2_0.z) < tol)
            or (abs(v1_0.x - v2_1.x) < tol and abs(v1_0.y - v2_1.y) < tol and abs(v1_0.z - v2_1.z) < tol)
        )
        and (
            (abs(v1_1.x - v2_0.x) < tol and abs(v1_1.y - v2_0.y) < tol and abs(v1_1.z - v2_0.z) < tol)
            or (abs(v1_1.x - v2_1.x) < tol and abs(v1_1.y - v2_1.y) < tol and abs(v1_1.z - v2_1.z) < tol)
        )
    ):
        return True

    return False


def objects(model=None, pts=None):
    """Return {"vx": [Vertex], "w": Wire} for a set of Topolys points.

    Populates `model` with the vertices/wire if missing. Ruby: TBD.objects.
    Returns {"vx": None, "w": None} on invalid input (logged).
    """
    mth = "TBD::objects"
    cl1 = py_topolys.Model
    cl3 = py_topolys.Point3D
    obj = {"vx": None, "w": None}
    if pts is None:
        pts = []
    if not isinstance(model, cl1):
        return oslg.mismatch("model", model, cl1, mth, DBG, obj)
    if not isinstance(pts, list):
        return oslg.mismatch("points", pts, list, mth, DBG, obj)

    for pt in pts:
        if not isinstance(pt, cl3):
            return oslg.mismatch("point", pt, cl3, mth, DBG, obj)

    obj["vx"] = model.get_vertices(pts)
    obj["w"] = model.get_wire(obj["vx"])
    return obj


def faces(s=None, e=None):
    """Populate edges dict `e` with the Topolys faces/wires referencing each edge.

    `s` maps surface id -> props with a "face" (py_topolys.Face). Mutates `e`.
    Ruby: TBD.faces. Returns False on invalid input (logged).
    """
    mth = "TBD::faces"
    if s is None:
        s = {}
    if e is None:
        e = {}
    if not isinstance(s, dict):
        return oslg.mismatch("surfaces", s, dict, mth, DBG, False)
    if not isinstance(e, dict):
        return oslg.mismatch("edges", e, dict, mth, DBG, False)

    for id, props in s.items():
        if "face" not in props:
            oslg.log(DBG, "Missing Topolys face '%s' (%s)" % (id, mth))
            continue

        # In py_topolys, Face.wires and Wire.edges are list attributes (not
        # methods); edge.id/length and edge.v0/v1 (Vertices) are attributes too.
        for wire in props["face"].wires:
            for edge in wire.edges:
                if edge.id not in e:
                    e[edge.id] = {
                        "length": edge.length,
                        "v0": edge.v0,
                        "v1": edge.v1,
                        "surfaces": {},
                    }
                # Record which surface (and which of its wires) touches this edge.
                if id not in e[edge.id]["surfaces"]:
                    e[edge.id]["surfaces"][id] = {"wire": wire.id}

    return True


def tru_normal(s=None, r=0):
    """Return the site/true Topolys normal of an OpenStudio planar surface.

    `r` is a group/site rotation angle in degrees. Ruby: TBD.truNormal.
    Returns None on invalid input (logged).
    """
    mth = "TBD::tru_normal"
    cl = openstudio.model.PlanarSurface
    if not isinstance(s, cl):
        return oslg.mismatch("surface", s, cl, mth)
    if not _to_f_ok(r):
        return oslg.invalid("rotation angle", mth, 2)

    r = -float(r) * math.pi / 180.0
    n = s.outwardNormal()
    vx = n.x() * math.cos(r) - n.y() * math.sin(r)
    vy = n.x() * math.sin(r) + n.y() * math.cos(r)
    vz = n.z()
    return py_topolys.Vector3D(vx, vy, vz)


def is_concave(s1=None, s2=None):
    """Whether two edge surfaces form a concave angle, seen from outside.

    s1/s2 dicts with "angle" (num), "normal"/"polar" (py_topolys.Vector3D).
    Ruby: TBD.concave?. Returns False on invalid input (logged).
    """
    return _concave_convex(s1, s2, "TBD::is_concave", concave=True)


def is_convex(s1=None, s2=None):
    """Whether two edge surfaces form a convex angle, seen from outside.

    Ruby: TBD.convex?. Returns False on invalid input (logged).
    """
    return _concave_convex(s1, s2, "TBD::is_convex", concave=False)


def _concave_convex(s1, s2, mth, concave):
    """Shared body of concave?/convex? — identical but for the final sign test."""
    a = False
    if not isinstance(s1, dict):
        return oslg.mismatch("s1", s1, dict, mth, DBG, a)
    if not isinstance(s2, dict):
        return oslg.mismatch("s2", s2, dict, mth, DBG, a)
    if s1 == s2:
        return False

    for tag, s in (("s1", s1), ("s2", s2)):
        if "angle" not in s:
            return oslg.hashkey(tag, s, "angle", mth, DBG, a)
    for tag, s in (("s1", s1), ("s2", s2)):
        if "normal" not in s:
            return oslg.hashkey(tag, s, "normal", mth, DBG, a)
    for tag, s in (("s1", s1), ("s2", s2)):
        if "polar" not in s:
            return oslg.hashkey(tag, s, "polar", mth, DBG, a)

    valid1 = isinstance(s1["angle"], (int, float)) and not isinstance(s1["angle"], bool)
    valid2 = isinstance(s2["angle"], (int, float)) and not isinstance(s2["angle"], bool)
    if not valid1:
        return oslg.mismatch("s1 angle", s1["angle"], float, DBG, a)
    if not valid2:
        return oslg.mismatch("s1 angle", s2["angle"], float, DBG, a)

    angle = 0
    if s2["angle"] > s1["angle"]:
        angle = s2["angle"] - s1["angle"]
    if s1["angle"] > s2["angle"]:
        angle = s1["angle"] - s2["angle"]
    if angle < TOL:
        return False
    if not abs(2 * math.pi - angle) > TOL:
        return False
    if angle > 3 * math.pi / 4 and angle < 5 * math.pi / 4:
        return False

    n1_d_p2 = s1["normal"].dot(s2["polar"])
    p1_d_n2 = s1["polar"].dot(s2["normal"])
    if concave:
        if n1_d_p2 > 0 and p1_d_n2 > 0:
            return True
    else:
        if n1_d_p2 < 0 and p1_d_n2 < 0:
            return True

    return False


def reset_kiva(model=None, boundary="Foundation"):
    """Purge KIVA-related objects; reset ground-facing surfaces' boundary.

    Ruby: TBD.resetKIVA. Returns True on success, False on invalid input (logged).
    """
    mth = "TBD::reset_kiva"
    cl = openstudio.model.Model
    ck1 = isinstance(model, cl)
    ck2 = hasattr(boundary, "__str__")
    kva = False
    b = ["Ground", "Foundation"]
    if not ck1:
        return oslg.mismatch("model", model, cl, mth, DBG, kva)
    if not ck2:
        return oslg.mismatch("boundary", boundary, str, mth, DBG, kva)

    boundary = boundary.capitalize()
    if boundary not in b:
        return oslg.invalid("boundary", mth, 2, DBG, kva)

    for surface in model.getSurfaces():
        if not surface.adjacentFoundation().empty():
            kva = True
        if not surface.surfacePropertyExposedFoundationPerimeter().empty():
            kva = True
        surface.resetAdjacentFoundation()
        surface.resetSurfacePropertyExposedFoundationPerimeter()
        if surface.outsideBoundaryCondition().capitalize() == boundary:
            continue
        if surface.outsideBoundaryCondition().capitalize() != "Foundation":
            continue
        surface.setOutsideBoundaryCondition(boundary)

    perimeters = model.getSurfacePropertyExposedFoundationPerimeters()
    if len(perimeters) > 0:
        kva = True

    for perimeter in perimeters:
        perimeter.remove()

    for kiva_obj in model.getFoundationKivas():
        kiva_obj.removeAllCustomBlocks()
        kiva_obj.remove()

    if kva:
        oslg.log(INF, "Purged KIVA objects from model (%s)" % mth)

    return True


# ---------------------------------------------------------------------------
# Heavy methods ported later in Phase 2 (need the full surface pipeline).
# ---------------------------------------------------------------------------
def kids(model=None, boys=None):
    """Add TBD subsurfaces ('kids') to a Topolys model as vertices/wires/holes.

    Faithful port of TBD.kids. `boys` maps subsurface id -> props with keys
    "points" (list of py_topolys.Point3D) and optionally "unhinged"/"n". Each
    subsurface becomes a Topolys wire (a "hole" cut into its base surface). The
    wire is stashed back into props["hole"], and every wire is returned as a list.

    Returns the list of hole wires (empty on invalid input, logged).
    """
    mth = "TBD::kids"
    cl1 = py_topolys.Model
    holes = []
    if boys is None:
        boys = {}
    if not isinstance(model, cl1):
        return oslg.mismatch("model", model, cl1, mth, DBG, {})
    if not isinstance(boys, dict):
        return oslg.mismatch("boys", boys, dict, mth, DBG, {})

    for id, props in boys.items():
        # Build (or fetch) the wire for this subsurface's 3D points.
        obj = objects(model, props["points"])
        if not obj["w"]:
            continue

        # Tag the wire so downstream edge classification can identify it. The
        # attributes dict mirrors Ruby's Topolys wire.attributes hash.
        obj["w"].attributes["id"] = id
        if "unhinged" in props:
            obj["w"].attributes["unhinged"] = props["unhinged"]
        if "n" in props:
            obj["w"].attributes["n"] = props["n"]

        props["hole"] = obj["w"]
        holes.append(obj["w"])

    return holes


def dads(model=None, pops=None):
    """Add TBD base surfaces ('dads') to a Topolys model, plus their subsurfaces.

    Faithful port of TBD.dads. `pops` maps surface id -> props with "points" and
    optionally "windows"/"doors"/"skylights" (each a `boys` dict for kids) and
    "n". Builds a Topolys face per base surface, cutting the hinged subsurface
    holes into it; the face is stashed into props["face"].

    Returns a dict of every hole wire keyed by its subsurface id (empty on
    invalid input, logged).
    """
    mth = "TBD::dads"
    cl1 = py_topolys.Model
    holes = {}
    if pops is None:
        pops = {}
    if not isinstance(model, cl1):
        return oslg.mismatch("model", model, dict, mth, DBG, {})
    if not isinstance(pops, dict):
        return oslg.mismatch("pops", pops, dict, mth, DBG, {})

    for id, props in pops.items():
        hols = []       # all holes (hinged + unhinged) for this base surface
        hinged = []     # only the hinged holes, which get cut into the face
        obj = objects(model, props["points"])
        if not (obj["vx"] and obj["w"]):
            continue

        # Collect holes from each subsurface family (kids tags & returns them).
        if "windows" in props:
            hols += kids(model, props["windows"])
        if "doors" in props:
            hols += kids(model, props["doors"])
        if "skylights" in props:
            hols += kids(model, props["skylights"])

        # Only hinged (coplanar) holes are punched into the base surface face; an
        # 'unhinged' subsurface (e.g. a TDD dome on a different plane) is not.
        for hol in hols:
            if not hol.attributes.get("unhinged"):
                hinged.append(hol)

        face = model.get_face(obj["w"], hinged)
        if not face:
            oslg.log(DBG, "Unable to retrieve valid 'dad' (%s)" % mth)
            continue

        face.attributes["id"] = id
        if "n" in props:
            face.attributes["n"] = props["n"]

        props["face"] = face

        # Index every hole by its subsurface id for the caller.
        for hol in hols:
            holes[hol.attributes["id"]] = hol

    return holes


def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def properties(surface=None, argh=None):
    """Fetch OpenStudio surface properties (openings, vertices, RSi, setpoints...).

    Faithful port of TBD.properties. Returns a rich TBD surface descriptor dict,
    or None on invalid input (logged). `argh` may carry "setpoints" (bool);
    NOTE: if absent, upstream references an undefined `model` (see PARITY below),
    so normal callers (process) must pre-set argh["setpoints"].
    """
    from ._helpers import osut  # local import: heavy dep, keeps import graph light
    mth = "TBD::properties"
    cl1 = openstudio.model.Surface
    cl3 = dict
    if argh is None:
        argh = {}
    if not isinstance(surface, cl1):
        return oslg.mismatch("surface", surface, cl1, mth)
    if not isinstance(argh, cl3):
        return oslg.mismatch("argh", argh, cl3, mth)

    nom = surface.nameString()
    surf = {}
    subs = {}
    fd = False
    if len(osut.poly(surface)) == 0:
        return oslg.invalid("%s" % nom, mth, 1, ERR)
    if surface.space().empty():
        return oslg.empty("%s space" % nom, mth, ERR)

    space = surface.space().get()
    stype = space.spaceType()
    story = space.buildingStory()
    tr = osut.transforms(space)
    if tr["t"] is None or tr["r"] is None:
        return oslg.invalid("%s transform" % nom, mth, 0, ERR)

    t = tr["t"]
    n = tru_normal(surface, tr["r"])
    if not n:
        return oslg.invalid("%s normal" % nom, mth, 0, ERR)

    type = surface.surfaceType().lower()
    facing = surface.outsideBoundaryCondition().lower()
    interz = False
    setpts = osut.setpoints(space)

    if facing == "surface":
        adj = surface.adjacentSurface()
        if adj.empty():
            return oslg.invalid("%s: adjacent surface" % nom, mth, 0, ERR)
        facing = adj.get().nameString()
        interz = True

    if not surface.construction().empty():
        lc = surface.construction().get().to_LayeredConstruction()
        if not lc.empty():
            lc = lc.get()
            lyr = osut.insulatingLayer(lc)
            idx = lyr["index"]
            if isinstance(idx, int) and 0 <= idx <= lc.numLayers() - 1:
                surf["construction"] = lc
                surf["index"] = lyr["index"]
                surf["ltype"] = lyr["type"]
                surf["r"] = lyr["r"]
            else:
                surf["index"] = None
                surf["ltype"] = None
                surf["r"] = 0.0

    if "setpoints" not in argh:
        # PARITY: upstream bug geo.rb:339 references an undefined local `model`
        # (should be `surface.model`). Ruby raises NameError; callers such as
        # process() always pre-set argh["setpoints"] so the branch never runs.
        heat = osut.hasHeatingTemperatureSetpoints(model)  # noqa: F821
        cool = osut.hasCoolingTemperatureSetpoints(model)  # noqa: F821
        argh["setpoints"] = heat or cool

    if argh["setpoints"]:
        if setpts["heating"] is not None:
            surf["heating"] = setpts["heating"]
        if setpts["cooling"] is not None:
            surf["cooling"] = setpts["cooling"]
    else:
        surf["heating"] = 21.0
        surf["cooling"] = 24.0

    surf["conditioned"] = ("heating" in surf) or ("cooling" in surf)
    surf["space"] = space
    surf["occupied"] = space.partofTotalFloorArea()
    surf["boundary"] = facing
    surf["ground"] = surface.isGroundSurface()
    surf["type"] = "floor"
    if "ceiling" in type:
        surf["type"] = "ceiling"
    if "wall" in type:
        surf["type"] = "wall"
    if not stype.empty():
        surf["stype"] = stype.get()
    if not story.empty():
        surf["story"] = story.get()
    surf["n"] = n
    surf["gross"] = surface.grossArea()
    surf["spandrel"] = osut.areSpandrels(surface)
    surf["filmRSI"] = surface.filmResistance()

    if interz:
        typ = "ceiling"  # interzone roof or ceiling
        if surf["type"] == "wall":
            typ = "partition"
        surf["filmRSI"] = osut.filmResistances(typ, surface.tilt())

    for s in sorted(surface.subSurfaces(), key=lambda x: x.nameString()):
        if len(osut.poly(s)) == 0:
            continue

        id = s.nameString()
        typ = surface.surfaceType().lower()

        if not (3 <= len(s.vertices()) <= 4):
            oslg.log(ERR, "Skipping '%s': vertex # 3 or 4 (%s)" % (id, mth))
            continue

        vec = s.vertices()
        area = s.grossArea()
        mult = s.multiplier()

        typ = s.subSurfaceType().lower()

        type = "skylight"
        if "window" in typ:
            type = "window"
        if "door" in typ:
            type = "door"

        glazed = type == "door" and "glass" in typ
        tubular = "tubular" in typ
        domed = "dome" in typ
        unhinged = False

        if domed:
            if not s.plane().equal(surface.plane()):
                unhinged = True
            if unhinged:
                n = s.outwardNormal()

        if area < TOL:
            oslg.log(ERR, "Skipping '%s': gross area ~zero (%s)" % (id, mth))
            continue

        c = s.construction()
        if c.empty():
            oslg.log(ERR, "Skipping '%s': missing construction (%s)" % (id, mth))
            continue

        c = c.get().to_LayeredConstruction()
        if c.empty():
            oslg.log(WRN, "Skipping '%s': subs limited to LayeredConstruction (%s)" % (id, mth))
            continue

        c = c.get()

        u = s.uFactor()
        if not u.empty():
            u = u.get()

        if tubular and hasattr(s, "daylightingDeviceTubular"):  # OSM > v3.3.0
            if not s.daylightingDeviceTubular().empty():
                r = s.daylightingDeviceTubular().get().effectiveThermalResistance()
                if r > TOL:
                    u = 1 / r

        if not _is_num(u):
            u = s.additionalProperties().getFeatureAsDouble("uFactor")

        if not _is_num(u):
            r = osut.rsi(c, surf["filmRSI"])
            if r < TOL:
                oslg.log(ERR, "Skipping '%s': U-factor unavailable (%s)" % (id, mth))
                continue
            u = 1 / r

        frame = s.allowWindowPropertyFrameAndDivider()
        if s.windowPropertyFrameAndDivider().empty():
            frame = False

        if frame:
            fd = True
            width = s.windowPropertyFrameAndDivider().get().frameWidth()
            vec = osut.offset(vec, width, 300)
            area = openstudio.getArea(vec)
            if area.empty():
                oslg.log(ERR, "Skipping '%s': invalid offset (%s)" % (id, mth))
                continue
            area = area.get()

        sub = {
            "v": s.vertices(),
            "points": vec,
            "n": n,
            "gross": s.grossArea(),
            "area": area,
            "mult": mult,
            "type": type,
            "u": u,
            "unhinged": unhinged,
        }
        if glazed:
            sub["glazed"] = True
        subs[id] = sub

    valid = True
    # Test for fits?/overlaps? conflicts between sub/surfaces to decide whether to
    # keep original points or switch to Frame & Divider offset coordinates.
    for id, sub in subs.items():
        if not fd:
            break
        if not valid:
            break

        valid = osut.fits(sub["points"], surface.vertices())
        if not valid:
            oslg.log(ERR, "Skipping '%s': can't fit in '%s' (%s)" % (id, nom, mth))

        for i, sb in subs.items():
            if not valid:
                break
            if i == id:
                continue
            if osut.overlapping(sb["points"], sub["points"]):
                oslg.log(ERR, "Skipping '%s': overlaps sibling '%s' (%s)" % (id, i, mth))
                valid = False

    if fd:
        if valid:
            for sub in subs.values():
                sub["gross"] = sub["area"]
        else:
            for sub in subs.values():
                sub["points"] = sub["v"]
            for sub in subs.values():
                sub["area"] = sub["gross"]

    subarea = 0
    for sub in subs.values():
        subarea += sub["area"] * sub["mult"]

    surf["net"] = surf["gross"] - subarea

    # Transform final Point3D sets, and store.
    pts = [py_topolys.Point3D(v.x(), v.y(), v.z()) for v in (t * surface.vertices())]
    surf["points"] = pts
    surf["minz"] = min(pt.z for pt in pts)

    for id, sub in subs.items():
        pts = [py_topolys.Point3D(v.x(), v.y(), v.z()) for v in (t * sub["points"])]
        sub["points"] = pts
        sub["minz"] = min(p.z for p in pts)

        for types in ("windows", "doors", "skylights"):
            type = types[:-1]  # "windows" -> "window"
            if sub["type"] != type:
                continue
            if types not in surf:
                surf[types] = {}
            surf[types][id] = sub

    return surf


def kiva(model=None, walls=None, floors=None, edges=None):
    """Generate KIVA foundation settings/objects for 'foundation'-facing surfaces.

    Faithful port of TBD.kiva. Tags each foundation floor as "slab" or "basement",
    accumulates its exposed perimeter from adjoining outdoor/foundation wall edges,
    then creates OpenStudio FoundationKiva objects and wires walls to them.

    NOTE the parameter order is (model, walls, floors, edges) — the upstream YARD
    comment lists (model, floors, walls, edges), which is wrong (tracked in
    UPSTREAM.md). Returns True on success, False on invalid input / failure.
    """
    from ._helpers import osut  # heavy dep; imported lazily like in properties
    mth = "TBD::kiva"
    cl1 = openstudio.model.Model
    a = False
    if walls is None:
        walls = {}
    if floors is None:
        floors = {}
    if edges is None:
        edges = {}
    if not isinstance(model, cl1):
        return oslg.mismatch("model", model, cl1, mth, DBG, a)
    if not isinstance(walls, dict):
        return oslg.mismatch("walls", walls, dict, mth, DBG, a)
    if not isinstance(floors, dict):
        return oslg.mismatch("floors", floors, dict, mth, DBG, a)
    if not isinstance(edges, dict):
        return oslg.mismatch("edges", edges, dict, mth, DBG, a)

    # Refuse to run if the model already holds KIVA objects (avoid duplicates).
    kva = False
    if len(model.getSurfacePropertyExposedFoundationPerimeters()) > 0:
        kva = True
    if len(model.getFoundationKivas()) > 0:
        kva = True

    if kva:
        oslg.log(ERR, "Exiting - KIVA objects in model (%s)" % mth)
        return a
    else:
        kva = True

    # Pre-validate that every foundation-facing surface has a usable, standard
    # (non-massless) layered construction; KIVA cannot use massless materials.
    for s in model.getSurfaces():
        id = s.nameString()
        construction = s.construction()
        if s.outsideBoundaryCondition().lower() != "foundation":
            continue

        if construction.empty():
            oslg.log(ERR, "Invalid construction for %s (%s)" % (id, mth))
            kva = False
        else:
            construction = construction.get().to_LayeredConstruction()
            if construction.empty():
                oslg.log(ERR, "Invalid layered constructions for %s (%s)" % (id, mth))
                kva = False
            else:
                construction = construction.get()
                if not osut.areStandardOpaqueLayers(construction):
                    oslg.log(ERR, "Non-standard materials for %s (%s)" % (id, mth))
                    kva = False

    if not kva:
        return a

    # KIVA uses a "total exposed perimeter" foundation model.
    arg = "TotalExposedPerimeter"
    result = True

    # Touch the KIVA settings (optional in the model, but exposing them lets a
    # user tweak e.g. soil conductivity later). Re-setting the value is a no-op
    # that simply materializes the settings object.
    settings = model.getFoundationKivaSettings()
    k = settings.soilConductivity()
    settings.setSoilConductivity(k)

    # Tag foundation-facing floors, then their walls.
    for code1, edge in edges.items():
        for id in list(edge["surfaces"].keys()):
            if id not in floors:
                continue
            if floors[id]["boundary"] != "foundation":
                continue
            if "kiva" in floors[id]:
                continue

            # Start as slab-on-grade; accumulate the exposed foundation perimeter
            # from: outdoor wall/slab edges, walkout edges, basement wall/slab edges.
            floors[id]["kiva"] = "slab"
            floors[id]["exposed"] = 0.0

            # Walls sharing THIS edge that are themselves foundation-facing make
            # the floor a basement, and get wired to it.
            for i in list(edge["surfaces"].keys()):
                if i == id:
                    continue
                if i not in walls:
                    continue
                if walls[i]["boundary"] != "foundation":
                    continue
                if "kiva" in walls[i]:
                    continue
                floors[id]["kiva"] = "basement"
                floors[id]["exposed"] += edge["length"]
                walls[i]["kiva"] = id

            # Outdoor walls sharing this edge contribute exposed perimeter too.
            for i in list(edge["surfaces"].keys()):
                if i == id:
                    continue
                if i not in walls:
                    continue
                if walls[i]["boundary"] != "outdoors":
                    continue
                floors[id]["exposed"] += edge["length"]

            # Repeat over the floor's OTHER edges (this floor may border several).
            for code2, e in edges.items():
                if code1 == code2:  # skip the same edge
                    continue
                for i in list(e["surfaces"].keys()):
                    if i != id:  # only edges that also touch this floor
                        continue
                    for ii in list(e["surfaces"].keys()):
                        if i == ii:
                            continue
                        if ii not in walls:
                            continue
                        if walls[ii]["boundary"] != "foundation":
                            continue
                        if "kiva" in walls[ii]:
                            continue
                        floors[id]["kiva"] = "basement"
                        walls[ii]["kiva"] = id
                        floors[id]["exposed"] += e["length"]

                    for ii in list(e["surfaces"].keys()):
                        if i == ii:
                            continue
                        if ii not in walls:
                            continue
                        if walls[ii]["boundary"] != "outdoors":
                            continue
                        floors[id]["exposed"] += e["length"]

            # Create the OpenStudio FoundationKiva object for this floor.
            foundation = openstudio.model.FoundationKiva(model)
            foundation.setName("KIVA Foundation Floor %s" % id)

            floor = model.getSurfaceByName(id)
            if floor.empty():
                result = False
                continue
            floor = floor.get()

            construction = floor.construction()
            if construction.empty():
                result = False
                continue
            construction = construction.get()

            floor.setAdjacentFoundation(foundation)
            floor.setConstruction(construction)
            ep = floors[id]["exposed"]
            per = floor.createSurfacePropertyExposedFoundationPerimeter(arg, ep)
            if per.empty():
                result = False
                continue
            per = per.get()

            perimeter = per.totalExposedPerimeter()
            if perimeter.empty():
                result = False
                continue
            perimeter = perimeter.get()

            if ep < 0.001:
                # A ~zero exposed perimeter isn't accepted as-is; nudge to a tiny
                # positive value so EnergyPlus/KIVA accepts the object.
                ok = per.setTotalExposedPerimeter(0.000)
                if not ok:
                    ok = per.setTotalExposedPerimeter(0.001)
                if not ok:
                    result = False
            elif abs(perimeter - ep) < TOL:
                # Add a default 0.6 m interior horizontal insulation strip
                # (reusing or creating a shared "XPS 25mm" material).
                xps25 = model.getStandardOpaqueMaterialByName("XPS 25mm")
                if xps25.empty():
                    xps25 = openstudio.model.StandardOpaqueMaterial(model)
                    xps25.setName("XPS 25mm")
                    xps25.setRoughness("Rough")
                    xps25.setThickness(0.0254)
                    xps25.setConductivity(0.029)
                    xps25.setDensity(28)
                    xps25.setSpecificHeat(1450)
                    xps25.setThermalAbsorptance(0.9)
                    xps25.setSolarAbsorptance(0.7)
                else:
                    xps25 = xps25.get()

                foundation.setInteriorHorizontalInsulationMaterial(xps25)
                foundation.setInteriorHorizontalInsulationWidth(0.6)

            floors[id]["foundation"] = foundation

    # Wire each tagged wall to its floor's foundation.
    for i, wall in walls.items():
        if "kiva" not in wall:
            continue
        id = walls[i]["kiva"]
        if id not in floors:
            continue
        if "foundation" not in floors[id]:
            continue

        mur = model.getSurfaceByName(i)  # locate the OpenStudio wall
        if mur.empty():
            result = False
            continue
        mur = mur.get()

        construction = mur.construction()
        if construction.empty():
            result = False
            continue
        construction = construction.get()

        mur.setAdjacentFoundation(floors[id]["foundation"])
        mur.setConstruction(construction)

    return result


def _to_f_ok(x):
    """True if x is coercible to float (mirrors Ruby respond_to?(:to_f))."""
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False
