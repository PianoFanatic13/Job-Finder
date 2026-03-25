import os
import time

import hashlib
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, Field
import redis
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "")
INGEST_INTERVAL_SECONDS = int(os.getenv("INGEST_INTERVAL_SECONDS", "21600"))
LISTINGS_FETCH_TIMEOUT_SECONDS = int(os.getenv("LISTINGS_FETCH_TIMEOUT_SECONDS", "30"))
LISTINGS_MAX_AGE_DAYS = int(os.getenv("LISTINGS_MAX_AGE_DAYS", "30"))

SIMPLIFY_LISTINGS_URL = os.getenv("SIMPLIFY_LISTINGS_URL", "")
VANSH_LISTINGS_URL = os.getenv("VANSH_LISTINGS_URL", "")

LISTINGS_FETCH_MAX_RETRIES = 3


class JobObject(BaseModel):
    """Raw job payload produced by source ingestion.

    This schema represents the normalized data model passed downstream.
    Source independant model to allow flexibility and stay modular.
    """

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


SOURCES_INFO = {
    "simplify": {
        "url": SIMPLIFY_LISTINGS_URL,
        "known_sorted_time_ascending": True,
    },
    "vansh": {
        "url": VANSH_LISTINGS_URL,
        "known_sorted_time_ascending": True,
    },
}


def wait_for_dependencies(max_retries: int = 30, sleep_seconds: int = 2) -> None:
    """Block startup until PostgreSQL and Redis are reachable.

    The ingestor depends on both services. This retry loop prevents the process
    from failing during normal container startup races.
    """

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
    """Normalizes raw URL before hashing and dedup checks.

    Normalization removes common tracking noise (like source references) and 
    standardizes casing/path formatting so equivalent URLs produce the same hashes.
    """

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
    """Convert one job listing from a source into a JobObject.

    Returns None when required fields are missing or invalid (like
    invalid URL or unparsable date_posted).
    """

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
    source_normalized = source.strip().lower() if source else "unknown"

    return JobObject(
        url=url,
        url_hash=url_hash,
        source=source_normalized,
        date_posted=date_posted,
        company_name=company_name,
        title=title,
        source_job_id=source_job_id
    )


def fetch_json_listings(url: str) -> list[dict]:
    """Fetch source listings JSON and return only dictionary rows.

    The response is expected to be a JSON array. Non-dict items are dropped
    to keep downstream normalization strict.
    """

    if not url:
        raise ValueError("Missing source URL")

    last_error: Optional[Exception] = None

    for attempt in range(1, LISTINGS_FETCH_MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=LISTINGS_FETCH_TIMEOUT_SECONDS, follow_redirects=True) as client:
                response = client.get(url, headers={"Accept": "application/json"})
                response.raise_for_status()
                payload = response.json()
            break
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            last_error = exc
            if attempt == LISTINGS_FETCH_MAX_RETRIES:
                raise
            backoff_seconds = min(2 ** (attempt - 1), 8)
            print(
                f"fetch retry attempt={attempt}/{LISTINGS_FETCH_MAX_RETRIES} "
                f"url={url} wait={backoff_seconds}s error={exc.__class__.__name__}"
            )
            time.sleep(backoff_seconds)

    if last_error is not None and "payload" not in locals():
        raise last_error

    if not isinstance(payload, list):
        raise ValueError("Source payload is not a list")

    return [row for row in payload if isinstance(row, dict)]


def get_source_listings(source_name: str) -> list[dict]:
    """Resolve source name to URL, fetch rows, and return raw listing dicts."""

    source = source_name.strip().lower()
    source_config = SOURCES_INFO.get(source)
    if source_config is None:
        raise ValueError(f"Source not configured: {source}")

    source_url = str(source_config.get("url", "")).strip()
    if source_url == "":
        raise ValueError(f"Source URL not configured for {source}")
    return fetch_json_listings(source_url)


def build_canonical_jobs_for_source(source_name: str) -> tuple[list[JobObject], dict[str, int]]:
    """Build canonical jobs for one source and return processing counters.

    Step 3 freshness filtering is applied here:
    - rows are traversed newest-to-oldest via reverse iteration
    - rows older than LISTINGS_MAX_AGE_DAYS are filtered out
    - if the source is known sorted ascending by time, traversal breaks early
      after the first old row to avoid unnecessary work
    """

    counters = {
        "fetched": 0,
    "scanned": 0,
    "invalid_date": 0,
    "filtered_old": 0,
    "early_breaks": 0,
        "invalid": 0,
        "normalized": 0,
        "fetch_errors": 0,
    }

    try:
        source_rows = get_source_listings(source_name)
    except Exception as exc:
        counters["fetch_errors"] += 1
        print(f"source={source_name} fetch failed: {exc}")
        return [], counters

    counters["fetched"] = len(source_rows)
    source = source_name.strip().lower()
    source_config = SOURCES_INFO.get(source, {})
    is_sorted_ascending = bool(source_config.get("known_sorted_time_ascending", False))
    cutoff_epoch = int(time.time()) - (LISTINGS_MAX_AGE_DAYS * 24 * 60 * 60)

    canonical_jobs: list[JobObject] = []

    for row in reversed(source_rows):
        counters["scanned"] += 1

        date_posted_raw = row.get("date_posted")
        try:
            row_date_posted = int(date_posted_raw)
        except (TypeError, ValueError):
            counters["invalid_date"] += 1
            continue

        if row_date_posted < cutoff_epoch:
            counters["filtered_old"] += 1
            if is_sorted_ascending:
                counters["early_breaks"] += 1
                break
            continue

        job = normalize_listing(row, source)
        if job is None:
            counters["invalid"] += 1
            continue
        canonical_jobs.append(job)
        counters["normalized"] += 1

    return canonical_jobs, counters


def iter_configured_sources() -> list[str]:
    """Return source names that currently have non-empty configured URLs."""

    return [
        source
        for source, config in SOURCES_INFO.items()
        if str(config.get("url", "")).strip() != ""
    ]


def run_step2_preview() -> dict[str, int]:
    """Execute one ingestion preview pass and report summary counters.

    Includes Step 2 source fetch/normalization plus Step 3 freshness filtering.
    Dedup and Redis stream enqueue are introduced in later steps.
    """

    configured_sources = iter_configured_sources()
    if not configured_sources:
        print("No sources configured. Set at least one source URL in environment variables.")
        return {
            "sources": 0,
            "fetched": 0,
            "scanned": 0,
            "invalid_date": 0,
            "filtered_old": 0,
            "early_breaks": 0,
            "invalid": 0,
            "normalized": 0,
            "fetch_errors": 0,
        }

    total_fetched = 0
    total_scanned = 0
    total_invalid_date = 0
    total_filtered_old = 0
    total_early_breaks = 0
    total_invalid = 0
    total_normalized = 0
    total_fetch_errors = 0

    for source in configured_sources:
        jobs, counters = build_canonical_jobs_for_source(source)
        source_config = SOURCES_INFO[source]
        is_sorted_ascending = bool(source_config.get("known_sorted_time_ascending", False))

        total_fetched += counters["fetched"]
        total_scanned += counters["scanned"]
        total_invalid_date += counters["invalid_date"]
        total_filtered_old += counters["filtered_old"]
        total_early_breaks += counters["early_breaks"]
        total_invalid += counters["invalid"]
        total_normalized += counters["normalized"]
        total_fetch_errors += counters["fetch_errors"]

        print(
            f"source={source} sorted_ascending={is_sorted_ascending} fetched={counters['fetched']} "
            f"scanned={counters['scanned']} filtered_old={counters['filtered_old']} "
            f"invalid_date={counters['invalid_date']} early_breaks={counters['early_breaks']} "
            f"normalized={counters['normalized']} invalid={counters['invalid']} "
            f"fetch_errors={counters['fetch_errors']}"
        )

        if jobs:
            newest_job = jobs[-1]
            print(
                f"source={source} sample_job title={newest_job.title!r} "
                f"company={newest_job.company_name!r}"
            )

    return {
        "sources": len(configured_sources),
        "fetched": total_fetched,
        "scanned": total_scanned,
        "invalid_date": total_invalid_date,
        "filtered_old": total_filtered_old,
        "early_breaks": total_early_breaks,
        "invalid": total_invalid,
        "normalized": total_normalized,
        "fetch_errors": total_fetch_errors,
    }


def main() -> None:
    """Ingestor service entrypoint with periodic Step 2 preview runs."""

    wait_for_dependencies()
    print("ingestor bootstrapped - running Step 2 source fetch and normalization preview")

    while True:
        summary = run_step2_preview()
        print(
            "step2_summary "
            f"sources={summary['sources']} fetched={summary['fetched']} scanned={summary['scanned']} "
            f"filtered_old={summary['filtered_old']} invalid_date={summary['invalid_date']} "
            f"early_breaks={summary['early_breaks']} "
            f"normalized={summary['normalized']} invalid={summary['invalid']} "
            f"fetch_errors={summary['fetch_errors']}"
        )
        print(f"ingestor sleep - next run in {INGEST_INTERVAL_SECONDS} seconds")
        time.sleep(INGEST_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
