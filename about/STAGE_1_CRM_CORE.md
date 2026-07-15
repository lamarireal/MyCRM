# Stage 1: CRM Core

Stage 1 turns the production-ready foundation into an actual multi-workspace
CRM. This document is updated as the stage is implemented. It distinguishes
finished code from the remaining domain and interface work so that project
status is never confused with the final Stage 1 completion criterion.

## 1. Current implementation status

The first Stage 1 slice is complete:

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

Stage 1 is not complete yet. Contacts, companies, pipelines, deals, tasks,
activities, notes, auditing, synthetic demo data, and the working React CRM
interface still need to be implemented.

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

## 12. Remaining Stage 1 sequence

The next implementation slices are:

1. shared workspace-owned model primitives and repository conventions;
2. contacts and companies;
3. pipelines, stages, and deals;
4. tasks, activities, and notes;
5. optimistic locking and deterministic business commands;
6. audit records for every mutation;
7. filtering, sorting, and pagination;
8. versioned synthetic demo seed and idempotent reset;
9. a backend-resolved anonymous demo context;
10. the React authentication, workspace, and CRM interface.

AI remains outside Stage 1. The CRM must first be useful, secure, and testable
without a model provider.
