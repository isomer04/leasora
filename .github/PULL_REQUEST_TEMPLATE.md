<!--
Thanks for the PR! Every PR must complete this template. Reviewers will reject
PRs that skip the checklist or that lack a self-review on solo PRs.

Per CONTRIBUTING.md: future `docs(review):` / `docs(plan):` /
`verification notes` commits should be squashed before merge. The history should
describe *what changed*, not the *process around what changed*.
-->

## What does this PR change?

<!-- One or two sentences. If the change has a longer rationale, link to an
issue or ADR — don't duplicate the explanation here. -->

Fixes #<!-- issue number, if any -->.

## How is the change verified?

<!-- List the commands you ran (pnpm test, leasora eval, manual UI smoke test,
etc.) and their results. For eval changes include the before/after numbers. -->

- [ ] `pnpm lint` passes
- [ ] `pnpm type-check` passes
- [ ] `pnpm test` passes
- [ ] Manual smoke / curl / UI check (describe above)
- [ ] New behavior has a test
- [ ] Eval-suite impact considered (if RAG-relevant): ran `leasora eval` and
      numbers in `docs/EVALUATION_REPORT.md` still hold, or this PR explicitly
      updates them

## Architecture impact

<!-- Skip if trivial. -->

- [ ] No architecture-rule changes
- [ ] If architecture rules are affected, an ADR is updated (or a new ADR is
      added in the same PR)
- [ ] If a new dependency is added, it is justified in the PR description and
      approved by a maintainer

## Security & privacy impact

- [ ] No new PII flows added
- [ ] If PII handling is touched, `redact_pii` runs before persistence and
      before any Langfuse span input/output
- [ ] If a new external service or env var is introduced, it is **off by
      default** and opt-in (see ADR-005 pattern)

## Review checklist

<!-- Two reviewers for a non-trivial change is the goal. For solo work, the
PR author self-reviews in the "Self-review" section below — do not leave the
reviewer field blank. -->

- [ ] **Reviewer:** <!-- name or "self" -->
- [ ] **Second reviewer** *(or "no second reviewer because solo project —
      self-review below")*:
- [ ] Code is read top-to-bottom by at least one reviewer
- [ ] Tests are read and the failure modes they exercise make sense
- [ ] Docs updated (README / docs/ / inline) if behavior or workflow changed
- [ ] Commit history is clean (no `docs(review):` / `docs(plan):` /
      `verification notes` commits left in)

## Self-review *(required for solo PRs)*

<!-- If you are the sole contributor, do the reviewer's job here. Walk through
your own diff and note the things a reviewer would have asked about. -->
