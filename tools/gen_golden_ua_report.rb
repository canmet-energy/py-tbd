# frozen_string_literal: true
#
# Docker golden generator for the UA' report path (qc33 + ua_summary + ua_md).
#
# For a few fixtures it runs TBD.process with the Quebec reference ruleset, then
# renders the bilingual UA' Markdown with a PINNED date, capturing the EN and FR
# report lines. The Python port must reproduce them (modulo the single date line,
# whose Time vs datetime string representation differs by language).
#
# Output: tests/fixtures/golden/ua_report.json (run via tools/run_golden.sh).

require "json"

$LOAD_PATH.unshift "/gems/oslg-0.4.0/lib"
$LOAD_PATH.unshift "/gems/osut-0.9.1/lib"
$LOAD_PATH.unshift "/gems/topolys-0.6.2/lib"
$LOAD_PATH.unshift "/tbd/lib"

require "openstudio"
require "tbd"

PINNED = Time.utc(2026, 1, 1, 0, 0, 0)
MODELS = ["seb.osm", "smalloffice.osm", "warehouse.osm"]

out = {}

MODELS.each do |name|
  translator = OpenStudio::OSVersion::VersionTranslator.new
  om = translator.loadModel(OpenStudio::Path.new("/osms/#{name}"))
  next if om.empty?

  TBD.clean!
  model = om.get
  argh = {
    option:  "code (Quebec)",
    gen_ua:  true,
    ua_ref:  "code (Quebec)",
    seed:    name,
    version: "",
  }
  TBD.process(model, argh)
  ua = TBD.ua_summary(PINNED, argh)
  next if ua.nil? || ua.empty?

  out[name] = {
    "en" => TBD.ua_md(ua, :en),
    "fr" => TBD.ua_md(ua, :fr),
  }
  warn "#{name}: en=#{out[name]['en'].size} fr=#{out[name]['fr'].size} lines"
end

File.write("/out/ua_report.json", JSON.pretty_generate(out) + "\n")
warn "wrote /out/ua_report.json (#{out.size} models)"
