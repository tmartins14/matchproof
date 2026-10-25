#!/usr/bin/env bash
# Check the deployed pair. Usage: scripts/smoke_prod.sh [WEB_URL API_URL]
# Without arguments, WEB_URL and API_URL come from the current azd environment.
# Exits non-zero on the first failing check and says which one.
set -uo pipefail

WEB_URL="${1:-$(azd env get-value WEB_URL 2>/dev/null || true)}"
API_URL="${2:-$(azd env get-value API_URL 2>/dev/null || true)}"
WEB_URL="${WEB_URL%/}"
API_URL="${API_URL%/}"
if [ -z "$WEB_URL" ] || [ -z "$API_URL" ]; then
  echo "usage: $0 [WEB_URL API_URL] (or run inside an azd environment that has both)" >&2
  exit 2
fi

fail() {
  echo "FAIL $1" >&2
  exit 1
}
pass() { echo "ok   $1"; }

# 1. web root
body="$(curl -fsS --max-time 20 "$WEB_URL/")" || fail "1 web root did not return 200 ($WEB_URL/)"
printf '%s' "$body" | grep -q "<title>Matchproof live desk</title>" || fail "1 web root is 200 but is not the desk's HTML"
pass "1 web root returns the desk"

# 2. API health
health="$(curl -fsS --max-time 60 "$API_URL/health")" || fail "2 $API_URL/health did not return 200"
printf '%s' "$health" | python3 -I -c 'import json,sys; assert json.load(sys.stdin)["agents"] == "ready"' \
  || fail "2 /health agents are not ready: $health"
pass "2 /health is 200 with agents ready"

# 3. CORS preflight: allowed from the web origin, refused from anywhere else
preflight() {
  curl -sS --max-time 20 -o /dev/null -D - -X OPTIONS "$API_URL/matches/random" \
    -H "Origin: $1" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: content-type" \
    | tr -d '\r' | grep -i '^access-control-allow-origin:' | head -n1 | cut -d' ' -f2-
}
allowed="$(preflight "$WEB_URL")"
[ "$allowed" = "$WEB_URL" ] || fail "3 preflight from $WEB_URL was not allowed (got '${allowed:-no header}')"
refused="$(preflight "https://example.com")"
[ -z "$refused" ] || fail "3 preflight from https://example.com was allowed (got '$refused')"
pass "3 CORS allows $WEB_URL and refuses https://example.com"

# 4. a match streams: status and an event within 30 s, then the stream closes
match_id="$(curl -fsS --max-time 30 -X POST "$API_URL/matches/random" -H 'Content-Type: application/json' -d '{}' \
  | python3 -I -c 'import json,sys; print(json.load(sys.stdin)["match_id"])')" || fail "4 POST /matches/random failed"
seen="$(curl -sS -N --max-time 30 "$API_URL/matches/$match_id/stream?speed=6" 2>/dev/null \
  | awk '/^event: status/ {s=1} /^event: event/ {e=1} s && e {print "both"; exit}')"
[ "$seen" = "both" ] || fail "4 stream of $match_id gave no status and event within 30 s"
pass "4 /matches/$match_id/stream delivers status and event"

# 5. archive listing
curl -fsS --max-time 30 -o /dev/null "$API_URL/matches" || fail "5 GET /matches did not return 200"
pass "5 GET /matches is 200"
