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

Stage 1 is not complete yet. Pipelines, deals, tasks, activities, notes,
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

## 20. Remaining Stage 1 sequence

The next implementation slices are:

1. pipelines, stages, and deals;
2. tasks, activities, and notes;
3. audit records for every mutation;
4. versioned synthetic demo seed and idempotent reset;
5. a backend-resolved anonymous demo context;
6. the React authentication, workspace, and CRM interface.

AI remains outside Stage 1. The CRM must first be useful, secure, and testable
without a model provider.
