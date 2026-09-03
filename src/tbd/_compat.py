# Runtime compatibility shims for KNOWN BUGS in py-tbd's dependencies.
#
# These are NOT part of the TBD port itself — they patch upstream defects in the
# dependency packages so py-tbd can run today. Each is version-guarded (applied
# only when the buggy version is installed) and behaviour-guarded (applied only
# when the defect is actually observed), so it becomes a no-op once the
# dependency ships a fix. Every shim here is mirrored by an entry in the
# "Dependency bugs" section of UPSTREAM.md for reporting to the authors.

import openstudio
from osut import osut
from oslg import oslg

CN = osut.CN


def _insulating_layer_fixed(lc=None):
    """Corrected osut.insulatingLayer, matching the canonical Ruby osut 0.9.1.

    pyOSut 0.9.0 has TWO defects here vs the Ruby gem py-tbd mirrors:
      (a) osut.py:579 reads `m.thermalResistance()` in the massless branch, but
          the loop variable is `l` (`m` undefined) -> NameError for any massless
          insulating layer.
      (b) it hardcodes the qualifying thresholds as 0.001 / 0.003 / 3.0 instead
          of the RMIN / DMIN / KMAX constants (0.005 / 0.01 / 2.0). This selects
          a different insulating layer than the Ruby gem (e.g. a k=2.31 concrete
          floor is excluded by Ruby's `k > KMAX` but kept by pyOSut's `k > 3.0`).
    This copy uses `l` and the RMIN/DMIN/KMAX constants, reproducing Ruby osut.
    """
    mth = "osut.insulatingLayer"
    cl = openstudio.model.LayeredConstruction
    res = dict(index=None, type=None, r=0.0)
    i = 0

    if not isinstance(lc, cl):
        return oslg.mismatch("lc", lc, cl, mth, CN.DBG, res)

    for l in lc.layers():
        if l.to_MasslessOpaqueMaterial():
            l = l.to_MasslessOpaqueMaterial().get()

            if l.thermalResistance() < CN.RMIN or l.thermalResistance() < res["r"]:
                i += 1
                continue
            else:
                res["r"] = l.thermalResistance()
                res["index"] = i
                res["type"] = "massless"

        if l.to_StandardOpaqueMaterial():
            l = l.to_StandardOpaqueMaterial().get()
            k = l.thermalConductivity()
            d = l.thickness()

            if d < CN.DMIN or k > CN.KMAX or d / k < res["r"]:
                i += 1
                continue
            else:
                res["r"] = d / k
                res["index"] = i
                res["type"] = "standard"

        i += 1

    return res


def _rsi_fixed(lc=None, film=0.0, t=0.0):
    """Corrected osut.rsi.

    pyOSut 0.9.0 (osut.py:536) accumulates the RAW OptionalMasslessOpaqueMaterial
    instead of `.get().thermalResistance()`, so `rsi` raises TypeError for any
    construction containing a MasslessOpaqueMaterial. This copy is identical to
    upstream except that one line is fixed.
    """
    mth = "osut.rsi"
    cl = openstudio.model.LayeredConstruction

    if not isinstance(lc, cl):
        return oslg.mismatch("lc", lc, cl, mth, CN.DBG, 0.0)
    try:
        film = float(film)
    except Exception:
        return oslg.mismatch("film", film, float, mth, CN.DBG, 0.0)
    try:
        t = float(t)
    except Exception:
        return oslg.mismatch("temp K", t, float, mth, CN.DBG, 0.0)

    t += 273.0  # °C to K
    if t < 0:
        return oslg.negative("temp K", mth, CN.ERR, 0.0)
    if film < 0:
        return oslg.negative("film", mth, CN.ERR, 0.0)

    rsi = film
    for m in lc.layers():
        if m.to_SimpleGlazing():
            return 1 / m.to_SimpleGlazing().get().uFactor()
        elif m.to_StandardGlazing():
            rsi += m.to_StandardGlazing().get().thermalResistance()
        elif m.to_RefractionExtinctionGlazing():
            rsi += m.to_RefractionExtinctionGlazing().get().thermalResistance()
        elif m.to_Gas():
            rsi += m.to_Gas().get().getThermalResistance(t)
        elif m.to_GasMixture():
            rsi += m.to_GasMixture().get().getThermalResistance(t)

        # Opaque materials next.
        if m.to_StandardOpaqueMaterial():
            rsi += m.to_StandardOpaqueMaterial().get().thermalResistance()
        elif m.to_MasslessOpaqueMaterial():
            rsi += m.to_MasslessOpaqueMaterial().get().thermalResistance()  # upstream missed .get().thermalResistance()
        elif m.to_RoofVegetation():
            rsi += m.to_RoofVegetation().get().thermalResistance()
        elif m.to_AirGap():
            rsi += m.to_AirGap().get().thermalResistance()

    return rsi


def _needs_rsi_shim():
    """True if osut.rsi raises on a construction with a massless layer."""
    try:
        m = openstudio.model.Model()
        lc = openstudio.model.Construction(m)
        mat = openstudio.model.MasslessOpaqueMaterial(m, "Smooth", 2.0)
        lc.insertLayer(0, mat)
        osut.rsi(lc, 0.15)
        return False
    except TypeError:
        return True
    except Exception:
        return False


def _needs_insulating_layer_shim():
    """True if osut.insulatingLayer deviates from the Ruby osut behavior.

    Probes both defects: (a) the NameError on a massless layer, and (b) the wrong
    KMAX threshold (a k=2.5 standard-only construction has no qualifying layer
    under the Ruby constants, so a non-None index signals the hardcoded 3.0 bug).
    """
    try:
        m = openstudio.model.Model()
        # (b) threshold probe: single standard layer, KMAX < k < 3.0.
        lc = openstudio.model.Construction(m)
        std = openstudio.model.StandardOpaqueMaterial(m, "Smooth", 0.15, 2.5, 2300.0, 900.0)
        lc.insertLayer(0, std)
        if osut.insulatingLayer(lc)["index"] is not None:
            return True
        # (a) NameError probe: massless layer.
        lc2 = openstudio.model.Construction(m)
        mat = openstudio.model.MasslessOpaqueMaterial(m, "Smooth", 2.0)
        lc2.insertLayer(0, mat)
        osut.insulatingLayer(lc2)
        return False
    except NameError:
        return True
    except Exception:
        return False


def apply():
    """Install all needed dependency shims. Idempotent; safe to call repeatedly."""
    if getattr(osut, "_tbd_shims_applied", False):
        return
    if _needs_insulating_layer_shim():
        osut.insulatingLayer = _insulating_layer_fixed
    if _needs_rsi_shim():
        osut.rsi = _rsi_fixed
    osut._tbd_shims_applied = True
