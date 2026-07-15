# MyCRM

A production-oriented CRM with deep AI integration into business logic. The
project is designed both as a useful product and as a publicly accessible
portfolio demonstration of backend, frontend, data, AI, and operational
engineering practices.

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

## Production blueprint

The repository includes [render.yaml](render.yaml) for a managed deployment of
the React static site, FastAPI service, and private PostgreSQL database. Before
creating the Render Blueprint, replace the placeholder `onrender.com` service
names in that file if different names will be used.

The API validates production settings at startup and refuses local database
addresses, fallback passwords, short application secrets, wildcard hosts, and
non-HTTPS CORS origins. Database migrations run in the platform's pre-deploy
step rather than in every API process.

No live portfolio URL is published yet. Deployment, monitoring, and backup
restoration must be verified before the public-demo link is added here.

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

Public-production and demo architecture:
[about/STAGE_0_5_PUBLIC_PRODUCTION.md](about/STAGE_0_5_PUBLIC_PRODUCTION.md).

Accepted decisions:

- [ADR 0001: modular monolith](docs/adr/0001-modular-monolith.md);
- [ADR 0002: AI safety boundary](docs/adr/0002-ai-safety-boundary.md);
- [ADR 0003: workspace isolation](docs/adr/0003-workspace-isolation.md);
- [ADR 0004: public demo mode](docs/adr/0004-public-demo-mode.md);
- [ADR 0005: managed production deployment](docs/adr/0005-managed-production-deployment.md).
