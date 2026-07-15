# ADR 0005: Managed production deployment with separate services

- Status: accepted
- Date: 2026-07-15

## Context

The local Docker Compose environment is optimized for development: it publishes
database and API ports, uses localhost CORS origins, and connects nginx to the
Docker service name `api`. Publishing that configuration directly would expose
unnecessary services and leave certificate renewal, backups, restarts, and
monitoring to the application owner.

The first production deployment is intended for a portfolio, not for learning
Kubernetes or operating a custom platform.

## Decision

Production uses a managed platform and separates the application into:

- a public React static site or web frontend;
- a public FastAPI web service;
- a private managed PostgreSQL database;
- provider-managed HTTPS and certificate renewal;
- provider-managed secret injection and health checks.

Local Docker Compose remains the development environment. Production receives a
separate infrastructure manifest and production-specific configuration.

The frontend receives the public API URL at build time. FastAPI receives exact
production CORS origins, trusts forwarded headers only from the platform proxy,
and binds to the platform-provided port. Database migrations run as an explicit
release/pre-deploy step before new application instances receive traffic.

## Consequences

- The first public deployment requires less infrastructure maintenance.
- Local and production configuration remain deliberately separate.
- The platform becomes an operational dependency, but the application remains
  portable through Docker images and standard PostgreSQL.
- Deployment manifests, environment validation, migration strategy, backup
  verification, and rollback instructions become part of the repository.
- Moving to a VPS or another provider later remains possible without changing
  domain logic.

## Initial platform direction

Render is the default initial target because it supports Docker web services,
static sites, managed PostgreSQL, private networking, TLS, custom domains, and
health checks. This is a deployment choice, not a domain dependency.

## Rejected alternatives

### Publish the local Compose file directly

The local file exposes development ports and does not provide an adequate
production secret, TLS, backup, or deployment lifecycle.

### Self-managed VPS as the first deployment

It provides control but adds operating-system patching, firewall, TLS renewal,
database backups, process supervision, and incident response before they add
portfolio value.

### Kubernetes

It is unnecessary for the expected scale and would obscure the product and
application-engineering work behind infrastructure complexity.
