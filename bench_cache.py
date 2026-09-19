"""
Q2 evidence: measure cache MISS vs cache HIT against the running API.

Usage:
    python3 bench_cache.py                    # defaults to http://localhost:8000
    python3 bench_cache.py http://localhost:8000 200

Each iteration sends the SAME text twice: the first call is a guaranteed miss
(unique text), the second is a guaranteed hit. Reports the server-side work time
(elapsed_ms, from the response body) and the full round-trip wall time.
"""
import statistics
import sys
import time

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 200

h = requests.get(f"{BASE}/healthz", timeout=5)
print(f"healthz -> {h.status_code} {h.json()}\n")
if not h.json().get("cache"):
    print("WARNING: API reports cache=False — Redis is not connected.\n")

# correctness check on both classes, both paths
for text, expect in [
    ("WIN a FREE iPhone now! Click here: bit.ly/xyz123", "spam"),
    ("Hey, are we still meeting for lunch on Friday?", "ham"),
]:
    a = requests.post(f"{BASE}/predict", json={"text": text}, timeout=5)
    b = requests.post(f"{BASE}/predict", json={"text": text}, timeout=5)
    print(f"  {a.json()['label']:<5} expected {expect:<5} "
          f"| 1st X-Cache={a.headers.get('X-Cache')} 2nd X-Cache={b.headers.get('X-Cache')}")
print()

miss_server, hit_server, miss_wall, hit_wall = [], [], [], []
stamp = int(time.time())

for i in range(N):
    text = f"URGENT: Your account will be suspended. Verify at bit.ly/run{stamp}-{i}"

    t0 = time.perf_counter()
    r1 = requests.post(f"{BASE}/predict", json={"text": text}, timeout=5)
    miss_wall.append((time.perf_counter() - t0) * 1000)
    miss_server.append(r1.json()["elapsed_ms"])

    t0 = time.perf_counter()
    r2 = requests.post(f"{BASE}/predict", json={"text": text}, timeout=5)
    hit_wall.append((time.perf_counter() - t0) * 1000)
    hit_server.append(r2.json()["elapsed_ms"])

    assert r1.headers.get("X-Cache") == "MISS", r1.headers
    assert r2.headers.get("X-Cache") == "HIT", r2.headers
    assert r1.json()["label"] == r2.json()["label"], "cache returned a different label!"


def row(name, xs):
    return (f"  {name:<22} mean={statistics.mean(xs):7.3f} ms   "
            f"median={statistics.median(xs):7.3f} ms   "
            f"p90={sorted(xs)[int(0.9 * len(xs))]:7.3f} ms")


print(f"N = {N} identical-text pairs ({2 * N} requests total)\n")
print("SERVER-SIDE WORK (model predict vs redis lookup)")
print(row("MISS  (compute)", miss_server))
print(row("HIT   (cache)", hit_server))
print(f"  --> speedup {statistics.mean(miss_server) / statistics.mean(hit_server):.2f}x\n")
print("END-TO-END ROUND TRIP (includes HTTP overhead)")
print(row("MISS", miss_wall))
print(row("HIT", hit_wall))
print(f"  --> speedup {statistics.mean(miss_wall) / statistics.mean(hit_wall):.2f}x")
