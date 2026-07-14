# ADR 0001: Modular monolith

- Status: accepted
- Date: 2026-07-14

## Context

MyCRM starts as a personal product, but it must support complex business logic,
background processes, and controlled AI capabilities. Microservices at this
stage would increase development and operational costs without proven value.

## Decision

The backend is implemented as a single FastAPI service backed by PostgreSQL and
divided into domain modules. The HTTP layer, application use cases, domain
rules, and infrastructure are kept separate. Modules communicate through public
application interfaces and domain events.

The frontend is implemented as a separate React application. FastAPI's OpenAPI
schema will become the source contract for future TypeScript client generation.

## Consequences

- A single service is easier to start, test, and deploy.
- CRM transactions remain simple and reliable.
- Module boundaries must be enforced through reviews and tests rather than
  network calls.
- A module can be extracted into a separate service later if there is a measured
  need for independent scaling or fault isolation.
