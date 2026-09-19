# AIOps Module 3 — Infrastructure & Containerization

**Rohan Sirsewad · DA24B023 · DA3408 AI Operations**

One small application — a REST API that classifies a message as `spam` or `ham`
with TF-IDF + Multinomial Naive Bayes — containerized and orchestrated four ways:

| Q | What | Headline result |
|---|---|---|
| 1 | Naive vs multi-stage Docker build | 2.41 GB → 824 MB, **65.8% smaller** |
| 2 | API + Redis cache with Docker Compose | cache hit **1.56× faster** server-side over 200 pairs |
| 3 | Kubernetes Indexed Job over 8 CSV shards | **4 pods concurrently** (2 per node), all 8 counts match ground truth |
| 4 | Deployment: self-healing + rolling update | pod replaced in <12 s; rollout with **0 / 358** failed requests |

Everything is CPU-only. Built and tested on an ARM64 Ubuntu VM (UTM on Apple
Silicon) with Docker 29 and a 2-node minikube cluster.

---

## Repository layout

```
.
├── app/main.py              FastAPI service: POST /predict, GET /healthz (+ optional Redis cache)
├── generate_dataset.py      seeded 1,000-row spam/ham dataset (script from the brief)
├── train.py                 TF-IDF + MultinomialNB pipeline -> model.joblib
├── requirements.txt         runtime deps for the API image
├── Dockerfile.naive         Q1 part 1 — single stage on python:3.11
├── Dockerfile               Q1 part 2 — multi-stage, runtime on python:3.11-slim
├── docker-compose.yml       Q2 — api + cache (redis:7-alpine)
├── bench_cache.py           Q2 — cache MISS vs HIT benchmark
├── rollout_probe.sh         Q4 — probes the Service during a rollout, counts failures
├── k8s/
│   ├── deployment.yaml      Q4 — v1 Deployment (2 replicas, probes, resources)
│   ├── deployment-v2.yaml   Q4 — v2 image + preStop hook, applied for the rolling update
│   ├── service.yaml         Q4 — NodePort 30080
│   └── q3-indexed-job.yaml  Q3 — Indexed Job, completions 8, parallelism 4
├── q3/
│   ├── generate_shards.py   8 seeded shards with a known number of invalid rows each
│   ├── validate_shard.py    validates the shard named by JOB_COMPLETION_INDEX
│   ├── Dockerfile           validator image (stdlib only)
│   ├── watch_job.sh         captures `kubectl get pods -o wide` at peak concurrency
│   ├── collect_results.py   reads every pod's result through the Kubernetes API
│   └── shards/              the 8 CSVs + expected_invalid.json (ground truth)
└── evidence/                every terminal capture the write-up cites
```

`model.joblib` and `spam_dataset.csv` are not committed — the Docker build
regenerates both deterministically (seed 42).

---

## Prerequisites

- Docker (with Compose v2 — `docker compose`, not `docker-compose`)
- minikube and kubectl
- Python 3.10+ on the host, for the helper scripts

```bash
git clone https://github.com/Ronyy33/aiops-module3.git
cd aiops-module3
python3 -m venv .venv && source .venv/bin/activate
pip install requests
```

The host only needs `requests` (for `bench_cache.py`); every other helper script is
stdlib-only. The pinned ML stack in `requirements.txt` is installed *inside* the image
by the Docker build, so it never has to match the host's Python version.

> **VM users:** if the VM was suspended, check `date -u` first. A stale clock makes
> `apt-get` inside `docker build` reject Debian's repo signatures (`Not live until …`)
> and breaks TLS for minikube. See [Troubleshooting](#troubleshooting).

---

## Q1 — Single-stage vs multi-stage Docker

```bash
docker build -f Dockerfile.naive -t spam-api:naive .
docker build -f Dockerfile       -t spam-api:multi .
docker images | grep spam-api
```

Check both serve the API identically:

```bash
docker run -d --name spam-naive -p 8001:8000 spam-api:naive
docker run -d --name spam-multi -p 8002:8000 spam-api:multi
sleep 8
curl -s localhost:8002/healthz
curl -s -X POST localhost:8002/predict -H 'Content-Type: application/json' \
     -d '{"text":"WIN a FREE iPhone now! Click here: bit.ly/xyz123"}'
docker rm -f spam-naive spam-multi
```

**Results** (`evidence/q1_*.txt`)

| | naive | multi-stage |
|---|---|---|
| Image size (disk) | 2.41 GB | 824 MB (**−65.8%**) |
| Content size | 630 MB | 177 MB (−71.9%) |
| Base image | `python:3.11` — 1.62 GB | `python:3.11-slim` — 226 MB |
| `which gcc` | `/usr/bin/gcc` | absent |
| pip cache | 90 MB | none |
| apt lists | 21 MB | 244 KB |
| `/app` contents | dataset, generator, trainer, requirements, both Dockerfiles, app, model | `app/` + `model.joblib` only |

The base-image swap alone accounts for 1.39 GB of the 1.59 GB saved (88%). The rest
is what the builder stage used and never handed over: the compiler toolchain, pip's
wheel cache, apt lists, and the training data and scripts. The runtime stage copies
exactly two things across — the venv and the 16 KB model.

---

## Q2 — Docker Compose with a Redis cache

```bash
docker compose up -d --build
docker compose ps                       # both services should be "healthy"
curl -s localhost:8000/healthz          # expect "cache": true
python3 bench_cache.py http://localhost:8000 200
docker compose down                     # when finished
```

How it's wired:

- The API reaches Redis at hostname **`cache`** — the Compose service name, resolved
  by the project network's embedded DNS. No IPs anywhere.
- `depends_on: condition: service_healthy` holds the API back until Redis answers `PING`.
- Redis publishes **no host port**; only the API can reach it.
- Cache key is `spam:` + SHA-256 of the text; TTL 300 s. Every response carries an
  `X-Cache: HIT|MISS` header so the behaviour is visible per request.
- If Redis is absent or down, the API still answers correctly with caching disabled —
  the same image runs standalone in Q1 and behind Compose here.

**Results** (`evidence/q2_cache_benchmark.txt`, 200 identical-text pairs = 400 requests)

| | MISS (compute) | HIT (cache) | speedup |
|---|---|---|---|
| Server-side work, mean | 0.210 ms | 0.135 ms | **1.56×** |
| End-to-end round trip, mean | 1.406 ms | 1.077 ms | 1.31× |

Every pair asserts that the MISS and the HIT returned the same label. The gap is
small in absolute terms because this model predicts in a fraction of a millisecond;
the benchmark shows it is consistent, and the saving scales with model cost.

---

## Kubernetes setup (Q3 and Q4)

```bash
minikube start --nodes=2 --cpus=2 --memory=2048
kubectl get nodes                       # minikube + minikube-m02, both Ready
```

A 2-node cluster matches the topology Q3 asks you to assume. Locally built images
live in the host's Docker, not in minikube's nodes, so every image must be loaded
explicitly — otherwise pods sit in `ErrImagePull`:

```bash
minikube image load spam-api:multi
```

> minikube's Docker driver reports the **host's** CPU count to kubelet, so each node
> advertises 6 allocatable CPUs here even with `--cpus=2`. The 4-CPU budget Q3 assumes
> is therefore enforced by the Job's own requests and parallelism, not by the nodes.

---

## Q4 — Deployment: self-healing and rolling update

**Deploy v1**

```bash
kubectl apply -f k8s/deployment.yaml -f k8s/service.yaml
kubectl rollout status deployment/spam-api
kubectl annotate deployment spam-api kubernetes.io/change-cause="v1: initial deploy of spam-api:multi" --overwrite
curl -s http://$(minikube ip):30080/healthz
```

**Self-healing** — delete a pod and watch the ReplicaSet replace it:

```bash
kubectl delete pod $(kubectl get pods -l app=spam-api -o jsonpath='{.items[0].metadata.name}') --wait=false
kubectl get pods -l app=spam-api -o wide
kubectl describe rs -l app=spam-api | sed -n '/Events:/,$p'
```

Recorded run (`evidence/q4_self_healing.txt`): deleted `…-9wq7x`; within 2 s the
`replicaset-controller` created `…-qlwxf` (new name, new IP), `Running` but `0/1`
ready until its readinessProbe passed; `2/2` ready by 12 s.

**Rolling update to v2** — `/healthz` now also reports which pod and node served it:

```bash
docker build -t spam-api:v2 .
minikube image load spam-api:v2
./rollout_probe.sh evidence/q4_rollout_probe.log kubectl apply -f k8s/deployment-v2.yaml
kubectl rollout history deployment/spam-api
```

`rollout_probe.sh` hits the Service every 0.2 s for the whole rollout and reports
every non-200. The strategy is `maxSurge: 1, maxUnavailable: 0`.

**What the probes showed**

| Rollout | Outgoing pods had preStop? | Failed requests |
|---|---|---|
| v1 → v2 (revision 2) | no | **2 / 362** |
| v2 restart (revision 3) | yes, `sleep 5` | **0 / 358** |

The two failures were `HTTP=000` (connection refused), one at each moment a v1 pod was
retired: the process exited on SIGTERM while kube-proxy could still route to it. v2
adds a 5 s `preStop` sleep so an outgoing pod keeps serving while it is removed from
the Service's endpoints; the next rollout, whose outgoing pods were v2, dropped nothing.

> `app/main.py` in this repo is the v2 code. `deployment.yaml` pins `APP_VERSION=v1`,
> so an image built from HEAD and deployed with it reports `"version": "v1"` but also
> includes the v2 `served_by` field. The original v1 source is in the first commit.

---

## Q3 — Indexed Job: parallel data validation

A separate batch workload: 8 CSV shards of user-signup records, each seeded with a
known number of rows that have a blank required field or a malformed email.

```bash
cd q3 && python generate_shards.py && cd ..      # optional: shards are committed
docker build -t shard-validator:v1 q3/
minikube image load shard-validator:v1
kubectl apply -f k8s/q3-indexed-job.yaml && q3/watch_job.sh
python q3/collect_results.py
```

To re-run, delete the Job first — a Job's pod template is immutable:
`kubectl delete job shard-validator`.

**Design**

- `completionMode: Indexed`, `completions: 8`, `parallelism: 4`,
  `restartPolicy: Never`, `backoffLimit: 4`.
- Each pod reads `JOB_COMPLETION_INDEX` (0–7) to pick its shard.
- `requests = limits = 1 CPU`: the validator is single-threaded, so one core per pod.
  2 CPUs per node ÷ 1 CPU per pod = 2 pods per node → **4 cluster-wide**, and 8
  shards ÷ 4 = **2 waves**, the minimum possible on 4 CPUs.
- Downward API injects `metadata.name` and `spec.nodeName`, so every result records
  which pod ran on which node.
- Validating a shard takes ~1 ms, so each pod holds 20 s (`HOLD_SECONDS`) after
  printing its result purely so concurrency can be observed. It does not change how
  many pods run at once — `parallelism` does.
- Results are read through the Kubernetes API (`GET /api/v1/.../pods/<pod>/log`), not
  a shared volume: minikube's default storage-provisioner backs PVCs with **hostPath**
  on a single node and does not support multi-node clusters, so pods on the two nodes
  would write to two different disks.

**Results** (`evidence/q3_*.txt`)

- Peak snapshot: **4 pods Running at once, 2 on each node**.
- Job `Complete`, 8/8 in 46 s, `Completed Indexes: 0-7`, 0 failed.
- All 8 shard counts match `expected_invalid.json` — 130 invalid rows in total.
- Max concurrency derived independently from container start/finish timestamps: 4.

| shard | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| invalid rows | 25 | 23 | 9 | 10 | 10 | 25 | 15 | 13 |

---

## Evidence index

| File | Shows |
|---|---|
| `q1_image_sizes.txt` | naive vs multi-stage vs base image sizes |
| `q1_api_verification.txt` | both images serving `/healthz` and `/predict` |
| `q1_layer_analysis.txt` | gcc, pip cache, apt lists, `/app` contents per image |
| `q2_cache_headers.txt` | one request pair: `X-Cache: MISS` then `HIT` |
| `q2_cache_benchmark.txt` | 200-pair MISS vs HIT timing |
| `q4_pods_initial.txt` | 2 replicas on 2 nodes |
| `q4_self_healing.txt` | pod deleted and recreated, ReplicaSet events |
| `q4_rollout_probe.log` / `q4_rollout_summary.txt` | v1→v2 rollout, 2/362 failures |
| `q4_restart_probe.log` / `q4_restart_summary.txt` | re-test with preStop, 0/358 failures |
| `q4_rollout_history_final.txt` | revisions 1–3 with change-causes, ReplicaSets |
| `q3_pods_watch_peak.txt` | `kubectl get pods -o wide` at 4 concurrent pods |
| `q3_pods_watch.txt` | every 2 s snapshot across both waves |
| `q3_results.txt` | per-shard counts vs ground truth |
| `q3_job_status.txt` | Job status, completed indexes, raw log API call |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `apt-get` in `docker build`: `Not live until …` | VM clock behind after suspend | `sudo timedatectl set-ntp false && sudo date -s "<current UTC>" && sudo hwclock --systohc` |
| Pods stuck in `ErrImagePull` / `ImagePullBackOff` | image not loaded into minikube | `minikube image load <image:tag>` |
| `healthz` shows `"cache": false` under Compose | API can't reach Redis | `docker compose ps` — cache must be `healthy`; `REDIS_HOST` must be `cache` |
| Port 8000 already in use | Q1 containers still running | `docker rm -f spam-naive spam-multi` |
| Job won't re-apply | pod template is immutable | `kubectl delete job shard-validator` first |
| cluster gone after a reboot | minikube nodes are Docker containers | `minikube start` (remembers the 2-node config) |
