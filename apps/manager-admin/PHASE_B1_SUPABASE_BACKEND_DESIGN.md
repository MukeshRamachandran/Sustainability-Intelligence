# Phase B1 — Supabase Backend Architecture and Database Design

Status: Senior-reviewed — owner approval required before Phase B2 migration implementation  
Date: 2026-08-11  
Frontend baseline: `3fd4a9123c0f2d766a2a6e1a01c9164dab834c4c`

## 0. Phase boundary

Phase B1 defines the target architecture and database contract. It does not
contain executable SQL, migration files, Supabase project changes, frontend
changes, deployment, or production credentials.

### Objective

Design a backend in which three domain managers submit evidence-backed activity
data, an administrator reviews and approves it, and anonymous dashboard users
receive only sanitized approved aggregates.

### Non-goals

- Applying or drafting production SQL.
- Changing `dashboard_master.json`, `data-loader.js`, or other frontend files.
- Importing historical Excel data.
- Selecting final institutional factor sources, retention duration, or MFA
  policy; these remain explicit configuration decisions.

## 1. Backend architecture overview

```text
Public dashboard (anon) ───────────────► Public API projection
                                                │
Manager/Admin portal ─► Supabase Auth           │ approved, published only
        │                    │                   │
        ├─► private data API/RPC ─► Postgres ────┤
        │                         RLS + workflow │
        └─► private evidence ─────► Storage      │
                                  policies      │
                                                ▼
                                      immutable release rows
```

Components:

1. **Supabase Auth** provides verified-email/password identity. A new account
   has no application privilege. Email verification proves control of an
   address; it does not assign a role.
2. **Private application schema** contains profiles, protected role grants,
   submissions, values, evidence metadata, reviews, factors, settings,
   calculation snapshots, releases, and audit events.
3. **RLS and controlled RPCs** enforce domain ownership and workflow
   transitions in PostgreSQL. UI hiding is never treated as authorization.
4. **Private Storage bucket** stores evidence. Object authorization is tied to
   submission ownership and review access, not merely a guessable path.
5. **Publication pipeline** calculates approved results with the factor version
   frozen at approval, builds sanitized release rows, and atomically activates
   a release. Anonymous users cannot query operational tables.
6. **Public API schema** exposes only active, approved release content and
   coverage metadata. It carries no user IDs, evidence paths, review notes, or
   unpublished values.
7. **Audit ingestion** records application actions synchronously in Postgres.
   Supabase Auth login/logout/failure events are imported from the platform's
   Auth audit/log stream through a protected server-side integration. Passwords,
   tokens, and service keys are never copied into the application audit table.

The browser may use the Supabase anonymous key; that key is public by design and
is constrained by grants and RLS. The service-role key is restricted to secure
server-side/CI secrets and is never shipped to either portal or dashboard.

## 2. Identity and role model

Roles are application records, not user-editable Auth metadata:

- `scope1_manager`
- `scope2_manager`
- `renewable_manager`
- `administrator`

One active domain assignment per manager is recommended for V1. A user may not
hold `administrator` and a manager role simultaneously; this structurally
prevents self-approval. If dual-role operation is ever required, approval must
still reject matching submitter and approver IDs.

Role grants are created only by a protected bootstrap/admin operation running
server-side. Initial administrator bootstrap requires an out-of-band,
single-use procedure recorded in the audit log. Public signup inserts no role.
Authorization reads protected role tables; it must not trust
`raw_user_meta_data`. Role changes revoke active authorization promptly and are
audited.

Email verification, active account status, and active role assignment are all
required for portal access. Protected authorization helpers and every
state-changing RPC check the authoritative Auth user confirmation timestamp
(the Phase B2 catalog check will confirm the current `auth.users` column) rather
than mutable metadata or a potentially stale UI claim. Disabling or unconfirming
a user revokes role access and refresh tokens; short privileged-session TTLs
limit already-issued JWT exposure. MFA is strongly recommended for
administrators and is a configuration decision for managers before production.

## 3. Role-permission matrix

| Capability | Anonymous | Assigned manager | Administrator | Protected server process |
|---|---:|---:|---:|---:|
| Read active public release | Yes | Yes | Yes | Yes |
| Read operational submissions | No | Own assigned domain only | All domains | As narrowly required |
| Create draft | No | Assigned domain only | No by default | Import path only |
| Edit/delete draft | No | Own draft only | No | Controlled recovery only |
| Submit/resubmit | No | Own eligible record | No | No |
| Read own evidence | No | Own submissions | All submissions | Malware/retention job |
| Upload/delete evidence | No | Own unapproved draft/correction only | No direct replacement | Controlled job |
| Start review/request correction | No | No | Yes | No |
| Approve | No | No | Yes, never own submission | No except controlled migration |
| Manage factors/settings | No | Read relevant effective metadata only | Propose/activate | Bootstrap only |
| Assign/revoke privileged roles | No | No | Protected admin operation | Bootstrap/admin service |
| Publish/revoke release | No | No | Controlled administrator RPC | Scheduled publisher if authorized |
| Read audit events | No | No | Restricted audit view | Audit exporter |
| Modify/delete audit events | No | No | No | Retention job only if policy permits |

## 4. Submission workflow state machine

```text
draft ──submit──► submitted ──begin review──► under_review
  ▲                    ▲                           │
  │                    │                           ├─request correction
  │                    └──────resubmit──── correction_requested
  │                                                │
  └────manager edits only before first submit──────┘
                                                   │
                                                   └─approve──► approved ─► published
```

Canonical persisted statuses are `draft`, `submitted`, `under_review`,
`correction_requested`, and `approved`. `published` belongs to the release
record, not the mutable submission status.

Rules:

- A manager creates a draft only for the assigned domain.
- Submission requires the reporting period, required metrics, units, source
  declaration, and required evidence to be valid. Confirmed zero is stored as
  `0`; an omitted measurement remains `null` and is not silently converted.
- Only an administrator can start review, request correction, or approve.
- A correction request requires a reason. The manager can edit the same
  unapproved record and resubmit; every revision remains reconstructable from
  audit and revision records.
- Approval is atomic: validate state and reviewer, select effective factors,
  calculate results, freeze snapshots, write approval/review events, and set
  `approved_at` in one transaction.
- Approved rows, values, evidence associations, factor snapshots, and approval
  decisions are immutable. Database triggers provide defense in depth against
  update/delete even if a future policy is misconfigured.
- A historical correction creates a separately authorized superseding
  submission linked to the prior approved record. It never edits the original.
- Publication is a separate controlled action. An approval may update the next
  candidate release, but anonymous users see it only after atomic activation.
- Concurrency uses row locking and expected version numbers so two reviewers
  cannot approve or request correction simultaneously.

## 5. Database table design

Names below are logical names for Phase B2; types and constraints will be
finalized in migrations.

### Identity and configuration

| Table | Important fields | Integrity notes |
|---|---|---|
| `profiles` | `user_id`, display name, active flag, timestamps | One-to-one with Auth user; no authorization fields editable by user |
| `role_assignments` | ID, user ID, role, domain, active range, granted/revoked by/at | Protected writes; unique active assignment; role/domain consistency |
| `institution_settings` | singleton/key, academic-year start month, email allowlist, retention/MFA settings, version, changed by/at | Start month constrained 1–12; history retained |
| `reporting_periods` | ID, calendar year/month, academic year label/index, start/end dates | Unique calendar month; derived using setting version |
| `metric_definitions` | stable code, domain, name, canonical unit, value kind, required flag, active dates | Prevents managers inventing metrics/units |

### Workflow and evidence

| Table | Important fields | Integrity notes |
|---|---|---|
| `submissions` | ID, domain, period ID or period range, granularity, status, submitter, revision, supersedes ID, source description, timestamps, row version | One active submission per domain/period/granularity unless supersession rules allow; monthly vs period-total explicit |
| `submission_values` | submission ID, metric code, numeric value, unit, measured flag/quality note | Numeric value nullable; zero preserved; canonical unit enforced; unique metric per submission |
| `submission_revisions` | submission ID, revision number, immutable sanitized before/after snapshot, actor, reason, time | Captures draft/correction history without secrets or file bytes |
| `evidence_upload_authorizations` | ID, submission ID, generated object path, uploader, expected MIME/extension, maximum bytes, expires at, consumed at, status | Created before upload; one-use capability bound to one eligible draft and uploader |
| `evidence_files` | ID, authorization ID, submission ID, bucket, object path, original display name, detected MIME, bytes, SHA-256, uploader, uploaded time, validation/scan status | PDF/PNG allowlist; <=10 MiB; unique object path; quarantined until clean |
| `review_actions` | ID, submission ID, action, reviewer, reason, from/to state, time | Append-only; correction reason required; reviewer differs from submitter for approval |

### Factors, calculations, and publication

| Table | Important fields | Integrity notes |
|---|---|---|
| `emission_factor_sets` | ID, version label, status, jurisdiction/source, valid-from/to, proposed/approved by/at | Draft/active/retired lifecycle; no overlapping active applicability for same context |
| `emission_factors` | set ID, code, input unit, output unit, numeric factor, gas/scope/method, source citation | Positive/allowed-zero constraint; unique code per set; immutable after set activation |
| `approval_calculations` | submission ID, metric, activity value/unit, factor ID/value/units, result, formula version, calculated at | Immutable provenance snapshot; calculation reproducible if factors later change |
| `aggregate_releases` | ID, release version, generated/approved/published by/at, status, content SHA-256, supersedes release | Exactly one active release; activation transaction is atomic |
| `public_energy_rows` | release ID, period ID, industrial/HT, temporary, commercial, procured RE, EB excluding RE, on-campus RE, solar water heater, total RE, DG kWh, completeness | Built only from approved source records; no submitter metadata |
| `public_transport_rows` | release ID, period ID, petrol litres, diesel litres, vehicle count, completeness | Built only from approved Scope 1 source records |
| `public_coverage` | release ID, period ID, Scope 1/2/renewable status, missing domain list, complete flag | Makes absence explicit instead of coercing to zero |
| `audit_events` | ID, occurred/recorded at, actor ID/type, event type, target type/ID, request correlation, outcome, metadata, previous hash/event hash | Append-only, redacted, indexed for investigation |

All measurements should use fixed-precision numeric types, never floating point.
Timestamps use UTC-aware types. IDs use non-sequential UUIDs. Human filenames
are metadata only and never become authorization identifiers.

### Granularity and period totals

`submissions.granularity` distinguishes `monthly` from `period_total`.
Period-total submissions require explicit start/end period IDs. They are
aggregatable only at a coverage that contains the complete interval and must
never be divided across months. The canonical V1 rule is **reject overlap**:
the same metric cannot have both an approved period total and an approved
monthly value within that total's coverage. A superseding record replaces the
prior record for publication but preserves it historically. Historical imports
with overlap enter a conflict queue and cannot be approved or published until
an administrator selects one authoritative granularity with a recorded reason.
Public monthly rows contain `null` for a metric known only as a period total; a
separate period-total projection carries its actual coverage and value.

## 6. RLS policy design

RLS is enabled on every application table and forced on owner-accessible
operational tables where practical. Base privileges are revoked before narrow
grants are added.

### Authorization helpers

Small, schema-qualified helper functions answer `is_active_admin()` and
`has_active_domain(domain)`. Prefer security-invoker behavior. Any required
security-definer transition RPC has a fixed safe `search_path`, fully qualified
objects, explicit authentication/role/state checks, narrow execute grants, and
no dynamic SQL.

### Policy intent

- `anon`: no operational schema access; select only stable public projections.
- authenticated unassigned/unverified/inactive user: no portal data access.
- manager select: own submissions in assigned domain and their values/evidence
  metadata/review responses.
- manager insert: submitter must equal authenticated user and domain must equal
  active assignment; initial status must be `draft`.
- manager update/delete: own record only while state permits; domain,
  submitter, period identity, and protected workflow fields cannot be changed
  directly. State transitions use controlled RPCs.
- administrator select: all workflow data required for review.
- administrator direct writes: generally denied; controlled RPCs perform
  review, approval, factor activation, role assignment, and publication.
- approved/released/audit rows: no client update/delete policy.
- factor draft writes: administrator via controlled operations; active factor
  rows immutable.

Column-level grants supplement RLS because RLS controls rows, not which columns
within an allowed row may be changed. Constraints and immutable triggers remain
the final integrity layer.

## 7. Storage bucket and private evidence policies

Bucket: `submission-evidence`, `public = false`, file-size limit 10 MiB. Objects
begin in quarantine and are unreadable by managers and reviewers until their
database record is `clean`.

Allowed content:

- `application/pdf`
- `image/png`

Object key format uses server-generated identifiers, for example
`<domain>/<submission-uuid>/<evidence-uuid>.<ext>`. Authorization validates the
linked database metadata, submission ownership/domain, and workflow state; it
does not rely on path text alone.

Defense in depth retains an authenticated Storage INSERT policy that would
accept only the exact active pending authorization/uploader/path, but direct
client INSERT grants remain revoked in V1. UPDATE/DELETE are denied to clients.
The controlled upload endpoint is the only normal writer, and every download
policy requires a matching application `evidence_files` row with `clean`
status.

Upload sequence:

1. Manager owns an eligible unapproved submission and requests a pending upload
   authorization. A protected operation creates a one-use, short-expiry record
   binding uploader, submission, generated key, expected PDF/PNG type, and the
   10 MiB maximum.
2. Browsers have no direct Storage insert/update/delete grant. A protected Edge
   Function atomically claims the authorization (`pending` to `uploading`) with
   compare-and-set semantics, rechecks verified role, and writes an
   `upload_started` audit event. It streams to the exact key using a server-only
   credential with create-only/no-upsert behavior, then calls an idempotent
   finalize operation. Concurrent/replayed claims fail unless they carry the
   same idempotency key and return the already-known result. No custom trigger
   or function is attached to Supabase's managed `storage` schema.
3. The upload endpoint rejects excessive size and disallowed declared MIME. The
   finalize operation atomically consumes the authorization, creates evidence
   metadata as `quarantined`, and records upload outcome. A protected validator
   independently checks byte count, magic bytes, parseability, SHA-256, and
   malware scan; extension and browser MIME are insufficient.
4. Only successful validation changes status to `clean`. Download policies and
   signed-URL issuance require `clean`; `pending`, `quarantined`, `failed`, and
   `infected` objects are unreadable to managers and reviewers.
5. Failure records a safe reason code, blocks submission, and schedules
   privileged deletion after the quarantine window. Retry uses a new key.
6. Upload failure records `upload_failed` and leaves the authorization retryable
   until expiry. Upload success followed by finalize failure leaves an
   unreadable orphan; the endpoint retries finalize with the authorization ID,
   while a scheduled reconciler discovers and finalizes or deletes it. Duplicate
   finalize calls return the existing evidence row. Expired authorizations can
   never finalize except through a privileged reconciler decision.
7. The reconciler also handles objects without evidence rows and evidence rows
   without objects. It quarantines/deletes orphans, writes idempotent audit
   events, and alerts on recurrence. An object without an application-owned
   `clean` evidence row is never eligible for download or a signed URL.

Managers can read their own clean linked evidence; administrators can read
clean evidence for review. Access uses short-lived signed URLs from a protected
operation that rechecks status at issuance. Anonymous users never receive paths
or URLs. Evidence for an approved record cannot be replaced or deleted.
Retention deletion, if adopted, is a documented privileged job and writes an
audit event while preserving required hashes/metadata.

## 8. Emission-factor versioning

- Factors belong to immutable versioned sets with draft, active, and retired
  states.
- Each factor records code, value, units, calculation method, source citation,
  jurisdiction, GHG basis, and validity range.
- Administrator A may propose; activation should require Administrator B if a
  second approver becomes available. In the current one-admin model, activation
  requires explicit re-authentication and a reason, and this residual
  segregation-of-duties risk is documented.
- Validity ranges for the same factor context cannot overlap.
- Approval selects the factor effective for the activity/reporting date, not
  whichever factor is active when a dashboard page loads.
- `approval_calculations` freezes factor ID, value, units, formula version,
  activity value, and result. Later factor versions never rewrite an approved
  calculation.
- Corrections or methodological restatements create a superseding submission or
  release with an explicit reason and retain prior releases.

## 9. Public approved aggregate contract

The public boundary reconstructs the current overlay structure while adding
coverage metadata in a backward-compatible way:

```json
{
  "metadata": {
    "version": "release-version",
    "last_updated": 0,
    "academic_year_start_month": 0,
    "latest_complete_period": { "year": 0, "month": "Jan" },
    "content_sha256": "..."
  },
  "data": {
    "energy": [
      {
        "Month": "Jun",
        "Year": 2026,
        "Industrial": null,
        "Temporary": null,
        "Commercial": null,
        "Procured_RE": null,
        "EB_Excluding_RE": null,
        "RE_On_Campus": null,
        "Solar_Water_Heater": null,
        "Total_RE": null,
        "DG_kWh": null,
        "Status": "Approved"
      }
    ],
    "transport": [
      {
        "Month": "Jun",
        "Year": 2026,
        "Petrol_Litres": null,
        "Diesel_Litres": null,
        "Vehicle_Count": null,
        "Status": "Approved"
      }
    ],
    "coverage": [
      {
        "Month": "Jun",
        "Year": 2026,
        "Scope1": "approved",
        "Scope2": "missing",
        "Renewable": "approved",
        "Complete": false,
        "MissingDomains": ["scope2"]
      }
    ],
    "period_totals": []
  }
}
```

`null` stays null; zero is emitted only from a confirmed approved zero. Internal
submission IDs, user IDs, timestamps identifying staff, evidence, review
notes, and factor administration details are excluded. `Status` in public rows
is always `Approved`; draft rows cannot reach this layer. The projection may be
served as JSON/RPC or materialized release rows, but release activation must be
atomic so users never see mixed versions.

The current fields `SubmittedAt`, `SubmittedBy`, `SubmissionID`, and
`ResponseID` should be omitted or fixed to null for compatibility because they
are unnecessary personal/operational data.

Release hashing uses RFC 8785 JSON Canonicalization Scheme over a payload made
from contract version, academic-year setting version, and `data`. The
`content_sha256`, publication timestamp, and other volatile envelope metadata
are excluded from their own hash. Database fixed-precision numerics are emitted
as canonical decimal strings in the hash payload (no exponent form or trailing
zeros), text is UTF-8 with NFC normalization, arrays use documented period/code
order, and object keys use canonical ordering. The public response may render
numbers for backward compatibility, but verification rebuilds the same
canonical hash payload.

## 10. Latest complete reporting period

A calendar month is complete only when all of the following exist for that
exact month:

1. at least one final approved Scope 1 submission satisfying required Scope 1
   metrics;
2. at least one final approved Scope 2 submission satisfying required Scope 2
   metrics;
3. at least one final approved renewable submission satisfying required
   renewable metrics;
4. no unresolved supersession/overlap conflict; and
5. every included calculation has its frozen valid factor provenance.

The latest complete period is the greatest `reporting_period` by calendar end
date satisfying those conditions. It is not the greatest submitted or approved
month, and approval in a later month does not make intervening missing months
complete. A period-total renewable submission does not make each covered month
complete unless genuine monthly records also exist; it contributes only to an
explicit period-total coverage.

The public coverage rows list every expected academic-year month through the
latest reporting cutoff and identify missing domains. The academic year label
and month order derive from the versioned `academic_year_start_month` setting,
never JavaScript constants.

## 11. Audit log design

Audit events cover:

- signup, email verification, login success/failure, logout, recovery, MFA and
  account disablement (from Supabase Auth audit/log integration);
- privileged role grant/revoke and bootstrap;
- draft creation, edits, submission, correction request, resubmission,
  review start, approval, supersession, and publication;
- evidence upload validation, read-link issuance, scan result, and retention
  deletion;
- setting and emission-factor proposal/activation/retirement;
- authorization denials for sensitive operations and administrative exports.

Each event includes UTC event/recording time, actor or anonymous/system type,
event and outcome, target, correlation/request ID, non-secret context, source
channel, and optional before/after hashes. It excludes passwords, session/JWT
tokens, service keys, signed URLs, evidence bytes, and unnecessary personal
data.

Application events are inserted in the same transaction as the protected
change so a successful action cannot exist without its audit record. Direct
client insert/update/delete is denied. For tamper evidence, events form a
hash-chain or are periodically exported to append-only external retention;
database superusers remain a documented trust boundary. Access to audit data is
limited and itself audited. Retention and privacy policy must be approved before
production.

### Auth and Storage audit completeness

The authoritative Auth source is Supabase's automatically populated
`auth.audit_log_entries`, covering signup, login, verification, token, recovery,
MFA, and logout actions. Database Auth audit logging remains enabled. A protected
Operations worker reads this source with a durable
`(event_timestamp, source_event_identifier)` cursor, normalizes it into
`audit_events`, and deduplicates on a unique source/service and source-event
key. Phase B2 must inspect the deployed table's exact columns; if no stable ID
exists, the idempotency key is a canonical SHA-256 of the full redacted event
and its timestamp.

The worker uses overlap-window polling so late records are safely re-read. Each
run stores checkpoint, source/import counts, first/last timestamps, and error.
An hourly reconciliation compares source and destination counts/hashes, alarms
on five-minute lag or any unexplained gap, and can replay from the last good
checkpoint. Auth-log retention must exceed the maximum outage window. Before
production, an Auth/Storage/Postgres Log Drain to append-only institutional
storage is required as independent retention; its receiver authenticates
ingest and deduplicates batches. Plan/add-on availability must be confirmed.

Storage API actions are independently observed through the Supabase Storage Log
Drain. The durable drain ingester deduplicates source events and reconciles them
against upload authorizations, application evidence rows, and bucket object
listings. The protected upload endpoint supplies the application correlation ID
and records attempt/finalize outcomes; drain gaps or unexpected direct objects
raise an alert. Authorization, upload, finalization, validation, scan,
signed-link issuance, and deletion are correlated but separate events. No
custom object, trigger, or function is installed in the managed `storage`
schema. Logout is recorded when Auth receives logout/token revocation; closing
a browser or losing connectivity is a session-expiry condition, not a
fabricated logout event.

Official capability references reviewed for this design:

- [Supabase Auth audit logs](https://supabase.com/docs/guides/auth/audit-logs)
- [Supabase Log Drains](https://supabase.com/docs/guides/telemetry/log-drains)
- [Supabase Database Webhooks](https://supabase.com/docs/guides/database/webhooks)

## 12. Migration file plan for Phase B2+

No files below are created in Phase B1. Proposed immutable order:

1. `0001_extensions_schemas_types.sql` — private schemas, extensions, and
   types; revoke default/public access in the same migration.
2. `0002_identity_roles_settings.sql` — profiles, roles, settings, and periods;
   enable/force RLS, revoke access, and install minimum policies before commit.
3. `0003_metric_definitions_submissions.sql` — metrics, submissions, values,
   revisions, constraints, indexes, immutability, RLS, revokes, and safe grants
   for every object created here.
4. `0004_evidence_metadata_storage.sql` — pending upload authorizations,
   evidence metadata, private bucket, validation states, application-table
   protections, Storage RLS, revokes, and safe grants without managed-schema
   triggers or functions.
5. `0005_review_workflow.sql` — controlled state transitions, concurrency,
   security-definer hardening where justified, exact execute revokes/grants.
6. `0006_emission_factors_calculations.sql` — factor lifecycle, frozen
   calculations, local RLS/revokes/grants, and immutability.
7. `0007_public_releases.sql` — release objects, approved aggregation,
   completeness logic, public least-data grants, and private-base revokes.
8. `0008_audit.sql` — audit objects, triggers, protected read view, Auth/Storage
   checkpoints/reconciliation, RLS, and revokes/grants.
9. `0009_authorization_integration.sql` — final cross-object integration and
   verification only; earlier objects must already be safe without it.
10. `0010_seed_reference_data.sql` — non-secret metric definitions and initial
    settings/factor drafts; no user UUIDs or administrator credentials.
11. `0011_verification.sql` — executable catalog and behavior assertions for
    staging (kept separate if migration runners should not install it).

Every migration is independently fail-closed: newly created tables are private
and RLS-protected within that migration's transaction. Deployment tooling must
apply each file transactionally, stop on error, and never expose an application
schema between steps. Staging tests deliberately interrupt after every file and
prove `anon` and `authenticated` cannot reach unfinished objects.

Each accepted migration receives a SHA-256 entry containing filename, byte
hash, review date, staging/production status, and applied database version.
Applied migrations are never edited; corrections append a new migration.

## 13. Testing and verification plan

### Database structure and authorization

- Catalog assertions for every table, type, constraint, foreign key, index,
  function signature, security mode, owner, fixed search path, grant, revoke,
  RLS flag, and policy predicate.
- Interrupt the migration chain after each file and prove unfinished objects
  remain unreachable to `anon`, `authenticated`, and unassigned users.
- Verify anonymous, unassigned, unverified, inactive, wrong-domain, and manager
  self-approval denials.
- Verify each manager can operate only on owned eligible submissions in the
  assigned domain.
- Verify administrator review actions work only through allowed transitions.
- Verify direct client mutation of protected workflow/factor/release/audit
  columns fails.

### Workflow and concurrency

- Full draft → submit → review → correction → resubmit → approve flow for each
  domain.
- Invalid transition, duplicate approval, stale row version, concurrent
  reviewers, and submitter-equals-approver tests.
- Approved update/delete/value/evidence replacement tests must fail.
- Superseding-record behavior preserves the original and release history.

### Data and calculations

- Known reference fixtures for unit conversion and every emission factor.
- Factor effective-date boundaries and non-overlap.
- Missing versus confirmed zero at storage, calculation, aggregate, JSON, and
  dashboard boundary.
- Academic-year start months including January and December boundaries.
- Missing month/domain coverage and latest-complete-month behavior.
- Period totals remain period totals; overlapping monthly data is rejected from
  approval/publication and historical conflicts require an audited resolution.
- Release checksum is stable for canonical content.

### Evidence and privacy

- Accept valid PDF/PNG at and below 10 MiB; reject >10 MiB, renamed executable,
  forged MIME, disallowed extension, malformed file, and unauthorized path.
- Verify short signed URL expiry and isolation between managers.
- Verify pending/quarantined/failed/infected objects cannot be downloaded or
  signed by their uploader or an administrator; only `clean` can be read.
- Verify anonymous users cannot list bucket objects or evidence metadata.
- Verify evidence becomes immutable on approval.
- Delete/corrupt test metadata to prove Storage/evidence reconciliation raises
  an alert and produces one idempotent audit event per discrepancy.

### Public and operational tests

- Anonymous public contract contains only approved active release rows.
- Draft, submitted, correction, and approved-but-unpublished content never
  leaks.
- Publication is atomic under concurrent reads; rollback can reactivate the
  prior immutable release.
- End-to-end staging test with one real verified account per manager role and
  one administrator.
- Portal/browser tests for loading, empty, incomplete, denial, validation,
  correction, approval, accessibility, desktop, and mobile states.
- Confirm no frontend bundle contains service-role credentials.
- Generate representative Auth events, verify durable-cursor import and
  deduplication, simulate lag/outage/replay, and prove gap alarms plus external
  drain retention. Treat browser close as expiry, not an asserted logout.

## 14. Security risk register

| Risk | Severity | Control / disposition | Owner / gate |
|---|---|---|---|
| Self-signup privilege escalation | Critical | Protected roles; ignore user metadata; denial tests | Phase B2 database owner |
| Service-role key exposed | Critical | Server secret only; scans and rotation | Phase B2 + Operations |
| Cross-domain access | Critical | Domain checks in RLS/RPC | Phase B2 database owner |
| Anonymous operational/evidence leak | Critical | Revokes, RLS, private bucket/public schema | Phase B2 + staging gate |
| Workflow bypass/approved mutation | Critical | Transitions, constraints, immutable triggers | Phase B2 database owner |
| Submitter self-approval | High | Exclusive V1 roles plus transaction check | Phase B2 |
| Malicious/oversized evidence | High | Pending authorization, quarantine, byte/type/scan checks | Phase B2 + Operations |
| Factor changed after approval | High | Immutable versions and frozen snapshots | Phase B2 |
| Partial/mixed public release | High | Immutable releases and atomic activation | Phase B2 |
| Fake monthly values/double counting | High | Explicit granularity and reject-overlap rule | Phase B2 |
| Missing coerced to zero | High | Nullable contract and boundary tests | Phase B2 + frontend integration |
| Audit tampering/sensitive audit data | High | Append-only, redaction, reconciliation, external drain | Phase B2 + Operations |
| One-admin segregation gap | Medium | Re-authentication, reason, alerts; add second approver | Institutional owner before production |
| Stolen privileged session | High | MFA, short sessions, revocation, recovery alerts | Institutional owner + Operations |
| External Auth-event lag/loss | Medium | Durable cursor, overlap poll, reconciliation, alarms, drain | Operations before production |
| Signed URL sharing | Medium | Clean-only issuance, short expiry and audit | Phase B2 |
| Setting reclassifies old periods | Medium | Version settings; retain setting version | Phase B2 |
| Historical import provenance | High | Dedicated reconciliation/quarantine design | Later import phase |
| Database owner alters audit | Medium | External append-only export and access controls | Operations before production |

## 15. Operational recovery and publication

- Releases are immutable. Rollback means atomically reactivating a prior known
  good release, never editing public rows in place.
- Submission approval transactions are idempotent and fail closed.
- Storage and database backup/restore objectives must be chosen before staging.
- Orphan object reconciliation compares Storage objects with `evidence_files`.
- Auth audit ingestion uses durable checkpoints, overlap-window retry,
  reconciliation, lag/gap alarms, and idempotency keys; Storage is reconciled
  against both pending authorizations and evidence metadata.
- No automatic production promotion follows migration or staging approval.

## 16. Phase B1 senior review checklist

The independent reviewer must perform a read-only review and return one of the
governance verdicts. Confirm:

- [ ] Scope is architecture only; no frontend, migration, SQL, staging, commit,
      or Supabase project mutation occurred.
- [ ] Public/private boundary excludes identities, evidence, notes, drafts, and
      approved-but-unpublished data.
- [ ] Signup cannot assign privilege; role source and bootstrap are protected.
- [ ] Role matrix and RLS intent deny wrong-domain, self-approval, and direct
      workflow bypass.
- [ ] Approved submissions, values, evidence links, factors, calculations, and
      releases are immutable.
- [ ] State transitions, correction, supersession, concurrency, and publication
      are unambiguous.
- [ ] Evidence is private, PDF/PNG only, <=10 MiB, content-validated, and never
      exposed anonymously.
- [ ] Factor validity/versioning and calculation provenance are reproducible.
- [ ] Null/zero, missing domains/months, period totals, overlaps, and latest
      complete period semantics match the reviewed frontend behavior.
- [ ] Public release matches `dashboard_master.json` without leaking operational
      metadata and activates atomically.
- [ ] Auth and application audit coverage, redaction, immutability, and trust
      boundaries are explicit.
- [ ] Migration ordering, SHA-256 manifest, canonical verification, staging,
      and rollback plans comply with governance.
- [ ] Tests include catalog assertions and behavior-level allow/deny,
      calculation, storage, concurrency, public leakage, and browser cases.
- [ ] Security risks have owners or a named phase for mitigation.
- [ ] Configurable decisions are resolved before production.

## 17. Decisions required before Phase B2 implementation

1. Confirm academic-year start month.
2. Confirm allowed institutional email domains, or explicitly allow verified
   external addresses with admin assignment.
3. Decide MFA policy (recommended: mandatory administrator; preferably all
   privileged users).
4. Decide evidence retention duration and malware-scanning service/process.
5. Name the official source, jurisdiction, GWP basis, and approval method for
   each emission factor.
6. Decide whether approval immediately prepares a candidate release or whether
   the administrator must press a separate Publish action (recommended:
   separate approval and atomic publish).
7. Confirm whether one person may ever hold multiple roles (recommended V1: no).
8. Decide whether a second administrator will be added for factor-change
   segregation of duties.

### Owner decisions approved for V1 (2026-08-11)

1. Academic year begins in June.
2. Managers use `@kct.ac.in`; `@kclas.ac.in` is allowed only for a trusted
   administrator/higher-official assignment through the protected process.
3. Administrator MFA is mandatory. Manager MFA is production-ready by design;
   staging may begin with verified email and password.
4. Evidence retention is at least seven years. Malware scanning is mandatory
   before production; staging first proves type, size, privacy, authorization,
   and audit controls.
5. Initial draft factors are petrol 2.388 kgCO2e/L, diesel 2.701 kgCO2e/L, and
   grid 0.727 kgCO2e/kWh. Source/jurisdiction must be institution-confirmed
   before production activation.
6. Approval and publication are separate actions.
7. A privileged user may hold exactly one active V1 role.
8. A second administrator is optional in staging and required/recommended for
   production recovery and continuity.

## 18. Exit criteria and authorization boundary

Phase B1 is ready to close only when:

- the independent senior design review has no unresolved critical/high finding;
- configurable decisions needed by the first migrations are recorded;
- the project owner approves this design for Phase B2 migration implementation.

Approval of this report authorizes preparation of reviewed migration source and
tests only. It does not authorize applying SQL to staging or production.

## 19. Independent senior review record

Verdict: `APPROVE WITH NON-BLOCKING NOTES`

No critical or high findings remain. The final review confirmed fail-closed
migration sequencing, protected privilege assignment, deterministic overlap
handling, clean-only evidence access, supported controlled upload, complete
Auth/Storage audit and reconciliation design, public least-data publication,
and canonical release hashing. The non-blocking implementation note requiring
atomic upload claims and create-only/no-upsert object creation is incorporated
in Section 7. The eight owner configuration decisions in Section 17 remain a
mandatory gate before Phase B2 begins.
