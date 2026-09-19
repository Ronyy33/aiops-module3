"""
Spam-detection API.

POST /predict  {"text": "..."}  -> {"label": "spam"|"ham", ...}
GET  /healthz                   -> 200 once the model is loaded

Redis caching is OPTIONAL: if REDIS_HOST is unset or unreachable, the API still
serves correct predictions with caching disabled. That is what lets the same
image run standalone in Q1 and behind Compose in Q2.
"""
import hashlib
import os
import time

import joblib
from fastapi import FastAPI, Response
from pydantic import BaseModel

APP_VERSION = os.getenv("APP_VERSION", "v1")
MODEL_PATH = os.getenv("MODEL_PATH", "model.joblib")
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))

app = FastAPI(title="spam-detection-api", version=APP_VERSION)

model = joblib.load(MODEL_PATH)
MODEL_READY = True

cache = None
if REDIS_HOST:
    try:
        import redis
        cache = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
            socket_connect_timeout=2, socket_timeout=2,
        )
        cache.ping()
        print(f"[cache] connected to redis at {REDIS_HOST}:{REDIS_PORT}, ttl={CACHE_TTL}s")
    except Exception as e:
        print(f"[cache] redis unavailable ({e}); running without cache")
        cache = None
else:
    print("[cache] REDIS_HOST not set; running without cache")


class PredictRequest(BaseModel):
    text: str


def cache_key(text: str) -> str:
    # hash so arbitrarily long / unicode input is a safe, fixed-size key
    return "spam:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@app.get("/healthz")
def healthz():
    if not MODEL_READY:
        return Response(status_code=503)
    return {"status": "ok", "version": APP_VERSION, "cache": bool(cache)}


@app.post("/predict")
def predict(req: PredictRequest, response: Response):
    key = cache_key(req.text)

    if cache is not None:
        t0 = time.perf_counter()
        try:
            hit = cache.get(key)
        except Exception:
            hit = None
        lookup_ms = (time.perf_counter() - t0) * 1000
        if hit is not None:
            response.headers["X-Cache"] = "HIT"
            return {"label": hit, "cached": True,
                    "elapsed_ms": round(lookup_ms, 3), "version": APP_VERSION}

    t0 = time.perf_counter()
    label = str(model.predict([req.text])[0])
    compute_ms = (time.perf_counter() - t0) * 1000

    if cache is not None:
        try:
            cache.setex(key, CACHE_TTL, label)
        except Exception:
            pass

    response.headers["X-Cache"] = "MISS"
    return {"label": label, "cached": False,
            "elapsed_ms": round(compute_ms, 3), "version": APP_VERSION}
