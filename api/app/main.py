import hashlib
import json
import os
from typing import Dict, List, Optional
from uuid import UUID

import redis
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text

app = FastAPI(title="InternIQ API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "")

engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
redis_client = redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None

_JOBS_CACHE_TTL = 3600
_STATS_CACHE_TTL = 3600


# Response models

class JobSummary(BaseModel):
    id: str
    company_name: str
    title: str
    location: List[str]
    is_remote: Optional[bool]
    required_grad_year: Optional[int]
    grad_year_flexible: Optional[bool]
    estimated_pay_hourly: Optional[int]
    tech_stack: List[str]
    sponsors_visa: Optional[bool]
    ai_extraction_status: str
    ai_confidence_score: Optional[float]
    source: Optional[str]
    date_posted: Optional[str]
    date_ingested: str
    url: str


class JobDetail(JobSummary):
    raw_description: Optional[str]
    date_processed: Optional[str]


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int


class JobsResponse(BaseModel):
    data: List[JobSummary]
    pagination: PaginationMeta
    cache_hit: bool


class StatsResponse(BaseModel):
    total: int
    by_source: Dict[str, int]
    by_grad_year: Dict[str, int]
    by_status: Dict[str, int]


# Helpers

def _cache_key(prefix: str, params: dict) -> str:
    """Stable cache key from sorted params — same filters always hit the same key."""
    raw = json.dumps(params, sort_keys=True)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"{prefix}:{digest}"


def _row_to_summary(row) -> dict:
    return {
        "id": str(row.id),
        "company_name": row.company_name,
        "title": row.title,
        "location": list(row.location or []),
        "is_remote": row.is_remote,
        "required_grad_year": row.required_grad_year,
        "grad_year_flexible": row.grad_year_flexible,
        "estimated_pay_hourly": row.estimated_pay_hourly,
        "tech_stack": list(row.tech_stack or []),
        "sponsors_visa": row.sponsors_visa,
        "ai_extraction_status": row.ai_extraction_status,
        "ai_confidence_score": row.ai_confidence_score,
        "source": row.source,
        "date_posted": row.date_posted.isoformat() if row.date_posted else None,
        "date_ingested": row.date_ingested.isoformat(),
        "url": row.url,
    }


def _row_to_detail(row) -> dict:
    d = _row_to_summary(row)
    d["raw_description"] = row.raw_description
    d["date_processed"] = row.date_processed.isoformat() if row.date_processed else None
    return d


# Endpoints

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


@app.get("/api/jobs", response_model=JobsResponse)
def list_jobs(
    grad_year: Optional[int] = Query(None),
    grad_year_flex: Optional[bool] = Query(None),
    min_pay: Optional[int] = Query(None),
    max_pay: Optional[int] = Query(None),
    tech_stack: Optional[str] = Query(None, description="Comma-separated; all must be present"),
    location: Optional[str] = Query(None),
    remote_only: Optional[bool] = Query(None),
    sponsors_visa: Optional[bool] = Query(None),
    source: Optional[str] = Query(None),
    sort: str = Query("date_desc", pattern="^(date_desc|pay_desc|company)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    # Capture only filter/sort/page params — exclude injected clients which aren't part of the query identity
    cache_params = {k: v for k, v in locals().items() if v is not None and k not in ("engine", "redis_client")}
    key = _cache_key("cache:jobs", cache_params)

    if redis_client:
        cached = redis_client.get(key)
        if cached:
            data = json.loads(cached)
            data["cache_hit"] = True
            return data

    # Always exclude failed extractions — partial records are included since they still have usable fields
    conditions = ["ai_extraction_status != 'failed'"]
    params: dict = {}

    if grad_year is not None:
        conditions.append("required_grad_year = :grad_year")
        params["grad_year"] = grad_year

    if grad_year_flex:
        conditions.append("grad_year_flexible = TRUE")

    if min_pay is not None:
        conditions.append("estimated_pay_hourly >= :min_pay")
        params["min_pay"] = min_pay

    if max_pay is not None:
        conditions.append("estimated_pay_hourly <= :max_pay")
        params["max_pay"] = max_pay

    if tech_stack:
        techs = [t.strip().lower() for t in tech_stack.split(",") if t.strip()]
        if techs:
            # @> is array containment — all requested techs must be present (AND, not OR)
            # Each tech needs its own bind param; SQLAlchemy text() doesn't support list params
            placeholders = ", ".join(f":tech_{i}" for i in range(len(techs)))
            conditions.append(f"tech_stack @> ARRAY[{placeholders}]::text[]")
            for i, t in enumerate(techs):
                params[f"tech_{i}"] = t

    if location:
        conditions.append("location @> ARRAY[:location]::text[]")
        params["location"] = location

    if remote_only:
        conditions.append("is_remote = TRUE")

    if sponsors_visa:
        conditions.append("sponsors_visa = TRUE")

    if source:
        conditions.append("source = :source")
        params["source"] = source

    sort_clause = {
        "date_desc": "date_ingested DESC",
        "pay_desc": "estimated_pay_hourly DESC NULLS LAST",
        "company": "company_name ASC",
    }[sort]

    where = " AND ".join(conditions)
    offset = (page - 1) * page_size

    with engine.connect() as conn:
        total_row = conn.execute(
            text(f"SELECT COUNT(*) FROM jobs WHERE {where}"), params
        ).fetchone()
        total = total_row[0] if total_row else 0

        rows = conn.execute(
            text(
                f"SELECT id, company_name, title, location, is_remote, required_grad_year, "
                f"grad_year_flexible, estimated_pay_hourly, tech_stack, sponsors_visa, "
                f"ai_extraction_status, ai_confidence_score, source, date_posted, "
                f"date_ingested, url "
                f"FROM jobs WHERE {where} ORDER BY {sort_clause} "
                f"LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": page_size, "offset": offset},
        ).fetchall()

    data = [_row_to_summary(r) for r in rows]
    response = {
        "data": data,
        "pagination": {"page": page, "page_size": page_size, "total": total},
        "cache_hit": False,
    }

    if redis_client:
        # default=str handles datetime serialization since timestamps aren't JSON-native
        redis_client.set(key, json.dumps(response, default=str), ex=_JOBS_CACHE_TTL)

    return response


@app.get("/api/jobs/{job_id}", response_model=JobDetail)
def get_job(job_id: UUID):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM jobs WHERE id = :id"),
            {"id": str(job_id)},
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return _row_to_detail(row)


@app.get("/api/stats", response_model=StatsResponse)
def get_stats():
    key = "cache:stats"

    if redis_client:
        cached = redis_client.get(key)
        if cached:
            return json.loads(cached)

    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT COUNT(*) FROM jobs WHERE ai_extraction_status != 'failed'")
        ).scalar()

        by_source = {
            row[0]: row[1]
            for row in conn.execute(
                text("SELECT source, COUNT(*) FROM jobs GROUP BY source")
            ).fetchall()
            if row[0] is not None
        }

        by_grad_year = {
            str(row[0]): row[1]
            for row in conn.execute(
                text(
                    "SELECT required_grad_year, COUNT(*) FROM jobs "
                    "WHERE required_grad_year IS NOT NULL "
                    "GROUP BY required_grad_year ORDER BY required_grad_year"
                )
            ).fetchall()
        }

        by_status = {
            row[0]: row[1]
            for row in conn.execute(
                text("SELECT ai_extraction_status, COUNT(*) FROM jobs GROUP BY ai_extraction_status")
            ).fetchall()
        }

    result = {
        "total": total,
        "by_source": by_source,
        "by_grad_year": by_grad_year,
        "by_status": by_status,
    }

    if redis_client:
        redis_client.set(key, json.dumps(result), ex=_STATS_CACHE_TTL)

    return result
