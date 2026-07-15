# Frontend Feature Slices

This directory is the target location for domain-oriented frontend slices.
The migration is incremental: existing feature components still live under
`src/components/features/`, and reusable data hooks currently live in
`src/hooks/`. Move code only when a feature has enough behavior to benefit
from colocation; do not reorganize unrelated files solely for consistency.

## Recommended shape

```text
features/
└── <feature>/
    ├── components/       # UI owned by the feature
    ├── hooks/            # Feature-scoped behavior and API state
    ├── api/              # Calls through the typed openapi-fetch client
    └── types.ts          # Local UI types, not duplicated API contracts
```

## Boundaries

- Keep route composition in `app/`.
- Keep genuinely reusable presentational primitives in `components/ui/`.
- Keep cross-cutting utilities and the typed client in `lib/`.
- Import API contracts from `@leasora/shared-types`; never copy them by hand.
- Keep server-only modules out of client component dependency trees.
