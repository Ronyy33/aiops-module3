"""Q3 part 3: collect each shard's invalid-row count through the Kubernetes API.

No shared volume and no extra Python packages: kubectl is already an
authenticated API client, so this calls the REST endpoints through it:
    GET /api/v1/namespaces/default/pods?labelSelector=app=<job>   (pod list + status)
    GET /api/v1/namespaces/default/pods/<pod>/log                 (each pod's output)
It parses the JSON result line each validator printed, checks it against the
generator's ground truth, and derives real concurrency from each container's
startedAt/finishedAt timestamps as a second proof of the parallelism reached.

Usage: python q3/collect_results.py [job-name]
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

JOB = sys.argv[1] if len(sys.argv) > 1 else "shard-validator"
NS = "default"
EXPECTED = json.loads(Path(__file__).with_name("shards").joinpath("expected_invalid.json").read_text())


def api_get(path):
    """Raw GET against the API server, authenticated with the kubeconfig."""
    return subprocess.run(["kubectl", "get", "--raw", path],
                          check=True, capture_output=True, text=True).stdout


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def parse_result(log_text):
    """The validator prints exactly one JSON object line; return it."""
    for line in log_text.splitlines():
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError("no JSON result line in pod log")


def max_overlap(intervals):
    """Largest number of (start, end) intervals open at the same instant."""
    events = sorted([(s, 1) for s, _ in intervals] + [(e, -1) for _, e in intervals],
                    key=lambda ev: (ev[0], ev[1]))   # ends before starts on ties
    cur = best = 0
    for _, delta in events:
        cur += delta
        best = max(best, cur)
    return best


def main():
    pods_path = f"/api/v1/namespaces/{NS}/pods?labelSelector=app%3D{JOB}"
    print(f"GET {pods_path}")
    pods = json.loads(api_get(pods_path))["items"]

    results, intervals, failed = {}, [], 0
    for p in pods:
        phase = p["status"]["phase"]
        if phase != "Succeeded":
            failed += phase == "Failed"
            continue
        name = p["metadata"]["name"]
        r = parse_result(api_get(f"/api/v1/namespaces/{NS}/pods/{name}/log"))
        results[r["shard"]] = r
        term = p["status"]["containerStatuses"][0]["state"]["terminated"]
        intervals.append((ts(term["startedAt"]), ts(term["finishedAt"])))
    print(f"GET /api/v1/namespaces/{NS}/pods/<pod>/log   x{len(results)}\n")

    print(f"{'shard':>5}  {'pod':<24} {'node':<13} {'rows':>4} {'invalid':>7} "
          f"{'expected':>8}  {'missing':>7} {'bad_email':>9}  check")
    all_ok = True
    for shard in sorted(results):
        r, e = results[shard], EXPECTED[str(shard)]
        ok = (r["invalid"], r["missing_field"], r["bad_email"]) == \
             (e["invalid"], e["missing_field"], e["bad_email"])
        all_ok &= ok
        print(f"{shard:>5}  {r['pod']:<24} {r['node']:<13} {r['rows']:>4} {r['invalid']:>7} "
              f"{e['invalid']:>8}  {r['missing_field']:>7} {r['bad_email']:>9}  "
              f"{'OK' if ok else 'MISMATCH'}")

    print()
    print(f"shards collected : {len(results)}/8   (failed pods retried: {failed})")
    print(f"total invalid    : {sum(r['invalid'] for r in results.values())}"
          f"   (expected {sum(e['invalid'] for e in EXPECTED.values())})")
    print("per-node pods    : " + ", ".join(
        f"{n}={sum(r['node'] == n for r in results.values())}"
        for n in sorted({r['node'] for r in results.values()})))
    print(f"max concurrent   : {max_overlap(intervals)} pods "
          f"(from container startedAt/finishedAt in pod status)")
    print("RESULT: all shard counts match ground truth" if all_ok and len(results) == 8
          else "RESULT: MISMATCH or missing shards")


if __name__ == "__main__":
    main()
