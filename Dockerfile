# Q1 part 2 — MULTI-STAGE build. Identical runtime behaviour to Dockerfile.naive.
#
# Stage 1 (builder) does everything that needs tooling or source data:
#   - installs the compiler toolchain
#   - resolves and installs all Python deps into an isolated venv
#   - generates the 1,000-row dataset and trains the TF-IDF + MultinomialNB pipeline
#
# Stage 2 (runtime) starts from a clean slim base and copies in exactly two things:
#   - the finished venv
#   - the 16 KB model.joblib
#
# Left behind in the builder, and therefore absent from the shipped image:
#   build-essential (gcc/g++/make), apt package lists, pip's HTTP + wheel cache,
#   spam_dataset.csv, generate_dataset.py, train.py.

# ---------- stage 1: builder ----------
FROM python:3.11-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Dataset + training happen here. Neither the CSV nor the scripts reach stage 2.
COPY generate_dataset.py train.py ./
RUN python generate_dataset.py && python train.py

# ---------- stage 2: runtime ----------
FROM python:3.11-slim

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY --from=builder /build/model.joblib ./model.joblib
COPY app/ ./app/

USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
