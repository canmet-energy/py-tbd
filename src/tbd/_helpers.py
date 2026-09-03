# Internal shim that centralises the dependency surface for the py-tbd port.
#
# The Ruby gem relies on Ruby's `extend OSut` / `OSut extend OSlg` mixin chain,
# so it calls bare helper names (`log`, `mismatch`, `matches?`, `rsi`, ...).
# Python has no such mixin, so every module imports `oslg` and `osut` and calls
# them explicitly through this module. This also pins the Ruby -> Python name
# mapping in one place (osut kept camelCase; oslg/py_topolys use their own
# conventions), so ports read against a single reference.

from oslg import oslg
from osut import osut

# Patch known dependency bugs (e.g. pyOSut 0.9.0 insulatingLayer) before any
# ported code calls into osut. Version/behaviour-guarded; see _compat.py.
from . import _compat as _compat  # noqa: E402
_compat.apply()

# --- Log-level constants (oslg.CN.DEBUG..FATAL == 1..5) ----------------------
DBG = oslg.CN.DEBUG
INF = oslg.CN.INFO
WRN = oslg.CN.WARN
ERR = oslg.CN.ERROR
FTL = oslg.CN.FATAL

# --- Numeric / string constants (mirrors lib/tbd.rb copying from OSut::*) -----
TOL = osut.CN.TOL       # 0.01 m geometry tolerance
TOL2 = osut.CN.TOL2     # TOL squared
DMIN = osut.CN.DMIN
DMAX = osut.CN.DMAX
KMIN = osut.CN.KMIN
KMAX = osut.CN.KMAX
UMIN = osut.CN.UMIN
UMAX = osut.CN.UMAX
RMIN = osut.CN.RMIN
RMAX = osut.CN.RMAX
NS = osut.CN.NS         # "nameString"

# Re-export the modules themselves so ported code can call, e.g.,
# `oslg.log(...)`, `oslg.mismatch(...)`, `osut.filmResistances(...)`.
__all__ = [
    "oslg", "osut",
    "DBG", "INF", "WRN", "ERR", "FTL",
    "TOL", "TOL2", "DMIN", "DMAX", "KMIN", "KMAX",
    "UMIN", "UMAX", "RMIN", "RMAX", "NS",
]
