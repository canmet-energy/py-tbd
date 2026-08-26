# frozen_string_literal: true
#
# Docker golden generator for TBD.process (the core engine).
#
# Runs the full Ruby TBD gem end-to-end on each .osm fixture with the default
# "poor (BETBG)" PSI set (no JSON), and records:
#   - per-surface: deratable flag, heat loss, derating ratio, un-derated U;
#   - the serialized io["edges"] array (type, PSI set, length, surfaces, coords).
# The Python port must reproduce these within tolerance.
#
# Output: tests/fixtures/golden/process.json (run via tools/run_golden.sh).

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
    "psi"      => e[:psi].to_s,          # PSI set name (symbol/string)
    "type"     => e[:type].to_s,
    "length"   => rnd(e[:length]),
    "surfaces" => e[:surfaces].sort,
    "v0"       => [rnd(e[:v0x], 4), rnd(e[:v0y], 4), rnd(e[:v0z], 4)],
    "v1"       => [rnd(e[:v1x], 4), rnd(e[:v1y], 4), rnd(e[:v1z], 4)],
  }
end

models = Dir.glob("/osms/*.osm").sort
out = {}

models.each do |path|
  name = File.basename(path)
  translator = OpenStudio::OSVersion::VersionTranslator.new
  om = translator.loadModel(OpenStudio::Path.new(path))
  next if om.empty?

  model = om.get
  argh  = { option: "poor (BETBG)" }
  res   = TBD.process(model, argh)
  next if res[:surfaces].empty?

  surfaces = {}
  res[:surfaces].each { |id, s| surfaces[id] = norm_surf(s) }

  edges = (res[:io] && res[:io][:edges] ? res[:io][:edges] : []).map { |e| norm_edge(e) }
  # Order-independent: sort edges by geometry for stable comparison.
  edges.sort_by! { |e| [e["v0"], e["v1"], e["type"]] }

  out[name] = { "surfaces" => surfaces, "edges" => edges }
  warn "#{name}: #{surfaces.size} surfaces, #{edges.size} edges"
end

File.write("/out/process.json", JSON.pretty_generate(out) + "\n")
warn "wrote /out/process.json (#{out.size} models)"
