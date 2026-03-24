import os
from typing import Dict

import redis
from fastapi import FastAPI
from sqlalchemy import create_engine, text

app = FastAPI(title="InternIQ API", version="0.1.0")

DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "")

engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
redis_client = redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None


@app.get("/")
def root() -> Dict[str, str]:
    return {"service": "api", "status": "running"}


@app.get("/health")
def health() -> Dict[str, object]:
    checks: Dict[str, str] = {}

    if engine is None:
        checks["postgres"] = "missing DATABASE_URL"
    else:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
        except Exception as exc:
            checks["postgres"] = f"error: {exc.__class__.__name__}"

    if redis_client is None:
        checks["redis"] = "missing REDIS_URL"
    else:
        try:
            redis_client.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"error: {exc.__class__.__name__}"

    status = "ok" if all(value == "ok" for value in checks.values()) else "degraded"
    return {"status": status, "checks": checks}
