# Phase B3 — Controlled Staging Application Plan

Status: Planning only — no staging execution authorized  
Date: 2026-08-11  
Approved source baseline: `3fd4a9123c0f2d766a2a6e1a01c9164dab834c4c`

## 0. Authorization boundary

This runbook prepares a future execution. It does not authorize project access,
project creation, CLI login/linking, user creation, SQL execution, migration
application, Storage changes, Git staging, or commit. The first real action
requires a separate owner approval and must target a new non-production project.

One named operator runs the migration push. A separate observer records
evidence and verifies project identity before the operator continues.

### Mandatory B2.1 source prerequisite

The current B2 source is **NO-GO for application** until a separately reviewed
follow-up migration and verification update are prepared:

1. Configure the Supabase Data API to expose only a dedicated `api` schema in
   addition to required platform defaults. Never expose `app_private`.
2. Add least-privilege `api` wrapper RPCs for manager/admin operations. Each
   delegates to a protected private function, has explicit grants/revokes and a
   reviewed security mode/search path, and exposes no operational tables.
3. Expand executable verification to assert exact columns/types, constraints,
   indexes, triggers, policies, RPC signatures/owners/security/search paths,
   grants/revokes, bucket existence/size/MIME allowlist and migration versions.
4. Update hashes/tests and obtain independent review. This B2.1 preparation
   requires separate owner approval and is not performed in Phase B3.

## 1. Staging project creation checklist

### Separate authorization gates

- **Gate B3.1 — project creation/configuration only:** create the empty staging
  project and record identifiers; no CLI link or SQL.
- **Gate B3.2 — link/read-only preflight only:** run exactly `supabase --version`,
  `supabase login`, `supabase link --project-ref <STAGING_REF>`,
  `supabase migration list`, and `supabase db push --dry-run`; then stop.
- **Gate B3.3 — migration application only:** after B2.1 review and a new
  approval, run exactly one `supabase db push`; then stop on its result.
- **Gate B3.4 — verification/users:** run approved verification, create staging
  personas and execute runtime tests. It does not authorize production.

Each gate requires its own target, action list, owner approval, evidence and
stop/go decision. Approval for an earlier gate never rolls into the next.

- [ ] Create a new Supabase organization/project clearly named
      `microcosm-staging`; never reuse a production or personal test database.
- [ ] Select the intended region and record it; production-region choice is a
      later decision.
- [ ] Generate a unique database password using a password manager.
- [ ] Confirm the dashboard shows the staging project name and reference.
- [ ] Add a visible `STAGING — NO REAL COLLEGE DATA` project description/tag.
- [ ] Disable anonymous Auth users and unneeded OAuth/phone providers.
- [ ] Enable email/password and Confirm Email.
- [ ] Configure only staging redirect URLs; exclude production domains.
- [ ] Configure Auth rate limits and CAPTCHA if public signup will be exercised.
- [ ] Confirm built-in `auth.audit_log_entries` and platform-log availability;
      separately confirm plan/retention support for the required Log Drain.
- [ ] Confirm PITR/backups available for the chosen plan; otherwise record that
      the new empty project can be recreated from migrations.
- [ ] Restrict Dashboard organization membership to named staging operators.
- [ ] Do not enter real bills or personal/production emissions data.
- [ ] Record project creation time, owner, plan, region and empty-state proof.

## 2. Safe values to collect

These may be recorded in the evidence sheet because they are identifiers or
public client configuration, not privileged credentials:

- staging project name;
- project reference ID;
- Supabase project URL;
- region and plan;
- publishable/anonymous client key **only if needed for later public/RLS tests**;
- expected migration filenames and SHA-256 values;
- CLI version, PostgreSQL version, Auth/Storage configuration screenshots;
- test-user email addresses (not passwords);
- evidence bucket name `submission-evidence`;
- execution timestamps and operator/reviewer names.

Treat even public keys as configuration: do not post them unnecessarily and
never confuse them with privileged secrets.

## 3. Secrets never to paste into chat, documents, screenshots or Git

- Supabase Personal Access Token (`sbp_...`);
- database password or connection URI;
- secret/service-role key;
- JWT signing secret or private signing keys;
- SMTP credentials;
- TOTP seed, QR code, recovery codes or one-time MFA code;
- any test-user password, password-reset link, access token, refresh token,
  session cookie or Authorization header;
- Log Drain ingest secret;
- signed evidence URL or private object contents;
- `.env` file contents.

Enter secrets only into the official Supabase UI, OS credential manager or a
local ignored environment file. Redact terminal/screenshots before retention.

## 4. Supabase CLI setup plan

Do not execute these commands until the staging-execution approval.

1. Install a pinned current CLI using an official supported method; record the
   source and version with `supabase --version`.
2. Confirm Docker Desktop only if local-stack rehearsal is separately approved.
3. From the repository root, confirm the existing `supabase/` directory before
   using `supabase init`; do not run `init --force` over reviewed configuration.
4. Authenticate interactively with `supabase login` so the token goes to native
   credential storage. Never use `--token` where shell history or screenshots
   may capture it. If native storage is unavailable, stop and select an approved
   secret-management method.
5. Link explicitly to staging using `supabase link --project-ref <STAGING_REF>`.
   Re-read the resulting project reference and compare it with the approved
   evidence sheet.
6. Run `supabase migration list` before any push. A new staging project must
   have no unexpected user migrations.
7. Do not use `db pull`, `migration repair`, `db reset --linked`, Dashboard SQL
   Editor, or Table Editor during the canonical application. `db reset
   --linked` is destructive.
8. Run `supabase db push --dry-run`. Capture redacted output and require both
   operator and observer to confirm the exact reviewed versions/order and no
   unexpected SQL.
9. Pause for an explicit continue/stop decision. The eventual application is
   one coordinated `supabase db push`. Do not use `--include-seed`; reference
   seeds are already migration `0010`.

Official references: [CLI reference](https://supabase.com/docs/reference/cli/getting-started),
[database migrations](https://supabase.com/docs/guides/deployment/database-migrations),
[CLI workflows](https://supabase.com/docs/guides/local-development/cli-workflows).

## 5. Local environment-file plan

Use `.env.staging.local`, already covered by `.gitignore` through `.env.*`.
Create it manually only after execution approval. Suggested variable names:

```text
SUPABASE_PROJECT_REF=
SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
```

Keep the database password in native credential storage/password manager, not
the default environment file. `SUPABASE_DB_PASSWORD` is allowed only for a
separately approved noninteractive run. Do not store the service-role key unless a later protected Edge/worker test
requires it. If required, keep it in the OS secret manager or Supabase Edge
Function secrets, not this repository. Restrict the local file to the operator,
verify `git status --ignored`, and delete it securely after the staging window
if the password manager is the system of record.

## 6. Canonical migration application order

Before execution, recompute every hash and compare with `SHA256SUMS` byte for
byte. Apply only through the CLI in lexical order:

1. `0001_extensions_schemas_types.sql`
2. `0002_identity_roles_settings_audit.sql`
3. `0003_metrics_submissions.sql`
4. `0004_private_evidence_storage.sql`
5. `0005_review_workflow.sql`
6. `0006_emission_factors_calculations.sql`
7. `0007_public_releases.sql`
8. `0008_auth_storage_audit_integration.sql`
9. `0009_authorization_workflow_publication.sql`
10. `0010_seed_reference_data.sql`
11. `0011_security_integrity_hardening.sql`

No migration is edited during execution. A defect produces a new reviewed
follow-up migration; never repair history merely to make the status look green.

## 7. Pre-application verification checklist

- [ ] Owner has separately authorized the exact staging execution window.
- [ ] Independent senior source verdict remains approved.
- [ ] `git status --short` contains only understood Phase B1/B2/B3 files.
- [ ] Current HEAD and reviewed source baseline are recorded.
- [ ] `SHA256SUMS` matches all eleven migrations.
- [ ] Full 17-test suite and `git diff --check` pass again.
- [ ] Secret scan finds no credential material.
- [ ] CLI version is recorded and compatible with the hosted project.
- [ ] Project name/reference/URL independently match the staging evidence sheet.
- [ ] Staging is empty; `supabase migration list` shows no unexpected history.
- [ ] Database recoverability/recreation method is recorded.
- [ ] No real users/data/bills exist in staging.
- [ ] Confirm Email is enabled; administrator MFA/TOTP is available.
- [ ] One operator holds the keyboard; one reviewer watches identity and output.
- [ ] Terminal transcript location is ready with secret redaction.
- [ ] Stop conditions and recovery owner are acknowledged.

Stop immediately for a project-reference mismatch, hash mismatch, unexpected
migration, dirty/unexplained source, credential exposure, or unavailable
recovery path.

## 8. Post-application SQL verification checklist

After the B2.1 expansion passes source review, run the canonical executable
verification SQL through an approved
read-only-capable method against staging. It uses a transaction and rolls back.
Capture results without secrets. Additionally verify through catalog queries:

- [ ] exact schemas, enums, tables, columns, constraints, indexes and triggers;
- [ ] all operational tables have RLS enabled and forced;
- [ ] grants/revokes for `anon`, `authenticated`, `service_role` and PUBLIC;
- [ ] exact RPC signatures, owner, security mode and fixed `search_path`;
- [ ] no executable privilege exists beyond the intended roles;
- [ ] private bucket, 10 MiB limit and PDF/PNG MIME allowlist;
- [ ] no authenticated direct-write Microcosm Storage policy;
- [ ] public view exposes only an active release;
- [ ] seed settings equal June, seven years, admin MFA true;
- [ ] seeded factors are exact and remain `draft`;
- [ ] migration history contains the exact expected migration versions in
      order; compare names only if the installed CLI/catalog exposes them;
- [ ] recomputed deployed source/manifest evidence is retained.

Catalog success is not behavior proof; complete Sections 9–14 afterward.

### Runtime runners and dependency split

Executable after B2.1 and Gate B3.4 approval:

- a local Node test runner using `@supabase/supabase-js`, the staging URL and
  publishable key, with one fresh authenticated session/JWT per persona;
- administrator `aal1` and `aal2` sessions created through official Auth/MFA
  APIs; never hand-edit JWT claims;
- a protected administrative runner for the service-role-only one-time
  bootstrap, with its secret supplied from credential storage;
- `psql`/approved SQL runner for transactional catalog verification only;
- parallel Node workers for stale-version, approval and factor-lock tests.

Expected denials record HTTP/PostgREST code, PostgreSQL SQLSTATE where returned,
and sanitized message. Fixtures use synthetic zero/nonzero/null activity and
small generated PDF/PNG files containing no real bills.

Blocked until separately implemented and reviewed:

- controlled Edge upload streaming/create-only behavior;
- malware scanner/validator worker;
- signed-URL issuance endpoint;
- Auth/Storage Log Drain receiver and reconciliation scheduler.

The bucket/RLS/catalog portions can be tested earlier, but Phase B3 runtime must
not be called complete and no production go-live can occur until these blocked
dependencies and their tests pass.

## 9. Test-user creation plan

Use four dedicated non-production mailboxes and unique password-manager-generated
passwords. Never reuse staff production passwords.

| User | Required domain | Application role | Domain |
|---|---|---|---|
| Scope 1 test manager | `@kct.ac.in` | `scope1_manager` | `scope1` |
| Scope 2 test manager | `@kct.ac.in` | `scope2_manager` | `scope2` |
| Renewable test manager | `@kct.ac.in` | `renewable_manager` | `renewable` |
| Staging administrator | `@kct.ac.in` or trusted `@kclas.ac.in` | `administrator` | null |

Create/invite accounts through Supabase Auth only after migrations verify.
Confirm every email before role assignment. Capture user IDs only in the secure
staging evidence sheet. Test unverified and wrong-domain users separately, then
delete/deactivate them after denial evidence.

## 10. Bootstrap and role-assignment plan

1. Confirm `institution_settings` was seeded before bootstrap.
2. Create and verify the staging administrator Auth account.
3. Invoke the service-role-only `bootstrap_first_admin` once from a protected
   server/administrative runner. Never expose the service key in a browser.
4. Verify profile, one administrator role, bootstrap completion and audit event.
5. Prove a second bootstrap attempt fails.
6. Enroll and verify administrator MFA before any administrator RPC.
7. Create/verify manager accounts and call MFA-protected `assign_role` from the
   administrator session.
8. Confirm exact domain pairing and one active role per user.
9. Negative tests: unverified email, wrong email domain, manager with null/wrong
   domain, duplicate role, manager assigning roles and self-revocation.
10. Test `revoke_role` and `deactivate_profile` on a disposable fifth account,
    then confirm immediate authorization denial and audit events.

## 11. Administrator MFA verification plan

Use a staging-only TOTP authenticator entry. Do not capture the QR/seed or code.

- Confirm password-only session reports `aal1` and administrator RPCs fail.
- Enroll and verify TOTP, refresh the session, and confirm `aal2`.
- At `aal2`, confirm administrator review/role/factor/release RPC authorization.
- Refresh/sign out/sign in and prove MFA challenge is required again.
- Test lost-factor recovery with documented two-admin continuity before
  production; do not disable MFA as a shortcut.
- Capture only assurance-level results and redacted RPC outcomes.

Supabase exposes `aal1`/`aal2` through JWT claims and MFA APIs; UI enrollment
alone is insufficient without database enforcement. See the
[MFA guide](https://supabase.com/docs/guides/auth/auth-mfa).

## 12. Private evidence Storage verification

- Confirm `submission-evidence` is private.
- Confirm bucket limit is exactly 10,485,760 bytes and MIME allowlist is PDF/PNG.
- Confirm anon cannot list/read/download/sign any object.
- Confirm managers cannot directly insert/update/delete Storage objects.
- Through the future controlled upload endpoint, accept valid PDF/PNG below and
  exactly at 10 MiB; reject above 10 MiB.
- Reject JPG, SVG, executable, renamed executable, forged MIME, malformed PDF,
  path traversal and reused/expired authorization.
- Prove parallel claims permit only one upload and create-only/no-upsert holds.
- Prove quarantined/failed/infected/missing-metadata objects cannot be read by
  uploader or administrator.
- In staging, exercise type/size/private/RLS/audit controls. Malware scanning
  must be integrated and pass before production; until then, never mark
  unscanned production evidence clean.
- Confirm clean evidence receives short-lived access only after protected
  authorization; capture expiry behavior, not the signed URL.
- Confirm approved evidence association cannot be changed/deleted.

Private bucket access is enforced with RLS, and signed URLs remain valid until
their expiry, so keep expiry short. See [Storage buckets](https://supabase.com/docs/guides/storage/buckets/fundamentals),
[file limits](https://supabase.com/docs/guides/storage/uploads/file-limits), and
[private downloads](https://supabase.com/docs/guides/storage/serving/downloads).

## 13. RLS runtime persona matrix

For each operation, capture allowed result or expected SQL/API denial:

| Test | anon | unassigned | wrong manager | owning manager | admin aal1 | admin aal2 |
|---|---:|---:|---:|---:|---:|---:|
| Read public active release | Allow | Allow | Allow | Allow | Allow | Allow |
| Read operational submission | Deny | Deny | Deny | Own only | Review scope | Review scope |
| Create/edit domain draft | Deny | Deny | Deny | Allow own | Deny | Deny |
| Submit/resubmit | Deny | Deny | Deny | Allow own valid | Deny | Deny |
| Review/correct/approve | Deny | Deny | Deny | Deny | Deny | Allow |
| Assign/revoke role | Deny | Deny | Deny | Deny | Deny | Allow |
| Manage factors/publish | Deny | Deny | Deny | Deny | Deny | Allow |
| Read clean evidence | Deny | Deny | Deny | Own only | Deny | Allow |
| Direct Storage write | Deny | Deny | Deny | Deny | Deny | Deny |
| Mutate approved/audit/release | Deny | Deny | Deny | Deny | Deny | Deny |

Also test stale row versions, simultaneous approvals, overlapping intervals,
factor activation races, upload replay and release preparation during approval.

## 14. Public approved-only API/view tests

1. Before an active release, anonymous query returns no payload—not drafts.
2. Insert submissions through each manager workflow; verify draft, submitted,
   correction and approved-but-unpublished values never appear publicly.
3. Approve all three domains for one genuine monthly period with frozen factors.
4. Prepare a candidate; verify anonymous still sees the prior release/nothing.
5. Validate JSON keys against `dashboard_master.json`, including null versus
   confirmed zero, month names, coverage, period totals and content hash.
6. Publish with administrator `aal2`; confirm atomic switch to exactly one active
   release.
7. Verify latest complete month requires three final approved monthly domains.
8. Verify a period total is retained in `period_totals` and never fabricated
   into monthly values or completeness.
9. Confirm no IDs, emails, evidence paths, notes, audit metadata or unpublished
   data appear in the public response.
10. Attempt concurrent approval/factor/release operations and confirm the lock
    protocol yields a consistent release.

## 15. Failure, rollback and recovery plan

### Before/during migration push

- A migration failure stops the run. Do not rerun blindly, edit applied files,
  use `migration repair`, or execute ad-hoc Dashboard SQL.
- Capture the redacted error, `migration list`, failing filename and project ID.
- Determine whether the migration transaction rolled back and run read-only
  catalog inspection.
- Because this is a new empty staging project, preferred recovery is often to
  delete/recreate the staging project or restore a pre-application backup, then
  apply a newly reviewed corrective migration chain.
- `db reset --linked` is destructive and requires a new explicit approval even
  for staging.

### After successful application

- Never reverse an applied migration by editing history. Add a reviewed forward
  corrective migration.
- Public rollback reactivates a prior immutable release through the authorized
  recovery design; do not edit payload rows.
- For credential exposure: stop, revoke/rotate immediately, invalidate sessions
  as applicable, preserve audit evidence and restart only after incident review.
- For RLS/privacy failure: stop all testing, disable affected access, preserve
  evidence and treat as no-go.

## 16. Evidence to capture

Store evidence in a restricted staging-review folder, not the repository:

- project name/reference/region/plan with secrets hidden;
- Auth configuration showing email confirmation and MFA settings;
- CLI version, pre/post `migration list`, push start/end and exit status;
- SHA-256 comparison and Git/source baseline;
- redacted verification SQL output and catalog results;
- bucket private/type/size settings;
- one redacted allow and denial result for each RLS matrix row;
- administrator `aal1` denial and `aal2` success without token/TOTP;
- workflow state changes, immutable-approved denial and audit events;
- evidence accept/reject/quarantine/clean/expiry outcomes without bill content or
  signed URLs;
- public empty, approved-but-unpublished hidden, and published response;
- concurrency test outcomes, latest-complete/missing-domain/period-total proof;
- failure/rollback rehearsal and final reviewer sign-off.

Every screenshot must hide keys, passwords, tokens, UUIDs where unnecessary,
emails beyond what the review requires, connection strings and private paths.

## 17. Final go/no-go checklist before first application

Go only if every item is yes:

- [ ] B2.1 API façade and expanded executable verification are prepared,
      hashed, tested, independently approved and included in the expected order.
- [ ] Owner explicitly approves the first staging execution step.
- [ ] Target is a newly created, empty, clearly named staging project.
- [ ] Project reference is independently double-checked.
- [ ] Migration hashes match the reviewed manifest.
- [ ] Source tests and senior review remain passing.
- [ ] No secrets are present in files, Git, chat, screenshots or command line.
- [ ] CLI authentication uses secure credential storage.
- [ ] Recovery/recreation path and stop conditions are agreed.
- [ ] Test mailboxes, administrator authenticator and evidence fixtures are ready.
- [ ] Operator, observer and evidence locations are named.
- [ ] `supabase db push --dry-run` lists only the exact reviewed migrations and
      the observer has signed the continue/stop checkpoint.
- [ ] No production data, accounts or integrations are connected.
- [ ] The current gate authorizes only its Section 1 actions: B3.2 link/read-only
      preflight, B3.3 one migration push, or B3.4 verification—never more than
      one gate and never production promotion.

Any “no”, uncertainty, unexpected remote state, warning involving migration
history, or secret exposure means **NO-GO**.

## 18. Approval request

Approval of this plan alone authorizes no external action. The next eligible
approval is B2.1 source preparation, followed by Gate B3.1 project creation.
Gate B3.2 exact commands are listed in Section 1; Gate B3.3 is exactly one
`supabase db push`. No gate authorizes production, destructive reset, migration
repair, frontend integration, Git commit, or additional Supabase projects.
