# Leasora Web

The Next.js 16 and React 19 frontend for Leasora. It uses the App Router,
strict TypeScript, Tailwind CSS, Radix UI primitives, and an `openapi-fetch`
client generated from the FastAPI contract.

## Run locally

Complete the installation and configuration steps in
[the setup guide](../../docs/setup.md), but replace its `pnpm dev` step with
these two commands in separate terminals:

```bash
# Terminal 1: FastAPI on port 8000
pnpm --filter @leasora/api dev

# Terminal 2: Next.js on port 3000
pnpm --filter @leasora/web dev
```

The UI runs at <http://localhost:3000> and expects the API at
`NEXT_PUBLIC_API_BASE_URL` (default: <http://localhost:8000>).

## Scripts

| Command | Purpose |
|---|---|
| `pnpm dev` | Start Next.js development mode on port 3000 |
| `pnpm build` | Create a production build |
| `pnpm start` | Serve the production build |
| `pnpm lint` | Run ESLint |
| `pnpm type-check` | Generate Next.js route types and run TypeScript |
| `pnpm test:run` | Run Vitest once |
| `pnpm format:check` | Check formatting with Prettier |

Run these inside `apps/web`, or prefix them from the root with
`pnpm --filter @leasora/web`.

## Current structure

```text
src/
├── app/
│   ├── (marketing)/      # Home, about, and pricing pages
│   └── (app)/            # Dashboard, upload, leases, ask, and compare
├── components/
│   ├── ui/               # Shared presentational primitives
│   ├── layout/           # App shell, navigation, theme, and footer
│   └── features/         # Existing domain-specific components
├── features/             # Target location for larger domain slices
├── hooks/                # Reusable API/data hooks
├── lib/                  # API client, environment, theme, and utilities
├── styles/               # Global styles and design tokens
└── tests/                # Cross-page tests such as accessibility checks
```

There is no authentication route group in the current single-tenant v1. The
`(app)` group provides application layout only; it is not an authorization
boundary.

## API contract workflow

FastAPI owns the HTTP schema. The frontend imports generated definitions from
`@leasora/shared-types` and calls the backend through `src/lib/api.ts`.

After changing a backend route or Pydantic request/response model:

```bash
pnpm gen:types
pnpm --filter @leasora/web type-check
git diff -- packages/shared-types/src/api.ts
```

Do not manually duplicate or edit generated API interfaces. See
[ADR 004](../../docs/adr/004-no-trpc-why-openapi-codegen.md).

## Organization guidelines

- Route files compose pages; move reusable UI out of `app/`.
- `components/ui/` remains domain-neutral.
- Existing feature code may remain in `components/features/`; use
  `src/features/` for new, larger slices and migrate incrementally.
- Keep server-only code outside client component dependency trees.
- Add tests beside the behavior they verify using `*.test.tsx`.
