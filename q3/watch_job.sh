#!/usr/bin/env bash
# Q3 part 2 evidence: poll `kubectl get pods -o wide` every 2s while the Job runs,
# keep every snapshot, and save the snapshot with the most pods Running at once.
# Usage: q3/watch_job.sh [job-name] [snapshot-log]
set -u
JOB=${1:-shard-validator}
OUT=${2:-evidence/q3_pods_watch.txt}
PEAK_FILE=${OUT%.txt}_peak.txt
: > "$OUT"; peak=0

while :; do
  snap=$(kubectl get pods -l app="$JOB" -o wide 2>/dev/null)
  running=$(echo "$snap" | awk 'NR>1 && $3=="Running"' | wc -l)
  { echo "=== $(date -u +%T)  running=$running ==="; echo "$snap"; echo; } >> "$OUT"
  if [ "$running" -gt "$peak" ]; then
    peak=$running
    { echo "# peak snapshot at $(date -u +%T) UTC: $running pods Running concurrently"
      echo "$snap"; } > "$PEAK_FILE"
  fi
  done_=$(kubectl get job "$JOB" -o jsonpath='{.status.succeeded}' 2>/dev/null)
  echo "$(date -u +%T)  running=$running  succeeded=${done_:-0}/8  peak=$peak"
  [ "${done_:-0}" -ge 8 ] && break
  sleep 2
done

echo
echo "PEAK CONCURRENT RUNNING PODS: $peak"
cat "$PEAK_FILE"
