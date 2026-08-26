# frozen_string_literal: true
#
# Golden generator for the PURE-TOPOLOGY geo methods (matches?/concave?/convex?).
# These need Topolys but not OpenStudio, so they run against the Ruby TBD gem with
# oslg + osut + topolys on the load path (osut's `require "openstudio"` satisfied
# by an empty stub). OpenStudio-dependent geo methods (tru_normal/reset_kiva/...)
# are handled by the Docker-based generator (Phase 2, later).
#
# Output: tests/fixtures/golden/geo_pure.json
#
# Usage:
#   GEMROOT=/path/to/gems TBD_SRC=/path/to/rd2/tbd ruby tools/gen_golden_geo_pure.rb

require "json"
require "fileutils"
require "tmpdir"

TBD_SRC = ENV["TBD_SRC"] || File.expand_path("../../tbd", __dir__)
GEMROOT = ENV["GEMROOT"] or abort("set GEMROOT to the gems dir")
OSUT_VERSION = ENV["OSUT_VERSION"] || "0.9.1"
OSLG_VERSION = ENV["OSLG_VERSION"] || "0.4.0"
TOPOLYS_VERSION = ENV["TOPOLYS_VERSION"] || "0.6.2"

stub_dir = File.join(Dir.tmpdir, "tbd_os_stub")
FileUtils.mkdir_p(stub_dir)
File.write(File.join(stub_dir, "openstudio.rb"), "module OpenStudio; end\n")

$LOAD_PATH.unshift stub_dir
$LOAD_PATH.unshift File.join(GEMROOT, "oslg-#{OSLG_VERSION}", "lib")
$LOAD_PATH.unshift File.join(GEMROOT, "osut-#{OSUT_VERSION}", "lib")
$LOAD_PATH.unshift File.join(GEMROOT, "topolys-#{TOPOLYS_VERSION}", "lib")

require "oslg"
require "osut"
require "topolys"

module TBD
  extend OSut
  DBG = OSut::DEBUG.dup
  INF = OSut::INFO.dup
  WRN = OSut::WARN.dup
  ERR = OSut::ERR.dup
  FTL = OSut::FATAL.dup
  TOL = OSut::TOL.dup
end

load File.join(TBD_SRC, "lib", "tbd", "geo.rb")
module TBD; extend TBD; end

PI = Math::PI

def pt(a) = Topolys::Point3D.new(a[0], a[1], a[2])
def vec(a) = Topolys::Vector3D.new(a[0], a[1], a[2])

# --- matches? cases: pairs of edges given as [[x,y,z],[x,y,z]] ---------------
matches_cases = [
  { "e1" => [[0, 0, 0], [1, 0, 0]], "e2" => [[0, 0, 0], [1, 0, 0]] }, # identical
  { "e1" => [[0, 0, 0], [1, 0, 0]], "e2" => [[1, 0, 0], [0, 0, 0]] }, # reversed
  { "e1" => [[0, 0, 0], [1, 0, 0]], "e2" => [[0, 0, 0.005], [1, 0, 0.005]] }, # within TOL
  { "e1" => [[0, 0, 0], [1, 0, 0]], "e2" => [[0, 0, 0.05], [1, 0, 0.05]] }, # outside TOL
  { "e1" => [[0, 0, 0], [1, 0, 0]], "e2" => [[0, 1, 0], [1, 1, 0]] }, # parallel offset
  { "e1" => [[0, 0, 0], [2, 2, 2]], "e2" => [[2, 2, 2], [0, 0, 0]] }, # diagonal reversed
]
matches_out = matches_cases.map do |c|
  e1 = { v0: pt(c["e1"][0]), v1: pt(c["e1"][1]) }
  e2 = { v0: pt(c["e2"][0]), v1: pt(c["e2"][1]) }
  c.merge("tol" => TBD::TOL, "result" => TBD.matches?(e1, e2))
end

# --- concave?/convex? cases --------------------------------------------------
cc_cases = [
  { "s1" => { "angle" => 0.0,      "normal" => [1, 0, 0], "polar" => [0, 1, 0] },
    "s2" => { "angle" => PI / 2,   "normal" => [0, 1, 0], "polar" => [1, 0, 0] } },
  { "s1" => { "angle" => 0.0,      "normal" => [1, 0, 0], "polar" => [0, 1, 0] },
    "s2" => { "angle" => 3 * PI / 2, "normal" => [0, -1, 0], "polar" => [1, 0, 0] } },
  { "s1" => { "angle" => 0.0,      "normal" => [1, 0, 0], "polar" => [0, 1, 0] },
    "s2" => { "angle" => PI,       "normal" => [-1, 0, 0], "polar" => [0, 1, 0] } }, # ~flat
  { "s1" => { "angle" => 0.1,      "normal" => [1, 0, 0], "polar" => [0, 1, 0] },
    "s2" => { "angle" => 0.1,      "normal" => [1, 0, 0], "polar" => [0, 1, 0] } }, # equal
  { "s1" => { "angle" => 0.0,      "normal" => [0, 0, 1], "polar" => [1, 0, 0] },
    "s2" => { "angle" => PI / 3,   "normal" => [0.5, 0, 0.87], "polar" => [0.87, 0, -0.5] } },
]
def build_s(h)
  { angle: h["angle"], normal: vec(h["normal"]), polar: vec(h["polar"]) }
end
concave_out = cc_cases.map { |c| c.merge("result" => TBD.concave?(build_s(c["s1"]), build_s(c["s2"]))) }
convex_out  = cc_cases.map { |c| c.merge("result" => TBD.convex?(build_s(c["s1"]), build_s(c["s2"]))) }

golden = {
  "_upstream_sha" => "dd6f12f8f2c24950485918c7eaca57d8f091a64d",
  "matches" => matches_out,
  "concave" => concave_out,
  "convex"  => convex_out,
}

out = File.expand_path("../tests/fixtures/golden/geo_pure.json", __dir__)
FileUtils.mkdir_p(File.dirname(out))
File.write(out, JSON.pretty_generate(golden) + "\n")
puts "wrote #{out} (matches=#{matches_out.size} concave/convex=#{cc_cases.size})"
