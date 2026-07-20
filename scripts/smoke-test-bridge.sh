#!/bin/sh
# Smoke test for the Lua bridge, meant to run INSIDE the backend Docker image
# (or any environment with luajit on PATH and the bridge script copied next
# to HeadlessWrapper.lua). See AI_BUILD_ADVISOR_PLAN.md, section
# "Aktualnost enginu pri zmenach ligy" -- run this after every
# `git submodule update --remote` before redeploying.
#
# Usage: docker build -t poe-build-advisor-api . && \
#        docker run --rm poe-build-advisor-api sh /app/scripts/smoke-test-bridge.sh
set -eu

POB_SRC_DIR="${POB_SRC_DIR:-/app/vendor/PathOfBuilding/src}"
SAMPLE_XML="${POB_SRC_DIR}/../spec/TestBuilds/3.13/Dual Savior.xml"

if [ ! -f "$SAMPLE_XML" ]; then
	echo "Sample build not found at $SAMPLE_XML -- pick any *.xml file under vendor/PathOfBuilding/spec/TestBuilds/<version>/" >&2
	exit 1
fi

cd "$POB_SRC_DIR"

python3 - "$SAMPLE_XML" <<'PYEOF'
import json
import subprocess
import sys

xml = open(sys.argv[1], encoding="utf-8").read()
proc = subprocess.Popen(
	["luajit", "pob-bridge.lua"],
	stdin=subprocess.PIPE,
	stdout=subprocess.PIPE,
	stderr=subprocess.PIPE,
	text=True,
)


def call(cmd, args=None):
	proc.stdin.write(json.dumps({"cmd": cmd, "args": args or {}}) + "\n")
	proc.stdin.flush()
	line = proc.stdout.readline()
	if not line:
		raise SystemExit(f"bridge died. stderr:\n{proc.stderr.read()}")
	response = json.loads(line)
	if not response.get("ok"):
		raise SystemExit(f"{cmd} failed: {response.get('error')}")
	return response.get("result")


print("ping ->", call("ping"))
print("import_xml ->", call("import_xml", {"xml": xml, "name": "smoke-test"}))
summary = call("get_summary")
print("get_summary keys:", sorted(summary.keys())[:20], "... (%d total)" % len(summary))
for key in ("TotalDPS", "CombinedDPS", "Life", "EnergyShield"):
	if key in summary:
		print(f"  {key} = {summary[key]}")
xml_out = call("export_xml")
print("export_xml -> %d chars" % len(xml_out))
proc.stdin.close()
proc.wait(timeout=10)
print("OK")
PYEOF
