# ADR 001: Monorepo Structure

**Date:** 2026-07-05
**Deciders:** Development Team

## Status: IN-FORCE (verified 2026-07-13)

Verified against the working tree: `apps/api/`, `apps/web/`, `packages/`
(`shared-schemas/`, `shared-types/`, `ts-config/`), `services/compose/`,
`scripts/`, `data/` all present with the documented roles. `pnpm-workspace.yaml`,
`turbo.json`, `grimp.yml` enforce the structure described under "Key principles."

## Context

Leasora is a multi-language, multi-service application:
- Backend: FastAPI (Python 3.12)
- Frontend: Next.js (TypeScript)
- Shared libraries: Python schemas, TypeScript types, shared configs
- Infrastructure: Docker, Docker Compose, CI/CD pipelines

Previous deployments used separate repositories for each component, which led to:
- Manual synchronization of breaking API changes
- Friction in atomic cross-service commits
- Duplicated dependency management
- Complex CI/CD orchestration

## Decision

Restructure Leasora as a **hybrid monorepo** using the following structure:

```
leasora/
├── apps/              # Independently deployable services
│   ├── api/          # FastAPI backend
│   └── web/          # Next.js frontend
├── packages/         # Shared libraries (imported by apps)
│   ├── shared-schemas/
│   ├── shared-types/
│   └── ts-config/
├── services/         # Infrastructure code (not imported by apps)
│   └── compose/
├── data/             # Runtime artifacts
├── scripts/          # Build automation
└── docs/             # Documentation
```

**Key principles:**

1. **Apps** are independently deployable with their own lifecycle (build, test, deploy)
2. **Packages** are shared libraries imported by apps at build time
3. **Services** are infrastructure code used at runtime (not imported programmatically)
4. **Data** contains runtime artifacts and fixtures (mostly gitignored where sensitive)
5. **Single repository** for atomic commits and unified CI/CD

## Consequences

### Positive

- **Atomic commits:** Cross-service changes (API + frontend) committed together
- **Single CI/CD:** One pipeline orchestrates all services; consistency guaranteed
- **Code sharing:** Typed schemas and types shared across language boundaries
- **Developer experience:** One clone, one build command, clear mental model
- **Reproducibility:** Docker Compose provides identical local/CI/prod environments
- **Type safety:** OpenAPI codegen ensures frontend-backend contract alignment

### Negative

- **Monorepo tooling:** Requires careful dependency management (uv for Python, pnpm for Node)
- **Build complexity:** Turborepo adds orchestration layer
- **Workspace conflicts:** Multiple languages require separate toolchains
- **CI/CD overhead:** Single pipeline must handle multiple runtimes
- **Repository size:** Single large repo can slow Git operations for some teams

### Mitigation

- **Clear boundaries:** Architectural rules enforce layering (grimp lint checks)
- **Parallel tooling:** Use `uv` for Python, `pnpm` for TypeScript (both fast and modern)
- **Caching:** Turborepo caches build artifacts; fast incremental builds
- **Pre-commit hooks:** Lint, type-check, and security scanning before push
- **Shallow cloning:** `git clone --depth 1` for initial checkout

## Related Decisions

- **ADR 002:** Python layered architecture (inward-only dependency flow)
- **ADR 004:** Why OpenAPI instead of tRPC for cross-language types

## References

- ["Monorepos and Monolithic Repositories" (Atlassian)](https://www.atlassian.com/git/tutorials/monorepos)
- [Turborepo Documentation](https://turbo.build/)
- [uv Documentation](https://docs.astral.sh/uv/)
- [pnpm Workspaces](https://pnpm.io/workspaces)
