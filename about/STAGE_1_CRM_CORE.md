# Stage 1: CRM Core

Stage 1 turns the production-ready foundation into an actual multi-workspace
CRM. This document is updated as the stage is implemented. It distinguishes
finished code from the remaining domain and interface work so that project
status is never confused with the final Stage 1 completion criterion.

## 1. Current implementation status

The first two Stage 1 slices are complete:

- passwords are hashed with Argon2id;
- registration creates a user, private workspace, and owner membership;
- login creates a random revocable server-side session;
- only a keyed hash of the session token is stored in PostgreSQL;
- the browser receives the original token in an `HttpOnly` cookie;
- logout revokes the database session and deletes the cookie;
- authenticated users can list their accessible workspaces;
- `X-Workspace-ID` selects a workspace but never grants access to it;
- the backend resolves a trusted `WorkspaceContext` from active membership;
- attempts to select another user's workspace return `404`;
- PostgreSQL integration tests use two workspaces and transaction rollback;
- the complete register/login/workspace/logout API flow is tested.
- companies and contacts are workspace-owned aggregates;
- contacts can reference only companies from the same workspace;
- list endpoints provide bounded pagination, search, filtering, and sorting;
- updates use optimistic version checks and return ETags;
- delete commands archive records rather than physically removing them;
- viewer and read-only contexts cannot mutate CRM records;
- PostgreSQL and API tests cover isolation, stale writes, search, and archival.
- pipelines are created with ordered, validated stages;
- deals store exact decimal money and ISO-style uppercase currency codes;
- deal relationships are constrained to the same workspace and pipeline;
- `move-stage` atomically derives status and probability from the target stage;
- won and lost stages produce deterministic deal lifecycle states;
- pipeline/deal API and PostgreSQL boundary tests are implemented.

Stage 1 is not complete yet. Pipeline editing, tasks, activities, notes,
auditing, synthetic demo data, and the working React CRM interface still need
to be implemented.

## 2. Why authentication comes before CRM tables

A contact or deal is not secure merely because it contains `workspace_id`. The
backend also needs a trustworthy way to answer two questions for every request:

1. Who is the actor?
2. Which workspace may that actor access?

If temporary headers or request-body fields were treated as authority, every
later repository would be built on an unsafe assumption. Stage 1 therefore
starts by proving identity and workspace resolution before introducing CRM
aggregates.

```text
HttpOnly session cookie
  -> hash token with backend secret
  -> find active, non-expired database session
  -> load active user
  -> read requested X-Workspace-ID
  -> verify active membership
  -> construct immutable WorkspaceContext
  -> execute workspace-scoped use case
```

The client may choose a workspace ID because the interface needs a workspace
switcher. Selection is not authorization. The membership query is the
authorization boundary.

## 3. Password storage with Argon2id

User passwords are never encrypted or stored directly. Encryption is
reversible; password verification does not require recovering the original
password. Instead, `pwdlib` uses the recommended Argon2id password hash.

Argon2id is intentionally expensive in CPU and memory. This makes each guessed
password more costly for an attacker who obtains the database. The encoded hash
contains its algorithm, parameters, salt, and result, allowing parameters to be
upgraded later without changing the user table format.

Login also performs a dummy Argon2 verification when an email does not exist.
Without this work, an attacker could compare response times and enumerate
registered email addresses.

The `password_hash` column is nullable because the identity model may later
support users authenticated exclusively through an OIDC provider. New local
password registrations always populate it.

## 4. Why sessions are opaque instead of long-lived JWTs

The implementation generates a cryptographically random token with 256 bits of
entropy. The browser receives the token, while PostgreSQL stores only an
HMAC-SHA-256 digest keyed by `MYCRM_SECRET_KEY`.

This design provides several useful properties:

- a database leak does not reveal immediately usable session tokens;
- logout can revoke a session immediately;
- disabling a user invalidates access on the next request;
- administrators can later list or revoke individual devices;
- session expiration is authoritative on the server;
- rotating the application secret invalidates all existing sessions.

A long-lived self-contained JWT is harder to revoke because the backend may not
consult the database until the token expires. Short access JWTs plus rotated
refresh tokens can also be secure, but they add protocol complexity that does
not provide an advantage for the first MyCRM deployment.

## 5. Cookie security

The session token is sent in a cookie with:

- `HttpOnly`, preventing ordinary JavaScript from reading it;
- `SameSite=Lax`, reducing cross-site request forgery exposure;
- `Secure` in production, allowing transport only over HTTPS;
- a root path so authentication works for all API routes;
- an explicit lifetime controlled by `MYCRM_SESSION_TTL_DAYS`.

Exact CORS origins and JSON request bodies provide additional protection. A
dedicated CSRF token should be added if future features require cross-site
embedding, less restrictive cookie settings, or state-changing form endpoints.

## 6. Registration transaction

Registration is one business transaction:

```text
normalize email
  -> reject an existing identity
  -> hash password
  -> create User
  -> create private Workspace
  -> create owner WorkspaceMembership
  -> commit once after the use case succeeds
```

A partial result is not useful. A user without a workspace, or a workspace
without an owner, would require repair logic. The database dependency therefore
commits only after the route succeeds and rolls back on exceptions.

The unique email constraint remains the final concurrency boundary. A nested
transaction converts a racing duplicate insert into a controlled conflict
without leaving the surrounding SQLAlchemy session unusable.

Public production registration is disabled by default. Local Compose enables
it for development, while the Render blueprint explicitly disables it until
privacy policy, account deletion, abuse controls, and persistent public-user
requirements are ready.

## 7. Workspace membership rules

`workspace_memberships` now has an explicit status:

```text
active | suspended
```

Only active memberships resolve a workspace. A disabled workspace also cannot
be selected. Returning `404` for an inaccessible workspace avoids confirming
whether a guessed UUID exists in another tenant.

The trusted context contains:

```text
workspace_id
actor_id
role
workspace kind
workspace status
can_write
```

Future repositories will require this context and include its `workspace_id`
in every query. A plain `get_by_id(entity_id)` repository method will not be
permitted for workspace-owned records.

## 8. API endpoints implemented

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/me
GET  /api/v1/workspaces
GET  /api/v1/workspaces/current
```

`GET /api/v1/workspaces/current` requires `X-Workspace-ID`. The response is a
safe representation of the resolved backend context and is useful for testing
the future workspace switcher.

Authentication errors use the common API error envelope and do not expose
password hashes, raw session tokens, or internal membership details.

## 9. Migration strategy

Migration `20260715_0003_authentication.py`:

- adds nullable `users.password_hash`;
- adds active/suspended membership status with a database check constraint;
- creates `auth_sessions` with expiration and revocation timestamps;
- adds an index for user-session expiration queries;
- supports complete downgrade to the Stage 0.5 schema.

Existing Stage 0.5 users remain valid database records, but they cannot use
password login until a password is set through a future owner-administration or
account-recovery flow. This is safer than assigning a fallback password during
migration.

## 10. Integration-test approach

Unit tests verify Argon2id behavior and token hashing without PostgreSQL.
Integration tests run against the migrated PostgreSQL database and wrap each
case in an outer transaction that is rolled back afterward.

The test dataset creates two independent users and workspaces. It proves the
negative case: the first user cannot resolve the second user's workspace. A
single-workspace fixture could prove successful access but could never prove
tenant isolation.

The API-flow test verifies:

1. registration;
2. login and `HttpOnly` cookie creation;
3. workspace listing;
4. authorized workspace resolution;
5. rejection of a random workspace UUID;
6. logout and subsequent authentication failure.

CI applies migrations before these tests and uses a dedicated PostgreSQL
service. This ensures the tests exercise the committed schema rather than an
SQLite approximation.

## 11. Configuration added

```text
MYCRM_REGISTRATION_ENABLED
MYCRM_SESSION_COOKIE_NAME
MYCRM_SESSION_TTL_DAYS
```

`MYCRM_SECRET_KEY`, introduced during Stage 0.5, now protects session-token
digests. Changing it is a deliberate global session-revocation operation.

## 12. Company and contact aggregates

`Company` is the parent organization record. Its first fields are deliberately
small: name, website, industry, lifecycle status, version, and timestamps. A
small stable aggregate is easier to validate and evolve than a table containing
every imagined CRM attribute before real use cases exist.

`Contact` stores a person's name, email, phone, job title, and optional company.
Both tables carry a non-null `workspace_id`; no use case accepts a workspace ID
from its create or update payload. The application always copies it from the
trusted `WorkspaceContext`.

Every model uses UUID primary keys and timezone-aware timestamps. The API never
exposes SQLAlchemy objects directly: response schemas define the public
contract and prevent future internal fields from leaking accidentally.

## 13. Database-enforced relationship isolation

Application code verifies that a selected company is active and belongs to the
current workspace before creating or updating a contact. This produces a clear
`404` response instead of exposing whether a foreign company UUID exists.

The database adds a second, independent boundary:

```text
contacts (workspace_id, company_id)
    -> companies (workspace_id, id)
```

The composite foreign key makes the workspace part of the relationship itself.
Even a future script, background task, or repository bug cannot attach a
contact in workspace A to a company in workspace B. Integration tests bypass
the application check intentionally and prove that PostgreSQL rejects the row.

The foreign key uses `RESTRICT` rather than cascading company deletion into
contacts. Removing an organization should never silently erase people. Current
business commands archive companies, so normal workflows do not physically
delete either aggregate.

## 14. Workspace-scoped application operations

All reads include both entity ID and trusted workspace ID:

```text
WHERE workspace_id = :context_workspace_id
  AND id = :entity_id
```

An entity from another workspace is indistinguishable from a missing entity and
returns `404`. List, search, count, update, and archive statements use the same
scope. Isolation would be incomplete if only detail endpoints were protected
while search or counts queried globally.

Mutation use cases check `WorkspaceContext.can_write`. Owners, admins, and
members of active workspaces may write. Viewers, demo visitors, and read-only
workspaces cannot create, change, or archive records even if they call the API
directly.

## 15. Optimistic locking

Companies and contacts begin with `version = 1`. Every successful update or
archive increments the version atomically:

```text
UPDATE contacts
SET ..., version = version + 1
WHERE workspace_id = :workspace_id
  AND id = :contact_id
  AND version = :expected_version
```

Suppose two browser tabs load version 1. The first update succeeds and produces
version 2. The second update still expects version 1, affects no row, and
receives `409 Conflict`. Without this check, the second tab would silently
overwrite the first tab's changes.

Responses include an `ETag` derived from the current version, and mutation
payloads contain `expected_version`. A future generated frontend client can
keep the version beside cached data and show a refresh/merge interface on
conflict.

## 16. Archival instead of destructive deletion

`DELETE` endpoints execute an archive business command. The record status
changes from `active` to `archived`, its version increments, and default reads
stop returning it. Administrative or recovery views can request
`include_archived=true`.

This provides a safer first CRM behavior because contacts and companies often
participate in historical activities, deals, and audit records. Physical data
deletion will later be a separate privacy/retention operation with explicit
cascade rules, not an ordinary UI action.

## 17. Query contracts

Company and contact list endpoints provide:

- `search`, limited to explicitly selected text fields;
- `company_id` filtering for contacts;
- `include_archived` for recovery-oriented views;
- an allowlisted `sort` field and direction;
- `limit` constrained to 1–100;
- a non-negative `offset`;
- total count and page metadata.

User search text is escaped before it is placed inside an SQL `LIKE` pattern.
This treats `%` and `_` as literal user input rather than accidental wildcard
instructions. SQLAlchemy still binds all values as parameters, preventing SQL
injection.

Offset pagination is acceptable for the initial company and contact directory.
Growing append-only streams such as activities and audit logs will use cursor
pagination as required by the API rules.

## 18. API endpoints added

```text
POST   /api/v1/companies
GET    /api/v1/companies
GET    /api/v1/companies/{company_id}
PATCH  /api/v1/companies/{company_id}
DELETE /api/v1/companies/{company_id}

POST   /api/v1/contacts
GET    /api/v1/contacts
GET    /api/v1/contacts/{contact_id}
PATCH  /api/v1/contacts/{contact_id}
DELETE /api/v1/contacts/{contact_id}
```

Every endpoint requires authentication and `X-Workspace-ID`. Pydantic validates
lengths, email addresses, URLs, UUIDs, pagination bounds, and update payloads
before an application use case runs.

## 19. Migration and tests

Migration `20260715_0004_contacts_companies.py` creates both tables, lifecycle
checks, query indexes, and the composite relationship constraint. Downgrade
drops contacts before companies so the dependency order remains valid.

An Alembic metadata comparison also exposed nullable timestamp columns left by
the early foundation migrations. Migration
`20260715_0005_align_model_constraints.py` makes those timestamps non-null and
aligns the workspace-status storage length with its enum. This is a follow-up
migration rather than an edit to committed history, so databases that already
applied the earlier revisions remain reproducible and upgrade safely.

Integration coverage now proves:

- successful company/contact creation inside one workspace;
- detail and list isolation from a second workspace;
- application rejection of a foreign company relationship;
- PostgreSQL rejection when the application boundary is bypassed;
- stale update rejection;
- search and company filtering;
- removal of a company relationship through a versioned update;
- viewer write denial;
- API ETags, pagination, update, conflict, and archive behavior.

## 20. Pipelines and ordered stages

A pipeline is created as one aggregate together with its initial stages. Stage
positions are assigned by the backend from request order, starting at 1. This
avoids trusting clients to submit conflicting positions and guarantees a
stable visual order.

Each stage defines:

- a name unique inside the creation request;
- probability from 0 to 100;
- position greater than zero;
- outcome: `open`, `won`, or `lost`;
- lifecycle status and optimistic version.

The database enforces unique positions inside `(workspace_id, pipeline_id)`.
Pipeline creation is transactional, so failure to create any stage rolls back
the parent pipeline as well.

## 21. Deal model and exact money

A deal belongs to one workspace, pipeline, and pipeline stage. It may reference
a company and contact from the same workspace. It stores title, optional
amount, three-letter currency code, probability, expected close date, lifecycle
status, version, and UTC timestamps.

Amounts use PostgreSQL `NUMERIC(18, 2)` and Python `Decimal`. Binary floating
point is unsuitable for money because common decimal values cannot be
represented exactly. Tests verify that `1234.56` returns as the same decimal
value.

Deal states are:

```text
open | won | lost | archived
```

`archived` is an explicit recovery-oriented lifecycle state. `won` and `lost`
are derived from stage outcomes rather than independently supplied by clients.

## 22. Composite relationship constraints

Deals use several database-level same-workspace relationships:

```text
(workspace_id, company_id) -> companies
(workspace_id, contact_id) -> contacts
(workspace_id, pipeline_id) -> pipelines
(workspace_id, pipeline_id, stage_id) -> pipeline_stages
```

The three-column stage foreign key is particularly important. Checking only
`stage_id` would prove that a stage exists, but not that it belongs to the
deal's selected pipeline. The composite key makes both pipeline membership and
workspace isolation database invariants.

The application performs the same checks first to return safe, understandable
errors. PostgreSQL remains the final boundary for scripts, jobs, imports, and
future code paths.

## 23. Move-stage as a business command

Changing a deal stage has business meaning and therefore uses a dedicated
command endpoint instead of a generic field patch:

```text
POST /api/v1/deals/{deal_id}/move-stage
```

The command:

1. resolves the deal inside the trusted workspace;
2. resolves an active target stage inside the same pipeline;
3. checks the expected deal version;
4. changes the stage;
5. copies the stage probability;
6. derives `open`, `won`, or `lost` from stage outcome;
7. increments the version and update timestamp atomically.

Two simultaneous moves from version 1 cannot both succeed. The first creates
version 2; the second receives `409 Conflict` rather than silently moving the
deal from an outdated screen.

## 24. Pipeline and deal API

```text
POST /api/v1/pipelines
GET  /api/v1/pipelines
GET  /api/v1/pipelines/{pipeline_id}

POST   /api/v1/deals
GET    /api/v1/deals
GET    /api/v1/deals/{deal_id}
PATCH  /api/v1/deals/{deal_id}
POST   /api/v1/deals/{deal_id}/move-stage
DELETE /api/v1/deals/{deal_id}
```

Deal listing supports bounded pagination, text search, pipeline, stage, and
status filters. General patching can change descriptive and monetary fields but
cannot bypass the dedicated pipeline-stage transition command.

Pipeline stage editing and reordering were intentionally deferred until the
rules for active deals, position swaps, stage removal, and audit history were
defined. Sections 33–38 describe the implemented commands.

## 25. Migration and verification

Migration `20260715_0006_pipelines_deals.py` creates pipelines, stages, deals,
indexes, checks, and composite foreign keys. It also adds the composite contact
uniqueness required as a PostgreSQL foreign-key target.

Tests prove:

- ordered stage creation;
- cross-workspace pipeline invisibility;
- exact decimal storage;
- stage-derived probability and deal status;
- stale transition rejection;
- application rejection of a foreign workspace pipeline;
- PostgreSQL rejection when that application check is bypassed;
- the complete pipeline/create-deal/move-to-won API flow;
- filtering won deals after transition.

Alembic metadata comparison reports no uncommitted schema operations.

## 26. Remaining Stage 1 sequence

The next implementation slices are:

1. versioned synthetic demo seed and idempotent reset;
2. a backend-resolved anonymous demo context;
3. the React authentication, workspace, and CRM interface;
4. final Docker and end-to-end verification.

AI remains outside Stage 1. The CRM must first be useful, secure, and testable
without a model provider.

## 27. Tasks as workflow entities

A task is more than a title and checkbox. It records priority, optional due
time, assignee, description, lifecycle state, completion time, optimistic
version, and links to relevant CRM records.

The supported states are:

```text
todo | in_progress | done | cancelled | archived
```

Descriptive changes use `PATCH`, while state transitions use the explicit
`change-status` command. This prevents an ordinary edit form from accidentally
bypassing workflow behavior. Entering `done` sets `completed_at`; leaving
`done` clears it. Archival remains separate, and archived tasks disappear from
normal reads.

Every mutation compares `expected_version` in the same SQL statement that
changes the task. A stale browser therefore receives a conflict instead of
silently overwriting a newer status or assignee.

## 28. Assignees and CRM relationships

Tasks may be unassigned or assigned to an active member of the current
workspace. A global user ID is not enough: the application verifies active
membership before storing it.

Tasks, activities, and notes may each reference a company, contact, and deal at
the same time. Multiple links are useful because a meeting can belong to a
deal while also appearing in the customer and contact timelines. Each link is
optional, but every supplied link must point to an active record in the same
workspace.

The reusable `crm_relations` application helper performs friendly validation.
PostgreSQL independently protects the boundary with composite foreign keys:

```text
(workspace_id, company_id) -> companies
(workspace_id, contact_id) -> contacts
(workspace_id, deal_id)    -> deals
```

This required a composite uniqueness constraint on `(workspace_id, id)` for
deals. The two-layer approach protects normal API requests as well as future
imports, scripts, workers, and administrative code.

## 29. Append-only activity timeline

Activities represent facts that happened: calls, meetings, emails, deal-stage
changes, task events, and other interactions. Each record contains an event
time, summary, optional details, creator, related records, and source:

```text
human | rule | ai | system
```

The public creation route always records `human`. Future rules, AI workflows,
and system handlers will call the internal use case with their explicit
source. A client cannot impersonate an AI or system action.

Activities expose create, list, and detail routes only. There are deliberately
no update or delete routes because changing history would make later auditing,
AI explanations, and customer timelines unreliable. Corrections should be
represented by a new activity rather than rewriting the original fact.

The list uses cursor pagination ordered by `(occurred_at DESC, id ASC)`. The
cursor identifies the last visible record and creates a stable boundary for
the next page. This is better than offsets for a growing timeline because new
events do not shift already visited pages.

## 30. Versioned notes

Notes contain original text and reserve `normalized_body` for a later
deterministic or AI-assisted normalization pipeline. The original body remains
the authoritative human input; normalization must never silently replace it.

Unlike activities, notes are working documents and may be corrected. Updates
therefore use optimistic locking and ETags. Archival is soft deletion, allowing
future recovery without exposing archived text in ordinary queries.

## 31. API surface

```text
POST   /api/v1/tasks
GET    /api/v1/tasks
GET    /api/v1/tasks/{task_id}
PATCH  /api/v1/tasks/{task_id}
POST   /api/v1/tasks/{task_id}/change-status
DELETE /api/v1/tasks/{task_id}

POST /api/v1/activities
GET  /api/v1/activities
GET  /api/v1/activities/{activity_id}

POST   /api/v1/notes
GET    /api/v1/notes
GET    /api/v1/notes/{note_id}
PATCH  /api/v1/notes/{note_id}
DELETE /api/v1/notes/{note_id}
```

Task lists support status, assignee, and deal filters with bounded offset
pagination. Notes support company, contact, and deal filters. Activities use
the cursor described above. Every route derives workspace scope from the
authenticated backend context rather than request bodies.

## 32. Migration and verification

Migration `20260715_0007_tasks_activities_notes.py` adds all three tables,
checks, query indexes, user relationships, composite CRM relationships, and
the deal composite uniqueness required by those foreign keys.

Integration coverage proves:

- completion timestamp and version changes through the task status command;
- rejection of stale task and note updates;
- application rejection of a deal from another workspace;
- PostgreSQL rejection when the application boundary is bypassed;
- stable multi-page activity cursor behavior;
- API creation and mutation flows for all three resources;
- absence of activity update and delete operations in OpenAPI.

The complete suite contains 30 passing tests against PostgreSQL. Ruff, strict
mypy, and Alembic schema comparison also pass, with no migration drift.

## 33. Why stage changes are commands

Pipeline stages are not independent labels. Their order determines the visual
sales process, their outcome determines whether a deal is open, won, or lost,
and active deals may reference them. Generic stage CRUD would make it easy to
create gaps, duplicate positions, or leave deals pointing at an invalid stage.

The API therefore exposes three explicit operations:

```text
PATCH /api/v1/pipelines/{pipeline_id}/stages/{stage_id}
POST  /api/v1/pipelines/{pipeline_id}/reorder-stages
POST  /api/v1/pipelines/{pipeline_id}/stages/{stage_id}/archive
```

Metadata updates can change a name, probability, or outcome. A name must remain
unique among active stages. Probability changes affect future moves into the
stage but do not silently rewrite manually adjusted probabilities on existing
deals. An outcome cannot change while active deals use the stage because doing
so would make their stored status disagree with pipeline semantics.

## 34. Atomic stage reordering

The reorder command requires the complete set of active stage IDs exactly once.
Partial lists and duplicates are rejected. This makes the intended final order
unambiguous and prevents a stale client from accidentally omitting a stage.

The command locks the pipeline and its active stages, checks the pipeline
version, moves every position into a collision-free temporary range, and then
assigns positions `1..N`. The temporary range is necessary because PostgreSQL
unique constraints are checked during updates; directly swapping positions 1
and 2 can otherwise create a transient duplicate.

All affected stage versions and the pipeline version advance atomically. A
second browser using the old pipeline version receives `409 Conflict`.
Submitting the existing order is idempotent and does not create versions or
audit noise.

## 35. Safe stage archival and deal migration

A pipeline must keep at least two active stages. Archival is rejected if it
would violate this invariant.

If active deals use the stage, the caller must provide
`replacement_stage_id`. The replacement must be another active stage in the
same workspace and pipeline. In one transaction the command:

1. locks the pipeline, stages, and affected deals;
2. validates pipeline and stage versions;
3. moves each deal to the replacement;
4. copies replacement probability and derives deal status from its outcome;
5. increments every moved deal version;
6. archives the source stage;
7. compacts remaining positions;
8. increments the pipeline version;
9. writes audit records for every business mutation.

Archived stages use `NULL` position. PostgreSQL unique constraints allow
multiple archived stages with no position while continuing to guarantee unique
positions for active stages.

## 36. Audit record design

Every company, contact, pipeline, stage, deal, task, activity, and note
mutation now creates an `audit_records` row in the same database transaction.
An audit record stores:

- non-null `workspace_id`;
- actor ID when a human identity exists;
- source: `human`, `rule`, `ai`, or `system`;
- action and entity type;
- entity UUID;
- JSONB state before and after the change;
- an authoritative server timestamp.

Audit writes live in application use cases rather than HTTP routes. The same
history is therefore produced by FastAPI, future workers, imports, rules, and
AI tools. If audit persistence fails, the surrounding CRM transaction also
fails.

The snapshots use JSONB because fields vary between entity types and audit
records are historical evidence rather than live domain objects. The original
tables remain the authoritative current state.

## 37. Append-only protection and ordering

The API exposes only list and detail operations:

```text
GET /api/v1/audit-records
GET /api/v1/audit-records/{record_id}
```

PostgreSQL additionally installs a trigger that rejects every `UPDATE` or
`DELETE` against `audit_records`. This protects history when application code
is bypassed by a script or future worker.

Audit pagination uses `(created_at DESC, id ASC)` and an opaque record cursor.
The timestamp default is `clock_timestamp()` rather than `now()`. PostgreSQL
`now()` is fixed for an entire transaction, so multiple business events in one
command would otherwise receive the same time and lose their true ordering.

Reads are always scoped by the trusted workspace context. A valid audit UUID
from another workspace behaves as not found.

## 38. Migration and verification

Migration `20260718_0008_stage_commands_audit.py` makes stage position nullable
for archived stages, creates the JSONB audit table and indexes, and installs
the append-only database trigger.

The new tests prove:

- complete, atomic stage reordering and stale-version rejection;
- prevention of outcome changes while active deals use a stage;
- mandatory replacement for occupied stage archival;
- atomic deal migration and position compaction;
- audit creation for aggregate commands;
- cross-workspace audit isolation;
- database rejection of audit tampering;
- FastAPI contracts for stage commands and read-only audit routes.

The complete suite now contains 35 passing tests against PostgreSQL. Ruff,
strict mypy, and Alembic schema comparison pass with no migration drift.
