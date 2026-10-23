#!/usr/bin/env bash
# Build the API image and start it with no model environment, as the platform's probe would.
# Fails if the container does not come up, /health is not 200, /openapi.json is missing a route,
# or any runtime file the installed packages read (voice rules, model config, prices, examples)
# cannot be found inside the image.
set -euo pipefail

IMAGE="${IMAGE:-matchproof-api:smoke}"
NAME="matchproof-smoke"
PORT="${PORT:-8000}"

cleanup() {
  docker logs "$NAME" 2>&1 | tail -n 40 || true
  docker rm -f "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker build -f services/api/Dockerfile -t "$IMAGE" .
docker run -d --name "$NAME" -p "$PORT:8000" "$IMAGE" >/dev/null

for _ in $(seq 1 60); do
  if curl -fsS "http://localhost:$PORT/health" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS "http://localhost:$PORT/health"
echo

curl -fsS "http://localhost:$PORT/openapi.json" | python3 -c '
import json, sys
paths = json.load(sys.stdin)["paths"]
need = ["/health", "/health/budget", "/compose", "/matches/{match_id}/audit"]
missing = [p for p in need if p not in paths]
if missing:
    sys.exit(f"openapi.json is missing {missing}")
print("openapi lists", need)
'

# The agent runtime is not started without a model, so read every runtime file directly.
docker exec "$NAME" python -c '
from agents.llm_client import load_models
from agents.narrator import load_examples
from agents.prices import load_prices
from agents.reconcile import comparatives
from intel.voice_lint import load_rules
load_models(); load_prices(); load_examples(); comparatives(); load_rules()
print("runtime files found")
'
