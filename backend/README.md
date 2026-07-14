# MyCRM API

The FastAPI backend of the application.

## Local development

From the project root:

```powershell
Copy-Item .env.example .env
docker compose up -d db
cd backend
uv sync --dev
uv run alembic upgrade head
uv run fastapi dev
```

The API will be available at <http://localhost:8000>, and its documentation at
<http://localhost:8000/docs>.
