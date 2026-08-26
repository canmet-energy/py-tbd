#!/usr/bin/env bash
# Run a Docker-based golden generator (any tools/gen_golden_*.rb harness that
# expects /gems, /tbd, /osms and /out mounts) inside an OpenStudio image.
#
# Usage:  tools/run_golden.sh gen_golden_geo.rb
#         tools/run_golden.sh gen_golden_edges.rb
#
# Env overrides:
#   IMG   OpenStudio Docker image (default: nrel/openstudio:3.11.0)
#   GEMS  host dir holding oslg-*/osut-*/topolys-* (default: /tmp/tbd_gems)
#   TBD   rd2/tbd source checkout (default: ../tbd relative to this repo)
set -euo pipefail

HARNESS="${1:?usage: run_golden.sh <harness.rb>}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
IMG="${IMG:-nrel/openstudio:3.11.0}"
GEMS="${GEMS:-/tmp/tbd_gems}"
TBD="${TBD:-$(cd "$REPO/../tbd" && pwd)}"

docker run --rm \
  -v "$GEMS":/gems:ro \
  -v "$TBD":/tbd:ro \
  -v "$REPO/tests/fixtures/osms/in":/osms:ro \
  -v "$REPO/tests/fixtures/json":/json:ro \
  -v "$REPO/tests/fixtures/golden":/out \
  -v "$REPO/tools/$HARNESS":/gen.rb:ro \
  "$IMG" bash -lc 'ruby /gen.rb'
