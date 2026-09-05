#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${CINEQO_PUBLIC_URL:-http://127.0.0.1:8080}"

echo "Checking Cineqo gateway: $BASE_URL"
curl -fsS "$BASE_URL/health" | python3 -m json.tool

echo
echo "Checking all AI engines..."
STATUS="$(curl -fsS "$BASE_URL/api/models/status")"
echo "$STATUS" | python3 -m json.tool

python3 - "$STATUS" <<'PY'
import json, sys
obj=json.loads(sys.argv[1])
failed=[m for m in obj.get('models',[]) if not m.get('ready')]
if failed:
    print('\nNOT READY: ' + ', '.join(m.get('name','unknown') for m in failed), file=sys.stderr)
    raise SystemExit(1)
print('\nAll Cineqo AI engines report READY.')
PY
