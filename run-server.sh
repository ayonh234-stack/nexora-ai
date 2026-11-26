#!/usr/bin/env bash
# Supervisor: keeps the Nexora AI web server running. Logs: logs/server.log
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$ROOT/logs"
cd "$ROOT"
echo $$ > "$ROOT/logs/server-supervisor.pid"
export PYTHONUNBUFFERED=1
PORT="${PORT:-8090}"
while true; do
  echo "$(date '+%Y-%m-%d %H:%M:%S %z') starting Nexora web on :$PORT" >> logs/server.log
  "$ROOT/.venv/bin/uvicorn" server:app --host 0.0.0.0 --port "$PORT" --proxy-headers --forwarded-allow-ips='*' >> logs/server.log 2>&1
  echo "$(date '+%Y-%m-%d %H:%M:%S %z') server exited ($?); restarting in 3s" >> logs/server.log
  sleep 3
done
