# AIOps Module 1 — Experiment Management & Reproducibility

**Rohan** · DA3408 AI Operations · Module 1 Assignment

Reproducible MLflow experiment tracking on MNIST and DVC data versioning with rollback.

---

## What's in here

| Path | What it is |
|---|---|
| `train.py` | Q2 — MLP on MNIST, sweeps learning rate × batch size, logs everything to MLflow |
| `build_index.py` | Q3 — walks the image folder and writes the versioned CSV index |
| `data/file_index.csv.dvc` | Q3 — DVC pointer file (holds the md5; the CSV itself is not in Git) |
| `requirements.txt` | pinned dependencies |
| `.dvc/config` | DVC remote configuration (credentials live in the gitignored `config.local`) |
| `environment.yml` | conda/mamba environment spec (for the Q4 reproducibility protocol) |
| `report.pdf` | the written answers for Q1–Q4 |

Git tags mark the two dataset versions: **`v1.0`** (1800 rows) and **`v2.0`** (2800 rows).

---

## Setup

Tested on Ubuntu 25.10 (ARM, UTM VM) with Python 3.14.

```bash
git clone https://github.com/Ronyy33/aiops-module1.git
cd aiops-module1

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Q2 — Reproducing the MLflow experiments

**1. Start the tracking server.** Leave it running in its own terminal:

```bash
mlflow server --backend-store-uri sqlite:///mlflow.db \
    --default-artifact-root ./mlruns --host 0.0.0.0 --port 5000
```

**2. Run the sweep.** In a second terminal (activate the venv again — venvs are per-shell):

```bash
source .venv/bin/activate
python train.py
```

This runs six experiments: learning rate ∈ {0.0001, 0.001, 0.01} crossed with batch size
∈ {64, 256}, everything else fixed (one hidden layer of 100 units, 20 epochs, seed 42,
16,000 train / 4,000 validation split of MNIST-784). MNIST downloads from OpenML on the
first run (~15 MB). Total runtime is about 60 seconds.

**3. View the results** at http://localhost:5000 → experiment `mnist-mlp-classifier`.
Select all six runs → **Compare**.

### How the logging is structured

The starter script logged one number per metric per run. This version logs **per epoch**:

```python
for epoch in range(1, max_iter + 1):
    model.partial_fit(X_train, y_train, classes=CLASSES)
    mlflow.log_metric("train_loss",   train_loss, step=epoch)
    mlflow.log_metric("val_accuracy", val_acc,    step=epoch)
```

The `step=epoch` argument is what makes the overfitting analysis possible. With a single
value per run you have two endpoints and no trend; with 20 you can see `train_loss` still
falling while `val_accuracy` has gone flat. That's the divergence discussed in the report.

`MLPClassifier` is driven with `max_iter=1` and `warm_start=True` so the epoch loop is
controlled manually rather than hidden inside one `.fit()` call.

**Expected result:** best run is `mlp-run-6` (lr=0.01, batch_size=256) at
`val_accuracy` = 0.9708. Seed 42 is fixed throughout, so these numbers should reproduce exactly.

---

## Q3 — Reproducing the DVC versioning and rollback

### Getting the data

```bash
mkdir -p data data/raw
dvc get https://github.com/iterative/dataset-registry tutorials/versioning/data.zip
dvc get https://github.com/iterative/dataset-registry tutorials/versioning/new-labels.zip
mv data.zip new-labels.zip data/
unzip -q data/data.zip -d data/raw          # 1800 images
```

### Building the index

```bash
python build_index.py data/raw
```

Prints the row count, the line count, and the md5. For v1 that's **1800 rows / 1801 lines /
md5 `3367084a395f40c99bba930684e2d51a`**. Output is sorted and deterministic, so the same
input always produces a byte-identical file — which is what makes the rollback check
meaningful.

### Creating v2

```bash
unzip -q data/new-labels.zip -d data/raw    # overlays 1000 more training images
python build_index.py data/raw              # 2800 rows / 2801 lines
dvc add data/file_index.csv
git commit -am "v2"
git tag -a v2.0 -m "data v2.0, 2800 rows"
dvc push
```

> **On the row count:** the brief says v2 "should 2801". This is 2800 data rows in a
> 2801-line file (1800 + 1000 new training images, plus one header line), consistent with
> the brief describing v1 as "1800 rows + a header line" — a 1801-line file.

### Rolling back

```bash
git checkout v1.0     # restores the .dvc pointer only
dvc checkout          # restores the actual CSV from the cache
wc -l < data/file_index.csv      # 1801
md5sum data/file_index.csv       # 3367084a395f40c99bba930684e2d51a
```

Two commands because they do different jobs. `git checkout` swaps the small `.dvc` pointer
file containing an md5; the CSV itself was never in Git. `dvc checkout` reads that md5 and
restores the matching blob from `.dvc/cache`. On a fresh clone with an empty cache, use
`dvc pull` first to fetch it from the remote.

Return to the latest state with `git checkout main && dvc checkout`.

### The remote

Configured as an SSH remote (`.dvc/config`). Credentials are in `.dvc/config.local`, which
is gitignored — the remote's location is shared, the keys are not.

```bash
dvc remote list          # see configured remotes
dvc status -c            # compare local cache against the remote
```

---

## Notes

- `.venv/`, `mlruns/`, `mlflow.db`, `data/raw/` and the zips are gitignored. No image files
  or datasets are committed — that separation is the point of Q3.
- Everything is seeded with 42. Re-running should give identical numbers.
- MLflow 3.x stores runs in `mlflow.db` (SQLite) rather than a plain `mlruns/` folder.

---

## Q4 — The partner reproducibility drill

I was **Partner B**. Partner A shared only a repository link, and I attempted to reproduce
her result using nothing but `git clone`, `git checkout <commit>`, `dvc checkout`,
`mamba env create -f environment.yml`, and rerunning the script.

**Outcome: the metric reproduced, but only after two workarounds.**

| | Partner A | This rerun |
|---|---|---|
| accuracy | ≈ 0.81 | 0.809000 |
| f1_macro | ≈ 0.80 | 0.804191 |
| dataset md5 | `7396020f8c1ab9425f2814ad058fa8d0` | identical |

Verified as MATCHED within a stated tolerance of 0.01 absolute. The note is logged as a tag
on the reproduction run itself:

```python
client.set_tag(run_id, "reproduction_note", "...")
client.set_tag(run_id, "metric_match", "PASS")
```

### What blocked it

**`dvc pull` failed** — the remote pointed at a VirtualBox NAT address, which is unreachable
from any other machine. NAT allows outbound connections but not inbound. Confirmed with both
ping and a direct check on port 22, with my own connectivity verified separately. Resolved
only after Partner A switched her VM to bridged networking and re-pushed the config, plus a
local `dvc remote modify --local ssh-remote user vboxuser` override.

**`environment.yml` didn't exist** — the repo shipped `q4/python_env.yaml`, which is MLflow
Projects format and cannot be read by mamba. I reconstructed an equivalent from its package
list.

Full detail, including a third finding about a missing `git_commit` tag and a non-defaulted
`--seed` argument, is in `report.pdf`.

### Applying the same lesson here

If you're reproducing **this** repo rather than Partner A's, note that the DVC remote in
`.dvc/config` is an SSH host on my own network and won't be reachable from elsewhere. The
Q3 dataset can be rebuilt from scratch with the `dvc get` commands above — the CSV is
regenerated deterministically by `build_index.py`, so you'll get the same md5 without needing
my remote at all.
