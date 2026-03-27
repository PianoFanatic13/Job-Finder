import os
import time
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, Field
import redis
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "")
#REDIS_URL = os.getenv("REDIS_URL_LOL", "redis://localhost:6379/0")
INGEST_INTERVAL_SECONDS = int(os.getenv("INGEST_INTERVAL_SECONDS", "21600"))
LISTINGS_FETCH_TIMEOUT_SECONDS = int(os.getenv("LISTINGS_FETCH_TIMEOUT_SECONDS", "30"))
LISTINGS_MAX_AGE_DAYS = int(os.getenv("LISTINGS_MAX_AGE_DAYS", "30"))
EARLY_BREAK_OLD_STREAK_THRESHOLD = int(
    os.getenv("EARLY_BREAK_OLD_STREAK_THRESHOLD", "20")
)

SIMPLIFY_LISTINGS_URL = os.getenv("SIMPLIFY_LISTINGS_URL", "")
VANSH_LISTINGS_URL = os.getenv("VANSH_LISTINGS_URL", "")
SIMPLIFY_ALLOWED_CATEGORIES = {
    value.strip().lower()
    for value in os.getenv("SIMPLIFY_ALLOWED_CATEGORIES", "software").split(",")
    if value.strip()
}

LISTINGS_FETCH_MAX_RETRIES = 3
INGEST_LOG_DIR = os.getenv("INGEST_LOG_DIR", "logs")
JOBS_PROCESSED_SET_KEY = os.getenv("JOBS_PROCESSED_SET_KEY", "jobs:processed")
JOBS_RAW_STREAM_KEY = os.getenv("JOBS_RAW_STREAM_KEY", "jobs:raw")
JOBS_RAW_STREAM_MAXLEN = int(os.getenv("JOBS_RAW_STREAM_MAXLEN", "200000"))

RUN_SUMMARY_COUNTER_KEYS = [
    "sources",
    "fetched",
    "normalized",
    "filtered_old",
    "invalid",
    "fetch_errors",
    "dedup_checked",
    "dedup_skipped",
    "enqueued",
    "enqueue_errors",
]


def write_debug_log(message: str, debug_log_path: Optional[Path]) -> None:
    """Write debug logs only when an explicit file path is provided from main."""

    if debug_log_path is None:
        return

    debug_log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with debug_log_path.open("a", encoding="utf-8", newline="\n") as debug_file:
        debug_file.write(f"{timestamp} {message}\n")


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


def is_allowed_category_for_source(source: str, row: dict) -> bool:
    """Return True when a listing passes source-specific category filtering."""

    source_normalized = source.strip().lower()
    if source_normalized != "simplify":
        return True

    if not SIMPLIFY_ALLOWED_CATEGORIES:
        return True

    category = str(row.get("category", "")).strip().lower()
    return category in SIMPLIFY_ALLOWED_CATEGORIES


def format_epoch_utc(epoch_seconds: int) -> str:
    """Format unix timestamp into an ISO-8601 UTC string for readable logs."""

    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


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
        except Exception as e:
            print(f"ingestor dependency check failed (attempt {attempt}/{max_retries}): {e}")
            time.sleep(sleep_seconds)

    raise RuntimeError("ingestor could not connect to dependencies")

def connect_to_redis(redis_url: str) -> redis.Redis:
    """Create and return a Redis client instance."""
    if not redis_url:
        raise ValueError("REDIS_URL must be set")
    try:
        r = redis.from_url(redis_url, decode_responses=True)
        r.ping()
        print("Connected to Redis successfully")
        return r
    except redis.exceptions.ConnectionError as e:
        print(f"Failed to connect to Redis: {e}")
        raise

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
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            last_error = e
            if attempt == LISTINGS_FETCH_MAX_RETRIES:
                raise
            backoff_seconds = min(2 ** (attempt - 1), 8)
            print(
                f"fetch retry attempt={attempt}/{LISTINGS_FETCH_MAX_RETRIES} "
                f"url={url} wait={backoff_seconds}s error={e.__class__.__name__}"
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


def collect_normalized_jobs_for_source(
    source_name: str,
    debug_log_path: Optional[Path] = None,
) -> tuple[list[JobObject], dict[str, int]]:
    """Fetch, filter, and normalize listings for one source.

    This function owns source-side shaping before Redis enqueue:
    - fetches raw source rows
    - filters to recent rows (with optional early-break optimization)
    - applies source-specific category filtering
    - normalizes valid rows into JobObject records

    Returns a tuple of normalized jobs and per-source counters.
    """

    counters = {
        "fetched": 0,
        "scanned": 0,
        "invalid_date": 0,
        "filtered_old": 0,
        "filtered_category": 0,
        "early_breaks": 0,
        "invalid": 0,
        "normalized": 0,
        "fetch_errors": 0,
    }

    try:
        source_rows = get_source_listings(source_name)
    except Exception as e:
        counters["fetch_errors"] += 1
        write_debug_log(f"source={source_name} fetch failed: {e}", debug_log_path)
        return [], counters

    counters["fetched"] = len(source_rows)
    source = source_name.strip().lower()
    source_config = SOURCES_INFO.get(source, {})
    is_sorted_ascending = bool(source_config.get("known_sorted_time_ascending", False))
    cutoff_epoch = int(time.time()) - (LISTINGS_MAX_AGE_DAYS * 24 * 60 * 60)

    canonical_jobs: list[JobObject] = []
    old_streak = 0

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
            old_streak += 1
            if is_sorted_ascending and old_streak >= EARLY_BREAK_OLD_STREAK_THRESHOLD:
                counters["early_breaks"] += 1
                break
            continue

        old_streak = 0

        if not is_allowed_category_for_source(source, row):
            counters["filtered_category"] += 1
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

def enqueue_new_jobs(
    jobs: list[JobObject],
    redis_client: redis.Redis,
    debug_log_path: Optional[Path] = None,
) -> dict[str, int]:
    """Deduplicate by hash set and enqueue unseen jobs to Redis Stream via XADD."""

    counters = {
        "dedup_checked": 0,
        "dedup_skipped": 0,
        "enqueued": 0,
        "enqueue_errors": 0,
    }

    for job in jobs:
        counters["dedup_checked"] += 1

        # SADD returns 1 if hash is new (new job), 0 if already exists (duplicate)
        is_new_hash = bool(redis_client.sadd(JOBS_PROCESSED_SET_KEY, job.url_hash))
        if not is_new_hash:
            counters["dedup_skipped"] += 1
            continue

        job_data = {
            "url": job.url,
            "url_hash": job.url_hash,
            "source": job.source,
            "date_posted": str(job.date_posted),
            "company_name": job.company_name,
            "title": job.title,
            "source_job_id": job.source_job_id or "",
            "ingested_at_epoch": str(int(time.time())),
        }

        try:
            redis_client.xadd(
                JOBS_RAW_STREAM_KEY,
                fields=job_data,
                maxlen=JOBS_RAW_STREAM_MAXLEN,
                approximate=True,
            )
            counters["enqueued"] += 1
        except Exception as e:
            # If enqueue fails after SADD, roll back hash so the job can retry next run.
            redis_client.srem(JOBS_PROCESSED_SET_KEY, job.url_hash)
            counters["enqueue_errors"] += 1
            write_debug_log(
                f"enqueue failed source={job.source} url_hash={job.url_hash} error={e}",
                debug_log_path,
            )

    return counters


def init_run_summary(source_count: int) -> dict[str, int]:
    """Initialize summary counters with all expected keys."""

    summary = {key: 0 for key in RUN_SUMMARY_COUNTER_KEYS}
    summary["sources"] = source_count
    return summary


def merge_counters(summary: dict[str, int], counters: dict[str, int]) -> None:
    """Merge one counter dict into the run summary in-place."""

    for key, value in counters.items():
        if key == "sources":
            continue
        if key in summary:
            summary[key] += value


def write_jobs_to_csv(jobs_csv_writer: csv.writer, jobs: list[JobObject]) -> None:
    """Write normalized jobs for one source into the picked jobs CSV."""

    for job_index, job in enumerate(jobs, start=1):
        jobs_csv_writer.writerow(
            [
                job.source,
                job_index,
                len(jobs),
                job.date_posted,
                format_epoch_utc(job.date_posted),
                job.company_name,
                job.title,
                job.source_job_id or "",
                job.url,
                job.url_hash,
            ]
        )


def process_source(
    source: str,
    redis_client: redis.Redis,
    summary_file,
    jobs_csv_writer: csv.writer,
    debug_log_path: Optional[Path] = None,
) -> dict[str, int]:
    """Process one configured source and return merged per-source counters."""

    jobs, counters = collect_normalized_jobs_for_source(source, debug_log_path=debug_log_path)
    source_config = SOURCES_INFO[source]
    is_sorted_ascending = bool(source_config.get("known_sorted_time_ascending", False))

    enqueue_counters = enqueue_new_jobs(
        jobs,
        redis_client,
        debug_log_path=debug_log_path,
    )

    source_line = (
        f"source={source} sorted_ascending={is_sorted_ascending} fetched={counters['fetched']} "
        f"scanned={counters['scanned']} filtered_old={counters['filtered_old']} "
        f"filtered_category={counters['filtered_category']} "
        f"invalid_date={counters['invalid_date']} early_breaks={counters['early_breaks']} "
        f"normalized={counters['normalized']} invalid={counters['invalid']} "
        f"fetch_errors={counters['fetch_errors']} dedup_checked={enqueue_counters['dedup_checked']} "
        f"dedup_skipped={enqueue_counters['dedup_skipped']} enqueued={enqueue_counters['enqueued']} "
        f"enqueue_errors={enqueue_counters['enqueue_errors']}"
    )
    write_debug_log(source_line, debug_log_path)
    summary_file.write(source_line + "\n")

    if jobs:
        newest_job = jobs[-1]
        sample_line = (
            f"source={source} sample_job title={newest_job.title!r} "
            f"company={newest_job.company_name!r}"
        )
        picked_count_line = f"source={source} picked_jobs_count={len(jobs)}"
        write_debug_log(sample_line, debug_log_path)
        write_debug_log(picked_count_line, debug_log_path)
        summary_file.write(sample_line + "\n")
        summary_file.write(picked_count_line + "\n")
        write_jobs_to_csv(jobs_csv_writer, jobs)
    else:
        picked_count_line = f"source={source} picked_jobs_count=0"
        write_debug_log(picked_count_line, debug_log_path)
        summary_file.write(picked_count_line + "\n")

    return {
        "fetched": counters["fetched"],
        "normalized": counters["normalized"],
        "filtered_old": counters["filtered_old"],
        "invalid": counters["invalid"],
        "fetch_errors": counters["fetch_errors"],
        "dedup_checked": enqueue_counters["dedup_checked"],
        "dedup_skipped": enqueue_counters["dedup_skipped"],
        "enqueued": enqueue_counters["enqueued"],
        "enqueue_errors": enqueue_counters["enqueue_errors"],
    }

def run_ingestion(debug_log_path: Optional[Path] = None) -> dict[str, int]:
    """Run one full ingestion cycle and return summary counters.

    A single cycle performs these actions:
    - prepares run artifacts (summary log + picked-jobs CSV)
    - processes each configured source
    - deduplicates and enqueues unseen jobs
    - aggregates and writes run totals
    """

    configured_sources = iter_configured_sources()
    run_started_epoch = int(time.time())
    run_id = datetime.fromtimestamp(run_started_epoch, tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_dir = Path(INGEST_LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_log_path = log_dir / f"ingestor_step2_{run_id}.txt"
    picked_jobs_csv_path = log_dir / f"ingestor_picked_jobs_{run_id}.csv"

    cutoff_epoch = int(time.time()) - (LISTINGS_MAX_AGE_DAYS * 24 * 60 * 60)
    simplify_categories_display = ",".join(sorted(SIMPLIFY_ALLOWED_CATEGORIES)) or "<all>"

    header_line = (
        "step2_header "
        f"sources={len(configured_sources)} listings_max_age_days={LISTINGS_MAX_AGE_DAYS} "
        f"cutoff_epoch={cutoff_epoch} cutoff_utc={format_epoch_utc(cutoff_epoch)} "
        f"early_break_old_streak_threshold={EARLY_BREAK_OLD_STREAK_THRESHOLD} "
        f"simplify_allowed_categories={simplify_categories_display}"
    )
    write_debug_log(header_line, debug_log_path)
    write_debug_log(
        f"step2_logs summary={summary_log_path} picked_jobs_csv={picked_jobs_csv_path}",
        debug_log_path,
    )

    with summary_log_path.open("w", encoding="utf-8", newline="\n") as summary_file, picked_jobs_csv_path.open(
        "w", encoding="utf-8", newline=""
    ) as jobs_csv_file:
        jobs_csv_writer = csv.writer(jobs_csv_file)
        jobs_csv_writer.writerow(
            [
                "source",
                "index_in_source",
                "source_picked_count",
                "date_posted",
                "posted_utc",
                "company_name",
                "title",
                "source_job_id",
                "url",
                "url_hash",
            ]
        )

        summary_file.write(header_line + "\n")

        summary = init_run_summary(len(configured_sources))

        if not configured_sources:
            no_sources_line = "No sources configured. Set at least one source URL in environment variables."
            write_debug_log(no_sources_line, debug_log_path)
            summary_file.write(no_sources_line + "\n")
            summary["sources"] = 0
            return summary

        redis_client = connect_to_redis(REDIS_URL)

        for source in configured_sources:
            source_counters = process_source(
                source,
                redis_client,
                summary_file,
                jobs_csv_writer,
                debug_log_path=debug_log_path,
            )
            merge_counters(summary, source_counters)

        totals_line = (
            "step2_totals "
            f"sources={summary['sources']} fetched={summary['fetched']} normalized={summary['normalized']} "
            f"filtered_old={summary['filtered_old']} invalid={summary['invalid']} "
            f"fetch_errors={summary['fetch_errors']} "
            f"dedup_checked={summary['dedup_checked']} dedup_skipped={summary['dedup_skipped']} "
            f"enqueued={summary['enqueued']} enqueue_errors={summary['enqueue_errors']}"
        )
        summary_file.write(totals_line + "\n")

        return summary


def main() -> None:
    """Ingestor service entrypoint for a single preview run."""

    # For debug output to logs
    # debug_log_path = Path(INGEST_LOG_DIR) / (
    #     f"ingestor_debug_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.txt"
    # )

    debug_log_path: Optional[Path] = None

    wait_for_dependencies()
    write_debug_log("ingestor bootstrapped - running ingestion flow", debug_log_path)

    summary = run_ingestion(debug_log_path=debug_log_path)
    write_debug_log(
        "step2_summary "
        f"sources={summary['sources']} fetched={summary['fetched']} normalized={summary['normalized']} "
        f"filtered_old={summary['filtered_old']} invalid={summary['invalid']} "
        f"fetch_errors={summary['fetch_errors']} dedup_checked={summary['dedup_checked']} "
        f"dedup_skipped={summary['dedup_skipped']} enqueued={summary['enqueued']} "
        f"enqueue_errors={summary['enqueue_errors']}",
        debug_log_path,
    )
    write_debug_log("ingestor test run complete", debug_log_path)


if __name__ == "__main__":
    main()
