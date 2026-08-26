# frozen_string_literal: true
#
# Golden generator for the PURE-DATA layer of TBD (KHI + PSI classes).
#
# This layer needs no OpenStudio model, so it runs against the Ruby TBD gem with
# only `oslg` + `osut` on the load path (osut's `require "openstudio"` is
# satisfied by an empty stub, since the KHI/PSI data path never calls the SDK).
#
# Output: tests/fixtures/golden/psi.json — the parity contract for test_psi.py.
#
# Usage (paths default to this repo layout; override via env):
#   TBD_SRC=/path/to/rd2/tbd \
#   GEMROOT=/path/to/vendor/bundle/ruby/3.2.0/gems \
#   OSUT_VERSION=0.9.1 \
#   ruby tools/gen_golden_psi.rb
#
# The pinned upstream revision is recorded in UPSTREAM.md / src/tbd/version.py.

require "json"
require "fileutils"
require "tmpdir"

TBD_SRC = ENV["TBD_SRC"] || File.expand_path("../../tbd", __dir__)
GEMROOT = ENV["GEMROOT"] or abort("set GEMROOT to the gems dir (oslg/osut live there)")
OSUT_VERSION = ENV["OSUT_VERSION"] || "0.9.1"
OSLG_VERSION = ENV["OSLG_VERSION"] || "0.4.0"

# Empty OpenStudio stub so `require "osut"` succeeds without the SDK.
stub_dir = File.join(Dir.tmpdir, "tbd_os_stub")
FileUtils.mkdir_p(stub_dir)
File.write(File.join(stub_dir, "openstudio.rb"), "module OpenStudio; end\n")

$LOAD_PATH.unshift stub_dir
$LOAD_PATH.unshift File.join(GEMROOT, "oslg-#{OSLG_VERSION}", "lib")
$LOAD_PATH.unshift File.join(GEMROOT, "osut-#{OSUT_VERSION}", "lib")

require "oslg"
require "osut"

module TBD
  extend OSut
  DBG = OSut::DEBUG.dup
  INF = OSut::INFO.dup
  WRN = OSut::WARN.dup
  ERR = OSut::ERR.dup
  FTL = OSut::FATAL.dup
end

load File.join(TBD_SRC, "lib", "tbd", "psi.rb")

# Deep-stringify symbol keys so JSON round-trips identically to the Python dicts.
def stringify(obj)
  case obj
  when Hash  then obj.each_with_object({}) { |(k, v), h| h[k.to_s] = stringify(v) }
  when Array then obj.map { |e| stringify(e) }
  when Symbol then obj.to_s
  else obj
  end
end

khi = TBD::KHI.new
psi = TBD::PSI.new

psi_out = {}
psi.set.keys.each do |id|
  sh = psi.shorthands(id)
  psi_out[id.to_s] = {
    "set"      => stringify(psi.set[id]),
    "has"      => stringify(sh[:has]),
    "val"      => stringify(sh[:val]),
    "complete" => psi.complete?(id)
  }
end

# A handful of `safe` inheritance cases across representative sets/types.
safe_cases = [
  ["90.1.22|wood.fr|unmitigated", "rimjoistconcave"],
  ["poor (BETBG)", "head"],
  ["poor (BETBG)", "doorjambconvex"],
  ["poor (BETBG)", "skylightsill"],
  ["90.1.22|steel.m|default", "cornerconcave"],
  ["(non thermal bridging)", "balconysillconvex"],
]
safe_out = safe_cases.map do |id, type|
  { "id" => id, "type" => type, "result" => psi.safe(id, type.to_sym)&.to_s }
end

golden = {
  "_upstream_sha" => "dd6f12f8f2c24950485918c7eaca57d8f091a64d",
  "_upstream_version" => "3.6.0",
  "khi_point" => stringify(khi.point),
  "psi" => psi_out,
  "safe" => safe_out
}

out = File.expand_path("../tests/fixtures/golden/psi.json", __dir__)
FileUtils.mkdir_p(File.dirname(out))
File.write(out, JSON.pretty_generate(golden) + "\n")
puts "wrote #{out} (#{psi_out.size} PSI sets, #{khi.point.size} KHI entries)"
