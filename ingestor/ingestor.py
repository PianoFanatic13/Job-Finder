import os
import time

import hashlib
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, Field
import redis
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "")
INGEST_INTERVAL_SECONDS = int(os.getenv("INGEST_INTERVAL_SECONDS", "21600"))


class JobObject(BaseModel):
    url: str = Field(..., description="URL to the original job posting")
    url_hash: str = Field(..., description="Unique identifier for the job")
    source: str = Field(..., description="Source of the job listing (e.g., 'linkedin', 'indeed')")
    date_posted: int = Field(..., description="Unix timestamp when the job was posted")
    company_name: str = Field(..., description="Company name")
    title: str = Field(..., description="Job title")
    source_job_id: Optional[str] = Field(default=None, description="Original UUID from source listings")


TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "source",
}


def wait_for_dependencies(max_retries: int = 30, sleep_seconds: int = 2) -> None:
    if not DATABASE_URL or not REDIS_URL:
        raise RuntimeError("DATABASE_URL and REDIS_URL must be set")

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)

    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            redis_client.ping()
            print("ingestor dependencies are ready")
            return
        except Exception as exc:
            print(f"ingestor dependency check failed (attempt {attempt}/{max_retries}): {exc}")
            time.sleep(sleep_seconds)

    raise RuntimeError("ingestor could not connect to dependencies")


def normalize_url(raw_url: str) -> str:
    url = raw_url.strip()
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"

    filtered_query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_PARAMS
    ]
    normalized_query = urlencode(filtered_query_pairs, doseq=True)

    return urlunsplit((scheme, netloc, path, normalized_query, ""))


def normalize_listing(raw_listing: dict, source: str) -> Optional[JobObject]:
    raw_url = str(raw_listing.get("url", "")).strip()
    if not raw_url:
        return None

    try:
        url = normalize_url(raw_url)
    except ValueError:
        return None

    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()

    company_name = str(raw_listing.get("company_name", "")).strip() or "unknown"
    title = str(raw_listing.get("title", "")).strip() or "unknown"

    date_posted_raw = raw_listing.get("date_posted")
    try:
        date_posted = int(date_posted_raw)
    except (TypeError, ValueError):
        return None

    source_job_id = str(raw_listing.get("id")).strip() if raw_listing.get("id") else None

    return JobObject(
        url=url,
        url_hash=url_hash,
        source=source,
        date_posted=date_posted,
        company_name=company_name,
        title=title,
        source_job_id=source_job_id
    )


def main() -> None:
    wait_for_dependencies()
    print("ingestor bootstrapped - Phase 1 placeholder loop running")

    while True:
        print(f"ingestor heartbeat - next run window in {INGEST_INTERVAL_SECONDS} seconds")
        time.sleep(INGEST_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
