#!/usr/bin/env bash
# Q4: probe /healthz every 0.2s during a rollout, count failed requests.
# Usage: ./rollout_probe.sh <logfile> <rollout command...>
set -u
LOG=$1; shift
IP=$(minikube ip)
WINDOW=${WINDOW:-75}
: > "$LOG"
(
  end=$((SECONDS + WINDOW))
  while [ $SECONDS -lt $end ]; do
    resp=$(curl -s --max-time 2 -w ' HTTP=%{http_code}' "http://$IP:30080/healthz")
    echo "$(date -u +%H:%M:%S.%3N) $resp"
    sleep 0.2
  done
) >> "$LOG" 2>&1 &
PROBE=$!
sleep 3
echo ">>> $*"
"$@"
kubectl rollout status deployment/spam-api --timeout=180s
echo "waiting for the ${WINDOW}s probe window to close..."
wait "$PROBE"
echo
echo "probes sent       : $(wc -l < "$LOG")"
echo "HTTP 200          : $(grep -c 'HTTP=200' "$LOG")"
echo "failures (non-200): $(grep -vc 'HTTP=200' "$LOG")"
grep -o '"version":"v[0-9]*"' "$LOG" | sort | uniq -c
grep -v 'HTTP=200' "$LOG" | sed 's/^/  FAIL /'
