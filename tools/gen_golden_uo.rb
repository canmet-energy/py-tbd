# frozen_string_literal: true
#
# Docker golden generator for TBD.uo (construction uprating numeric core).
#
# Builds a handful of layered constructions from explicit material specs, runs
# TBD.uo against each, and records the returned Uo plus the resulting construction
# RSi (which captures the layer mutation uo performs). The Python test rebuilds
# the identical constructions from the same specs and must reproduce the numbers.
#
# Output: tests/fixtures/golden/uo.json  (run via tools/run_golden.sh gen_golden_uo.rb)

require "json"

$LOAD_PATH.unshift "/gems/oslg-0.4.0/lib"
$LOAD_PATH.unshift "/gems/osut-0.9.1/lib"
$LOAD_PATH.unshift "/gems/topolys-0.6.2/lib"
$LOAD_PATH.unshift "/tbd/lib"

require "openstudio"
require "tbd"

# Build one layered construction in `model` from a list of layer specs. Each spec
# is {"type"=>"massless","r"=>..} or {"type"=>"standard","k"=>..,"d"=>..}.
def build(model, name, layers)
  lc = OpenStudio::Model::Construction.new(model)
  lc.setName(name)
  mats = []
  layers.each_with_index do |ly, i|
    if ly["type"] == "massless"
      m = OpenStudio::Model::MasslessOpaqueMaterial.new(model, "Smooth", ly["r"])
    else
      m = OpenStudio::Model::StandardOpaqueMaterial.new(model)
      m.setThickness(ly["d"])
      m.setConductivity(ly["k"])
    end
    m.setName("#{name} L#{i}")
    mats << m
  end
  lc.setLayers(mats)
  lc
end

CASES = [
  { "id" => "C1", "layers" => [{ "type" => "massless", "r" => 3.0 }],
    "area" => 100.0, "film" => 0.15, "hloss" => 5.0, "ut" => 0.21 },
  { "id" => "C2", "layers" => [{ "type" => "massless", "r" => 3.0 },
                               { "type" => "standard", "k" => 2.31, "d" => 0.15 }],
    "area" => 80.0, "film" => 0.12, "hloss" => 3.0, "ut" => 0.18 },
  { "id" => "C3", "layers" => [{ "type" => "standard", "k" => 0.03, "d" => 0.10 }],
    "area" => 50.0, "film" => 0.16, "hloss" => 2.0, "ut" => 0.25 },
  { "id" => "C4", "layers" => [{ "type" => "massless", "r" => 5.0 }],
    "area" => 200.0, "film" => 0.20, "hloss" => 500.0, "ut" => 0.20 }, # forces UMIN
  { "id" => "C5", "layers" => [{ "type" => "standard", "k" => 0.04, "d" => 0.20 }],
    "area" => 120.0, "film" => 0.14, "hloss" => 8.0, "ut" => 0.15 },
]

out = []
CASES.each do |c|
  model = OpenStudio::Model::Model.new
  lc = build(model, c["id"], c["layers"])
  u = TBD.uo(c["id"], lc, c["area"], c["film"], c["hloss"], c["ut"])
  out << c.merge("result_uo" => u, "final_rsi" => TBD.rsi(lc, c["film"]))
end

File.write("/out/uo.json", JSON.pretty_generate({ "uo" => out }) + "\n")
warn "wrote /out/uo.json (#{out.size} cases)"
