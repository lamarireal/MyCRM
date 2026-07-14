# ADR 0002: AI does not modify data directly

- Status: accepted
- Date: 2026-07-14

## Context

The CRM stores personal information and performs meaningful business actions. A
language model response is nondeterministic and may contain an error or follow
an instruction embedded in untrusted external text.

## Decision

AI receives only explicitly prepared and authorized context. Model output is
validated against a typed schema. The model has no direct SQL access; changes
are performed by application use cases after authorization and domain-rule
checks. Risky actions require user confirmation.

Every future AI run records the model version, prompt version, source links,
result, cost, and the user's decision.

## Consequences

- The core CRM continues to operate when the AI provider is unavailable.
- AI capabilities require additional contracts and auditing.
- An incorrect suggestion can be rejected without damaging data.
