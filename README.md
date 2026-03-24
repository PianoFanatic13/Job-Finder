# InternIQ - Phase 1 Setup

This workspace contains the Phase 1 foundation for InternIQ:

- Monorepo folders: `frontend`, `api`, `worker`, `ingestor`
- Local infrastructure via Docker Compose: PostgreSQL 15 + Redis 7
- Initial database migration mounted into PostgreSQL init directory
- Service stubs for API, worker, and ingestor so all services can boot and communicate

## 1. Prerequisites

- Docker Desktop
- Docker Compose (included with Docker Desktop)

## 2. Create local env file

Copy `.env.example` to `.env`.

On PowerShell:

```powershell
Copy-Item .env.example .env
```

## 3. Start all services

```powershell
docker compose up --build
```

## 4. Verify health

- API health endpoint: `http://localhost:8000/health`
- API root endpoint: `http://localhost:8000/`

A healthy response should report both `postgres` and `redis` as `ok`.

## 5. Stop services

```powershell
docker compose down
```

Use the command below to also remove volumes if you need a clean DB reset:

```powershell
docker compose down -v
```
