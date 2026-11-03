#!/usr/bin/env bash
# ZKP-CerebraChain V2: non-destructive local launcher and source archiver.
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
LEGACY="${CEREBRACHAIN_LEGACY_ROOT:-$HOME/hackethon projects/ZKP Phaltan/mypro/ZKP-CerebraChain-Step1-Backend/zkp-cerebrachain}"
PY="${CEREBRACHAIN_PYTHON:-$LEGACY/.venv/bin/python}"
DEPS="${CEREBRACHAIN_PY_DEPS:-$HOME/.local/share/cerebrachain-v2/python-deps}"
STATE="$HOME/.local/state/cerebrachain-v2"
API_ENV="$ROOT/services/api/.env"
FRONTEND="$ROOT/apps/web"
mkdir -p "$STATE"
chmod 700 "$STATE"
umask 077

check_port() {
  python3 - "$1" <<'PY'
import socket, sys
try:
    with socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=0.5):
        sys.exit(0)
except OSError:
    sys.exit(1)
PY
}

check_http() {
  python3 - "$1" <<'PY'
import sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1], timeout=2) as r:
        sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
PY
}

check_json_rpc() {
  python3 - "$1" <<'PY'
import json
import sys
import urllib.request

request = urllib.request.Request(
    sys.argv[1],
    data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}).encode(),
    headers={"Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(request, timeout=2) as response:
        payload = json.loads(response.read().decode())
    sys.exit(0 if isinstance(payload, dict) and isinstance(payload.get("result"), str) else 1)
except Exception:
    sys.exit(1)
PY
}

listening_pids() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u || true
  fi
}

listener_matches() {
  local port="$1" expected="$2" pid args
  while IFS= read -r pid; do
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    args="$(ps -p "$pid" -o args= 2>/dev/null || true)"
    [[ "$args" == *"$expected"* ]] && return 0
  done < <(listening_pids "$port")
  return 1
}

api_listener_matches_source() {
  local pid args cwd
  while IFS= read -r pid; do
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    args="$(ps -p "$pid" -o args= 2>/dev/null || true)"
    cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
    [[ "$args" == *uvicorn*app.main:app* && "$cwd" == "$ROOT" ]] && return 0
  done < <(listening_pids 8002)
  return 1
}

web_listener_matches_source() {
  local pid args cwd
  while IFS= read -r pid; do
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    args="$(ps -p "$pid" -o args= 2>/dev/null || true)"
    cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
    [[ "$args" == *vite* && "$args" == *5175* && "$cwd" == "$FRONTEND" ]] && return 0
  done < <(listening_pids 5175)
  return 1
}

api_status() {
  if ! check_port 8002; then
    printf 'OFFLINE'
  elif api_listener_matches_source && check_http 'http://127.0.0.1:8002/openapi.json'; then
    printf 'EXPECTED_SOURCE_HTTP_READY'
  elif api_listener_matches_source; then
    printf 'EXPECTED_SOURCE_HTTP_UNHEALTHY'
  else
    printf 'PORT_OCCUPIED_UNVERIFIED'
  fi
}

web_status() {
  if ! check_port 5175; then
    printf 'OFFLINE'
  elif web_listener_matches_source && check_http 'http://127.0.0.1:5175/'; then
    printf 'EXPECTED_SOURCE_HTTP_READY'
  elif web_listener_matches_source; then
    printf 'EXPECTED_SOURCE_HTTP_UNHEALTHY'
  else
    printf 'PORT_OCCUPIED_UNVERIFIED'
  fi
}

start_detached() {
  local log_file="$1"
  shift
  # ``nohup`` alone can still leave a child in its caller's process session.
  # A separate session keeps launcher-owned services alive when the invoking
  # terminal closes, while the existing PID/source-path checks continue to
  # guard every later stop or restart action.  Keep the portable nohup fallback
  # for hosts without util-linux ``setsid``.
  if command -v setsid >/dev/null 2>&1; then
    setsid "$@" </dev/null >>"$log_file" 2>&1 &
  else
    nohup "$@" </dev/null >>"$log_file" 2>&1 &
  fi
  echo "$!"
}

tcp_component_status() {
  local port="$1" expected_process="${2:-}"
  if ! check_port "$port"; then
    printf 'OFFLINE'
  elif [[ -n "$expected_process" ]] && listener_matches "$port" "$expected_process"; then
    printf 'TCP_OPEN_PROCESS_MATCHED_UNVERIFIED'
  else
    printf 'TCP_OPEN_UNVERIFIED'
  fi
}

wait_http() {
  local url="$1"
  for _ in $(seq 1 20); do
    if check_http "$url"; then return 0; fi
    sleep 1
  done
  return 1
}

print_status() {
  printf '\n%-28s %-8s %s\n' 'SERVICE' 'PORT' 'STATUS (NOT TRAINING HEALTH)'
  printf '%-28s %-8s %s\n' 'PostgreSQL' '5432' "$(tcp_component_status 5432)"
  printf '%-28s %-8s %s\n' 'V2 FastAPI' '8002' "$(api_status)"
  printf '%-28s %-8s %s\n' 'React Frontend' '5175' "$(web_status)"
  if ! check_port 8545; then
    hardhat_state='OFFLINE'
  elif check_json_rpc 'http://127.0.0.1:8545'; then
    hardhat_state='JSON_RPC_RESPONDS_UNVERIFIED'
  else
    hardhat_state='TCP_OPEN_UNVERIFIED'
  fi
  printf '%-28s %-8s %s\n' 'Hardhat Blockchain' '8545' "$hardhat_state"
  printf '\nV2 frontend: http://127.0.0.1:5175\n'
  printf 'Federation:  http://127.0.0.1:5175/app/federation\n'
  printf 'Blockchain:  http://127.0.0.1:5175/app/blockchain\n'
  printf '\nFederation status is served by the V2 custom coordinator dashboard.\n'
  printf 'Legacy Flower processes are intentionally not started or monitored by this launcher.\n'
}

start_api() {
  [[ -f "$API_ENV" ]] || { echo "ERROR: Missing $API_ENV (private configuration)." >&2; return 1; }
  [[ -x "$PY" ]] || { echo "ERROR: Missing Python virtual environment: $PY" >&2; return 1; }
  if check_port 8002; then
    echo "ERROR: Port :8002 is occupied ($(api_status)); refusing to start a duplicate API." >&2
    return 1
  fi

  echo 'Starting V2 FastAPI on :8002 ...'
  (
    cd "$ROOT"
    export PYTHONPATH="$DEPS:$ROOT/services/api:$ROOT/packages/ml-adapter/src${PYTHONPATH:+:$PYTHONPATH}"
    set -a
    # shellcheck disable=SC1090
    source "$API_ENV"
    set +a
    start_detached "$STATE/api.log" "$PY" -m uvicorn app.main:app --app-dir "$ROOT/services/api" --host 127.0.0.1 --port 8002 \
      > "$STATE/api.pid"
  )
  if wait_http 'http://127.0.0.1:8002/openapi.json' && api_listener_matches_source; then
    echo 'V2 API: EXPECTED_SOURCE_HTTP_READY'
  else
    echo "ERROR: API did not become ready from this source. Inspect $STATE/api.log" >&2
    return 1
  fi
}

start_web() {
  [[ -x "$FRONTEND/node_modules/.bin/vite" ]] || {
    echo "ERROR: Vite dependencies missing. Run: cd '$FRONTEND' && npm ci" >&2; return 1;
  }
  if check_port 5175; then
    echo "ERROR: Port :5175 is occupied ($(web_status)); refusing to start a duplicate frontend." >&2
    return 1
  fi

  echo 'Starting React/Vite frontend on :5175 ...'
  (
    cd "$FRONTEND"
    start_detached "$STATE/web.log" "$FRONTEND/node_modules/.bin/vite" --host 127.0.0.1 --port 5175 --strictPort \
      > "$STATE/web.pid"
  )
  if wait_http 'http://127.0.0.1:5175/' && web_listener_matches_source; then
    echo 'Frontend: EXPECTED_SOURCE_HTTP_READY'
  else
    echo "ERROR: Frontend did not become ready from this source. Inspect $STATE/web.log" >&2
    return 1
  fi
}

start_api_if_needed() {
  if ! check_port 8002; then
    start_api
  elif [[ "$(api_status)" == 'EXPECTED_SOURCE_HTTP_READY' ]]; then
    echo 'V2 API already running from this source — leaving it untouched.'
  else
    echo "ERROR: V2 API port conflict or unhealthy process ($(api_status))." >&2
    echo 'Use ./cerebrachain.sh restart-api only for a launcher-owned backend.' >&2
    return 1
  fi
}

start_web_if_needed() {
  if ! check_port 5175; then
    start_web
  elif [[ "$(web_status)" == 'EXPECTED_SOURCE_HTTP_READY' ]]; then
    echo 'Frontend already running from this source — leaving it untouched.'
  else
    echo "ERROR: Frontend port conflict or unhealthy process ($(web_status))." >&2
    echo 'Use ./cerebrachain.sh restart-web only for a launcher-owned frontend.' >&2
    return 1
  fi
}

start_services() {
  [[ -f "$ROOT/services/api/app/main.py" && -f "$FRONTEND/package.json" ]] || {
    echo 'ERROR: Place cerebrachain.sh in the V2 repository root (next to apps/ and services/).' >&2; exit 1;
  }
  echo '=== ZKP-CerebraChain V2 Safe Start ==='
  if ! check_port 5432; then
    echo 'WARNING: PostgreSQL :5432 is offline. If needed, start it separately: sudo systemctl start postgresql'
  fi
  start_api_if_needed
  start_web_if_needed

  if ! check_port 8545; then
    echo 'WARNING: Hardhat :8545 offline. NOT restarting: an un-restored Hardhat chain loses historical on-chain anchors.'
  fi
  print_status
}

restart_api() {
  local pidfile="$STATE/api.pid" pid args cwd
  [[ -f "$pidfile" ]] || {
    echo 'ERROR: No launcher-owned API PID file exists; refusing to stop port :8002.' >&2
    exit 1
  }
  pid="$(cat "$pidfile")"
  [[ "$pid" =~ ^[0-9]+$ ]] || {
    echo 'ERROR: API PID file is invalid; refusing to stop port :8002.' >&2
    exit 1
  }
  kill -0 "$pid" 2>/dev/null || {
    rm -f "$pidfile"
    start_api
    return
  }
  args="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
  if [[ "$args" != *uvicorn*app.main:app* || "$cwd" != "$ROOT" ]]; then
    echo "ERROR: PID file does not identify this launcher's V2 API; refusing to stop it." >&2
    exit 1
  fi
  echo "Stopping launcher-owned V2 API (PID $pid) ..."
  kill -TERM "$pid"
  for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo 'ERROR: API did not exit after SIGTERM; refusing to escalate or kill other processes.' >&2
    exit 1
  fi
  rm -f "$pidfile"
  start_api
}

restart_web() {
  local pidfile="$STATE/web.pid" pid args cwd
  [[ -f "$pidfile" ]] || {
    echo 'ERROR: No launcher-owned frontend PID file exists; refusing to stop port :5175.' >&2
    exit 1
  }
  pid="$(cat "$pidfile")"
  [[ "$pid" =~ ^[0-9]+$ ]] || {
    echo 'ERROR: Frontend PID file is invalid; refusing to stop port :5175.' >&2
    exit 1
  }
  kill -0 "$pid" 2>/dev/null || {
    rm -f "$pidfile"
    start_web
    return
  }
  args="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
  if [[ "$args" != *vite* || "$args" != *5175* || "$cwd" != "$FRONTEND" ]]; then
    echo "ERROR: PID file does not identify this launcher's Vite frontend; refusing to stop it." >&2
    exit 1
  fi
  echo "Stopping launcher-owned Vite frontend (PID $pid) ..."
  kill -TERM "$pid"
  for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo 'ERROR: Frontend did not exit after SIGTERM; refusing to escalate or kill other processes.' >&2
    exit 1
  fi
  rm -f "$pidfile"
  start_web
}

stop_owned() {
  echo 'Stopping only V2 services previously started by this launcher.'
  for svc in api web; do
    pidfile="$STATE/$svc.pid"
    [[ -f "$pidfile" ]] || continue
    pid="$(cat "$pidfile")"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      args="$(ps -p "$pid" -o args= 2>/dev/null || true)"
      cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
      case "$svc:$args" in
        api:*uvicorn*app.main:app*)
          [[ "$cwd" == "$ROOT" ]] && kill "$pid" && echo "Stopped $svc (PID $pid)." || echo "Skipping API PID $pid (source path does not match launcher).";;
        web:*vite*5175*)
          [[ "$cwd" == "$FRONTEND" ]] && kill "$pid" && echo "Stopped $svc (PID $pid)." || echo "Skipping web PID $pid (source path does not match launcher).";;
        *) echo "Skipping $svc PID $pid (process does not match launcher service).";;
      esac
    fi
    rm -f "$pidfile"
  done
  echo 'PostgreSQL, Hardhat and legacy Flower were not touched.'
}

make_zip() {
  [[ -d "$ROOT/.git" ]] || { echo 'ERROR: .git repository required for a safe tracked-source archive.' >&2; exit 1; }
  # Fail closed if a protected file accidentally reached the commit.
  python3 - "$ROOT" <<'PY'
import subprocess, sys
from pathlib import PurePosixPath
root=sys.argv[1]
paths=subprocess.check_output(['git','-C',root,'ls-tree','-r','--name-only','-z','HEAD']).split(b'\0')
for raw in paths:
    if not raw: continue
    p=raw.decode('utf-8','replace')
    name=PurePosixPath(p).name.lower()
    suffix=PurePosixPath(p).suffix.lower()
    if ((name.startswith('.env') and name not in ('.env.example','.env.sample'))
        or suffix in ('.pth','.pt','.nii','.gz','.sqlite','.db','.pem','.key','.p12','.pfx','.dump')
        or name in ('id_rsa','id_ed25519')
        or '/private/' in '/' + p + '/'):
        raise SystemExit('REFUSING ARCHIVE: potentially private tracked file: '+p)
print('Tracked-file safety preflight: OK')
PY
  local date_tag out
  date_tag="$(date +%Y-%m-%d_%H%M%S)"
  out="$HOME/Downloads/ZKP-CerebraChain-V2-source-$date_tag.zip"
  git -C "$ROOT" archive --format=zip --prefix='cerebrachain-v2/' -o "$out" HEAD
  # Include local launcher even if not committed yet.
  python3 - "$out" "$ROOT/cerebrachain.sh" <<'PY'
import sys,zipfile
archive,launcher=sys.argv[1:]
with zipfile.ZipFile(archive,'a',compression=zipfile.ZIP_DEFLATED) as z:
    if 'cerebrachain-v2/cerebrachain.sh' not in z.namelist():
        z.write(launcher, 'cerebrachain-v2/cerebrachain.sh')
PY
  chmod 600 "$out"
  echo "SAFE SOURCE ZIP CREATED: $out"
  echo 'Includes committed Git source + launcher, not private .env, checkpoint, DB, patient files or untracked images.'
  echo 'A different computer needs the external legacy runtime/assets and private env configured separately.'
}

case "${1:-start}" in
  start) start_services ;;
  start-api) start_api_if_needed ;;
  start-web) start_web_if_needed ;;
  status) print_status ;;
  stop) stop_owned ;;
  restart-api) restart_api ;;
  restart-web) restart_web ;;
  zip) make_zip ;;
  *) echo 'Usage: ./cerebrachain.sh [start|start-api|start-web|status|stop|restart-api|restart-web|zip]' >&2; exit 2 ;;
esac
