# MIT License
#
# Copyright (c) 2020-2026 Denis Bourgeois & Dan Macumber
#
# Native Python port of the TBD (Thermal Bridging & Derating) Ruby gem.
# Mirrors lib/tbd.rb: loads the dependency chain and re-exports the public API
# plus the shared constants, so callers can do `import tbd; tbd.process(...)`.

from .version import (
    VERSION,
    UPSTREAM_REPO,
    UPSTREAM_SHA,
    UPSTREAM_VERSION,
)

from ._helpers import (
    oslg,
    osut,
    DBG, INF, WRN, ERR, FTL,
    TOL, TOL2, DMIN, DMAX, KMIN, KMAX,
    UMIN, UMAX, RMIN, RMAX, NS,
)

from .psi import KHI, PSI, inputs, derate, process, exit  # noqa: E402
from .geo import (  # noqa: E402
    matches, objects, faces, tru_normal, is_concave, is_convex,
    reset_kiva, kids, dads, properties, kiva,
)
from .ua import uo, uprate, qc33, ua_summary, ua_md  # noqa: E402

__all__ = [
    "VERSION", "UPSTREAM_REPO", "UPSTREAM_SHA", "UPSTREAM_VERSION",
    "oslg", "osut",
    "DBG", "INF", "WRN", "ERR", "FTL",
    "TOL", "TOL2", "DMIN", "DMAX", "KMIN", "KMAX",
    "UMIN", "UMAX", "RMIN", "RMAX", "NS",
    "KHI", "PSI", "inputs", "derate", "process", "exit",
    "matches", "objects", "faces", "tru_normal", "is_concave", "is_convex",
    "reset_kiva", "kids", "dads", "properties", "kiva",
    "uo", "uprate", "qc33", "ua_summary", "ua_md",
]
