import os
import time

import redis
from sqlalchemy import create_engine, text
from typing import Optional
from pydantic import BaseModel, Field

DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "")

from pydantic import BaseModel, Field
from typing import Optional, List

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
        except Exception as exc:
            print(f"worker dependency check failed (attempt {attempt}/{max_retries}): {exc}")
            time.sleep(sleep_seconds)

    raise RuntimeError("worker could not connect to dependencies")


def main() -> None:
    wait_for_dependencies()
    print("worker bootstrapped - Phase 1 placeholder loop running")

    while True:
        time.sleep(30)


if __name__ == "__main__":
    main()
