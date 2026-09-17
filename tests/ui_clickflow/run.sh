#!/usr/bin/env bash
# Click-level test of the manual workflow: real React app (jsdom) + real studio API.
#
#   ./tests/ui_clickflow/run.sh            # full flow, 59 checks
#   PORT=8123 ./tests/ui_clickflow/run.sh  # if 8011 is taken
#
# Needs: node, npm (for jsdom + esbuild via the frontend's node_modules), and a
# python env with the studio's requirements installed. Nothing is written inside
# the repo: the data dir, bundle and scratch node_modules live in a temp dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PORT="${PORT:-8011}"
PY="${PYTHON:-python3}"
WORK="$(mktemp -d /tmp/studio-uiclick.XXXXXX)"
DATA="$WORK/data"
SRV=""

cleanup() {
  [ -n "$SRV" ] && kill "$SRV" 2>/dev/null
  rm -rf "$WORK"
}
trap cleanup EXIT

if command -v lsof >/dev/null && lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "port $PORT is busy — stop your studio or run: PORT=8123 $0"; exit 3
fi
[ -x "$ROOT/ai_studio/frontend/node_modules/.bin/esbuild" ] || {
  echo "missing ai_studio/frontend/node_modules — run: (cd ai_studio/frontend && npm ci)"; exit 3; }

echo "── jsdom + bundle"
npm i --prefix "$WORK" jsdom --silent --no-audit --no-fund >/dev/null 2>&1 || {
  echo "npm install jsdom failed (network?)"; exit 3; }
PYTHONPATH="$ROOT" "$PY" "$HERE/prep.py" "$DATA" >/dev/null || { echo "prep.py failed"; exit 3; }
( cd "$ROOT/ai_studio/frontend" && ./node_modules/.bin/esbuild src/main.tsx --bundle \
    --format=cjs --platform=node --jsx=automatic --loader:.css=empty \
    --define:process.env.NODE_ENV='"development"' --outfile="$WORK/app.cjs" >/dev/null ) || {
  echo "esbuild failed"; exit 3; }

echo "── studio API on :$PORT (data: $DATA)"
( cd "$ROOT" && PYTHONPATH="$ROOT" STUDIO_DATA_DIR="$DATA" \
    "$PY" -m uvicorn ai_studio.app:app --host 127.0.0.1 --port "$PORT" --log-level error ) \
  >"$WORK/server.log" 2>&1 &
SRV=$!
for _ in $(seq 1 40); do
  curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 || {
  echo "studio did not start:"; tail -5 "$WORK/server.log"; exit 3; }

echo "── clicking"
# run the driver from the scratch dir: ESM looks up `jsdom` from the *importing
# file's* directory (NODE_PATH only works for CJS), so it needs to sit next to
# the installed node_modules
cp "$HERE/clickflow.mjs" "$WORK/clickflow.mjs"
STUDIO="http://127.0.0.1:$PORT" APP_BUNDLE="$WORK/app.cjs" node "$WORK/clickflow.mjs"
RC=$?
[ $RC -ne 0 ] && tail -5 "$WORK/server.log"
exit $RC
