# ADR 005: Self-Hosted Langfuse as the Preferred Observability Option

**Date:** 2026-07-05
**Status:** In force, clarified 2026-07-14
**Deciders:** Development Team

## Context

LLM traces can help diagnose prompts, latency, token use, and groundedness, but
lease content is sensitive. Requiring a hosted tracing service would create an
unnecessary external data boundary and make local development dependent on
credentials and network access.

## Decision

Keep Langfuse tracing **disabled by default**. When LLM observability is needed,
prefer the repository's self-hosted Langfuse v3 Compose profile; hosted
Langfuse remains an explicit configuration option.

“Preferred” does not mean that Langfuse starts in the default development
stack. The default Compose profile runs web and API; Chroma is embedded in the
API process. The heavier observability profile is opt-in.

## Self-hosted workflow

The profile includes Langfuse web and worker services plus Postgres,
ClickHouse, Redis, and MinIO. Before starting it, define these service secrets:

- `LANGFUSE_SALT`
- `LANGFUSE_ENCRYPTION_KEY` (64 hexadecimal characters)
- `LANGFUSE_NEXTAUTH_SECRET`

Then run from the repository root:

```bash
docker compose -f services/compose/docker-compose.yml \
  --profile observability up --build
```

Langfuse is available at <http://localhost:3001>. Create a project in its UI,
then configure the API client with:

```env
LEASORA_LANGFUSE_ENABLED=true
LEASORA_LANGFUSE_HOST=http://localhost:3001
LEASORA_LANGFUSE_PUBLIC_KEY=pk-lf-...
LEASORA_LANGFUSE_SECRET_KEY=sk-lf-...
```
When the API itself runs inside Compose, explicitly set
`LEASORA_LANGFUSE_HOST=http://langfuse:3000`; that hostname resolves only when
the `observability` profile is active. A host-run API uses
`http://localhost:3001`. Compose preserves an explicitly provided host and
otherwise leaves it empty so tracing fails closed instead of targeting an
inactive profile service. Compose also forwards `LEASORA_LANGFUSE_ENABLED` but
defaults it to `false`; enabling the profile and opting the API into tracing
remain separate, intentional actions.

## Hosted option

Hosted Langfuse may be selected by explicitly setting all four API variables
and using the hosted endpoint. This sends redacted trace content to a third
party and requires a privacy review appropriate to the deployment.

## Consequences

### Positive

- Normal development works without observability credentials or services.
- Self-hosting keeps trace storage under operator control.
- The API wrapper remains deployment-agnostic and fails closed when required
  settings are incomplete.
- PII redaction is applied before span input and output.

### Tradeoffs

- Langfuse v3 has a substantial local infrastructure footprint.
- Initial setup requires creating a project and copying generated keys.
- Operators must distinguish Compose service secrets from API client keys.
- Self-hosting does not eliminate the need for retention, access, and backup
  policies.

## Related configuration

Prometheus application metrics are exposed at `GET /metrics`. LLM tracing uses
the Langfuse SDK and the `LEASORA_LANGFUSE_*` settings documented above; there
is no separate generic OpenTelemetry exporter.

## Reconsider when

Revisit this decision if the project adopts a managed deployment, adds user
authentication and tenant isolation, or establishes formal data residency and
retention requirements.
