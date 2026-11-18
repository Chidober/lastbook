#!/bin/sh
set -eu

: "${LASTBOOK_LIBRARIES:=/data/config/libraries.json}"
if [ -f "$LASTBOOK_LIBRARIES" ]; then
  SEL="$(python3 -c 'import os,sys; sys.path.insert(0,"/app"); from docker.libraries import active_path; print(active_path() or "")')"
  if [ -n "$SEL" ]; then
    LASTBOOK_DATA="$SEL"
    echo "library: $LASTBOOK_DATA"
  fi
fi
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
export LASTBOOK_LIBRARIES
export SURVIVAL_MODEL_BASE
export MODEL_PROXY_PORT
export XDG_CONFIG_HOME
export LMSTUDIO_URL
export LMSTUDIO_TOKEN
mkdir -p "$XDG_CONFIG_HOME" "$LASTBOOK_DATA" /app/setup
# Do not create catalog.json here. An empty file counts as a library and hides a failed switch.
if [ ! -s /app/setup/manifest-v1.json ]; then
  echo "fetching setup manifest from downloads.lastbook.org…"
  if curl -fsS --connect-timeout 15 --max-time 60 \
      -o /app/setup/manifest-v1.json \
      https://downloads.lastbook.org/manifest-v1.json; then
    echo "manifest saved ($(wc -c < /app/setup/manifest-v1.json) bytes)"
  else
    echo "WARNING: could not fetch manifest-v1.json; setup downloads may be unavailable until /api/setup/state fetches it" >&2
    rm -f /app/setup/manifest-v1.json
  fi
fi

# Use the HTTP model path, not the bundled GGUF runner.
unset LASTBOOK_LOCAL_AI || true

# Apply any staged library switch (desktop app does this in main.py). Never block boot.
python3 - <<'PY' || true
import os, traceback
from pathlib import Path
try:
    from engine.setup import api as setup_api
    settings = Path(os.environ["XDG_CONFIG_HOME"]) / "Lastbook"
    data = Path(os.environ["LASTBOOK_DATA"])
    lib, note = setup_api.startup(settings, only=data)
    if note:
        print("setup: pending switch note:", note, flush=True)
    if lib:
        print("setup: library after pending:", lib, flush=True)
    setup_api.opened(settings, data, note)
    lib_dir = data / "library-data"
    n = sum(1 for p in lib_dir.rglob("*") if p.is_file()) if lib_dir.is_dir() else 0
    print(f"setup: library-data files={n}", flush=True)
except Exception:
    traceback.print_exc()
    print("setup: pending apply skipped (non-fatal)", flush=True)
PY

echo "starting model-proxy -> ${LMSTUDIO_URL} on ${SURVIVAL_MODEL_BASE}"
python3 /app/docker/model_proxy.py &
PROXY_PID=$!

# Wait until the proxy accepts TCP (upstream LM Studio may still be down).
i=0
while [ "$i" -lt 20 ]; do
  if python3 - <<PY
import os, socket, urllib.parse
base = urllib.parse.urlparse(os.environ["SURVIVAL_MODEL_BASE"])
s = socket.create_connection((base.hostname, base.port), timeout=1)
s.close()
PY
  then
    echo "model-proxy is listening"
    break
  fi
  if ! kill -0 "$PROXY_PID" 2>/dev/null; then
    echo "WARNING: model-proxy exited early (Chat may be offline). Continuing so setup/UI can still run." >&2
    break
  fi
  i=$((i + 1))
  sleep 0.25
done

LAN_ARGS=
if [ "${LASTBOOK_LAN:-0}" = "1" ]; then
  LAN_ARGS=--lan
  echo "LAN mode on: non-loopback clients need the printed ?key= link"
fi

echo "starting lastbook server port=${PORT} data=${LASTBOOK_DATA}"
# Keep proxy as child; if it dies, server keeps serving the library.
exec python3 /app/server.py --data "$LASTBOOK_DATA" --port "$PORT" $LAN_ARGS "$@"
