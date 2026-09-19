"""Q3: validate ONE shard. Which one comes from JOB_COMPLETION_INDEX, which the
Job controller injects into every pod of an Indexed Job (0..completions-1).
Prints a single JSON result line to stdout -> read back via the Kubernetes API.

Local test:  python validate_shard.py 3
"""
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
REQUIRED = ["user_id", "name", "email", "signup_date", "country"]

idx = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ["JOB_COMPLETION_INDEX"])
path = f"shards/shard_{idx}.csv"
started = datetime.now(timezone.utc).isoformat(timespec="seconds")
t0 = time.perf_counter()

rows = missing = bad_email = 0
with open(path, newline="") as fh:
    for row in csv.DictReader(fh):
        rows += 1
        if any(not (row.get(f) or "").strip() for f in REQUIRED):
            missing += 1                       # a blank required field, email included
        elif not EMAIL_RE.match(row["email"].strip()):
            bad_email += 1

print(json.dumps({
    "shard": idx,
    "file": path,
    "rows": rows,
    "invalid": missing + bad_email,
    "missing_field": missing,
    "bad_email": bad_email,
    "pod": os.getenv("POD_NAME", "local"),     # Downward API: metadata.name
    "node": os.getenv("NODE_NAME", "local"),   # Downward API: spec.nodeName
    "started_at": started,
    "validate_ms": round((time.perf_counter() - t0) * 1000, 2),
}), flush=True)

# Validating 250 rows takes a few ms, so without a hold every pod would finish
# before `kubectl get pods` could ever observe it. HOLD_SECONDS only widens the
# observation window; how many pods run at once is still set by `parallelism`.
hold = float(os.getenv("HOLD_SECONDS", "0"))
if hold > 0:
    time.sleep(hold)
