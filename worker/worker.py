import os
import json
import time
from typing import Any, List, Optional

import httpx
import redis
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "")
MIN_CANDIDATE_CHARS = 120
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_CHARS = 12000

SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

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
    return " ".join(value.split())


def _extract_jobposting_from_json(node: Any) -> Optional[str]:
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
    non_empty = [c for c in candidates if c]
    if not non_empty:
        return None

    preferred = [c for c in non_empty if len(c) >= MIN_CANDIDATE_CHARS]
    if preferred:
        return max(preferred, key=_score_candidate_text)

    return max(non_empty, key=len)


def _safe_text(node: Any) -> str:
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
    section_candidates: List[str] = []
    heading_terms = [
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

    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b"]):
        heading_text = _safe_text(heading).lower()
        if not heading_text or not any(term in heading_text for term in heading_terms):
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
    for tag in soup(["script", "style", "noscript", "svg", "form"]):
        try:
            tag.decompose()
        except Exception:
            continue

    noise_keywords = [
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

        if any(keyword in haystack for keyword in noise_keywords):
            elements_to_remove.append(element)

    for element in elements_to_remove:
        try:
            element.decompose()
        except Exception:
            continue


def _extract_main_candidate(soup: BeautifulSoup) -> str:
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
    lowered = text.lower()
    noise_tokens = [
        "privacy policy",
        "terms of service",
        "candidate privacy policy",
        "community guidelines",
        "help center",
        "language",
    ]
    anchors = [
        "job code",
        "responsibilities",
        "qualifications",
        "about the team",
    ]

    has_noise = any(token in lowered[:1500] for token in noise_tokens)
    if not has_noise:
        return text

    anchor_indexes = [lowered.find(anchor) for anchor in anchors if lowered.find(anchor) != -1]
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
            print("worker dependencies are ready")
            return
        except Exception as e:
            print(f"worker dependency check failed (attempt {attempt}/{max_retries}): {e}")
            time.sleep(sleep_seconds)

    raise RuntimeError("worker could not connect to dependencies")


def main() -> None:
    test_url = "https://job-boards.greenhouse.io/billiontoone/jobs/4680728005"
    test2_url = "https://snyk.wd103.myworkdayjobs.com/External/job/United-States---Boston-Office/Software-Engineer-Intern--Container-_JR100491"
    test3_url = "https://lifeattiktok.com/search/7533388869200333074"

    if not test_url.strip():
        print("Set test_url in main() to run the scraping smoke test.")
        return

    scraped_text = scrape_job_page(test_url)
    if not scraped_text:
        print("Scrape failed or returned no content.")
        return

    print("Scrape succeeded.")
    print(f"Extracted characters: {len(scraped_text)}")
    print("Preview (first 2000 chars):")
    print(scraped_text[:2000])


if __name__ == "__main__":
    main()
