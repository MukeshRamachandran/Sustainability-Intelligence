# Microcosm Development and Review Protocol

This protocol is automatically applied when the project owner gives a basic
phase request. The owner is not expected to provide a formal technical prompt.
The implementation agent must translate the request into a bounded phase plan,
verification plan and independent senior-review gate.

## 1. Separate types of work

Each task must be classified before action:

- **Audit/design:** read-only; no file edits, SQL application, staging, commit or
  push.
- **Implementation:** make only the approved scoped changes and tests.
- **Senior review:** independent and read-only; do not repair findings during
  the review itself.
- **Controlled staging:** apply only the reviewed migration/change to staging.
- **Production promotion:** separate authorization after staging evidence.

Audit approval does not authorize implementation. Implementation completion
does not authorize SQL application, commit, push or production promotion.

## 2. Baseline evidence

Before every implementation or review, record as applicable:

```text
git status --short
git branch --show-current
git rev-parse HEAD
git diff --name-status
git diff --stat
```

Preserve user-owned or unrelated changes. Report a dirty or unexpected baseline
before proceeding when it prevents reliable scope attribution. Confirm the
actual code, schema, policies and runtime behavior; never infer implementation
solely from filenames or documentation.

## 3. Phase plan

Every phase must state:

- objective and non-goals;
- files, tables, functions, roles and routes in scope;
- workflow actors and state transitions;
- public/private data boundary;
- expected migrations and whether historical migrations are touched;
- test and verification evidence required;
- staging sequence and rollback/recovery approach;
- explicit exit criteria.

Avoid unrelated redesign and V1 overbuilding.

## 4. SQL and migration discipline

- Use ordered, immutable migration files.
- Never edit an already applied historical migration. Add a new migration.
- Calculate SHA-256 for every migration accepted into the canonical chain.
- Preserve a manifest of migration filename, normalized/byte hash, review date
  and application status.
- Review functions, triggers, views, constraints, indexes, grants, revocations,
  RLS policies, ownership and schema qualification.
- Prefer `security invoker`. Every necessary `security definer` function must
  have a justified purpose, fixed safe `search_path`, qualified object names,
  least-privilege grants and direct authorization checks.
- Do not use dynamic SQL unless evidence proves it necessary and safe.
- Do not apply SQL during an audit or senior-review-only task.
- Apply reviewed SQL to staging before production.

## 5. Canonical SQL verification

Each database phase must supply executable verification SQL that checks, where
applicable:

- exact table, column, type, constraint and index definitions;
- function/RPC existence and exact signatures;
- function security mode, owner and `search_path`;
- grants and revocations for anon, authenticated and service roles;
- RLS enabled and forced where appropriate;
- exact policy commands, roles, predicates and check expressions;
- private Storage bucket and object-policy restrictions;
- public views expose approved aggregates only;
- immutable approved-record enforcement;
- audit-trigger/function presence;
- expected denial for anonymous and wrong-domain users;
- migration history and SHA-256 manifest consistency.

Verification must distinguish source-text assertions from behavior proven in a
real PostgreSQL/Supabase staging environment.

## 6. Security searches

Search changed production and migration files for at least:

```text
service_role
secret
password
credential
token
raw_user_meta_data
raw_app_meta_data
auth.users
SECURITY DEFINER
search_path
EXECUTE
format(
dynamic SQL
INSERT
UPDATE
DELETE
UPSERT
storage path
signed URL
hard-coded email
hard-coded UUID
dangerouslySetInnerHTML
```

Every legitimate match must be explained. Absence of a text match is not, by
itself, proof of security.

## 7. Test quality

Do not report only test counts. Review whether tests genuinely prove:

- calculation correctness and unit conversion;
- missing versus confirmed-zero behavior;
- academic-year period boundaries;
- workflow state-transition enforcement;
- role and domain authorization;
- self-approval denial;
- approved-record immutability;
- private bill isolation and file constraints;
- public approved-only projection;
- invalid input, boundary and concurrency behavior;
- loading, empty, incomplete and error states;
- desktop/mobile accessibility and navigation;
- regression protection for existing dashboard behavior.

Run focused tests, the full regression suite, syntax/type/static checks, build,
and `git diff --check` when those commands exist.

## 8. Independent senior review

The senior review is review-only and must inspect the actual diff and untracked
files. It must not modify files, apply SQL, stage, commit, push or begin the next
phase.

Review areas:

- scope control and unrelated changes;
- architecture and end-to-end handoffs;
- database integrity and migration safety;
- authentication, authorization, RLS and Storage;
- privacy and least-data projection;
- carbon-accounting and calculation semantics;
- auditability and operational recovery;
- UI, accessibility, mobile and error states;
- test strength and gaps;
- documentation and staging readiness.

Classify findings as blocking, high, medium or low. Critical/high findings must
be corrected and independently reverified before the phase passes.

## 9. Controlled staging

The standard staging order is:

1. Reconfirm Git baseline and migration SHA-256.
2. Back up or confirm recoverability of staging.
3. Apply only the reviewed migration set.
4. Verify installed definitions against canonical verification SQL.
5. Test one real account for each manager domain and one administrator.
6. Verify anonymous, wrong-domain, inactive and unverified denial.
7. Test evidence upload type/size/privacy and signed access expiry.
8. Test draft, submit, correction, approve and immutable-approved behavior.
9. Verify public dashboard approved-only aggregates and incomplete-period flags.
10. Run calculations against known reference fixtures.
11. Inspect desktop and mobile workflows.
12. Record evidence and do not promote to production in the same gate.

## 10. Git and integrity checks

Before requesting commit approval:

```text
git status --short
git diff --name-status
git diff --stat
git diff
git diff --check
git diff --cached --check
```

Confirm that commit scope matches the phase, no secrets or generated clutter are
included, and historical migrations retain their recorded SHA-256 values.
Staging, committing, pushing and opening a pull request require explicit scope
and must occur only after the relevant review/staging gate.

## 11. Phase verdict

Every senior phase review returns exactly one verdict:

- `APPROVE FOR CONTROLLED STAGING`
- `APPROVE WITH NON-BLOCKING NOTES`
- `REJECT — BLOCKING CHANGES REQUIRED`

The report includes baseline, reviewed scope, findings by severity, migration
and hash verdict, SQL/RLS/privacy verdicts, test evidence, security-search
results, staging checklist, accepted risks and authorization for the next step.
