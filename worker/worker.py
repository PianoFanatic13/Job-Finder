import os
import json
import re
import time
from datetime import datetime, timezone
from typing import Any, List, Optional

import httpx
import redis
from bs4 import BeautifulSoup
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
JOBS_RAW_STREAM_KEY = os.getenv("JOBS_RAW_STREAM_KEY", "jobs:raw")
WORKER_GROUP = "worker-group"
WORKER_CONSUMER = "worker-1"
RATE_LIMIT_SLEEP_SECONDS = 5
MIN_CANDIDATE_CHARS = 120
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_CHARS = 12000

SECTION_HEADING_TERMS = [
    "responsibilities",
    "what you'll do",
    "what you will do",
    "qualifications",
    "minimum qualifications",
    "preferred qualifications",
    "requirements",
    "about the team",
    "job description",
]

NOISE_KEYWORDS = [
    "nav",
    "menu",
    "header",
    "footer",
    "cookie",
    "language",
    "locale",
    "social",
    "breadcrumb",
    "legal",
    "policy",
]

BOILERPLATE_TOKENS = [
    "privacy policy",
    "terms of service",
    "candidate privacy policy",
    "community guidelines",
    "help center",
    "language",
]

BOILERPLATE_ANCHORS = [
    "job code",
    "responsibilities",
    "qualifications",
    "about the team",
]

SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


class RateLimitError(Exception):
    def __init__(self, retry_after: int = 65):
        self.retry_after = retry_after
        super().__init__(f"rate limited, retry after {retry_after}s")


def _parse_retry_delay(error_str: str, default: int = 65) -> int:
    match = re.search(r"retry in (\d+)", error_str, re.IGNORECASE)
    return int(match.group(1)) + 5 if match else default


class JobMetadata(BaseModel):
    company_name: str = Field(description="Company name")
    title: str = Field(description="Normalized job title")
    location: List[str] = Field(description="List of locations, include Remote if applicable")
    is_remote: bool = Field(description="True if any location is remote or hybrid")
    required_grad_year: Optional[int] = Field(
        description=(
            "Applicant graduation year requirement only (e.g., 2027). "
            "Do not use company founding years, posting dates, or any non-applicant "
            "year mentioned in the text. Use None if not specified."
        )
    )
    class_standing_required: Optional[List[str]] = Field(
        default=None,
        description="Optional class standing requirements such as freshman, sophomore, junior, senior, masters, or phd"
    )
    grad_year_flexible: bool = Field(
        description="True if earlier or later graduation years are explicitly accepted"
    )
    estimated_pay: Optional[int] = Field(
        default=None,
        description=(
            "Representative pay amount as an integer for sorting/filtering; "
            "interpreted using salary_unit"
        )
    )
    salary_unit: Optional[str] = Field(description="hourly or annual")
    tech_stack: List[str] = Field(
        description=(
            "Normalized list of technologies in lowercase only (e.g., python, "
            "react, kubernetes). Deduplicate obvious variants/synonyms where "
            "possible to avoid duplicates like JavaScript vs JS as separate entries."
        )
    )
    sponsors_visa: bool = Field(
        description="True if H1B or OPT sponsorship is explicitly mentioned"
    )
    confidence_score: float = Field(
        description=(
            "Overall confidence from 0.0-1.0 across all extracted fields. "
            "Score low whenever any field required inference/guessing, not only "
            "when one specific field is uncertain."
        )
    )


def _extract_text_from_json_node(node: Any) -> str:
    """Extract useful long strings from generic JSON structures.

    This acts as a broad fallback when a clear JobPosting schema is not present.
    """
    collected: List[str] = []

    def walk(value: Any, parent_key: str = "") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, key.lower())
            return

        if isinstance(value, list):
            for item in value:
                walk(item, parent_key)
            return

        if isinstance(value, str):
            cleaned = " ".join(value.split())
            if len(cleaned) < 20:
                return

            useful_keys = {
                "description",
                "jobdescription",
                "responsibilities",
                "qualifications",
                "requirements",
                "summary",
                "title",
                "jobtitle",
            }
            if parent_key in useful_keys or len(cleaned) > 120:
                collected.append(cleaned)

    walk(node)
    return " ".join(collected)


def _normalize_text(value: str) -> str:
    """Collapse repeated whitespace into single spaces.

    Normalization keeps scoring and downstream extraction consistent across pages.
    """
    return " ".join(value.split())


def _extract_jobposting_from_json(node: Any) -> Optional[str]:
    """Extract title/description style text from JSON-LD JobPosting payloads.

    This is the highest-signal path when sites expose structured job metadata.
    """
    postings: List[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            type_value = value.get("@type") or value.get("type")
            if isinstance(type_value, str) and "jobposting" in type_value.lower():
                postings.append(value)
            elif isinstance(type_value, list):
                for item in type_value:
                    if isinstance(item, str) and "jobposting" in item.lower():
                        postings.append(value)
                        break

            for nested in value.values():
                walk(nested)
            return

        if isinstance(value, list):
            for item in value:
                walk(item)

    walk(node)

    for posting in postings:
        parts: List[str] = []

        title = posting.get("title") or posting.get("name")
        if isinstance(title, str):
            parts.append(_normalize_text(title))

        description = posting.get("description")
        if isinstance(description, str):
            clean_description = BeautifulSoup(description, "html.parser").get_text(" ", strip=True)
            parts.append(_normalize_text(clean_description))

        for key in ["responsibilities", "qualifications"]:
            value = posting.get(key)
            if isinstance(value, str):
                parts.append(_normalize_text(value))

        merged = _normalize_text(" ".join(parts))
        if len(merged) >= 120:
            return merged

    return None


def _score_candidate_text(text: str) -> float:
    """Score extracted text by job-signal keywords and boilerplate penalties.

    Higher scores indicate text that is more likely to contain job requirements.
    """
    lowered = text.lower()

    positive_terms = [
        "responsibilities",
        "qualifications",
        "minimum qualifications",
        "preferred qualifications",
        "requirements",
        "about the team",
        "what you'll do",
        "internship",
    ]
    negative_terms = [
        "privacy policy",
        "terms of service",
        "candidate privacy policy",
        "community guidelines",
        "help center",
        "fair chance",
        "ordinance",
    ]

    score = min(len(text), 9000) / 450.0
    score += 3.0 * sum(1 for term in positive_terms if term in lowered)
    score -= 2.5 * sum(1 for term in negative_terms if term in lowered)
    return score


def _pick_best_candidate(candidates: List[str]) -> Optional[str]:
    """Choose the best candidate, preferring richer job-like text.

    If no candidate meets the preferred length threshold, choose the longest one.
    """
    non_empty = [c for c in candidates if c]
    if not non_empty:
        return None

    preferred = [c for c in non_empty if len(c) >= MIN_CANDIDATE_CHARS]
    if preferred:
        return max(preferred, key=_score_candidate_text)

    return max(non_empty, key=len)


def _safe_text(node: Any) -> str:
    """Safely get normalized text from a BeautifulSoup node.

    This prevents malformed tags from crashing the scraper pipeline.
    """
    if node is None:
        return ""

    get_text = getattr(node, "get_text", None)
    if callable(get_text):
        try:
            return _normalize_text(get_text(separator=" ", strip=True))
        except Exception:
            return ""

    return ""


def _safe_tag_attr_text(node: Any, key: str) -> str:
    """Safely read a BeautifulSoup tag attribute as a string.

    Attribute values may be missing, strings, or lists depending on the tag.
    """
    attrs = getattr(node, "attrs", None)
    if not isinstance(attrs, dict):
        return ""

    value = attrs.get(key)
    if value is None:
        return ""

    if isinstance(value, list):
        return " ".join(str(item) for item in value)

    return str(value)


def _extract_section_candidates(soup: BeautifulSoup) -> List[str]:
    """Collect text blocks near headings like Responsibilities and Qualifications.

    Section extraction helps recover key details when page-level text is noisy.
    """
    section_candidates: List[str] = []

    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b"]):
        heading_text = _safe_text(heading).lower()
        if not heading_text or not any(term in heading_text for term in SECTION_HEADING_TERMS):
            continue

        blocks: List[str] = []
        blocks.append(_safe_text(heading))

        cursor = heading
        for _ in range(4):
            cursor = getattr(cursor, "find_next_sibling", lambda *_: None)()
            if cursor is None:
                break

            sibling_text = _safe_text(cursor)
            if sibling_text:
                blocks.append(sibling_text)

            sibling_name = getattr(cursor, "name", "") or ""
            if sibling_name.lower() in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                break

        merged = _normalize_text(" ".join(blocks))
        if merged:
            section_candidates.append(merged)

    return section_candidates


def _iter_json_payloads(soup: BeautifulSoup) -> List[Any]:
    """Parse and return JSON payloads found in script tags.

    Many job pages embed structured data in JSON or JSON-LD script tags.
    """
    payloads: List[Any] = []

    for script in soup.find_all("script"):
        script_text = script.string or script.get_text(strip=True)
        if not script_text:
            continue

        script_type = (script.get("type") or "").lower()
        looks_like_json = (
            "application/json" in script_type
            or "application/ld+json" in script_type
            or script_text.startswith("{")
            or script_text.startswith("[")
        )
        if not looks_like_json:
            continue

        try:
            payloads.append(json.loads(script_text))
        except Exception:
            continue

    return payloads


def _collect_json_candidates(soup: BeautifulSoup) -> List[str]:
    """Create text candidates from structured and unstructured JSON payloads.

    Tries explicit JobPosting extraction first, then falls back to generic JSON text.
    """
    candidates: List[str] = []

    for payload in _iter_json_payloads(soup):
        jobposting_text = _extract_jobposting_from_json(payload)
        if jobposting_text:
            candidates.append(jobposting_text)
            continue

        extracted = _extract_text_from_json_node(payload)
        if extracted:
            candidates.append(_normalize_text(extracted))

    return candidates


def _remove_noise_elements(soup: BeautifulSoup) -> None:
    """Remove known non-content containers like nav/footer/cookie blocks.

    This reduces the chance that menus and policy text dominate extracted content.
    """
    for tag in soup(["script", "style", "noscript", "svg", "form"]):
        try:
            tag.decompose()
        except Exception:
            continue

    elements_to_remove: List[Any] = []
    for element in soup.find_all(True):
        if element is None or getattr(element, "attrs", None) is None:
            continue

        haystack = " ".join(
            [
                _safe_tag_attr_text(element, "id"),
                _safe_tag_attr_text(element, "class"),
                _safe_tag_attr_text(element, "role"),
                _safe_tag_attr_text(element, "aria-label"),
            ]
        ).lower()

        if any(keyword in haystack for keyword in NOISE_KEYWORDS):
            elements_to_remove.append(element)

    for element in elements_to_remove:
        try:
            element.decompose()
        except Exception:
            continue


def _extract_main_candidate(soup: BeautifulSoup) -> str:
    """Extract text from the most likely main job content container.

    Uses a priority order of selectors commonly seen on job detail pages.
    """
    content_root = (
        soup.find("article")
        or soup.find("main")
        or soup.select_one('[role="main"]')
        or soup.select_one('[class*="job" i], [id*="job" i]')
        or soup.select_one('[class*="posting" i], [id*="posting" i]')
        or soup.select_one('[class*="description" i], [id*="description" i]')
        or soup.body
        or soup
    )

    text = _safe_text(content_root)
    return _trim_leading_boilerplate(_normalize_text(text))


def _collect_candidates_from_html(html: str) -> List[str]:
    """Build extraction candidates from sections, JSON payloads, and HTML fallbacks.

    Candidate diversity improves resilience across Greenhouse, Workday, and custom sites.
    """
    candidates: List[str] = []

    original_soup = BeautifulSoup(html, "html.parser")
    candidates.extend(_extract_section_candidates(original_soup))
    candidates.extend(_collect_json_candidates(original_soup))

    cleaned_soup = BeautifulSoup(html, "html.parser")
    _remove_noise_elements(cleaned_soup)
    main_candidate = _extract_main_candidate(cleaned_soup)
    if main_candidate:
        candidates.append(main_candidate)

    fallback_soup = BeautifulSoup(html, "html.parser")
    for tag in fallback_soup(["script", "style", "noscript", "svg", "form"]):
        try:
            tag.decompose()
        except Exception:
            continue

    fallback_text = fallback_soup.get_text(separator=" ", strip=True)
    fallback_candidate = _trim_leading_boilerplate(_normalize_text(fallback_text))
    if fallback_candidate:
        candidates.append(fallback_candidate)

    return candidates


def _trim_leading_boilerplate(text: str) -> str:
    """Trim leading site boilerplate when job anchors are present later.

    This keeps legal and navigation text from appearing ahead of real job content.
    """
    lowered = text.lower()

    has_noise = any(token in lowered[:1500] for token in BOILERPLATE_TOKENS)
    if not has_noise:
        return text

    anchor_indexes = [
        lowered.find(anchor)
        for anchor in BOILERPLATE_ANCHORS
        if lowered.find(anchor) != -1
    ]
    if not anchor_indexes:
        return text

    first_anchor = min(anchor_indexes)
    if first_anchor > 0:
        return text[first_anchor:].strip()

    return text

def scrape_job_page(
    url: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> Optional[str]:
    """Fetch a job page and return cleaned plain text for metadata extraction.

    The function combines structured-data parsing and HTML fallbacks, then selects
    the strongest candidate for downstream LLM parsing.
    """

    try:
        response = httpx.get(
            url,
            headers=SCRAPE_HEADERS,
            timeout=timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()

        html = response.text
        if not html.strip():
            print(f"scrape_job_page got empty HTTP body for {url}")
            return None

        candidates = _collect_candidates_from_html(html)

        best_candidate = _pick_best_candidate(candidates)
        if best_candidate:
            return best_candidate[:max_chars]

        print(
            f"scrape_job_page found very little extractable text for {url}. "
            "The page may require JavaScript rendering or block bot traffic."
        )
        fallback = _normalize_text(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
        return fallback[:max_chars] if fallback else None
    except httpx.HTTPError as e:
        print(f"scrape_job_page failed for {url}: {e}")
        return None
    except Exception as e:
        print(f"scrape_job_page unexpected error for {url}: {e}")
        return None

_EXTRACT_PROMPT_TEMPLATE = """\
You are a structured data extractor for software engineering job postings.

Extract all fields from the job description below and return them as structured data.
Follow each field's description exactly. When information is not present, use null or
false as appropriate — do not guess or hallucinate values.

Job description:
{raw_text}"""

_VALID_GRAD_YEAR_RANGE = range(2024, 2031)
_MAX_HOURLY_PAY = 500


def extract_metadata(raw_text: str, structured_llm=None) -> Optional[JobMetadata]:
    """Extract structured job metadata from scraped plain text using Gemini.

    Returns a validated JobMetadata object, or None if extraction fails.
    Pass a pre-built structured_llm to skip LLM construction (useful for testing).
    """
    if not raw_text or not raw_text.strip():
        return None

    try:
        if structured_llm is None:
            llm = ChatGoogleGenerativeAI(
                model=GEMINI_MODEL,
                temperature=0,
                google_api_key=GEMINI_API_KEY,
            )
            structured_llm = llm.with_structured_output(JobMetadata)

        prompt = _EXTRACT_PROMPT_TEMPLATE.format(raw_text=raw_text)
        result: JobMetadata = structured_llm.invoke([HumanMessage(content=prompt)])

        # Hallucination guards
        if result.required_grad_year is not None and result.required_grad_year not in _VALID_GRAD_YEAR_RANGE:
            result.required_grad_year = None

        if result.estimated_pay is not None and result.salary_unit == "hourly" and result.estimated_pay > _MAX_HOURLY_PAY:
            result.estimated_pay = None
            result.salary_unit = None

        if result.tech_stack:
            seen: set[str] = set()
            deduped: List[str] = []
            for tech in result.tech_stack:
                normalized = tech.lower().strip()
                if normalized not in seen:
                    seen.add(normalized)
                    deduped.append(normalized)
            result.tech_stack = deduped

        return result

    except (ValidationError, Exception) as e:
        err_str = str(e)
        if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
            raise RateLimitError(_parse_retry_delay(err_str))
        print(f"extract_metadata failed: {e}")
        return None


_UPSERT_SQL = text("""
INSERT INTO jobs (
    url, url_hash, company_name, title, location, is_remote,
    required_grad_year, grad_year_flexible, estimated_salary_low,
    salary_unit, tech_stack, sponsors_visa, raw_description,
    ai_extraction_status, ai_confidence_score, source,
    date_posted, date_processed
) VALUES (
    :url, :url_hash, :company_name, :title, :location, :is_remote,
    :required_grad_year, :grad_year_flexible, :estimated_salary_low,
    :salary_unit, :tech_stack, :sponsors_visa, :raw_description,
    :ai_extraction_status, :ai_confidence_score, :source,
    :date_posted, :date_processed
)
ON CONFLICT (url) DO UPDATE SET
    company_name         = EXCLUDED.company_name,
    title                = EXCLUDED.title,
    location             = EXCLUDED.location,
    is_remote            = EXCLUDED.is_remote,
    required_grad_year   = EXCLUDED.required_grad_year,
    grad_year_flexible   = EXCLUDED.grad_year_flexible,
    estimated_salary_low = EXCLUDED.estimated_salary_low,
    salary_unit          = EXCLUDED.salary_unit,
    tech_stack           = EXCLUDED.tech_stack,
    sponsors_visa        = EXCLUDED.sponsors_visa,
    raw_description      = EXCLUDED.raw_description,
    ai_extraction_status = EXCLUDED.ai_extraction_status,
    ai_confidence_score  = EXCLUDED.ai_confidence_score,
    date_processed       = EXCLUDED.date_processed
RETURNING id
""")

_CONFIDENCE_THRESHOLD = 0.6


def save_to_database(
    job_stream_data: dict,
    metadata: JobMetadata,
    raw_text: str,
    engine=None,
) -> Optional[str]:
    """Upsert an enriched job record into PostgreSQL and return its UUID.

    Accepts an injectable engine for testing. When engine is None, creates one
    from DATABASE_URL — callers should reuse a single engine across multiple jobs.
    """
    try:
        if engine is None:
            engine = create_engine(DATABASE_URL, pool_pre_ping=True)

        status = "success" if metadata.confidence_score >= _CONFIDENCE_THRESHOLD else "partial"

        date_posted_str = job_stream_data.get("date_posted", "0")
        date_posted = datetime.fromtimestamp(int(date_posted_str), tz=timezone.utc)
        date_processed = datetime.now(tz=timezone.utc)

        params = {
            "url": job_stream_data["url"],
            "url_hash": job_stream_data["url_hash"],
            "company_name": metadata.company_name,
            "title": metadata.title,
            "location": metadata.location,
            "is_remote": metadata.is_remote,
            "required_grad_year": metadata.required_grad_year,
            "grad_year_flexible": metadata.grad_year_flexible,
            "estimated_salary_low": metadata.estimated_pay,
            "salary_unit": metadata.salary_unit,
            "tech_stack": metadata.tech_stack,
            "sponsors_visa": metadata.sponsors_visa,
            "raw_description": raw_text,
            "ai_extraction_status": status,
            "ai_confidence_score": metadata.confidence_score,
            "source": job_stream_data.get("source"),
            "date_posted": date_posted,
            "date_processed": date_processed,
        }

        with engine.connect() as conn:
            result = conn.execute(_UPSERT_SQL, params)
            conn.commit()
            row = result.fetchone()
            return str(row[0]) if row else None

    except Exception as e:
        print(f"save_to_database failed: {e}")
        return None


def _process_one_job(fields: dict, engine) -> Optional[str]:
    url = fields.get("url", "")

    raw_text = scrape_job_page(url)
    if not raw_text:
        print(f"_process_one_job scrape returned nothing for {url}")
        return None

    metadata = extract_metadata(raw_text)
    if not metadata:
        print(f"_process_one_job extract returned nothing for {url}")
        return None

    return save_to_database(fields, metadata, raw_text, engine=engine)


def run_consumer_loop(redis_client, engine) -> None:
    try:
        redis_client.xgroup_create(JOBS_RAW_STREAM_KEY, WORKER_GROUP, id="0", mkstream=True)
        print(f"consumer group '{WORKER_GROUP}' created")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise
        print(f"consumer group '{WORKER_GROUP}' already exists, resuming")

    processed = 0
    failed = 0

    while True:
        messages = redis_client.xreadgroup(
            WORKER_GROUP,
            WORKER_CONSUMER,
            {JOBS_RAW_STREAM_KEY: ">"},
            count=1,
            block=5000,
        )

        if not messages:
            continue

        _, entries = messages[0]
        msg_id, fields = entries[0]
        url = fields.get("url", "unknown")

        print(f"\n[{processed + failed + 1}] {url}")

        try:
            job_id = _process_one_job(fields, engine)
            if job_id:
                processed += 1
                print(f"  saved {job_id}  (ok={processed} fail={failed})")
            else:
                failed += 1
                print(f"  skipped  (ok={processed} fail={failed})")
            redis_client.xack(JOBS_RAW_STREAM_KEY, WORKER_GROUP, msg_id)
            time.sleep(RATE_LIMIT_SLEEP_SECONDS)
        except RateLimitError as e:
            print(f"  rate limited — sleeping {e.retry_after}s, message stays pending for retry")
            time.sleep(e.retry_after)


def wait_for_dependencies(max_retries: int = 30, sleep_seconds: int = 2) -> None:
    """Block until Postgres and Redis are reachable.

    Worker startup should fail early when required infrastructure is unavailable.
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
            print("worker dependencies are ready")
            return
        except Exception as e:
            print(f"worker dependency check failed (attempt {attempt}/{max_retries}): {e}")
            time.sleep(sleep_seconds)

    raise RuntimeError("worker could not connect to dependencies")


def main() -> None:
    wait_for_dependencies()
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    print("worker started — listening on stream")
    run_consumer_loop(redis_client, engine)


if __name__ == "__main__":
    main()
