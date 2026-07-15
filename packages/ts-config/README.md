# @leasora/ts-config

Shared TypeScript compiler configurations for Leasora workspace packages.

## Base configuration

```json
{
  "extends": "@leasora/ts-config/base.json"
}
```

## Next.js configuration

```json
{
  "extends": "@leasora/ts-config/next.json"
}
```

Project-specific `include`, `exclude`, output, and path settings remain in the
consuming package's `tsconfig.json`.
