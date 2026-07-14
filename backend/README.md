# MyCRM API

Backend приложения на FastAPI.

## Локальный запуск

Из корня проекта:

```powershell
Copy-Item .env.example .env
docker compose up -d db
cd backend
uv sync --dev
uv run alembic upgrade head
uv run fastapi dev
```

API будет доступен по адресу <http://localhost:8000>, документация —
<http://localhost:8000/docs>.
