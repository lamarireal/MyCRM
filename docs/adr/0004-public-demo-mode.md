# ADR 0004: Public demo mode uses synthetic, resettable data

- Status: accepted
- Date: 2026-07-15

## Context

The production deployment must be publicly accessible so recruiters,
developers, and other visitors can understand and try the project. Anonymous
internet access creates risks: vandalized data, spam, automated abuse, AI cost,
unsafe uploads, and accidental exposure of personal information.

## Decision

The public experience uses a dedicated demo mode.

- Demo data is entirely synthetic and contains no personal customer data.
- Demo workspaces are separate from the owner's private workspace.
- A visible banner explains that demo data is temporary and reset regularly.
- Demo state is restored from a versioned seed dataset on a schedule.
- Destructive actions, external email, calendar synchronization, arbitrary file
  uploads, and other side effects are disabled until explicitly designed for
  safe demonstration.
- AI capabilities use per-session and global budgets, rate limits, and a small
  allowlist of safe operations.
- The initial implementation may use a shared resettable workspace. Per-session
  ephemeral workspaces are the preferred upgrade when write-heavy interaction
  is introduced.
- The demo can fall back to read-only mode during incidents or budget
  exhaustion.

## Consequences

- Visitors can explore the real application without touching private data.
- Seed and reset operations become first-class, tested use cases.
- Demo restrictions must be enforced by the backend, not only hidden in the UI.
- Some production capabilities may intentionally be unavailable in the public
  demo.
- Operational monitoring must distinguish ordinary use from abuse.

## Rejected alternatives

### Public access to the owner's workspace

This is unacceptable because it exposes or risks modifying private data.

### One permanent anonymous writable workspace with no reset

It would quickly accumulate vandalism, spam, and misleading content.

### Mock-only frontend

A mock can be useful for design previews, but it does not demonstrate the real
FastAPI, PostgreSQL, authorization, and operational architecture of the
portfolio project.
