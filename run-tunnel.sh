#!/usr/bin/env bash
# Free Cloudflare quick tunnel (no account). URL changes every restart; current URL in logs/tunnel-url.txt
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"; mkdir -p logs
echo $$ > logs/tunnel-supervisor.pid
while true; do
  : > logs/tunnel.log
  /workspace/tools/cloudflared tunnel --no-autoupdate --url http://localhost:${PORT:-8090} >> logs/tunnel.log 2>&1 &
  CPID=$!
  for i in $(seq 1 60); do
    U=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' logs/tunnel.log | head -1)
    [ -n "$U" ] && { echo "$U" > logs/tunnel-url.txt; echo "$(date) $U" >> logs/tunnel-history.log; break; }
    sleep 1
  done
  wait $CPID
  sleep 5
done
