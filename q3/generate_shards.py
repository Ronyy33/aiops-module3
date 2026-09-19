"""Q3: generate 8 deterministic shards of user-signup records, with a seeded,
KNOWN number of deliberately invalid rows per shard (same random.seed(42)
pattern as the spam dataset). Writes shards/shard_<i>.csv plus
shards/expected_invalid.json, the ground truth the Job's results are checked against."""
import csv
import json
import random
from pathlib import Path

random.seed(42)
N_SHARDS, ROWS = 8, 250
FIELDS = ["user_id", "name", "email", "signup_date", "country"]
FIRST = ["Aarav", "Diya", "Rohan", "Sahithi", "Maya", "Kabir", "Isha", "Arjun"]
LAST = ["Sharma", "Reddy", "Iyer", "Nair", "Gupta", "Rao", "Menon", "Das"]
COUNTRIES = ["IN", "US", "SG", "DE", "JP"]
BAD_EMAILS = [
    lambda f, l: f"{f}.{l}.example.com",   # no @ at all
    lambda f, l: f"{f}@@example.com",      # double @
    lambda f, l: f"{f}.{l}@example",       # no top-level domain
    lambda f, l: "@example.com",           # empty local part
    lambda f, l: f"{f} {l}@example.com",   # whitespace
]

out = Path("shards")
out.mkdir(exist_ok=True)
expected = {}

for s in range(N_SHARDS):
    n_invalid = random.randint(5, 25)
    bad_rows = set(random.sample(range(ROWS), n_invalid))
    counts = {"missing_field": 0, "bad_email": 0}
    rows = []
    for r in range(ROWS):
        f, l = random.choice(FIRST), random.choice(LAST)
        row = {
            "user_id": f"u{s}{r:04d}",
            "name": f"{f} {l}",
            "email": f"{f.lower()}.{l.lower()}{r}@example.com",
            "signup_date": f"2026-{random.randint(1, 9):02d}-{random.randint(1, 28):02d}",
            "country": random.choice(COUNTRIES),
        }
        if r in bad_rows:
            if random.random() < 0.5:
                row[random.choice(FIELDS[1:])] = ""          # blank a required field
                counts["missing_field"] += 1
            else:
                row["email"] = random.choice(BAD_EMAILS)(f.lower(), l.lower())
                counts["bad_email"] += 1
        rows.append(row)

    with open(out / f"shard_{s}.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    expected[s] = {"rows": ROWS, "invalid": n_invalid, **counts}
    print(f"shard_{s}.csv  rows={ROWS}  invalid={n_invalid:2d}  "
          f"(missing_field={counts['missing_field']}, bad_email={counts['bad_email']})")

(out / "expected_invalid.json").write_text(json.dumps(expected, indent=2))
print(f"total invalid across shards: {sum(v['invalid'] for v in expected.values())}")
