# MyCRM

A personal CRM with deep AI integration into business logic.

## Stack

- FastAPI / Python 3.12
- PostgreSQL 18
- React 19 / TypeScript / Vite

## Quick start

### Requirements

On Windows, install
[Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/).
It includes Docker Engine, the `docker` command, and modern Docker Compose v2.
You do not need to install the Python `docker-compose` package with `pip`: it
does not install Docker Engine and belongs to the obsolete Compose v1.

After installation, start Docker Desktop, wait until the engine is ready, open
a new PowerShell window, and verify the installation:

```powershell
docker --version
docker compose version
```

### Start the application

1. Create a local environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Replace `change-me` in `.env`, then start the application:

   ```powershell
   docker compose up --build
   ```

After startup:

- UI: <http://localhost:8080>;
- API: <http://localhost:8000>;
- OpenAPI: <http://localhost:8000/docs>;
- liveness: <http://localhost:8000/api/v1/health/live>;
- readiness: <http://localhost:8000/api/v1/health/ready>.

## Development

The backend and frontend live in separate directories:

```text
backend/   FastAPI, SQLAlchemy, Alembic, pytest
frontend/  React, TypeScript, Vite
docs/      project plan and architecture decisions
```

Detailed plan: [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md).

Educational explanation of the implemented foundation:
[about/STAGE_0_FOUNDATION.md](about/STAGE_0_FOUNDATION.md).

Accepted decisions:

- [ADR 0001: modular monolith](docs/adr/0001-modular-monolith.md);
- [ADR 0002: AI safety boundary](docs/adr/0002-ai-safety-boundary.md).
