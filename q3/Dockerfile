# Q3 — shard-validator image.
#
# The validator is stdlib-only Python (csv, re, json), so there is no pip install
# and no compiler needed: unlike the Q1 spam API there is nothing for a builder
# stage to leave behind, and a single stage on python:3.11-slim is already minimal.
# The 8 shards are baked in, so every pod starts with its input already on disk.

FROM python:3.11-slim

RUN useradd --create-home --uid 10001 validator
WORKDIR /app

COPY validate_shard.py .
COPY shards/ ./shards/

USER validator
ENTRYPOINT ["python", "validate_shard.py"]
