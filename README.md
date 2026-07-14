# MyCRM

Персональная CRM с глубокой интеграцией ИИ в бизнес-логику.

## Стек

- FastAPI / Python 3.12
- PostgreSQL 18
- React 19 / TypeScript / Vite

## Быстрый запуск

1. Установите Docker Desktop.
2. Создайте локальный файл окружения:

   ```powershell
   Copy-Item .env.example .env
   ```

3. Замените `change-me` в `.env` и запустите приложение:

   ```powershell
   docker compose up --build
   ```

После запуска:

- интерфейс: <http://localhost:8080>;
- API: <http://localhost:8000>;
- OpenAPI: <http://localhost:8000/docs>;
- liveness: <http://localhost:8000/api/v1/health/live>;
- readiness: <http://localhost:8000/api/v1/health/ready>.

## Разработка

Backend и frontend находятся в отдельных каталогах:

```text
backend/   FastAPI, SQLAlchemy, Alembic, pytest
frontend/  React, TypeScript, Vite
docs/      план и архитектурные решения
```

Подробный план: [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md).

Учебное объяснение реализованного фундамента:
[about/STAGE_0_FOUNDATION.md](about/STAGE_0_FOUNDATION.md).

Принятые решения:

- [ADR 0001: модульный монолит](docs/adr/0001-modular-monolith.md);
- [ADR 0002: граница безопасности ИИ](docs/adr/0002-ai-safety-boundary.md).
