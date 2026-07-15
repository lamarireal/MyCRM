# MyCRM Project Plan

## 1. Product vision

MyCRM is a production-oriented CRM and public portfolio project in which AI is
not a separate chatbot. Instead, it assists inside ordinary workflows: it
interprets incoming messages, enriches records, suggests next actions, drafts
replies, identifies risks, and explains its recommendations.

The application serves three compatible purposes: a private workspace for the
owner, isolated workspaces for future users or teams, and a safe public demo
containing only synthetic, resettable data.

The primary principle is that conventional business logic remains
deterministic, testable, and authoritative. The model proposes or prepares
changes, while critical actions are executed only after rule validation and,
when necessary, explicit user confirmation.

## 2. First-version goals

The first useful version should make it possible to:

1. Manage contacts, companies, deals, tasks, notes, and activities.
2. See the complete interaction history for a person or company in one place.
3. Move deals through a configurable pipeline.
4. Find records using both conventional and semantic search.
5. Generate an AI summary of a client or deal.
6. Receive a suggested next action together with an explanation.
7. Convert free-form text into a draft structured CRM record.
8. Control every change through an event log and confirmation of dangerous
   actions.
9. Let a public visitor explore a realistic seeded CRM without registration or
   access to private data.
10. Run from a reproducible production deployment with HTTPS, health checks,
    managed secrets, backups, and rollback instructions.

The first version should not include a complex automation builder,
enterprise billing, advanced team administration, a mobile application,
microservices, custom model training, or a fully autonomous agent.

## 3. Recommended stack

### Backend

- Python 3.12+.
- FastAPI for the HTTP API, dependency injection, validation, and OpenAPI.
- Pydantic Settings for configuration and environment secrets.
- SQLAlchemy 2.x with an asynchronous PostgreSQL driver.
- Alembic for schema migrations.
- PostgreSQL as the single primary source of truth.
- pgvector for embeddings and semantic search; begin with exact search and add
  HNSW only after measuring the need.
- Redis for short-lived caching, locks, rate limiting, and task queues.
- Celery as a straightforward initial background-task solution; consider
  Temporal later for long, multi-step, recoverable workflows.
- S3-compatible storage for attachments.

### Frontend

- React with TypeScript.
- A typed API client generated from OpenAPI.
- TanStack Query for server state; do not mix local UI state with CRM data.

### Engineering infrastructure

- uv for dependencies and the Python virtual environment.
- Ruff for formatting and static checks.
- mypy or pyright for type checking.
- pytest, pytest-asyncio, and Testcontainers for tests against real PostgreSQL.
- Docker Compose for local PostgreSQL, Redis, and object storage.
- GitHub Actions for checks, migrations against a test database, and container
  image builds.
- OpenTelemetry, structured JSON logs, and Sentry for observability.

## 4. Architecture: modular monolith

Start with a single deployable backend, while dividing it into independent
domain modules. This is simpler to develop and operate and does not prevent
high-load components from being extracted later.

Proposed structure:

```text
src/mycrm/
  main.py
  core/                 # configuration, security, database, logging, errors
  modules/
    identity/           # user, sessions, API keys
    workspaces/         # workspace ownership, memberships, demo access
    contacts/
    companies/
    deals/
    pipelines/
    tasks/
    activities/
    notes/
    communications/     # email, calendar, and import adapters
    search/
    automations/
    ai/
  shared/               # shared primitives, not business modules
  workers/              # background jobs
tests/
  unit/
  integration/
  contract/
  e2e/
```

Inside each module, separate:

- `api` — HTTP schemas and routes;
- `application` — use cases and transaction boundaries;
- `domain` — entities, rules, events, and interfaces;
- `infrastructure` — SQLAlchemy, external APIs, and concrete implementations.

A FastAPI route must not contain business logic. It validates the request,
invokes an application use case, and converts the result into an HTTP response.

## 5. Base data model

Minimum identity and ownership entities:

- `users` — identities and preferences;
- `workspaces` — the primary tenant and data-ownership boundary;
- `workspace_memberships` — user role and membership in a workspace;
- `demo_sessions` — optional temporary visitor-to-workspace assignment;

Minimum workspace-owned entities:

- `contacts` — people, contact details, tags, source, and owner;
- `companies` — organizations and their relationships to contacts;
- `pipelines`, `pipeline_stages` — configurable pipelines;
- `deals` — amount, currency, probability, stage, and expected closing date;
- `tasks` — due date, priority, status, and relationship to any entity;
- `activities` — calls, meetings, emails, stage changes, and other events;
- `notes` — notes with original and normalized text;
- `messages`, `threads` — imported communications;
- `attachments` — file metadata, with content stored separately;
- `tags` and relationship tables;
- `custom_field_definitions`, `custom_field_values` — only when a real need
  appears;
- `audit_log` — who changed what and when, including `human`, `rule`, or `ai`
  as the source;
- `outbox_events` — reliable domain-event delivery after a transaction;
- `ai_runs` — request, model, prompt version, input references, result, cost,
  latency, and review status;
- `ai_suggestions` — suggestion, confidence, explanation, and
  `pending/accepted/rejected/expired` status;
- `knowledge_documents`, `knowledge_chunks`, `embeddings` — knowledge base and
  RAG.

Every CRM aggregate, audit record, event, AI run, knowledge document, embedding,
and attachment must carry a non-null `workspace_id`. Repository and application
operations always receive an explicit workspace context. Business uniqueness
constraints are scoped to the workspace.

Use UUIDs and UTC timestamps from the beginning. Apply optimistic locking with
a `version` field to mutable entities and use soft deletion only where recovery
is actually required. Store monetary values as decimal plus a currency code,
never as floating-point numbers.

## 6. AI as a separate subsystem

The AI layer must not execute SQL or arbitrary actions directly. It receives
limited context and can call a small set of typed application-level tools.

### AI capabilities by priority

#### Level 1 — low risk, high value

- concise summary of a contact, company, or deal;
- extraction of contacts, dates, amounts, intentions, and tasks from text;
- incoming-message classification and urgency detection;
- semantic and hybrid search across notes and communications;
- email and note drafts that require confirmation;
- contact deduplication as a suggestion rather than automatic merging.

#### Level 2 — decision support

- recommended next-best action;
- assessment of stalled-deal risk using explicit signals;
- automatic meeting summary and draft task creation;
- morning briefing with overdue tasks, inactive deals, and important replies;
- detection of contradictions and missing data in records.

#### Level 3 — controlled agents

- preparation of action sequences for a user goal;
- execution of reversible operations through tools;
- mandatory pause before sending email, deleting, merging, changing amounts, or
  moving a deal to another stage;
- workflow resumption after approval and external API retries.

### Contract for every AI capability

Every capability must define:

- an exact task and JSON result schema;
- allowed context sources;
- the minimum required data and PII-masking rules;
- prompt and model version;
- timeout, retry policy, and cost limit;
- risk level and confirmation policy;
- a fallback path that does not require AI;
- test cases and a measurable quality metric.

The model must never decide which records it is allowed to access. Authorization
and context filtering happen before the model call.

## 7. Event flow and automations

Every significant change produces a domain event, for example:

```text
DealStageChanged -> outbox -> worker -> recalculate score
                               |-------> generate next-action suggestion
                               |-------> schedule follow-up reminder
```

Only mandatory invariants and data persistence happen synchronously. Embeddings,
summaries, external integrations, and notifications run in the background.

Every handler must be idempotent: repeated event delivery must not create a
second task, email, or charge. External actions store an idempotency key and
execution status.

## 8. API rules

- Version the public path as `/api/v1`.
- Use resource-oriented routes and dedicated command endpoints when a command
  represents a business action, for example `/deals/{id}/move-stage`.
- Use cursor pagination for growing logs and activity lists.
- Return a common error shape with a machine-readable `code`, message, and
  `request_id`.
- Accept an idempotency key for creation and external actions.
- Use ETag or version checks to prevent lost updates.
- Allow filtering and sorting only by explicitly permitted fields.
- Add WebSocket or Server-Sent Events only for proven real-time needs; polling
  is sufficient initially.
- Treat OpenAPI as the contract and verify changes with contract tests.

## 9. Security and privacy

A publicly deployed CRM contains sensitive data and is continuously exposed to
untrusted traffic. The minimum requirements are:

- Argon2id password hashing or authentication through a trusted OAuth/OIDC
  provider;
- short-lived access tokens and secure refresh-token rotation;
- encrypted transport and backups;
- secrets stored only in a secret manager or environment variables;
- authorization checks in the application layer, not only in routes;
- rate limits for login, import, and AI endpoints;
- auditing of access to and changes of sensitive entities;
- prompt-injection protection: external text is always treated as data, never
  as instructions;
- an allowlist of agent tools and arguments;
- the ability to delete user data and associated embeddings;
- configuration of which data types may be sent to each AI provider;
- regular backups and tested restoration.
- strict workspace scoping for every read and write;
- synthetic data only in the public demo;
- per-IP, per-session, and global limits for expensive or state-changing demo
  operations;
- a backend-enforced read-only fallback for the demo;
- separate local, test, staging, and production secrets.

## 10. Testing AI and conventional logic

Separate the following types of checks:

- unit tests for domain rules without a database or model;
- integration tests for repositories, transactions, the outbox, and PostgreSQL;
- API contract tests;
- migration tests in both directions when rollback is supported;
- a golden dataset for AI containing real but anonymized examples and expected
  fields;
- evaluations of extraction accuracy, recommendation usefulness, false actions,
  cost, and latency;
- an adversarial dataset for prompt injection and malformed input;
- replay of recorded AI calls in tests without paying for repeated calls;
- canary releases and feature flags before enabling a new prompt or model
  version.

Unit tests must not call an LLM. The provider is hidden behind an internal
interface, and responses are recorded or replaced with stable fixtures.

## 11. Development stages

### Stage 0 — decisions and foundation (2–4 days)

- document 5–10 specific personal use cases;
- choose the frontend and AI provider without coupling the domain to their SDKs;
- initialize FastAPI, configuration, PostgreSQL, migrations, and quality checks;
- configure Docker Compose, CI, health/readiness endpoints, and logging;
- record key decisions as ADRs.

Completion criterion: the application starts with one command, CI passes, a
migration initializes an empty database, and the API has request IDs and a
common error format.

### Stage 0.5 — public production and demo foundation (implemented)

- redefine data ownership around workspaces rather than a single owner;
- specify membership roles and workspace-aware authorization boundaries;
- define a public demo containing only synthetic, resettable data;
- document disabled demo side effects and AI budgets;
- separate local and production configuration;
- define managed deployment for frontend, API, and private PostgreSQL;
- define production secret, migration, HTTPS, backup, health-check, rollback,
  and observability requirements;
- expand CI requirements to include container builds, a real PostgreSQL
  migration test, and an end-to-end smoke test;
- record workspace, demo, and deployment decisions as ADRs.
- implement the identity/workspace schema and trusted workspace context;
- fail closed on unsafe production configuration;
- enforce initial request-size, rate, host, CORS, and demo-side-effect policies;
- provide a managed deployment blueprint and release migration command.

Completion criterion: Stage 1 can create every domain table with a stable
workspace boundary, and the project has an explicit path from local Compose to a
safe public demo deployment.

Status: the repository foundation is implemented and verified locally. The
actual public launch remains an operational task because HTTPS, monitoring,
backup restoration, and the live URL can only be verified after deployment.

Detailed architecture and learning notes:
[Stage 0.5: Public Production and Demo Architecture](../about/STAGE_0_5_PUBLIC_PRODUCTION.md).

### Stage 1 — CRM core (1–2 weeks)

- authentication and server-resolved context for the existing users,
  workspaces, and memberships;
- contacts, companies, deals, stages, tasks, and activities;
- `workspace_id` on every CRM entity, index, and repository operation;
- CRUD plus real business commands;
- transactions, optimistic locking, and audit logging;
- filters, sorting, and pagination;
- basic web interface;
- a versioned synthetic demo seed;
- cross-workspace authorization tests.

Completion criterion: daily work can be managed without AI or direct database
access, and a visitor can explore seeded demo data without accessing another
workspace.

Status: in progress. Password authentication, revocable sessions, automatic
private-workspace creation, membership-aware workspace resolution, and
two-workspace isolation tests are implemented. CRM aggregates, auditing, demo
seed/reset, and the working React CRM interface remain.

### Stage 2 — events and background tasks (3–5 days)

- outbox and worker;
- idempotent handlers;
- Redis and a task queue;
- retries, failed/dead-letter jobs, and observability.

Completion criterion: a worker failure neither loses an event nor duplicates a
result.

### Stage 3 — first AI value (1 week)

- AI-provider interface and prompt-version registry;
- structured output for entity extraction;
- record summaries;
- draft tasks generated from notes;
- `ai_runs`, limits, cost logging, and manual approval.

Completion criterion: results are reliably schema-validated, suggestion sources
are visible, and model failure does not interrupt the core CRM.

### Stage 4 — search and RAG (1 week)

- PostgreSQL full-text search;
- background chunking and embeddings;
- pgvector and hybrid ranking;
- references to source records in answers;
- reindexing when the embedding model changes.

Completion criterion: answers contain verifiable references to records the user
may access, and search quality is measured on a test dataset.

### Stage 5 — integrations (one at a time)

- CSV import;
- calendar;
- email;
- messaging platforms where their APIs and terms allow it.

For each integration, implement a separate adapter, sync cursor, deduplication,
retries, import log, and the ability to rerun synchronization safely.

### Stage 6 — recommendations and controlled agents

- next-best-action recommendations based on transparent signals;
- a simple `trigger -> conditions -> actions` rule builder;
- agent runs represented as a state machine with approval pauses;
- budget, step limit, timeout, and tool allowlist;
- a dashboard for quality and rejected recommendations.

## 12. Initial user stories

1. “I paste a conversation; the CRM proposes a contact, note, and tasks, and I
   confirm their creation.”
2. “I open a deal and see a concise summary, recent events, risks, and a
   recommended next step with reasons.”
3. “I ask whom I have not contacted recently; search returns relevant records
   and explains the criterion.”
4. “After a meeting I save a note; the CRM proposes tasks with dates and
   assignees.”
5. “Every morning the CRM shows the five most important actions, but sends and
   changes nothing without my confirmation.”
6. “As a portfolio visitor, I open a live demo, explore realistic synthetic
   contacts and deals, and understand which actions are temporary or disabled.”
7. “As the owner, I can use my private workspace without any demo visitor being
   able to read or modify it.”

## 13. Product metrics

- time from incoming text to an updated record;
- percentage of accepted and rejected AI suggestions;
- percentage of suggestions edited before acceptance;
- extraction completeness for tasks, dates, and contacts;
- number of overdue tasks and deals without activity;
- p95 latency of API and background AI jobs;
- AI cost per active day and per accepted suggestion;
- number of incorrect or unauthorized actions — target: zero.
- number of successful cross-workspace access attempts — target: zero;
- public demo uptime and p95 page-load time;
- demo reset success rate;
- abusive requests rejected by rate limits;
- AI cost per demo visitor and per day.

## 14. Decisions required before feature development

1. Which three scenarios provide the greatest daily value to the owner and best
   demonstrate the product publicly?
2. Which data channels come first: manual input, CSV, email, or calendar?
3. Where will the CRM run: locally, on a VPS, or in a managed cloud?
4. Which AI provider is acceptable for cost and privacy?
5. Which actions may AI never perform automatically?
6. Which membership roles are required in the first version?
7. Is offline operation required, and how long may communications be retained?
8. Should the first demo be shared and periodically reset, or should each
   visitor receive an ephemeral workspace?
9. Which operations are read-only, disabled, rate-limited, or simulated in demo
   mode?

## 15. Next practical sprint

1. Add authentication and derive the active workspace context from a trusted
   identity or demo session.
2. Add integration fixtures containing two workspaces.
3. Implement workspace-owned `Contact`, `Company`, `Deal`, `PipelineStage`, and
   `Activity` entities.
4. Add repository-level cross-workspace denial tests before expanding CRUD.
5. Add auditing and the outbox before the first AI capability.
6. Create a versioned synthetic demo seed and an idempotent reset use case.
7. Deploy the prepared production blueprint and verify operational controls.
8. Implement “text -> contact/note/task drafts” with structured output and user
   confirmation after the ownership boundary is proven.
9. Collect 20–50 anonymized examples for the first evaluation dataset.

## Official references

- [FastAPI: async and concurrency](https://fastapi.tiangolo.com/async/)
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/)
- [Celery](https://docs.celeryq.dev/en/stable/)
- [pgvector](https://github.com/pgvector/pgvector)
- [PostgreSQL Row-Level Security](https://www.postgresql.org/docs/17/ddl-rowsecurity.html)
- [FastAPI deployment concepts](https://fastapi.tiangolo.com/deployment/concepts/)
- [Docker Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/)
- [Render web services](https://render.com/docs/web-services)
