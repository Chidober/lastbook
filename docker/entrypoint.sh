#!/bin/sh
set -eu

: "${LASTBOOK_DATA:=/data/LastbookData}"
: "${MODEL_PROXY_PORT:=19443}"
: "${SURVIVAL_MODEL_BASE:=http://127.0.0.1:${MODEL_PROXY_PORT}}"
: "${PORT:=8890}"
: "${XDG_CONFIG_HOME:=/data/config}"

if [ -z "${LMSTUDIO_URL:-}" ]; then
  echo "LMSTUDIO_URL is required (e.g. http://192.168.1.11:1234)" >&2
  exit 1
fi
if [ -z "${LMSTUDIO_TOKEN:-}" ]; then
  echo "LMSTUDIO_TOKEN is required" >&2
  exit 1
fi
if [ -z "${SURVIVAL_MODEL:-}" ]; then
  echo "SURVIVAL_MODEL is required (exact id from LM Studio /v1/models)" >&2
  exit 1
fi

export LASTBOOK_DATA
export SURVIVAL_MODEL_BASE
export MODEL_PROXY_PORT
export XDG_CONFIG_HOME
mkdir -p "$XDG_CONFIG_HOME" "$LASTBOOK_DATA"

# Use the HTTP model path, not the bundled GGUF runner.
unset LASTBOOK_LOCAL_AI || true

# Apply any staged library switch from a previous setup download (desktop app does this in main.py).
python3 - <<'PY'
import os
from pathlib import Path
from engine.setup import api as setup_api

settings = Path(os.environ["XDG_CONFIG_HOME"]) / "Lastbook"
data = Path(os.environ["LASTBOOK_DATA"])
lib, note = setup_api.startup(settings, only=data)
if note:
    print("setup: pending switch note:", note, flush=True)
if lib:
    print("setup: library after pending:", lib, flush=True)
setup_api.opened(settings, data, note)
PY

echo "starting model-proxy -> ${LMSTUDIO_URL}"
python3 /app/docker/model_proxy.py &
PROXY_PID=$!

i=0
while [ "$i" -lt 30 ]; do
  if python3 - <<PY
import os, urllib.request
base = os.environ["SURVIVAL_MODEL_BASE"].rstrip("/")
try:
    urllib.request.urlopen(base + "/v1/models", timeout=2).read(64)
    raise SystemExit(0)
except Exception:
    raise SystemExit(1)
PY
  then
    break
  fi
  i=$((i + 1))
  sleep 0.5
done

if ! kill -0 "$PROXY_PID" 2>/dev/null; then
  echo "model-proxy exited early" >&2
  exit 1
fi

LAN_ARGS=
if [ "${LASTBOOK_LAN:-0}" = "1" ]; then
  LAN_ARGS=--lan
  echo "LAN mode on: non-loopback clients need the printed ?key= link"
fi

echo "starting lastbook server port=${PORT} data=${LASTBOOK_DATA}"
exec python3 /app/server.py --data "$LASTBOOK_DATA" --port "$PORT" $LAN_ARGS "$@"
