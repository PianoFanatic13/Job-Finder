# Job Finder

InternIQ is a distributed, AI-powered internship job aggregator. It ingests listings from community sources, then uses an AI agent to validate job links, detect stale or removed postings, and extract key details from job descriptions for frontend filtering.

## Status

In Progress

## What This Project Includes

- Ingestor service for pulling and normalizing job listings
- API service for health checks and data access
- Worker service that runs an AI agent to check listing validity and extract filterable metadata
- Local infrastructure with PostgreSQL and Redis via Docker Compose
- Frontend workspace for the dashboard application

## Tech Stack

- Python
- FastAPI
- PostgreSQL
- Redis
- Docker
- TypeScript and React

## Tools and Frameworks

- Pydantic
- SQLAlchemy
- httpx
- LangChain

## Repository Layout

- frontend
- api
- worker
- ingestor
- infra
