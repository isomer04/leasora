# Documentation Index

Use this page to find the canonical document for each topic. Commands and
claims should be maintained in their linked source rather than duplicated.

## Start here

1. [Project overview and quick start](../README.md)
2. [Complete local setup](setup.md)
3. [System architecture](ARCHITECTURE.md)
4. [Contributing guide](../CONTRIBUTING.md)

## Guides and references

| Topic | Document |
|---|---|
| Local development and troubleshooting | [Setup](setup.md) |
| System and RAG data flow | [Architecture](ARCHITECTURE.md) |
| Python dependency rules | [Backend layers](architecture/layers.md) |
| Evaluation methodology and results | [Evaluation report](EVALUATION_REPORT.md) |
| Release history | [Release notes](../RELEASE_NOTES.md) |
| Git hooks | [Pre-commit setup](../PRE_COMMIT_SETUP.md) |
| Frontend structure | [Web README](../apps/web/README.md) |
| Golden evaluation fixtures | [Golden dataset guide](../apps/api/tests/evals/golden/README.md) |

## Architecture Decision Records

| ADR | Decision |
|---|---|
| [001](adr/001-monorepo-structure.md) | Monorepo structure |
| [002](adr/002-python-layered-architecture.md) | Python layered architecture |
| [003](adr/003-prompt-versioning-and-llm-observability.md) | Prompt versioning and observability |
| [004](adr/004-no-trpc-why-openapi-codegen.md) | OpenAPI code generation instead of tRPC |
| [005](adr/005-langfuse-self-host-default.md) | Self-hosted Langfuse option |
| [006](adr/006-no-user-auth-single-tenant-v1.md) | No authentication in local v1 |
| [007](adr/007-retrieval-quality-and-evaluation.md) | Retrieval quality and evaluation |

## Common tasks

| Task | Start here |
|---|---|
| Install and run from source | [Host workflow](setup.md#option-a-run-from-source) |
| Run with Docker Compose | [Compose workflow](setup.md#option-b-run-with-docker-compose) |
| Regenerate frontend API types | [ADR 004 workflow](adr/004-no-trpc-why-openapi-codegen.md#developer-workflow) |
| Understand retrieval metrics | [Evaluation report](EVALUATION_REPORT.md) |
| Add or change Python dependencies between layers | [Layer contract](architecture/layers.md#changing-the-boundaries) |
| Prepare a pull request | [Contributing](../CONTRIBUTING.md) |

## Project status

Leasora is an educational, local-first, single-tenant application. It has no
user authentication and must not be exposed directly to the public internet.
No open-source license file is currently included; see the root
[README](../README.md#license) for the current license status.
