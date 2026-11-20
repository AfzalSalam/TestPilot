#!/usr/bin/env bash
# Start a TestPilot run from CI and wait for its conclusion.
# Env: TESTPILOT_URL, TESTPILOT_API_KEY, optional TESTPILOT_LABEL, TESTPILOT_FAIL_ON_PERF=true
set -euo pipefail
: "${TESTPILOT_URL:?}" "${TESTPILOT_API_KEY:?}"
api="${TESTPILOT_URL%/}/api/v1"
body=$(printf '{"label":"%s"}' "${TESTPILOT_LABEL:-ci}")
run=$(curl -fsS -X POST "$api/ci/runs" -H "X-API-Key: $TESTPILOT_API_KEY" -H 'Content-Type: application/json' -d "$body")
id=$(echo "$run" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
echo "Started run $id"
for _ in $(seq 1 120); do
  r=$(curl -fsS "$api/ci/runs/$id?fail_on_performance=${TESTPILOT_FAIL_ON_PERF:-false}" -H "X-API-Key: $TESTPILOT_API_KEY")
  c=$(echo "$r" | python3 -c 'import sys,json; print(json.load(sys.stdin)["conclusion"])')
  [ "$c" = pending ] || { echo "$r"; [ "$c" = success ]; exit $?; }
  sleep 5
done
echo "Timed out waiting for run $id" >&2; exit 2
