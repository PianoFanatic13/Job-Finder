# InternIQ — Distributed AI-Powered Job Aggregator
**Product Requirements Document — Version 2.0**

| | |
|---|---|
| **Status** | In Development |
| **Target Timeline** | 14 Days (2 Weeks) |
| **Architecture** | 4-Service Distributed Microservices |
| **AI Framework** | LangChain (ReAct Agent + Structured Output) |
| **Primary Stack** | Python, TypeScript/React, PostgreSQL, Redis, Docker |
| **Cloud Target** | AWS Free Tier (EC2, RDS, ElastiCache) |

---

## 1. Problem Statement & Motivation

The software engineering internship market is simultaneously hyper-competitive and information-fragmented. Candidates waste hours cross-referencing community GitHub repos, corporate career portals, and aggregator sites like LinkedIn and Handshake. None of these offer the specific metadata that actually matters: graduation year requirements, estimated compensation, or visa sponsorship status.

**InternIQ** solves this by creating a single, enriched, always-fresh database that normalizes and enriches job listings using an AI agent chain, then exposes the data via a fast, filterable dashboard.

> **Why AI?** Raw job descriptions embed critical metadata in prose: *"Must graduate December 2026 or earlier," "Compensation: $45–55/hr," "Experience with Kubernetes preferred."* A rule-based parser cannot reliably extract this. A LangChain agent can — and with structured output binding, the results are Pydantic-validated before database insertion.

---

## 2. Data Sources

The MVP ingests from two open-source community repositories via their raw GitHub URLs. No scraping, no anti-bot issues.

- **PittCSC/Summer2025-Internships** — `https://raw.githubusercontent.com/pittcsc/Summer2025-Internships/dev/README.md` (parsed from Markdown table)
- **Ouckah/CS-Jobs-And-Internships** — `https://raw.githubusercontent.com/Ouckah/Summer2026-Internships/dev/.github/scripts/listings.json`

Both are fetched by the Ingestor service on a configurable cron schedule (default: every 6 hours). The PittCSC repo requires light Markdown table parsing; the Ouckah repo is already structured JSON.

---

## 3. Core MVP Features

### 3.1 Automated Ingestion Pipeline
A scheduled Python script fetches raw listing data from both repos and publishes new job objects to a Redis Stream. Uses `httpx` with retry/backoff — no Selenium or Playwright overhead.

### 3.2 LangChain AI Extraction Agent
The centerpiece of the system. A Python worker runs a LangChain ReAct agent loop with access to custom tools. This is meaningfully different from a raw LLM prompt call — the agent makes decisions, retries on failure, and uses tools in sequence.

**Agent Tools:**
- `scrape_job_page(url)` — fetches and extracts plain text from a job posting URL using BeautifulSoup; handles timeouts and 404s gracefully
- `check_redis_dedup(url_hash)` — confirms this URL hash hasn't already been processed (O(1) Redis Set lookup)
- `extract_metadata(raw_text)` — calls GPT-4o-mini via LangChain's `with_structured_output`, enforcing a Pydantic schema
- `save_to_database(job_record)` — upserts the enriched record into PostgreSQL via SQLAlchemy

**Agent Loop Logic:** The agent receives a job object from the Redis Stream and decides the sequence of tool calls. If scraping fails (404, timeout), it marks the job as `FAILED` in Redis rather than retrying indefinitely. If extraction confidence is below threshold, the record is stored as `partial` and flagged for review.

### 3.3 Redis Deduplication & Queuing
Redis serves three distinct roles using three different data structures:

- **Deduplication Set (SADD/SISMEMBER)** — before any job URL is enqueued, its SHA-256 hash is checked against a persistent Redis Set. O(1) lookup. Prevents duplicate AI processing and redundant API spend.
- **Work Queue (Redis Streams with XADD/XREADGROUP)** — preferred over Lists because Streams support consumer groups (multiple workers can process in parallel) and message acknowledgment. If a worker crashes mid-job, the message is not lost — another worker picks it up after a visibility timeout.
- **Query Result Cache (Redis Strings with TTL)** — the API layer caches serialized query results using a hash of the query parameters as the key, with a 1-hour TTL. Dramatically reduces PostgreSQL load during peak usage.

### 3.4 PostgreSQL Enriched Job Store
All AI-enriched records are persisted in PostgreSQL (AWS RDS Free Tier). The schema stores the structured metadata the AI extracts, plus operational fields like confidence score and extraction status.

### 3.5 REST API with Filter Support
A FastAPI application exposes `GET /api/jobs` with query parameters:
- `grad_year` — filter by required graduation year (e.g., `2027`)
- `min_salary` / `max_salary` — salary range filtering
- `salary_unit` — `hourly` or `annual`
- `tech_stack` — comma-separated, all must be present (AND logic)
- `location` — city/state string or `Remote`
- `remote_only` — boolean shorthand
- `sponsors_visa` — filter for confirmed H1B/OPT sponsorship
- `sort` — `date_desc` (default), `salary_desc`, `company`
- `page` / `page_size` — standard pagination

### 3.6 React + TypeScript Frontend Dashboard
A clean dashboard that allows candidates to filter jobs in ways no other internship board supports — particularly graduation year and estimated compensation filtering.

---

## 4. System Architecture

### 4.1 Service Decomposition

| Service | Tech | Role |
|---|---|---|
| **A — Frontend** | React + TypeScript + Vite | User dashboard, filters, job cards |
| **B — API** | Python + FastAPI | REST endpoints, cache logic, DB queries |
| **C — Ingestor** | Python + httpx | Fetches raw data, deduplicates, enqueues |
| **D — AI Worker** | Python + LangChain | Agent loop, scraping, AI extraction, DB write |

### 4.2 End-to-End Data Flow

1. Ingestor fetches listings from both GitHub repos (raw URLs)
2. For each job, compute `SHA-256(url)` → check Redis Set. If present, skip. If absent, `SADD` and continue.
3. Ingestor publishes raw job object to Redis Stream `jobs:raw` via `XADD`
4. AI Worker reads from Stream using `XREADGROUP` (consumer group `workers`)
5. LangChain Agent receives the job object and calls `check_redis_dedup` → confirms it's new
6. Agent calls `scrape_job_page(url)` → retrieves raw HTML, strips to plain text
7. Agent calls `extract_metadata(raw_text)` → LLM returns structured JSON enforced by Pydantic model
8. Agent calls `save_to_database(job_record)` → SQLAlchemy upserts into PostgreSQL
9. Agent sends `XACK` to Redis Stream → message removed from pending list
10. User hits React frontend → API call to `GET /api/jobs?grad_year=2027&min_salary=45`
11. FastAPI checks Redis cache. On miss: queries PostgreSQL, stores result in Redis with 1hr TTL
12. Response returned to frontend; job cards rendered with enriched metadata

---

## 5. Database Schema

### 5.1 `jobs` Table

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated v4 UUID |
| `url` | TEXT UNIQUE | Canonical job posting URL |
| `url_hash` | CHAR(64) | SHA-256 of url; mirrors Redis Set key |
| `company_name` | TEXT NOT NULL | Extracted company name |
| `title` | TEXT NOT NULL | Normalized job title |
| `location` | TEXT[] | Array of locations |
| `is_remote` | BOOLEAN | True if any location is remote |
| `required_grad_year` | INT | Integer year (e.g., 2027). NULL if not specified |
| `grad_year_flexible` | BOOLEAN | True if description says "or earlier/later" |
| `estimated_salary_low` | INT | Lower bound of compensation range |
| `estimated_salary_high` | INT | Upper bound of compensation range |
| `salary_unit` | TEXT | Enum: `hourly` or `annual` |
| `tech_stack` | TEXT[] | PostgreSQL array of normalized tech strings |
| `sponsors_visa` | BOOLEAN | True if H1B/OPT sponsorship is mentioned |
| `raw_description` | TEXT | Full raw text fed to the LLM (for debugging/re-processing) |
| `ai_extraction_status` | TEXT | Enum: `success`, `partial`, `failed` |
| `ai_confidence_score` | FLOAT | 0.0–1.0 confidence from LLM response |
| `source` | TEXT | e.g., `pittcsc`, `ouckah` |
| `date_posted` | TIMESTAMPTZ | Extracted or inferred posting date |
| `date_ingested` | TIMESTAMPTZ | When ingestor first saw this URL |
| `date_processed` | TIMESTAMPTZ | When AI worker completed extraction |

### 5.2 Indexes

```sql
CREATE INDEX ON jobs(required_grad_year);
CREATE INDEX ON jobs(estimated_salary_low);
CREATE INDEX ON jobs(is_remote);
CREATE INDEX ON jobs USING GIN(tech_stack);  -- array containment queries
CREATE INDEX ON jobs(date_ingested DESC);    -- default sort
```

---

## 6. LangChain Agent — Full Specification

### 6.1 Why LangChain (Not a Raw Prompt)

A raw "call the LLM and parse the response" approach is brittle. LangChain's agent framework provides:

- **Structured Output Binding** — `.with_structured_output(JobMetadata)` binds the LLM response to a Pydantic model. If the LLM returns malformed JSON or omits required fields, LangChain raises a validation error before anything reaches PostgreSQL.
- **ReAct Tool Loop** — the agent can decide to call `scrape_job_page` again with a different URL variant if the first attempt returns a 404 or empty page.
- **Retry & Error Handling** — LangChain's built-in `with_retry` handles transient LLM API rate limits without custom boilerplate.
- **Observability** — integrates with LangSmith for full agent trace logging. Every tool call, LLM invocation, and decision is recorded — invaluable for debugging hallucinations.

### 6.2 Pydantic Output Schema

```python
from pydantic import BaseModel, Field
from typing import Optional, List

class JobMetadata(BaseModel):
    company_name: str = Field(description="Company name")
    title: str = Field(description="Normalized job title")
    location: List[str] = Field(description="List of locations, include Remote if applicable")
    is_remote: bool = Field(description="True if any location is remote or hybrid")
    required_grad_year: Optional[int] = Field(
        description="Graduation year required (e.g., 2026). None if not specified."
    )
    grad_year_flexible: bool = Field(
        description="True if earlier or later graduation years are explicitly accepted"
    )
    estimated_salary_low: Optional[int] = Field(
        description="Lower bound of compensation range as integer"
    )
    estimated_salary_high: Optional[int] = Field(
        description="Upper bound of compensation range as integer"
    )
    salary_unit: Optional[str] = Field(description="hourly or annual")
    tech_stack: List[str] = Field(
        description="Normalized list of technologies (e.g., Python, React, Kubernetes)"
    )
    sponsors_visa: bool = Field(
        description="True if H1B or OPT sponsorship is explicitly mentioned"
    )
    confidence_score: float = Field(
        description="Your confidence 0.0-1.0 in the accuracy of all extracted fields"
    )
```

### 6.3 Agent Tool Definitions

```python
from langchain.tools import tool
from langchain_openai import ChatOpenAI

@tool
def scrape_job_page(url: str) -> str:
    """Fetch and extract plain text from a job posting URL."""
    # Uses httpx + BeautifulSoup; strips scripts, nav, footer
    # Returns first 4000 tokens of main content
    ...

@tool
def check_redis_dedup(url_hash: str) -> bool:
    """Returns True if this url_hash already exists in the processed set."""
    return redis_client.sismember("jobs:processed", url_hash)

@tool
def save_to_database(metadata: dict) -> str:
    """Upsert the enriched job record into PostgreSQL. Returns the job UUID."""
    ...

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
structured_llm = llm.with_structured_output(JobMetadata)

agent = create_react_agent(
    llm=llm,
    tools=[scrape_job_page, check_redis_dedup, save_to_database],
    prompt=agent_prompt
)
```

### 6.4 Hallucination Guards

- `confidence_score < 0.6` → stored as `ai_extraction_status = 'partial'`; not returned in default API queries
- `required_grad_year` outside 2024–2030 → stored as NULL (LLM likely misread a different number)
- `estimated_salary_high > 500` when `salary_unit = 'hourly'` → flagged for unit re-check
- `tech_stack` → normalized to lowercase and deduplicated before storage

---

## 7. Redis Architecture

### 7.1 Key Structure

| Key Pattern | Structure | TTL | Purpose |
|---|---|---|---|
| `jobs:processed` | Set | None | Deduplication — SHA-256 URL hashes |
| `jobs:raw` | Stream | None | Work queue — raw job objects |
| `cache:jobs:{hash}` | String | 3600s | API query result cache |
| `jobs:failed:{hash}` | String | 86400s | Prevents infinite retries on bad URLs |
| `stats:daily` | Hash | None | Counters: ingested, processed, failed per day |

### 7.2 Why Redis Streams over Lists

The original approach used Redis Lists (`LPUSH`/`RPOP`). Redis Streams are strictly better here: they support consumer groups for parallel worker scaling, message acknowledgment (at-least-once delivery), and message history for replay. If a worker crashes mid-job, the message isn't lost — it stays in the pending list until acknowledged.

---

## 8. API Specification

### `GET /api/jobs`

**Query Parameters:**
```
grad_year         int      Filter by required graduation year
grad_year_flex    bool     Include listings that accept other grad years  
min_salary        int      Minimum salary (in salary_unit)
max_salary        int      Maximum salary
salary_unit       string   "hourly" | "annual"
tech_stack        string   Comma-separated; all must be present (AND)
location          string   City/state string or "Remote"
remote_only       bool     Shorthand for location=Remote
sponsors_visa     bool     Filter for confirmed sponsorship
source            string   "pittcsc" | "ouckah"
sort              string   "date_desc" (default) | "salary_desc" | "company"
page              int      Default: 1
page_size         int      Default: 25, max: 100
```

**Example Response:**
```json
{
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "company_name": "Stripe",
      "title": "Software Engineering Intern",
      "location": ["Remote", "San Francisco, CA"],
      "is_remote": true,
      "required_grad_year": 2027,
      "grad_year_flexible": true,
      "estimated_salary_low": 50,
      "estimated_salary_high": 55,
      "salary_unit": "hourly",
      "tech_stack": ["python", "ruby", "kubernetes", "postgresql"],
      "sponsors_visa": false,
      "source": "ouckah",
      "date_posted": "2025-07-01T00:00:00Z",
      "ai_extraction_status": "success",
      "url": "https://stripe.com/jobs/..."
    }
  ],
  "pagination": { "page": 1, "page_size": 25, "total": 847 },
  "cache_hit": true
}
```

### `GET /api/jobs/{id}`
Returns full job record including `raw_description` for detail view.

### `GET /api/stats`
Returns: total jobs, breakdown by grad year, breakdown by location, avg salary by tech stack. Cached 15 minutes.

### `POST /api/jobs/refresh`
Admin endpoint (API-key authenticated). Triggers an immediate re-run of the ingestor.

---

## 9. Build Plan — 14-Day Timeline

### Phase 1 — Days 1–2 — Infrastructure & Schema
- Initialize monorepo with `/frontend`, `/api`, `/worker`, `/ingestor` directories
- Write `docker-compose.yml`: PostgreSQL 15, Redis 7, API, Worker, Ingestor containers with health checks
- Write database migration SQL: create `jobs` table with all columns, indexes, and constraints
- Verify all four services start cleanly and can communicate
- Set up `.env` file and `docker-compose` `env_file` configuration

### Phase 2 — Days 3–4 — Ingestor & Deduplication
- Write `ingestor.py` to fetch from both repos:
  - Ouckah: fetch and parse `listings.json` directly
  - PittCSC: fetch README.md, parse Markdown table rows into job objects
- Implement SHA-256 URL hashing and Redis Set membership check (`SISMEMBER`)
- Implement Redis Stream publish (`XADD`) for new, unseen jobs
- Write unit tests: mock HTTP responses, assert Redis calls, assert deduplication
- Run end-to-end: confirm new jobs appear in Stream, re-run ingestor and confirm 0 new messages (dedup works)

### Phase 3 — Days 5–8 — LangChain AI Worker
- Install `langchain`, `langchain-openai`, `pydantic v2`, `sqlalchemy`, `beautifulsoup4`
- Define `JobMetadata` Pydantic model with all fields and `Field()` descriptions
- Implement `scrape_job_page` `@tool` using `httpx` + BeautifulSoup4; handle 404s and timeouts
- Implement `save_to_database` `@tool` using SQLAlchemy with upsert (`ON CONFLICT DO UPDATE`)
- Wire up LangChain ReAct agent with `llm.with_structured_output(JobMetadata)`
- Implement Redis Stream consumer loop: `XREADGROUP` with 5s block, `XACK` on success, mark failed on exception
- Add hallucination guard logic (confidence threshold, year bounds, salary sanity checks)
- Run end-to-end: ingest 5 jobs from each source, confirm worker processes them, inspect PostgreSQL rows
- Set up LangSmith tracing (free tier) for observability

### Phase 4 — Days 9–10 — FastAPI Backend & Caching
- Scaffold FastAPI app with uvicorn; add `/health` endpoint
- Implement `GET /api/jobs` with all query parameters using SQLAlchemy dynamic filter building
- Implement Redis cache layer: hash query params → SHA-256 key, check before DB query, set on miss with 3600s TTL
- Implement `GET /api/stats` with 900s TTL
- Add CORS middleware for `localhost:5173` (Vite dev) and production domain
- Smoke test all endpoints and filter combinations

### Phase 5 — Days 11–12 — React Frontend
- Scaffold React + TypeScript project with Vite; add Tailwind CSS
- Build `JobCard` component: company name, title, location badges, salary chip, grad year badge, tech stack pills
- Build `FilterPanel` component: grad year select, salary range slider, remote toggle, tech stack multi-select, visa toggle
- Implement `useJobs` custom hook: manages filter state, debounced API calls, loading/error states
- Add pagination controls and sort dropdown
- Add empty state and skeleton loading cards

### Phase 6 — Days 13–14 — AWS Deployment
- Create AWS RDS PostgreSQL instance (db.t4g.micro, free tier) — run migration SQL
- Create AWS ElastiCache Redis cluster (cache.t3.micro, free tier)
- Launch EC2 t2.micro; install Docker and docker-compose
- Configure security groups: RDS and ElastiCache accessible only from EC2; EC2 port 8000 open
- Write `docker-compose.prod.yml` with environment variables pointing to RDS and ElastiCache endpoints
- Deploy and smoke-test full pipeline
- Deploy frontend to Vercel (static hosting, free tier)

---

## 10. Infrastructure Notes

### docker-compose.yml Structure

```yaml
services:
  postgres:
    image: postgres:15-alpine
    environment: { POSTGRES_DB: interniq, POSTGRES_USER: ..., POSTGRES_PASSWORD: ... }
    volumes: [postgres_data:/var/lib/postgresql/data]
    healthcheck: { test: pg_isready, interval: 5s, retries: 5 }

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes  # persistence enabled
    volumes: [redis_data:/data]

  api:
    build: ./api
    ports: [8000:8000]
    depends_on: { postgres: { condition: service_healthy } }
    environment: { DATABASE_URL: ..., REDIS_URL: ... }

  worker:
    build: ./worker
    depends_on: [postgres, redis]
    environment: { OPENAI_API_KEY: ..., DATABASE_URL: ..., REDIS_URL: ... }

  ingestor:
    build: ./ingestor
    depends_on: [redis]
    environment: { REDIS_URL: ..., INGEST_INTERVAL_SECONDS: 21600 }
```

### AWS Free Tier Cost Estimate

| Service | Config | Est. Monthly Cost |
|---|---|---|
| EC2 | t2.micro | $0 (free tier) |
| RDS PostgreSQL | db.t4g.micro | $0 (free tier) |
| ElastiCache Redis | cache.t3.micro | $0 (free tier) |
| OpenAI API | gpt-4o-mini | ~$2–5 for ~10,000 jobs |
| Data transfer | ~1GB egress | ~$0.09 |
| **Total** | | **< $6/month** |

---

## 11. Future Expansion

### RAG Resume Matcher
Add a `POST /api/match` endpoint where users upload their PDF resume. Extract text with PyMuPDF, generate embeddings with `text-embedding-3-small`, store in a `pgvector` column on the jobs table. Return top-10 cosine similarity matches as a "Match Score" for each job.

### LangChain Re-Extraction Agent
A second LangChain agent that runs nightly on records with `ai_extraction_status = 'partial'` or `ai_confidence_score < 0.6`. Uses GPT-4o (full model, not mini) with a more detailed prompt to attempt re-extraction and merge with the partial record.

### Discord / Email Alerts
A third consumer group on `jobs:raw` Stream that runs filtering logic before full AI processing. If a raw listing matches a user's saved alert criteria (e.g., "Pittsburgh + Python + 2027"), it immediately fires a Discord webhook — before enrichment, for maximum speed.

### Analytics Dashboard
A second frontend page powered by `GET /api/stats` showing salary distributions by company tier, grad year demand trends over time, and most in-demand tech stacks. Built with Recharts.

---

## 12. Key Engineering Decisions

**FastAPI over Express** — the entire backend is Python (ingestor, worker, API), so FastAPI keeps the stack consistent. Native async, automatic OpenAPI docs, and Pydantic integration with the same schemas used in the worker are significant bonuses.

**GPT-4o-mini over Gemini** — LangChain's `with_structured_output` is most reliably tested with OpenAI function calling. At $0.15/1M input tokens, a 2,000-token job description costs ~$0.0003 — essentially free for this scale.

**LangChain over PydanticAI** — PydanticAI is clean for structured extraction alone. LangChain's ReAct agent enables the multi-step, tool-using loop where the agent retries on scrape failure and makes decisions. LangSmith tracing is a significant operational advantage. The Pydantic model is still used — it's passed to `with_structured_output`.

**Redis Streams over Lists** — message acknowledgment and consumer groups make Streams the correct choice for any production-grade queue. It's also a stronger architectural talking point.

**Monorepo** — a single GitHub repo with `/frontend`, `/api`, `/worker`, `/ingestor` is easier to manage solo and easier for recruiters to explore.
