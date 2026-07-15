# Карта файлов и связей MyCRM

> Снимок текущего, в том числе незавершённого, состояния проекта на 15 июля 2026 года.
> Карта построена по фактическим импортам, настройкам запуска, Docker/CI-конфигурации,
> миграциям и тестам. Каталоги зависимостей и кэши (`.git/`, `.venv/`,
> `node_modules/`, `.pnpm-store/`, `.mypy_cache/`, `dist/`, `__pycache__/`) не
> перечислены пофайлово: это генерируемые файлы, а не исходники проекта.

## 1. Откуда всё начинается

```text
ПОЛЬЗОВАТЕЛЬ / РАЗРАБОТЧИК / CI / RENDER
│
├─ Локальный полный запуск
│  └─ compose.yaml
│     ├─ .env (локальные секреты, игнорируется Git)
│     ├─ .env.example (образец переменных)
│     ├─ db: postgres:18-alpine ───────────────────────────────────────┐
│     ├─ api: backend/Dockerfile                                      │
│     │  ├─ backend/pyproject.toml                                    │
│     │  ├─ backend/uv.lock                                           │
│     │  ├─ backend/alembic.ini                                       │
│     │  ├─ backend/alembic/** ── миграции ───────────────────────────┤
│     │  └─ backend/src/mycrm/main.py ── FastAPI ─────────────────────┤
│     └─ web: frontend/Dockerfile                                     │
│        ├─ frontend/package.json + pnpm-lock.yaml                     │
│        ├─ Vite собирает frontend/src/**                             │
│        └─ frontend/nginx.conf                                       │
│           ├─ / → собранный React                                   │
│           └─ /api/* → api:8000 ─────────────────────────────────────┘
│
├─ Backend отдельно
│  ├─ backend/pyproject.toml: mycrm.main:app
│  └─ backend/src/mycrm/main.py
│     ├─ core/config.py ── читает MYCRM_* и проверяет production
│     ├─ core/logging.py ── JSON-логи
│     ├─ TrustedHost + CORS
│     ├─ core/middleware.py ── request ID, размер запроса, rate limit
│     ├─ core/errors.py ── единый JSON ошибок
│     └─ api.py ── общий префикс /api/v1
│        ├─ modules/health/api.py
│        │  ├─ GET /health/live
│        │  └─ GET /health/ready ── core/database.py ── PostgreSQL
│        ├─ modules/identity/api.py
│        │  ├─ POST /auth/register
│        │  ├─ POST /auth/login
│        │  ├─ POST /auth/logout
│        │  └─ GET /auth/me
│        │     ├─ identity/dependencies.py ── cookie → текущий User
│        │     ├─ identity/application.py ── auth use cases
│        │     ├─ identity/security.py ── Argon2id + session token hash
│        │     ├─ identity/models.py ── users, auth_sessions
│        │     └─ workspaces/models.py ── workspace при регистрации
│        ├─ modules/workspaces/api.py
│        │  ├─ GET /demo/capabilities
│        │  ├─ GET /workspaces
│        │  └─ GET /workspaces/current
│        │     ├─ identity/dependencies.py ── аутентификация
│        │     ├─ workspaces/dependencies.py ── X-Workspace-ID
│        │     ├─ workspaces/application.py ── проверка membership
│        │     ├─ workspaces/domain.py ── trusted WorkspaceContext
│        │     ├─ workspaces/models.py ── workspaces/memberships/demo
│        │     └─ workspaces/policy.py ── запрет внешних side effects demo
│        ├─ modules/companies/api.py
│        │  └─ companies/application.py
│        │     ├─ companies/models.py ── companies
│        │     ├─ crm_shared.py ── статусы и общие ошибки
│        │     └─ workspaces/domain.py ── scope + право записи
│        └─ modules/contacts/api.py
│           └─ contacts/application.py
│              ├─ contacts/models.py ── contacts
│              ├─ companies/models.py ── проверка связанной компании
│              ├─ crm_shared.py
│              └─ workspaces/domain.py
│
├─ Frontend отдельно
│  ├─ frontend/package.json: pnpm dev/build/lint/typecheck
│  ├─ frontend/vite.config.ts ── dev server и /api proxy
│  └─ frontend/index.html
│     └─ frontend/src/main.tsx
│        ├─ frontend/src/styles.css
│        └─ frontend/src/App.tsx
│           └─ GET /api/v1/health/live ── backend health API
│
├─ Миграции базы
│  └─ backend/alembic.ini
│     └─ backend/alembic/env.py
│        ├─ core/config.py + core/database.py
│        ├─ импорт всех modules/*/models.py → Base.metadata
│        └─ backend/alembic/versions/
│           ├─ 20260714_0001_initial.py
│           └─ 0001 → 0002 → 0003 → 0004 → 0005 (строгая цепочка)
│
├─ Автоматическая проверка
│  └─ .github/workflows/ci.yml
│     ├─ backend: uv.lock → lint → types → migrate → pytest → rollback/upgrade
│     ├─ frontend: pnpm-lock.yaml → lint → typecheck → build
│     └─ container-smoke: compose.yaml → GET /api/v1/health/ready
│
└─ Production
   └─ render.yaml
      ├─ backend/Dockerfile + preDeploy Alembic
      ├─ managed PostgreSQL
      └─ frontend static build + VITE_API_URL → production API
```

## 2. Полное дерево проектных файлов

Обозначения: `[RUN]` — участвует во время выполнения; `[BUILD]` — сборка или
развёртывание; `[TEST]` — проверка; `[DOC]` — документация/решение; `[META]` —
настройка репозитория; `[PKG]` — файл-маркер Python-пакета.

```text
MyCRM/
├─ .editorconfig                                      [META]
├─ .env                                               [RUN, local, gitignored]
├─ .env.example                                       [RUN, template]
├─ .gitignore                                         [META]
├─ .github/
│  └─ workflows/
│     └─ ci.yml                                       [TEST, BUILD]
├─ PROJECT_FILE_MAP.md                                [DOC, эта карта]
├─ README.md                                          [DOC]
├─ compose.yaml                                       [RUN, BUILD]
├─ render.yaml                                        [BUILD, production]
├─ about/
│  ├─ STAGE_0_FOUNDATION.md                           [DOC]
│  ├─ STAGE_0_5_PUBLIC_PRODUCTION.md                  [DOC]
│  └─ STAGE_1_CRM_CORE.md                             [DOC]
├─ docs/
│  ├─ PROJECT_PLAN.md                                 [DOC]
│  └─ adr/
│     ├─ 0001-modular-monolith.md                     [DOC]
│     ├─ 0002-ai-safety-boundary.md                   [DOC]
│     ├─ 0003-workspace-isolation.md                  [DOC]
│     ├─ 0004-public-demo-mode.md                     [DOC]
│     └─ 0005-managed-production-deployment.md        [DOC]
├─ backend/
│  ├─ .dockerignore                                   [BUILD]
│  ├─ Dockerfile                                      [BUILD, RUN]
│  ├─ README.md                                       [DOC]
│  ├─ alembic.ini                                     [BUILD, RUN]
│  ├─ pyproject.toml                                  [BUILD, RUN, TEST]
│  ├─ uv.lock                                         [BUILD, RUN, TEST]
│  ├─ alembic/
│  │  ├─ env.py                                       [RUN]
│  │  ├─ script.py.mako                               [BUILD]
│  │  └─ versions/
│  │     ├─ 20260714_0001_initial.py                  [RUN]
│  │     ├─ 20260715_0002_workspace_foundation.py     [RUN]
│  │     ├─ 20260715_0003_authentication.py           [RUN]
│  │     ├─ 20260715_0004_contacts_companies.py       [RUN]
│  │     └─ 20260715_0005_align_model_constraints.py  [RUN]
│  ├─ src/
│  │  └─ mycrm/
│  │     ├─ __init__.py                               [PKG]
│  │     ├─ main.py                                   [RUN, backend entry]
│  │     ├─ api.py                                    [RUN, router root]
│  │     ├─ core/
│  │     │  ├─ __init__.py                            [PKG]
│  │     │  ├─ config.py                              [RUN]
│  │     │  ├─ database.py                            [RUN]
│  │     │  ├─ errors.py                              [RUN]
│  │     │  ├─ logging.py                             [RUN]
│  │     │  └─ middleware.py                          [RUN]
│  │     └─ modules/
│  │        ├─ __init__.py                            [PKG]
│  │        ├─ crm_shared.py                          [RUN]
│  │        ├─ health/
│  │        │  ├─ __init__.py                         [PKG]
│  │        │  └─ api.py                              [RUN]
│  │        ├─ identity/
│  │        │  ├─ __init__.py                         [PKG]
│  │        │  ├─ api.py                              [RUN]
│  │        │  ├─ application.py                      [RUN]
│  │        │  ├─ dependencies.py                     [RUN]
│  │        │  ├─ models.py                           [RUN]
│  │        │  └─ security.py                         [RUN]
│  │        ├─ workspaces/
│  │        │  ├─ __init__.py                         [PKG]
│  │        │  ├─ api.py                              [RUN]
│  │        │  ├─ application.py                      [RUN]
│  │        │  ├─ dependencies.py                     [RUN]
│  │        │  ├─ domain.py                           [RUN]
│  │        │  ├─ models.py                           [RUN]
│  │        │  └─ policy.py                           [RUN]
│  │        ├─ companies/
│  │        │  ├─ __init__.py                         [PKG]
│  │        │  ├─ api.py                              [RUN]
│  │        │  ├─ application.py                      [RUN]
│  │        │  └─ models.py                           [RUN]
│  │        └─ contacts/
│  │           ├─ __init__.py                         [PKG]
│  │           ├─ api.py                              [RUN]
│  │           ├─ application.py                      [RUN]
│  │           └─ models.py                           [RUN]
│  └─ tests/
│     ├─ test_config.py                               [TEST]
│     ├─ test_health.py                               [TEST]
│     ├─ test_identity_security.py                    [TEST]
│     ├─ test_public_safety.py                        [TEST]
│     └─ integration/
│        ├─ __init__.py                               [PKG]
│        ├─ conftest.py                               [TEST]
│        ├─ test_auth_workspace.py                    [TEST]
│        └─ test_contacts_companies.py                [TEST]
└─ frontend/
   ├─ .dockerignore                                   [BUILD]
   ├─ Dockerfile                                      [BUILD, RUN]
   ├─ README.md                                       [DOC]
   ├─ eslint.config.js                                [TEST]
   ├─ index.html                                      [RUN, frontend entry]
   ├─ nginx.conf                                      [RUN]
   ├─ package.json                                    [BUILD, RUN, TEST]
   ├─ pnpm-lock.yaml                                  [BUILD, RUN, TEST]
   ├─ pnpm-workspace.yaml                             [BUILD]
   ├─ tsconfig.app.json                               [BUILD, TEST]
   ├─ tsconfig.json                                   [BUILD, TEST]
   ├─ tsconfig.node.json                              [BUILD, TEST]
   ├─ vite.config.ts                                  [BUILD, RUN]
   └─ src/
      ├─ App.tsx                                      [RUN]
      ├─ main.tsx                                     [RUN]
      ├─ styles.css                                   [RUN]
      └─ vite-env.d.ts                                [BUILD, TEST]
```

## 3. Что делает каждый файл

### Корень и инфраструктура

- **`.editorconfig`** — задаёт UTF-8, LF, финальную новую строку и размеры
  отступов для Python, TypeScript, YAML, Markdown и других форматов.
- **`.env`** — фактические локальные переменные и секреты. Его читает
  `core/config.py`, а Compose подставляет из него параметры PostgreSQL; файл не
  должен попадать в Git, и его значения в этой карте намеренно не раскрываются.
- **`.env.example`** — безопасный шаблон всех основных `MYCRM_*`, PostgreSQL и
  `VITE_API_URL` переменных для создания локального `.env`.
- **`.gitignore`** — не даёт закоммитить секреты, окружения, зависимости, кэши,
  результаты сборки, IDE-файлы и логи.
- **`.github/workflows/ci.yml`** — запускает три CI-ветки: строгие backend
  проверки с PostgreSQL и полным циклом миграций, frontend lint/typecheck/build
  и smoke-тест собранных Docker-контейнеров.
- **`PROJECT_FILE_MAP.md`** — этот документ: навигационная карта текущих файлов,
  путей выполнения и связей проекта.
- **`README.md`** — главная инструкция проекта: назначение, стек, Docker-старт,
  адреса сервисов, production blueprint и ссылки на подробную документацию.
- **`compose.yaml`** — локально связывает `db`, `api` и `web`; ждёт healthcheck
  базы, применяет миграции, запускает FastAPI и публикует nginx на порту 8080.
- **`render.yaml`** — production blueprint для отдельного Docker API, статического
  frontend и managed PostgreSQL; миграции выполняются перед деплоем API.

### Объяснения, план и архитектурные решения

- **`about/STAGE_0_FOUNDATION.md`** — учебное объяснение фундамента: стек,
  структура, FastAPI, БД, ошибки, middleware, frontend, Docker, CI и диагностика.
- **`about/STAGE_0_5_PUBLIC_PRODUCTION.md`** — описание workspace-изоляции,
  публичного demo threat model, production-конфигурации, деплоя и ограничений.
- **`about/STAGE_1_CRM_CORE.md`** — состояние Stage 1: аутентификация, сессии,
  компании, контакты, optimistic locking, архивирование, API и оставшиеся шаги.
- **`docs/PROJECT_PLAN.md`** — общий продуктовый и технический roadmap от CRM-core
  до событий, AI/RAG, интеграций и контролируемых агентов.
- **`docs/adr/0001-modular-monolith.md`** — фиксирует выбор модульного монолита
  вместо преждевременных микросервисов.
- **`docs/adr/0002-ai-safety-boundary.md`** — запрещает AI напрямую изменять данные:
  изменения должны проходить через валидируемые application-команды.
- **`docs/adr/0003-workspace-isolation.md`** — закрепляет обязательный
  `workspace_id`, проверку доступа и защиту от cross-workspace чтения/связей.
- **`docs/adr/0004-public-demo-mode.md`** — требует синтетические, сбрасываемые
  demo-данные и запрет опасных внешних действий.
- **`docs/adr/0005-managed-production-deployment.md`** — выбирает первый managed
  production с раздельными web/API/database сервисами.

### Backend: упаковка, запуск и миграции

- **`backend/.dockerignore`** — уменьшает и защищает Docker build context,
  исключая тесты, локальные окружения, кэши, логи и env-файлы.
- **`backend/Dockerfile`** — строит Python 3.12 образ, устанавливает `uv`,
  воспроизводимо ставит lock-зависимости, копирует Alembic и приложение, затем
  по умолчанию запускает FastAPI на 8000.
- **`backend/README.md`** — краткая инструкция отдельной разработки API с `uv`,
  PostgreSQL, Alembic и FastAPI dev server.
- **`backend/pyproject.toml`** — манифест Python-пакета и единый источник команд,
  зависимостей и строгих настроек FastAPI, pytest, Ruff и mypy; объявляет entry
  point `mycrm.main:app`.
- **`backend/uv.lock`** — точные версии всего Python dependency graph для
  одинаковой установки локально, в CI и Docker; вручную обычно не редактируется.
- **`backend/alembic.ini`** — указывает Alembic каталог миграций, добавляет `src`
  в Python path и настраивает вывод логов.
- **`backend/alembic/env.py`** — runtime Alembic: берёт URL из `Settings`, импортирует
  все ORM-модели в `Base.metadata` и запускает async online или offline миграции.
- **`backend/alembic/script.py.mako`** — шаблон, по которому Alembic генерирует
  новые revision-файлы с `upgrade()` и `downgrade()`.
- **`backend/alembic/versions/20260714_0001_initial.py`** — пустой базовый revision,
  открывающий историю схемы.
- **`backend/alembic/versions/20260715_0002_workspace_foundation.py`** — создаёт
  `users`, `workspaces`, `workspace_memberships`, `demo_sessions`, их ключи,
  ограничения и индексы.
- **`backend/alembic/versions/20260715_0003_authentication.py`** — добавляет password
  hash, статус membership и таблицу отзываемых `auth_sessions`.
- **`backend/alembic/versions/20260715_0004_contacts_companies.py`** — создаёт
  workspace-scoped `companies` и `contacts`; составной внешний ключ не позволяет
  контакту ссылаться на компанию другого workspace.
- **`backend/alembic/versions/20260715_0005_align_model_constraints.py`** — выравнивает
  nullability timestamp-полей и длину статуса workspace с ORM-инвариантами.

### Backend: точка входа и общее ядро

- **`backend/src/mycrm/__init__.py`** — объявляет `mycrm` Python-пакетом и содержит
  его короткое описание.
- **`backend/src/mycrm/main.py`** — главная точка backend: создаёт FastAPI app,
  включает docs, логирование, TrustedHost, CORS, request middleware, handlers и
  общий router; при остановке освобождает database engine.
- **`backend/src/mycrm/api.py`** — собирает health, identity, workspaces, companies
  и contacts routers под единым префиксом `/api/v1`.
- **`backend/src/mycrm/core/__init__.py`** — маркер пакета общей инфраструктуры.
- **`backend/src/mycrm/core/config.py`** — типизированно читает настройки, переводит
  Render PostgreSQL URL на asyncpg и fail-closed отклоняет небезопасный production.
- **`backend/src/mycrm/core/database.py`** — создаёт общий async SQLAlchemy engine,
  declarative `Base`, session factory и FastAPI dependency с commit/rollback.
- **`backend/src/mycrm/core/errors.py`** — формирует единый JSON-контракт ошибок и
  регистрирует handlers для HTTP, validation и неожиданных исключений.
- **`backend/src/mycrm/core/logging.py`** — форматирует структурированные JSON-логи
  с временем, request ID, HTTP-полями и stack trace.
- **`backend/src/mycrm/core/middleware.py`** — назначает/возвращает request ID,
  ограничивает declared body size и частоту API-запросов, измеряет время и логирует
  ответ. Rate limiter пока in-memory и рассчитан на один API instance.

### Backend: модульные пакеты и общие CRM-правила

- **`backend/src/mycrm/modules/__init__.py`** — маркер корневого пакета бизнес-модулей.
- **`backend/src/mycrm/modules/crm_shared.py`** — общий статус active/archived,
  исключения not-found/version/write/relationship, проверка права записи и
  экранирование SQL `LIKE` поиска для contacts/companies.
- **`backend/src/mycrm/modules/health/__init__.py`** — маркер health-пакета.
- **`backend/src/mycrm/modules/health/api.py`** — предоставляет liveness с метаданными
  сервиса и readiness, который выполняет `SELECT 1` через database session.

### Backend: identity

- **`backend/src/mycrm/modules/identity/__init__.py`** — маркер identity-пакета.
- **`backend/src/mycrm/modules/identity/api.py`** — HTTP-контракт регистрации,
  login/logout/me; преобразует domain-ошибки в HTTP и управляет HttpOnly session
  cookie с production-флагом Secure.
- **`backend/src/mycrm/modules/identity/application.py`** — регистрирует пользователя
  вместе с private owner workspace, проверяет credentials, создаёт hash-only
  сессии, разрешает cookie-сессию и отзывает её при logout.
- **`backend/src/mycrm/modules/identity/dependencies.py`** — достаёт session cookie,
  разрешает `(User, AuthSession)`, выдаёт 401 при ошибке и предоставляет типы
  `CurrentIdentity`/`CurrentUser` для защищённых endpoints.
- **`backend/src/mycrm/modules/identity/models.py`** — ORM-схема `User` и
  `AuthSession`, включая статусы, timestamps, expiry, revoke и индексы.
- **`backend/src/mycrm/modules/identity/security.py`** — Argon2id hash/verify паролей,
  dummy verify против timing leak, генерация случайного token и keyed hash токена.

### Backend: workspaces и demo boundary

- **`backend/src/mycrm/modules/workspaces/__init__.py`** — маркер workspaces-пакета.
- **`backend/src/mycrm/modules/workspaces/api.py`** — API demo capabilities, списка
  доступных workspaces и текущего trusted context.
- **`backend/src/mycrm/modules/workspaces/application.py`** — выбирает только
  активные memberships, проверяет принадлежность пользователя workspace и отдельно
  разрешает включённый demo workspace.
- **`backend/src/mycrm/modules/workspaces/dependencies.py`** — соединяет текущего
  пользователя, database session и заголовок `X-Workspace-ID` в trusted
  `CurrentWorkspace`; недоступный workspace скрывается как 404.
- **`backend/src/mycrm/modules/workspaces/domain.py`** — перечисления kind/status/role,
  immutable `WorkspaceContext`, вычисление `can_write` и assert против выхода за scope.
- **`backend/src/mycrm/modules/workspaces/models.py`** — ORM-таблицы `Workspace`,
  `WorkspaceMembership` и `DemoSession` со статусами, ролями, FK и индексами.
- **`backend/src/mycrm/modules/workspaces/policy.py`** — единая политика внешних
  side effects: запрещает email/calendar/webhook/export/automation для demo и
  любого context без права записи.

### Backend: companies

- **`backend/src/mycrm/modules/companies/__init__.py`** — маркер companies-пакета.
- **`backend/src/mycrm/modules/companies/api.py`** — CRUD-подобные endpoints create,
  list/search/sort, get, versioned patch и soft-delete/archive; ставит ETag и
  переводит application-ошибки в 403/404/409.
- **`backend/src/mycrm/modules/companies/application.py`** — чистит входные поля,
  всегда фильтрует по workspace, считает страницы, сортирует и обновляет/архивирует
  через optimistic locking по `version`.
- **`backend/src/mycrm/modules/companies/models.py`** — ORM `Company` с обязательным
  `workspace_id`, индексами поиска, status, version и timestamps; составная
  уникальность `(workspace_id, id)` поддерживает безопасную связь контактов.

### Backend: contacts

- **`backend/src/mycrm/modules/contacts/__init__.py`** — маркер contacts-пакета.
- **`backend/src/mycrm/modules/contacts/api.py`** — endpoints create, page/filter,
  get, versioned patch и archive; использует `CurrentWorkspace`, ETag и общий
  перевод business errors в HTTP.
- **`backend/src/mycrm/modules/contacts/application.py`** — проверяет, что выбранная
  компания существует в том же workspace, выполняет scoped поиск/фильтрацию,
  обновление и архивирование с optimistic locking.
- **`backend/src/mycrm/modules/contacts/models.py`** — ORM `Contact`; хранит имя,
  email, phone, должность, optional company, status/version и enforcing составной
  FK, который блокирует cross-workspace связь даже при обходе application layer.

### Backend: тесты

- **`backend/tests/test_config.py`** — проверяет нормализацию PostgreSQL URL и
  fail-closed правила безопасного production config.
- **`backend/tests/test_health.py`** — проверяет liveness, наличие request ID и
  единый JSON для 404.
- **`backend/tests/test_identity_security.py`** — проверяет Argon2id, случайность
  session tokens и то, что хранится детерминированный hash, а не сам token.
- **`backend/tests/test_public_safety.py`** — проверяет лимит body, безопасные demo
  capabilities, запрет demo side effects и workspace scope assertion.
- **`backend/tests/integration/__init__.py`** — маркер пакета integration-тестов.
- **`backend/tests/integration/conftest.py`** — создаёт PostgreSQL `AsyncSession` для
  каждого теста и полностью откатывает внешнюю транзакцию после него; без test URL
  интеграционные тесты пропускаются.
- **`backend/tests/integration/test_auth_workspace.py`** — проверяет регистрацию с
  owner workspace, изоляцию пользователей, hash-only session и полный auth/workspace
  HTTP flow с dependency overrides.
- **`backend/tests/integration/test_contacts_companies.py`** — проверяет scope чтения,
  запрет cross-workspace company relation на двух слоях, viewer read-only,
  фильтрацию, optimistic locking и полный companies/contacts HTTP flow.

### Frontend

- **`frontend/.dockerignore`** — исключает зависимости, build output, кэши, env и
  лишнюю документацию из frontend Docker context.
- **`frontend/Dockerfile`** — в Node 24 ставит pinned pnpm-зависимости и собирает
  Vite bundle, затем переносит `dist` и nginx config в минимальный runtime-образ.
- **`frontend/README.md`** — кратко описывает `pnpm install`, dev server и `/api` proxy.
- **`frontend/eslint.config.js`** — строгие type-aware TypeScript правила плюс
  React Hooks и React Refresh; игнорирует `dist`.
- **`frontend/index.html`** — HTML-точка входа: metadata, `#root` и загрузка
  `/src/main.tsx`. Текст description сейчас выглядит повреждённым кодировкой.
- **`frontend/nginx.conf`** — раздаёт SPA, fallback на `index.html` и проксирует
  `/api/` в Compose-сервис `api:8000` с proxy headers.
- **`frontend/package.json`** — объявляет React/Vite/TypeScript зависимости и
  команды dev, build, lint, preview, typecheck.
- **`frontend/pnpm-lock.yaml`** — фиксирует точные версии всего Node dependency
  graph для воспроизводимой локальной, CI и Docker установки.
- **`frontend/pnpm-workspace.yaml`** — объявляет текущую папку единственным pnpm
  workspace и разрешает build script `esbuild`.
- **`frontend/tsconfig.json`** — корневой TypeScript project references-файл,
  объединяющий browser app и Node tooling configurations.
- **`frontend/tsconfig.app.json`** — строгая TypeScript-конфигурация React-кода из
  `src`, DOM libraries, JSX transform и запрет emit/unused/fallthrough.
- **`frontend/tsconfig.node.json`** — строгая конфигурация Vite и ESLint config,
  работающих в Node-среде.
- **`frontend/vite.config.ts`** — включает React plugin, поднимает dev server на
  5173 и проксирует `/api` на `VITE_PROXY_TARGET` или localhost:8000.
- **`frontend/src/App.tsx`** — текущий стартовый экран: при mount запрашивает
  `/api/v1/health/live`, показывает checking/online/offline и версию API. Полноценный
  UI auth/companies/contacts пока не реализован; видимый русский текст сейчас
  выглядит повреждённым кодировкой.
- **`frontend/src/main.tsx`** — React entry: находит `#root`, включает StrictMode,
  подключает `App` и глобальные стили.
- **`frontend/src/styles.css`** — вся текущая responsive-вёрстка стартового экрана,
  цветовая тема и состояния health-индикатора.
- **`frontend/src/vite-env.d.ts`** — подключает типы Vite и типизирует optional
  compile-time переменную `VITE_API_URL`.

## 4. Главные сквозные сценарии

### Открытие страницы

```text
Browser → nginx (production/Compose) или Vite (dev)
        → index.html → main.tsx → App.tsx
        → GET /api/v1/health/live
        → main.py → middleware.py → api.py → health/api.py
        → JSON status/version → индикатор frontend
```

### Регистрация, вход и выбор workspace

```text
POST /auth/register
→ identity/api.py → identity/application.py
→ identity/security.py (password hash)
→ identity/models.py (User)
→ workspaces/models.py (private Workspace + owner Membership)
→ core/database.py (commit)

POST /auth/login
→ identity/application.py → security.py
→ AuthSession в БД + opaque HttpOnly cookie пользователю

GET /workspaces/current + cookie + X-Workspace-ID
→ identity/dependencies.py → workspaces/dependencies.py
→ workspaces/application.py проверяет membership
→ WorkspaceContext из workspaces/domain.py
```

### Работа с компанией или контактом

```text
HTTP request + cookie + X-Workspace-ID
→ request middleware
→ identity dependency (кто пользователь)
→ workspace dependency (к какому workspace есть доступ)
→ companies/api.py или contacts/api.py (валидация HTTP-контракта)
→ application.py (scope, can_write, поиск, version)
→ models.py + core/database.py
→ PostgreSQL
→ response + ETag + X-Request-ID
```

### Что пока не подключено полностью

- Backend API для auth, workspaces, companies и contacts уже подключён к общему
  router, но frontend пока вызывает только health endpoint.
- Demo-модель, capability endpoint и side-effect policy существуют, но полный
  lifecycle seed/reset и anonymous demo session flow ещё не реализованы.
- Планируемые deals, activities, tasks, notes, events, jobs, audit, AI, search и
  integrations присутствуют в документации, но соответствующих runtime-файлов
  пока нет.
- In-memory rate limiter защищает только один backend process; перед горизонтальным
  масштабированием нужен общий storage, например Redis.

## 5. Как поддерживать карту актуальной

После добавления файла нужно обновить две части: его место в полном дереве и
короткое описание. Если файл меняет runtime flow, также обновляется дерево
«Откуда всё начинается» и соответствующий сквозной сценарий. Lock-файлы следует
обновлять только пакетным менеджером, а новые миграции добавлять в конец фактической
Alembic-цепочки.
