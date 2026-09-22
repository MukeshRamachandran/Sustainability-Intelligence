# Phase 1 Calculation-Fix Review

Date: 2026-08-10
Pre-phase baseline: `b985fa8f25b8fa7ede0cc3a972285bc455f30778`

## Scope

- Preserve missing observations as unavailable rather than numeric zero.
- Use approved records only and expose incomplete monthly coverage.
- Prevent renewable period totals from being fabricated into monthly values or double counted.
- Apply year/month filters consistently to KPIs, charts, explorer rows, and CSV export.
- Separate avoided-emissions estimates from the formal Scope 1 and Scope 2 inventory.
- Document backend requirements and phase governance.

## Independent senior verdict

`APPROVE WITH NON-BLOCKING NOTES`

No critical or high findings remain. Non-blocking notes are to add browser-level UI tests in a later phase and manage the repository's existing line-ending convention deliberately.

## Verification evidence

- `node --check app.js`
- `node --check data-loader.js`
- `node --check walkthrough.js`
- `node --test --test-isolation=none tests\\data-loader.test.js tests\\ui-contract.test.js` — 10/10 passed
- `git diff --check` — passed; existing LF-to-CRLF conversion warnings noted
- Secret-pattern scan — no credential values found
- Changed-file size review — no new or modified large binary files

## Baseline boundary

This phase contains dashboard calculation, data-quality, terminology, tests, requirements, and governance changes only. It does not contain Supabase schema, authentication, storage policies, RLS policies, production deployment, or SQL migrations.
