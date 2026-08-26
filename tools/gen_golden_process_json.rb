# frozen_string_literal: true
#
# Docker golden generator for process() driven by TBD JSON inputs and by uprating.
#
# Exercises the code paths NOT covered by the plain process golden:
#   - JSON input parsing + schema validation (inputs),
#   - per-surface / subsurface / edge / KHI overrides (_apply_json_overrides),
#   - construction uprating (uprate + uo) before derating.
#
# Output: tests/fixtures/golden/process_json.json (run via tools/run_golden.sh).

require "json"

$LOAD_PATH.unshift "/gems/oslg-0.4.0/lib"
$LOAD_PATH.unshift "/gems/osut-0.9.1/lib"
$LOAD_PATH.unshift "/gems/topolys-0.6.2/lib"
$LOAD_PATH.unshift "/tbd/lib"

require "openstudio"
require "tbd"

def rnd(x, n = 6)
  x.is_a?(Numeric) ? x.round(n) : x
end

def norm_surf(s)
  h = { "deratable" => s[:deratable] }
  h["heatloss"] = rnd(s[:heatloss]) if s.key?(:heatloss)
  h["ratio"]    = rnd(s[:ratio])    if s.key?(:ratio)
  h["u"]        = rnd(s[:u])        if s.key?(:u)
  h
end

def norm_edge(e)
  {
    "psi"      => e[:psi].to_s,
    "type"     => e[:type].to_s,
    "length"   => rnd(e[:length]),
    "surfaces" => e[:surfaces].sort,
    "v0"       => [rnd(e[:v0x], 4), rnd(e[:v0y], 4), rnd(e[:v0z], 4)],
    "v1"       => [rnd(e[:v1x], 4), rnd(e[:v1y], 4), rnd(e[:v1z], 4)],
  }
end

def run(model_file, argh)
  translator = OpenStudio::OSVersion::VersionTranslator.new
  om = translator.loadModel(OpenStudio::Path.new("/osms/#{model_file}"))
  return nil if om.empty?

  TBD.clean!
  model = om.get
  res = TBD.process(model, argh)
  surfaces = {}
  res[:surfaces].each { |id, s| surfaces[id] = norm_surf(s) }
  edges = (res[:io] && res[:io][:edges] ? res[:io][:edges] : []).map { |e| norm_edge(e) }
  edges.sort_by! { |e| [e["v0"], e["v1"], e["type"]] }
  out = { "surfaces" => surfaces, "edges" => edges }
  out["wall_uo"]  = rnd(argh[:wall_uo])  if argh[:wall_uo]
  out["roof_uo"]  = rnd(argh[:roof_uo])  if argh[:roof_uo]
  out["floor_uo"] = rnd(argh[:floor_uo]) if argh[:floor_uo]
  out
end

SCHEMA = "/tbd/tbd.schema.json"

# JSON-driven cases: [label, model, json file].
JSON_CASES = [
  ["warehouse10", "warehouse.osm",  "tbd_warehouse10.json"],
  ["warehouse4",  "warehouse.osm",  "tbd_warehouse4.json"],
  ["warehouse17", "warehouse.osm",  "tbd_warehouse17.json"],
  ["warehouse18", "warehouse.osm",  "tbd_warehouse18.json"],
  ["seb_n2",      "seb.osm",        "tbd_seb_n2.json"],
  ["seb_n4",      "seb.osm",        "tbd_seb_n4.json"],
  ["5zone",       "5ZoneNoHVAC.osm", "tbd_5ZoneNoHVAC.json"],
]

out = {}

JSON_CASES.each do |label, model_file, jfile|
  argh = {
    option:  "poor (BETBG)",
    io_path: "/json/#{jfile}",
  }
  r = run(model_file, argh)
  next if r.nil?

  out[label] = r
  warn "#{label}: #{r['surfaces'].size} surfaces, #{r['edges'].size} edges"
end

# Uprating case: uprate ALL wall constructions to a target Ut, then derate.
argh = {
  option:       "poor (BETBG)",
  uprate_walls: true,
  wall_ut:      0.210,
  wall_option:  "all wall constructions",
}
r = run("warehouse.osm", argh)
if r
  out["uprate_walls"] = r
  warn "uprate_walls: wall_uo=#{r['wall_uo']}"
end

File.write("/out/process_json.json", JSON.pretty_generate(out) + "\n")
warn "wrote /out/process_json.json (#{out.size} cases)"
