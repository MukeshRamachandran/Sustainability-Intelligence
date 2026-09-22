# Microcosm Backend Requirements

## Confirmed operating model

- The public sustainability dashboard is readable without authentication.
- Three authenticated managers submit activity data:
  - Scope 1 manager
  - Scope 2 manager
  - Renewable-energy manager
- One authenticated administrator reviews and approves submissions.
- Accounts use email verification followed by password login.
- Public self-registration must not grant a manager or administrator role. An
  administrator must assign every privileged role.
- Reporting follows an academic year. The start month must be a database
  setting so it is not hardcoded in dashboard JavaScript.
- Supporting evidence accepts PDF or PNG files up to 10 MB.
- Evidence is private and is never exposed through the public dashboard.
- Approved records are immutable. An approved value cannot be edited or
  deleted through the application.
- Emission factors are entered and approved through the authenticated backend.
- Only approved records and sanitized aggregates may reach the public API.

## Mandatory phase quality gate

The detailed standing procedure is defined in `DEVELOPMENT_GOVERNANCE.md` and
applies automatically to basic phase requests.

Every development phase requires a senior review before the following phase
starts. The review must cover architecture, calculation correctness, security,
data quality, tests, documentation and operational risks as applicable.

The phase gate is:

1. Complete the scoped implementation and documentation.
2. Run automated tests, static checks and relevant manual verification.
3. Perform a senior review and record findings by severity.
4. Resolve all critical and high-severity findings.
5. Rerun the affected tests and regression suite.
6. Publish a short phase-completion report containing evidence, accepted risks
   and any medium/low findings deferred to a named later phase.
7. Begin the next phase only after the gate passes.

No phase is considered complete merely because its code has been written.

## Submission workflow

`draft -> submitted -> under_review -> approved`

An administrator may move an unapproved record from `under_review` to
`correction_requested`; the manager can then correct and resubmit it. Approval
is final. If the institution later requires a historical correction, it must
be implemented as a separately authorized superseding record, never an update
to the original approved row.

## Security boundaries

- Managers can create and update only unapproved submissions in their assigned
  domain.
- Managers cannot approve submissions or manage emission factors.
- The administrator can review all domains and approve through a controlled
  database function.
- A submitter cannot approve their own submission.
- Bills live in a private Storage bucket protected by Row Level Security.
- The Supabase service-role key must never appear in frontend code.
- Anonymous users can query only dedicated approved aggregate views.
- Authentication events, submissions, reviews, approvals, factor changes and
  document uploads require audit records.

## Data-quality rules

- Zero is a confirmed measurement; null means missing or not submitted.
- Period totals must not be divided into fabricated monthly readings.
- Every record retains its unit, source, reporting period and evidence link.
- Emission calculations retain the factor version used at approval time.
- Missing domains and missing months must be visible as incomplete coverage.
- Dashboard totals are calculated from approved activity in the database, not
  independently in the browser.

## Decisions still configurable

- Academic-year start month
- Institutional email-domain allowlist
- Whether MFA is mandatory for managers as well as the administrator
- Evidence-retention duration
- Formal source and review process for each emission factor
