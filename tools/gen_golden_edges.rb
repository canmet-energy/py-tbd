# frozen_string_literal: true
#
# Docker golden generator for the Topolys graph builders (objects/kids/dads/faces).
#
# For each .osm fixture it mirrors the pre-processing that TBD.process performs
# up to (but not including) edge classification:
#   1. build a per-surface descriptor with TBD.properties,
#   2. add every base surface + its subsurfaces to ONE Topolys model via dads
#      (so coincident edges are shared through deduplicated vertices),
#   3. collect the resulting edges with faces.
#
# Topolys edge/wire IDs are non-deterministic UUIDs, so the output is keyed by
# EDGE GEOMETRY (rounded, orientation-independent endpoint coordinates) instead.
# Each entry records the edge length and the sorted set of surfaces it touches —
# a language-independent contract the Python port must reproduce.
#
# Output: tests/fixtures/golden/geo_edges.json  (run via tools/run_golden.sh).

require "json"

$LOAD_PATH.unshift "/gems/oslg-0.4.0/lib"
$LOAD_PATH.unshift "/gems/osut-0.9.1/lib"
$LOAD_PATH.unshift "/gems/topolys-0.6.2/lib"
$LOAD_PATH.unshift "/tbd/lib"

require "openstudio"
require "tbd"

# Orientation-independent geometry key for an edge, from its two endpoint
# vertices. Rounded to 1e-4 m (0.1 mm) so floating noise never splits an edge.
def edge_key(e)
  a = e[:v0].point
  b = e[:v1].point
  pa = [a.x.round(4), a.y.round(4), a.z.round(4)]
  pb = [b.x.round(4), b.y.round(4), b.z.round(4)]
  [pa, pb].sort.to_json # sort so v0/v1 order is irrelevant
end

models = Dir.glob("/osms/*.osm").sort
out = {}

models.each do |path|
  name = File.basename(path)
  translator = OpenStudio::OSVersion::VersionTranslator.new
  om = translator.loadModel(OpenStudio::Path.new(path))
  next if om.empty?

  model = om.get
  heat = TBD.heatingTemperatureSetpoints?(model)
  cool = TBD.coolingTemperatureSetpoints?(model)
  setpts = heat || cool

  # 1. per-surface descriptors
  surfaces = {}
  model.getSurfaces.sort_by(&:nameString).each do |s|
    props = TBD.properties(s, { setpoints: setpts })
    surfaces[s.nameString] = props unless props.nil?
  end

  # 2. one shared Topolys model; add all dads (+ their kids)
  t_model = Topolys::Model.new
  TBD.dads(t_model, surfaces)

  # 3. collect edges
  edges = {}
  TBD.faces(surfaces, edges)

  graph = {}
  edges.each_value do |e|
    graph[edge_key(e)] = {
      "length"   => e[:length].round(6),
      "surfaces" => e[:surfaces].keys.sort,
    }
  end

  out[name] = graph
  warn "#{name}: #{graph.size} edges"
end

File.write("/out/geo_edges.json", JSON.pretty_generate(out) + "\n")
warn "wrote /out/geo_edges.json (#{out.size} models)"
