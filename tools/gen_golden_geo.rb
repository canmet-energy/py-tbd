# frozen_string_literal: true
#
# Docker golden generator for OpenStudio-backed geo methods (currently:
# TBD.properties). Runs the FULL TBD Ruby gem with real OpenStudio + the mounted
# oslg/osut/topolys gems, over every .osm fixture, and serializes a normalized,
# JSON-able surface descriptor per surface.
#
# Run inside the OpenStudio Docker image via `tools/run_golden.sh gen_golden_geo.rb`,
# which mounts:
#   /gems  -> oslg/osut/topolys gem trees
#   /tbd   -> the rd2/tbd source
#   /osms  -> py-tbd tests/fixtures/osms/in
#   /out   -> py-tbd tests/fixtures/golden   (writes geo_properties.json)

require "json"

$LOAD_PATH.unshift "/gems/oslg-0.4.0/lib"
$LOAD_PATH.unshift "/gems/osut-0.9.1/lib"
$LOAD_PATH.unshift "/gems/topolys-0.6.2/lib"
$LOAD_PATH.unshift "/tbd/lib"

require "openstudio"
require "tbd"

# Topolys Point3D/Vector3D and OpenStudio Vector3d all expose .x/.y/.z as
# parenless methods in Ruby, so one helper serializes either.
def xyz(v)
  [v.x, v.y, v.z]
end

def norm_sub(sub)
  h = {
    "type"     => sub[:type].to_s,
    "gross"    => sub[:gross],
    "area"     => sub[:area],
    "mult"     => sub[:mult],
    "u"        => sub[:u],
    "unhinged" => sub[:unhinged],
    "n"        => xyz(sub[:n]),
    "minz"     => sub[:minz],
    "points"   => sub[:points].map { |p| xyz(p) },
  }
  h["glazed"] = true if sub[:glazed]
  h
end

def norm_surf(surf)
  h = {
    "type"        => surf[:type].to_s,
    "boundary"    => surf[:boundary],
    "ground"      => surf[:ground],
    "conditioned" => surf[:conditioned],
    "occupied"    => surf[:occupied],
    "spandrel"    => surf[:spandrel],
    "gross"       => surf[:gross],
    "net"         => surf[:net],
    "filmRSI"     => surf[:filmRSI],
    "minz"        => surf[:minz],
    "r"           => surf[:r],
    "index"       => surf[:index],
    "ltype"       => surf[:ltype].nil? ? nil : surf[:ltype].to_s,
    "space"       => surf[:space].nameString,
    "n"           => xyz(surf[:n]),
    "points"      => surf[:points].map { |p| xyz(p) },
  }
  h["heating"] = surf[:heating] if surf.key?(:heating)
  h["cooling"] = surf[:cooling] if surf.key?(:cooling)
  h["construction"] = surf[:construction].nameString if surf.key?(:construction)
  h["stype"] = surf[:stype].nameString if surf.key?(:stype)
  h["story"] = surf[:story].nameString if surf.key?(:story)
  %i[windows doors skylights].each do |k|
    next unless surf.key?(k)

    h[k.to_s] = surf[k].transform_values { |sub| norm_sub(sub) }
  end
  h
end

models = Dir.glob("/osms/*.osm").sort
out = {}

models.each do |path|
  name = File.basename(path)
  translator = OpenStudio::OSVersion::VersionTranslator.new
  om = translator.loadModel(OpenStudio::Path.new(path))
  next if om.empty?

  model = om.get

  # Mirror process(): setpoints presence is a model-wide flag.
  heat = TBD.heatingTemperatureSetpoints?(model)
  cool = TBD.coolingTemperatureSetpoints?(model)
  setpts = heat || cool

  surfaces = {}
  model.getSurfaces.sort_by(&:nameString).each do |s|
    props = TBD.properties(s, { setpoints: setpts })
    next if props.nil?

    surfaces[s.nameString] = norm_surf(props)
  end

  out[name] = { "setpoints" => setpts, "surfaces" => surfaces }
  warn "#{name}: #{surfaces.size} surfaces"
end

File.write("/out/geo_properties.json", JSON.pretty_generate(out) + "\n")
warn "wrote /out/geo_properties.json (#{out.size} models)"
