# ADR 0003: Workspace-based data isolation

- Status: accepted
- Date: 2026-07-15

## Context

MyCRM was initially described as a personal application. It will also be
deployed publicly as a portfolio project, and visitors must be able to explore
it without gaining access to the owner's data or to another visitor's data.

Adding ownership only after CRM tables exist would require changing every
table, query, repository, endpoint, unique constraint, and test. The isolation
boundary therefore has to be defined before Stage 1 creates domain entities.

## Decision

The primary data-ownership boundary is a `Workspace`.

- A user may belong to one or more workspaces through `WorkspaceMembership`.
- Every CRM aggregate belongs to exactly one workspace.
- Every workspace-owned table contains a non-null `workspace_id`.
- Uniqueness rules that describe business data are scoped to a workspace.
- Application use cases receive an explicit workspace context.
- Repository operations always filter by `workspace_id`.
- Authorization is enforced in the application layer, not only in HTTP routes.
- Background jobs, audit records, events, AI runs, embeddings, and attachments
  carry the same workspace boundary.

PostgreSQL Row-Level Security may later be added as defense in depth. It does not
replace application-layer authorization.

## Consequences

- Personal, team, and demo data can use the same domain model safely.
- Stage 1 models require workspace-aware keys, indexes, repositories, and tests.
- Cross-workspace access must be included in security and integration tests.
- Queries are slightly more verbose because the workspace scope is explicit.
- Future team support does not require a destructive ownership migration.

## Rejected alternatives

### Single global owner

This is simpler initially but cannot safely support a public demo or future
team access.

### Separate database per visitor

This gives strong isolation but creates unnecessary provisioning and operational
complexity for an early portfolio project.

### Rely only on frontend filtering

Frontend checks are not a security boundary and can be bypassed by direct API
requests.
