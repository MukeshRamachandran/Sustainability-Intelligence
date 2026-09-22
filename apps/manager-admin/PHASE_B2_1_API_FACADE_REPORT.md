# Phase B2.1 — Supabase Data API Façade Report

Date: 2026-08-11  
Status: Senior-reviewed — approved with non-blocking notes  
Baseline: `3fd4a9123c0f2d766a2a6e1a01c9164dab834c4c`

## Scope

- Added additive migration `0012_api_facade.sql`.
- Revoked client schema/table/sequence/function access in `app_private`.
- Added an allowlisted `api` RPC façade and approved-only dashboard RPC.
- Kept audit, bootstrap, evidence scan/path/read, worker and private workflow
  implementation out of the browser-facing API.
- Added local Data API configuration exposing only `api`; hosted configuration
  remains a separate B3 gate and is not changed by this file.
- Expanded executable verification and source tests.
- Updated the SHA-256 migration manifest.

## Access contract

Anonymous users can execute only `api.get_dashboard()`. Authenticated users can
execute workflow wrapper RPCs, but every operation delegates to private
authorization that verifies active profile, confirmed email, assigned domain or
administrator role, and administrator `aal2` where required. No client role has
schema usage or routine execution in `app_private`.

Evidence upload/scan/signing primitives are intentionally not exposed through
the client façade. They remain blocked until the protected Edge/worker service
is implemented and reviewed.

## Verification boundary

Source tests and catalog verification prove intended definitions only after
they execute successfully in a controlled database. No SQL, Supabase project,
CLI, user, Storage, staging, Git stage or commit action occurred in B2.1.

## Senior verdict

`APPROVE WITH NON-BLOCKING NOTES`

No critical/high findings remain. The final non-blocking notes were incorporated:
service-only routines have positive and negative ACL assertions,
`api.assign_role()` returns only success rather than an internal assignment ID,
and manager DTOs include non-sensitive start/end period and granularity.

This verdict returns the source to Phase B3 planning. It does not authorize
Supabase access, project creation, CLI operations, migration application, users,
Storage changes, Git staging or commit.
