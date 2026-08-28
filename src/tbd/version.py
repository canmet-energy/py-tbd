# MIT License
#
# Copyright (c) 2020-2026 Denis Bourgeois & Dan Macumber
#
# Native Python port of the TBD (Thermal Bridging & Derating) Ruby gem.

# py-tbd version. Tracks the upstream Ruby TBD version it is ported from.
#
# THIS IS THE tbd-3.5.2-compat BRANCH (2026-08-28): main ports upstream
# v3.6.0; this branch backports uo()/uprate() to v3.5.2 semantics so the
# canmet-energy btap family can integrate py-tbd against its FROZEN Ruby
# TBD 3.5.2 / OSut 0.8.2 verification baseline (btap D-78/D-79, Option A of
# the M7 review). 3.5.2 REFUSES an infeasible uprate outright where 3.6.0
# partially uprates — a physical-output difference (~43% on a wall), not
# serialization noise. The branch exists solely to complete that
# verification; retire it when the btap family rebaselines on 3.6.x.
VERSION = "3.5.2"

# Exact rd2/tbd revision this port was branched from. See UPSTREAM.md for the
# tracking process. Bump together with the ported source + regenerated goldens.
UPSTREAM_REPO = "https://github.com/rd2/tbd"
UPSTREAM_SHA = "95156a922f54e45293e1896eba11bc29cd1b5c6d"
UPSTREAM_VERSION = "3.5.2"
