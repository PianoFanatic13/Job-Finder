# InternIQ

A distributed, AI-powered internship aggregator that pulls job listings from various sources into a single, enriched, filterable set.

## Check it Out!

https://job-finder-dun-beta.vercel.app/

## Overview

SWE Internship market is cooked and hyper-competitive. There's too many sources where students have to look through like GitHub repos, corporate career portals, aggregator sites like LinkedIn, etc. And many of them don't surface key metadata that's important to know before even considering applying, such as required grad year, visa sponsorship requirements, etc,

InternIQ solves this by ingesting listings from open-source community repositories, then running each posting through an AI agent that extracts structured metadata from the raw job description. The result is a clean, queryable database of internships exposed via a fast filterable dashboard, and allow candidates to filter by graduation year, hourly pay, tech stack, sponsorship, and location in ways no other internship board supports.

The system is built as four loosely-coupled microservices coordinating through Redis (for queuing and deduplication) and PostgreSQL (for persisted state), all deployed on AWS free-tier infrastructure with a static frontend on Vercel.

_This system is still in an early stage. More sources for listings will pteontailly be added in the future for more listing diversity_

## Architecture

```
GitHub sources ──► Ingestor ──► Redis Stream ──► Worker (LangChain)
                                                       │
                                                       ▼
                                                  PostgreSQL ──► API ──► Frontend
```

| Service      | Role                                                                                                                                                                                       |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Ingestor** | Polls community GitHub repos every 6 hours, normalizes listings, deduplicates URLs via SHA-256 hashing in a Redis Set, and publishes new jobs to a Redis Stream.                           |
| **Worker**   | Consumes the Redis Stream, scrapes each job URL, and uses a LangChain agent backed by Groq's LLM to extract structured metadata. Persists results to PostgreSQL with hallucination guards. |
| **API**      | FastAPI service exposing filterable, paginated endpoints. Caches query results in Redis with a 1-hour TTL to reduce database load.                                                         |
| **Frontend** | React + TypeScript dashboard with filter controls, paginated job cards, and a detail panel. Deployed to Vercel;                                                                            |

## Features

- AI-powered metadata extraction (graduation year, estimated pay, tech stack, visa sponsorship)
- Multi-criteria filtering: grad year, pay range, tech stack , location, remote-only, visa sponsorship, source
- Deduplication via SHA-256 URL hashing in a Redis Set (fast lookups)
- At-least-once delivery via Redis Streams with consumer groups and message acknowledgment
- 1-hour query result caching to reduce PostgreSQL load
- Hallucination guards: confidence threshold filtering, grad year sanity bounds, pay unit checks, tech stack normalization
- Three sort modes: most recent, highest pay, alphabetical by company

## Tech Stack

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, React Query, Framer Motion, Axios
- **API:** Python, FastAPI, Uvicorn, SQLAlchemy
- **Worker:** Python, LangChain, LangGraph, Groq, BeautifulSoup, httpx
- **Ingestor:** Python, httpx, Pydantic
- **Data:** PostgreSQL, Redis
- **Infra:** Docker, Docker Compose

## Deployment Architecture

| Component     | Service                                | Notes                                                                |
| ------------- | -------------------------------------- | -------------------------------------------------------------------- |
| Backend host  | AWS EC2 `t2.micro`                     | Runs api, worker, and ingestor as Docker containers.                 |
| Database      | AWS RDS PostgreSQL `db.t4g.micro`      | Managed PostgreSQL instance.                                         |
| Cache & queue | AWS ElastiCache Redis `cache.t3.micro` | Managed Redis for deduplication, work queue, and API response cache. |
| Frontend      | Vercel (static hosting)                | Vite build deployed to Vercel; proxies API calls to EC2.             |

## Repository Layout

```
.
├── frontend/                       React + TypeScript dashboard (deployed to Vercel)
├── api/                            FastAPI REST service
├── worker/                         LangChain AI extraction worker
├── ingestor/                       Scheduled GitHub source fetcher
├── infra/migrations/               PostgreSQL schema migrations
└── docker-compose.prod.yml         Production compose (api/worker/ingestor only — managed AWS services for data)
```

## Roadmap

Future or potential features:

- **More sources for job listings** - Currently uses two main repos for internship listings, Pitt CSC and Vansh. However it's recognized that there's a lot of jobs not posted on these repos and posted elsewhere like LinkedIn and Handshake. Scraping from those sites is definitely a challenge due to their anti-botting safeguards. Nonetheless we will try 😅
- **RAG resume matcher** — Find most similar jobs based on uploaded resume
- **Nightly re-extraction agent** — A scheduled job that re-runs the LangChain agent on records flagged as `partial` or with low confidence scores, using a stronger model.
- **ReAct agent migration for failure mode processing** — Move from the current single-shot extraction loop to a full ReAct agent that can reason about scrape failures, retry with different URL variations, and self-correct job data when extraction confidence is low.
- **Analytics dashboard page** — Dasboard page showing things like salary distributions, grad year demand trends, and most in-demand tech stacks.
