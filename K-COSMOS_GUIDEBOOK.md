# K-COSMOS Guidebook

**Kumaraguru Climate Observatory and Sustainability Monitoring System**

A plain-language, file-by-file tour of everything in this repository: what each part does, why it exists, and how the parts connect.

- Prepared: 29 September 2026
- Branch at time of writing: `production-fix-2026-09-27`
- Latest commit: `c94d10b feat(public-dashboard): stabilize KPI rendering, chart periods, and responsive layout`
- Database migration head in code: `0012_environment_readings`

---

## Contents

1. [What K-COSMOS is, in one minute](#1-what-k-cosmos-is-in-one-minute)
2. [The big picture](#2-the-big-picture)
3. [Words you will see everywhere](#3-words-you-will-see-everywhere)
4. [The life of one monthly number](#4-the-life-of-one-monthly-number)
5. [The ground rules the whole project follows](#5-the-ground-rules-the-whole-project-follows)
6. [Repository map](#6-repository-map)
7. [Backend: `services/main-api`](#7-backend-servicesmain-api)
8. [Manager/Admin portal: `apps/manager-admin`](#8-manageradmin-portal-appsmanager-admin)
9. [Public dashboard (current): `apps/public-dashboard-final-staging`](#9-public-dashboard-current-appspublic-dashboard-final-staging)
10. [Public dashboard (original): `apps/public-dashboard`](#10-public-dashboard-original-appspublic-dashboard)
11. [Portal backup: `apps/manager-admin-backup-before-recovery`](#11-portal-backup-appsmanager-admin-backup-before-recovery)
12. [Report generation: `services/report-generation`](#12-report-generation-servicesreport-generation)
13. [Root-level documents and reports](#13-root-level-documents-and-reports)
14. [Other folders](#14-other-folders)
15. [How to run it locally](#15-how-to-run-it-locally)
16. [Where the work stands today](#16-where-the-work-stands-today)
17. [Known issues and clean-up candidates](#17-known-issues-and-clean-up-candidates)

---

## 1. What K-COSMOS is, in one minute

K-COSMOS is the sustainability platform for Kumaraguru College of Technology (KCT), branded **MICROCOSM** in the user interface. It does three jobs:

1. **Collects** monthly sustainability data from staff. Each area — transport fuel, electricity, LPG, water, waste and community outreach — has its own manager who types in that month's numbers and uploads proof documents.
2. **Checks and publishes** that data. An administrator reviews every submission, sends it back for correction or approves it, then publishes a frozen, tamper-evident "release" for the month.
3. **Shows** the published data to the public on a dashboard: carbon emissions (GHG), energy, water, waste, green cover, outreach, and a live weather and air-quality station fed by the **Aeron** sensor on campus.

It also holds **historical data** — older institutional spreadsheets imported with full traceability — so the public dashboard can show past years alongside newly published months.

---

## 2. The big picture

```
                        ┌──────────────────────────────────────────┐
  Managers (6 domains)  │  Manager/Admin portal  (apps/manager-admin)│
  Administrator    ───► │  static HTML + JS, served on port 3000    │
                        └───────────────┬──────────────────────────┘
                                        │ cookies + CSRF header
                                        ▼
┌──────────────────┐        ┌───────────────────────────────────────┐        ┌─────────────────┐
│ Aeron sensor     │        │  Main API  (services/main-api)        │        │ PostgreSQL      │
│ live3.aeron...   │        │  FastAPI, port 8000                    │◄──────►│ schemas:        │
└────────▲─────────┘        │  auth · submissions · review ·        │        │  identity       │
         │ every 5 min      │  evidence · factors · releases ·      │        │  sustainability │
┌────────┴─────────┐        │  public API · environment API         │        │  publication    │
│ Aeron worker     │───────►│                                        │        │  audit          │
│ (same codebase,  │ writes │                                        │        │  history        │
│  separate proc.) │ readings                                        │        │  environment    │
└──────────────────┘        └───────────────▲───────────────────────┘        └─────────────────┘
                                            │ read-only /api/public/* and /api/environment/*
                        ┌───────────────────┴──────────────────────┐
  Public visitors  ───► │ Public dashboard (apps/public-dashboard-  │
                        │ final-staging), port 3001 locally         │
                        └──────────────────────────────────────────┘

  Separate, not yet connected:  services/report-generation  (PDF report engine)
```

**In simple words:** the portal and the public dashboard are plain web pages. Every real decision — who may log in, what can be edited, how emissions are calculated, what the public sees — is made by the Main API and stored in PostgreSQL. The browser only displays what the API returns.

---

## 3. Words you will see everywhere

| Term | Meaning |
| --- | --- |
| **Domain** | One area of data collection. There are six: `transport`, `energy`, `lpg`, `water`, `waste`, `outreach`. Each manager is assigned exactly one. |
| **Manager** | A staff member who enters monthly data for one domain (role code `manager`). |
| **Admin** | The MICROCOSM administrator who reviews, approves and publishes (role code `microcosm_admin`). |
| **Reporting period** | One calendar month (e.g. September 2026). Managers can only create entries for the *current* month in India time (Asia/Kolkata). |
| **Submission** | One domain's data for one month. Only one active submission per domain per month. |
| **Metric** | One measured value in a submission, e.g. `transport_petrol_litres`. Defined in the `metric_definitions` table with unit, allowed range and whether managers may edit it. |
| **Calculated metric** | A metric the database works out itself, e.g. `grid_total_kwh = HT + commercial + temporary`. Managers can never type it. |
| **Evidence** | A PDF, PNG or JPG uploaded as proof (bills, meter photos). Stored privately; only its metadata is in the database. |
| **Emission factor** | "How much CO₂ one unit produces", e.g. kgCO₂e per litre of petrol. Grouped into versioned **factor sets** that an admin activates. |
| **Scope 1** | Direct emissions from burning fuel on campus: petrol, transport diesel, diesel generators (DG), LPG. |
| **Scope 2** | Indirect emissions from grid electricity. |
| **Operational GHG** | Scope 1 + Scope 2. |
| **tCO₂e / kgCO₂e** | Tonnes / kilograms of carbon-dioxide equivalent. |
| **Release** | A frozen snapshot of one month's approved data, with a SHA-256 checksum. Goes `candidate → active`. Only one release is active at a time. |
| **Schema version** | The shape of a release's JSON payload. New releases use **1.4**; older releases keep the version they were frozen with. |
| **Historical data** | Pre-portal institutional records imported from CSV files into the `history` schema, each value tagged MONTHLY / YTD / ANNUAL / STATIC. |
| **Aeron** | The campus environmental sensor station (weather, air quality, noise). |
| **Freshness** | Whether the latest sensor reading is `LIVE` (< 10 min old), `STALE` (10–30 min) or `OFFLINE` (older, missing or future-dated). |

---

## 4. The life of one monthly number

Follow one number — say, the litres of petrol used by campus vehicles in September 2026:

1. **Login.** The Transport manager opens `transport-login.html` and signs in. The API checks the password (Argon2), creates a server-side session, and sets two cookies: a session cookie and a CSRF cookie.
2. **Draft.** On `transport-entry.html` the manager types the litres and clicks Save. The API checks the value is within range and belongs to the Transport domain, then stores it as a **draft**. The page shows a *provisional* emission preview computed by the backend.
3. **Evidence.** The manager uploads the fuel bill. It is stored as *temporary* evidence until the submission is sent.
4. **Submit.** The manager clicks Submit. The API checks every required metric is present, changes the status to **submitted**, **freezes the emission calculation** with the factor set that applied to that month, and commits the evidence. From now on the manager cannot change anything.
5. **Review.** The admin opens the review queue, clicks *Begin Review* (**under_review**), then either:
   - *Request Correction* with a reason → **correction_requested**; the manager edits and resubmits as revision 2; or
   - *Approve* → **approved**. Approval does **not** publish.
6. **Readiness.** When all six domains are approved for the month, the readiness panel shows *6 / 6 Approved*.
7. **Prepare release.** The admin enters a version name (e.g. `sustainability-2026-09-v1`). The API builds the JSON payload — metrics, frozen calculations, derived indicators, population — computes its checksum, and saves it as a **candidate**.
8. **Publish.** The admin previews the candidate and clicks Publish. The API re-verifies the checksum and completeness, marks the previous active release **superseded** and this one **active**.
9. **Public view.** The public dashboard calls `/api/public/dashboard/timeline`, which merges published releases with verified historical data, and the petrol figure appears in the GHG charts.

Every step above is written to the **audit log**.

```
draft ──submit──► submitted ──begin review──► under_review ──approve──► approved
  ▲                   │                            │
  │                   └──────request correction────┤
  └──────── correction_requested ◄─────────────────┘
               (manager edits, resubmits as a new revision)
```

---

## 5. The ground rules the whole project follows

These rules appear again and again in code comments, tests and reports. Knowing them explains most design decisions.

1. **Missing is never zero.** A blank value stays blank. An explicit `0` is a real measurement. Any total with a missing part is itself missing.
2. **The backend is the only calculator.** Browsers never apply emission factors or build official totals. They display what the API returns.
3. **Managers never write calculated values.** Totals like `grid_total_kwh` are computed by database triggers.
4. **Submit once, then read-only.** After submission a manager can edit again only if the admin requests a correction.
5. **Current month only.** Managers can create entries only for the current month in India time.
6. **Approval ≠ publication.** Approving data and publishing it are separate, deliberate steps.
7. **Releases are immutable.** A published payload is never rewritten; its checksum proves it. Corrections mean a new release.
8. **Factors are versioned and dated.** Each month uses the factor set whose effective date applies to it — never "whatever is current today".
9. **History keeps its true shape.** An annual figure is never split into months; a YTD figure is never shown as a single month.
10. **Public visitors never trigger ingestion.** Only the background worker talks to Aeron.
11. **No secrets in the repository.** (See [section 17](#17-known-issues-and-clean-up-candidates) — one file currently breaks this rule.)

---

## 6. Repository map

```
K-COSMOS-FINAL/
├── apps/
│   ├── manager-admin/                      ← Manager & Admin portal (ACTIVE)
│   ├── public-dashboard-final-staging/     ← Public dashboard, API-driven (ACTIVE)
│   ├── public-dashboard/                   ← Original public dashboard, CSV-driven (older)
│   └── manager-admin-backup-before-recovery/ ← Snapshot of the old prototype portal
├── services/
│   ├── main-api/                           ← FastAPI backend + Aeron worker (ACTIVE)
│   └── report-generation/                  ← PDF report engine (standalone, not wired in)
├── tests/manager-admin/                    ← Older cross-app JS tests (currently failing, see §17)
├── docs/legacy/supabase-reference/         ← Old Supabase design, reference only
├── docs/{architecture,backup,database,...} ← Empty placeholders
├── database/, deployment/, config/         ← Empty placeholders
├── recovery-backups/                       ← Local safety snapshots (git-ignored)
├── .claude/, .impeccable/                  ← AI-assistant tooling (design skills and agents)
└── *.md                                    ← Project reports, contracts and audits (§13)
```

---

## 7. Backend: `services/main-api`

The heart of the system. A **FastAPI** (Python 3.12) application backed by **PostgreSQL** via **SQLAlchemy**, with **Alembic** for database migrations.

### 7.1 Project files in the service root

| File | What it does | In simple words |
| --- | --- | --- |
| `pyproject.toml` | Python package definition. Runtime deps: FastAPI, SQLAlchemy, psycopg, Alembic, Argon2, Pydantic, structlog, uvicorn. Extras: `dev` (pytest, ruff, mypy) and `aeron-worker` (Playwright). Configures ruff (lint) and mypy (strict types). | The shopping list of libraries plus the code-quality settings. |
| `uv.lock` | Exact locked versions of every dependency. | Makes installs reproducible. |
| `.env.example` | Template of every setting (database URL, secrets, cookie names, session times, evidence folder, login lockout, Aeron worker settings). | Copy to `.env` for local runs. **Contains what look like real Aeron credentials — see §17.** |
| `compose.yaml` | Docker Compose for local dev: a `postgres:17.6` container and the `api` container on `127.0.0.1:8000`, plus volumes for the database and evidence files. Points at the clean database `microcosm_clean_20260922`. | One command (`docker compose up`) starts the database and the API. |
| `compose.worker.yaml` | Adds the `environment-worker` container (the Aeron poller). Requires Aeron station/username/password from your environment. | Starts the sensor-reading worker. |
| `compose.yaml.before-aeron-worker` | Backup of `compose.yaml` before the worker was added. | Safety copy; not used. |
| `Dockerfile` | Builds the API image as a non-root user, creates evidence folders, runs `uvicorn app.main:app`. | Recipe for the API container. |
| `Dockerfile.worker` | Builds the worker image with Playwright + Chromium, runs `python -m app.environment.worker`. | Recipe for the worker container (the only image with a browser). |
| `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako` | Alembic configuration and migration template. | Tells Alembic how to reach the database. |
| `README.md` | How to run with Docker, run checks, apply migrations, and bootstrap accounts. | Setup notes (partly outdated — it still says "D3 contains no schema migration"). |
| `DELIVERY_SOURCE_OF_TRUTH.md` | Early checkpoint note: which folders were authoritative and which demo behaviours must be removed from the production path. | Historical note; its paths point to another machine (`C:\Users\Ram\...`). |
| `.dockerignore`, `.gitignore` | Exclusion lists. | Keep junk out of images and git. |

### 7.2 Application start-up and plumbing — `app/`

| File | What it does | In simple words |
| --- | --- | --- |
| `app/main.py` | Builds the FastAPI app: loads settings, creates the DB engine, adds CORS (credentials allowed, explicit origins only), a request-ID middleware (every response gets `X-Request-ID`), a security-headers middleware (`nosniff`; `no-store` on auth/admin/manager routes), uniform JSON error responses, and registers all 15 routers. API docs at `/docs` except in production. | The front door. Wires everything together. |
| `app/core/config.py` | The `Settings` class (read from environment/.env). Validates origins, timezone, evidence types (PDF/PNG/JPEG only) and paths. **In production it refuses to start** with development secrets, insecure cookies, non-HTTPS URL, dev DB credentials or relative evidence paths. | All configuration in one place, with safety checks. |
| `app/core/logging.py` | Configures structured JSON logs with timestamps and the request ID. | Makes logs machine-readable. |
| `app/db/base.py` | SQLAlchemy `Base` with a naming convention for indexes/constraints. | Parent class for every table. |
| `app/db/session.py` | Creates the engine and session factory; `get_db` gives each request a session; `database_is_ready` runs `select 1`. | Database connection helpers. |
| `app/db/transactions.py` | A `transaction()` context manager. | "Do these writes all-or-nothing." |
| `app/bootstrap.py` | CLI: `python -m app.bootstrap development` creates seven demo accounts (`demo.admin`, `demo.transport`, `demo.energy`, `demo.lpg`, `demo.water`, `demo.outreach`, `demo.waste`) and reporting periods for 2025–2027; blocked in production. `python -m app.bootstrap admin --username …` interactively creates the first real admin. All accounts must change password on first login. | Creates the first users safely. |
| `app/api/__init__.py` | Empty package marker. | — |

### 7.3 Database tables — `app/models/`

The database is split into **schemas** (named groups of tables).

| File | Schema | Tables and purpose |
| --- | --- | --- |
| `enums.py` | — | All fixed lists: roles (`manager`, `microcosm_admin`), the six domains, accounting classes (scope1/scope2/avoided/activity/renewable/water), publication class (`public_aggregate`, `admin_only`, `internal_verification`), submission statuses, review actions, factor-set status (`draft/active/retired`), factor codes (`PETROL`, `DIESEL`, `GRID_ELECTRICITY`, `LPG`), release status (`candidate/active/superseded/revoked`). |
| `identity.py` | `identity` | **users** (username, Argon2 hash, lockout counters, `must_change_password`), **roles**, **user_role_assignments** (one active role per user), **manager_domain_assignments** (one active domain per manager), **sessions** (stores only *hashes* of session and CSRF tokens, idle and absolute expiry, IP, user agent). |
| `sustainability.py` | `sustainability` | **reporting_periods** (year/month/open flag); **institutional_population_references** (population per year — 6,991 for 2026); **metric_definitions** (the catalogue of every metric); **submissions** (domain, manager, period, status, revision, `row_version` for conflict detection); **submission_values**; **review_actions** (history of every status change with a data snapshot); **submission_evidence** (file metadata, SHA-256, revision, temporary vs committed); **outreach_programmes** (one row per event: theme, participants by category and gender, saplings, waste collected, species, volunteers); **waste_categories**, **waste_materials**, **waste_submission_items** (dry-waste inventory); **emission_factor_sets**, **emission_factors**; **calculation_results** (frozen emission results per submission revision). |
| `publication.py` | `publication` | **public_releases** (version, status, checksum, who prepared/published; only one `active`), **public_release_payloads** (the frozen JSON), **public_release_metadata** (marks a release `official` or `test`; a test release can never be public). |
| `audit.py` | `audit` | **audit_logs**: who did what, to what, outcome, request ID, safe metadata. |
| `history.py` | `history` | **import_batches** (one per source file + mapping version, identified by SHA-256), **source_rows** (raw rows), **periods**, **metric_values** (with granularity MONTHLY/YTD/ANNUAL/STATIC, verification status, authority status and qualifier EXACT/AT_LEAST/APPROXIMATE), **calculation_results**, **conflicts**. |
| `environment.py` | `environment` | **readings** (one row per station per observation time; 35 sensor fields such as PM2.5, PM10, NO₂, SO₂, O₃, CO, CO₂, temperature, humidity, rain, wind, noise, UV, AQI, plus device health and the raw payload), **ingestion_runs** (one row per worker cycle: `INSERTED`, `DUPLICATE` or `FAILED` with a fixed error code). |

**The metric catalogue** (seeded in migration `0001`, adjusted by later migrations):

| Domain | Manager-entered metrics | Calculated / published |
| --- | --- | --- |
| Transport | petrol litres, transport diesel litres, petrol vehicles, diesel vehicles, EV kWh (optional), DG diesel litres, DG unit count | Petrol, diesel and DG diesel are public; counts are admin-only |
| Energy | grid HT kWh, grid commercial kWh, grid temporary kWh, renewable on-campus kWh, renewable procured kWh, solar water heater kWh | `grid_total_kwh` (sum of the three grid parts), `renewable_total_kwh` (legacy) |
| LPG | cylinder count, weight kg (reference only), **consumption litres** (the governed activity) | LPG litres public |
| Water | TWAD KL, borewell KL, private KL, wastewater KL, recycled KL, plus optional inlet/outlet lab values (pH, TSS, TDS, NH₃-N, phosphorus, chloride, sulphate, oil & grease, COD, BOD) | `water_consumed_kl` (sum of three sources); lab values are internal-verification only |
| Waste | wet waste kg + a dry-material inventory (19 materials in 7 categories: paper/cardboard, plastic, metal, organic/biomass, e-waste, rubber, other/mixed) | `dry_waste_generated_kg`, `total_waste_generated_kg` computed by the backend |
| Outreach | programme records (see `outreach_programmes` above) | Aggregated totals at publication |

### 7.4 Security — `app/security/`

| File | What it does | In simple words |
| --- | --- | --- |
| `passwords.py` | Argon2id hashing, verification, a "dummy check" so unknown usernames take the same time as real ones, rehash detection, and the password policy (min 12 chars, not only spaces). | Safe password storage. |
| `tokens.py` | Creates random opaque tokens and their SHA-256 hashes. | The database never stores a usable session token. |
| `dependencies.py` | FastAPI "guards" used by every protected route: `AuthenticatedUser` (valid, unexpired session; slides the idle timeout), `CsrfUser` (header token must match cookie and the stored hash), `ManagerUser`, `AdminUser` (and both block users who still must change their password), `enforce_manager_domain`. | The bouncers at each door. |

### 7.5 The API routes — `app/routers/`

Every route below starts from the API base (`http://localhost:8000` locally). "CSRF" means the request must send the `X-CSRF-Token` header.

| File | Routes | Who | What it does |
| --- | --- | --- | --- |
| `health.py` | `GET /health/live`, `GET /health/ready` | anyone | Liveness, and readiness (database reachable + evidence folder writable). |
| `auth.py` | `POST /api/auth/login`, `GET /api/auth/session`, `POST /api/auth/logout`, `POST /api/auth/change-password` | anyone / logged in | Login with lockout after 5 failures for 15 min, audit of every attempt, session creation; logout revokes the session; changing password revokes all *other* sessions and clears the must-change flag. |
| `access.py` | `GET /api/access/manager/{domain}`, `GET /api/access/admin` | manager / admin | Simple "am I allowed here?" checks used by pages. |
| `manager_submissions.py` | `GET /api/manager/{domain}/periods`, `/current-period`, `/metrics`, `/submissions/current`, `/submissions`, `/submissions/{id}`; `POST /api/manager/{domain}/submissions` (create or save draft); `PUT /api/manager/{domain}/submissions/{id}`; `POST …/{id}/submit`; `GET /api/manager/waste/catalog` | manager of that domain, CSRF for writes | The generic monthly workflow for Transport, Energy, LPG, Water and Waste. Enforces current month, ownership, `expected_row_version` (so two tabs can't overwrite each other) and read-only after submit. On submit: freezes calculations and commits evidence. |
| `manager_outreach.py` | `GET /api/manager/periods`, `GET /api/manager/outreach/current-period`, CRUD on `/api/manager/outreach/programmes`, `POST /api/manager/outreach/submissions/{id}/submit`, `GET /api/manager/outreach/submissions` | outreach manager | Outreach works differently: the manager adds several **programme** records to the month's submission, then submits them together. |
| `evidence.py` | Manager: `POST/GET /api/manager/{domain}/submissions/{id}/evidence`, `DELETE …/evidence/{evidence_id}`, `GET /api/manager/{domain}/evidence/{id}/content`. Admin: `GET /api/admin/submissions/{id}/evidence`, `GET /api/admin/evidence` (searchable repository), `GET /api/admin/evidence/{id}/content` | manager / admin | Upload, replace, remove (only while editable) and download proof files. Admin gets a searchable Evidence Repository of committed files. |
| `admin_outreach.py` | `GET /api/admin/periods`, `GET /api/admin/review-queue`, `GET /api/admin/submissions/{id}`, `POST …/begin-review`, `POST …/request-correction`, `POST …/approve` | admin, CSRF | The review workflow for **all** domains (despite the file name). Approve responds "Publication is still required." |
| `admin_users.py` | `GET/POST /api/admin/users`, `POST /api/admin/users/{id}/reset-password`, `/deactivate`, `/activate`, `/revoke-sessions` | admin, CSRF | Create manager accounts with a temporary password, reset passwords, enable/disable accounts, force logout. |
| `audit.py` | `GET /api/admin/audit-logs` (filters: action, user, domain, dates, resource; paginated) | admin | Browse the audit trail; metadata is sanitised before display. |
| `emission_factors.py` | `GET/POST /api/admin/emission-factor-sets`, `GET/PUT /api/admin/emission-factor-sets/{id}`, `POST …/{id}/activate` | admin, CSRF | Create and edit draft factor sets; activation requires an effective date, the three core factors (petrol, diesel, grid; LPG optional), correct units, and a source reference. |
| `releases.py` | Admin: `GET /api/admin/reporting-periods/{id}/publication-readiness`, `POST /api/admin/releases/prepare`, `GET /api/admin/releases?reporting_period_id=`, `GET /api/admin/releases/{id}/preview`, `POST /api/admin/releases/{id}/publish`. Public: `GET /api/public/dashboard`, `/api/public/dashboard/timeline`, `/api/public/dashboard/history` | admin / anyone | Readiness check (6/6 domains approved), prepare a checksummed candidate, preview, publish. Public routes serve only official, publicly visible releases, plus the merged timeline with history. |
| `environment.py` | `GET /api/environment/latest`, `/history` (start, end, limit ≤ 1000), `/status` | anyone | Read-only sensor data from the database, with server-computed freshness. Never contacts Aeron. |

### 7.6 Request/response shapes — `app/schemas/`

Pydantic models that define and validate the JSON going in and out: `auth.py`, `admin_users.py`, `audit.py`, `submissions.py`, `outreach.py`, `waste.py`, `evidence.py`, `emission_factors.py`, `publication.py`, `environment.py`.

**In simple words:** the forms the API accepts and the replies it sends. Anything that doesn't match is rejected with a `validation_error`.

### 7.7 Business logic — `app/services/`

| File | What it does | In simple words |
| --- | --- | --- |
| `submission_workflow.py` | Loads/serialises submissions, validates values against their metric definition (domain, editable, whole numbers for counts, zero allowed, min/max), saves values in one transaction, checks required metrics before submit, bumps revision on resubmission, records a snapshot. | The rules for filling in and sending a monthly form. |
| `reporting_periods.py` | Works out the current month in Asia/Kolkata, and blocks creating or editing anything outside it (except correction requests). | "You can only report this month." |
| `sustainability_formulas.py` | **The one place formulas live.** Pure functions: activity × factor, grid total, renewable electricity (on-campus + procured, *not* solar water heater), renewable share, estimated avoided emissions, Scope 1, operational GHG, per-capita, water total, water per capita, waste total, waste per capita. `None` in → `None` out. | The calculator. Both live releases and historical imports use it, so they can't disagree. |
| `emission_factors.py` | Serialises factor sets, validates activation, picks the factor set that applies to a period, calculates provisional emissions for drafts, and **freezes** them into `calculation_results` on submit. Governed activities: petrol, transport diesel, DG diesel, grid total kWh, LPG litres. | Applies the right factor to the right month and locks the result. |
| `publication_readiness.py` | Checks all six domains have an approved submission for the period; lists blockers. | The "6 / 6 Approved" check. |
| `publication.py` | Builds the release payload (schema 1.4): each domain's public metrics and frozen calculations, waste inventory, outreach aggregates, Scope 1/2, operational GHG and per-capita, renewable/total electricity, renewable share, avoided grid emissions (with factor provenance), water per capita, population, and the static landfill-diversion reference (88.1%). Blocks preparation if waste parts disagree or any derived indicator is missing. Computes the SHA-256 checksum. | Packages a month into the frozen public snapshot. |
| `outreach.py` | Snapshots programmes and aggregates approved ones: programme count, participants (by category and gender), unique partner organisations, saplings, experts, volunteers, volunteer hours, programmes per theme. | Adds up the month's outreach events. |
| `waste.py` | Serves the waste catalogue, validates and replaces dry-waste items, computes dry and total from the items, and checks consistency before submit. | Waste is inventory only — no emission factor. |
| `evidence.py` | Rules for attaching evidence (valid metric or category), editability, revision numbers, temporary → committed on submit, replace/remove. | Manages proof files' lifecycle. |
| `evidence_repository.py` | Filtered, paginated search over committed evidence for the admin repository. | The admin's evidence search. |
| `audit.py` | `add_audit_log(...)` helper used by every write. | One line to record "who did what". |

### 7.8 File storage — `app/storage/evidence.py`

Streams uploads in 1 MB chunks, enforces the 10 MB limit, checks the extension matches the declared type, checks the **file's first bytes** really are PDF/PNG/JPEG, computes SHA-256, and saves under a random name (`<32-hex>.pdf|png|jpg`). Download paths are validated so a stored name can never escape the evidence folder.

**In simple words:** a careful file locker. The database holds the label; the disk holds the file. Back up both together.

### 7.9 Historical data layer — `app/historical/`

Imports older institutional CSVs into the `history` schema without ever pretending they were portal submissions.

| File | What it does |
| --- | --- |
| `sources.py` | Parsers for the irregular legacy CSV layouts (wide monthly, year blocks, long monthly, paired, period totals, year columns, water blocks, annual rows). Handles values like `20+` (AT_LEAST). A blank cell produces nothing — no zeros, no interpolation. |
| `mappings/*.json` | One JSON file per source (13 files: DG, energy ×3, LPG, outreach, population, renewable, transport, waste, water, plus `resolutions.json`) describing how to read it. `resolutions.json` records owner-approved choices when sources disagree (e.g. the 2025 annual water total). |
| `validator.py` | Reconciles every copy of a value using rules R0–R5: rounding-only differences are resolved; real disagreements become `CONFLICT` unless an owner resolution exists; annual/YTD totals are checked against their months. |
| `importer.py` | CLI: `python -m app.historical.importer --source-root <repo> --dry-run` (read-only report) or `--commit` (one transaction). Re-running with unchanged files is a no-op; a changed file under the same mapping version is refused. |
| `calculator.py` | Recomputes historical emissions and indicators using the **same** formula module and the factor set that applied at the time; stores inputs, factor and population used. |
| `resolver.py` | Builds the public **timeline**. Priority per month: official published release → verified MONTHLY history → YTD → ANNUAL → static reference → missing. Test releases never appear. Full-Year/YTD views sum only genuine months and state their coverage. |

**In simple words:** a museum for old data — every value keeps its label, its source file and row, and whether it was verified.

### 7.10 Aeron environmental monitoring — `app/environment/`

| File | What it does |
| --- | --- |
| `config.py` | Worker-only settings (station ID, Aeron URLs, credentials as `SecretStr`, poll interval 300 s, timeouts). Read from the process environment. |
| `parameters.py` | The 35 Aeron parameter IDs with captions and source units, verified against the live station on 2026-09-25. No unit conversion. |
| `normalizer.py` | Turns one Aeron payload into a reading. `recordedAt` is treated as true UTC — **no +330-minute correction** (verified). Records quality flags. |
| `source.py` | `AeronReadingsClient` (plain HTTP with the session cookie) and `PlaywrightLogin` (headless browser used only to log in and get cookies, roughly hourly). Errors carry fixed codes, never upstream text or secrets. |
| `repository.py` | Inserts a reading once per station + timestamp; reads latest/history; records worker runs. |
| `freshness.py` | LIVE / STALE / OFFLINE classification from server time. |
| `worker.py` | `python -m app.environment.worker` (loop) or `--once`. Each cycle: reuse session → fetch latest → re-login once if expired → normalise → insert if new → record the run. A PostgreSQL advisory lock guarantees only one worker runs. |

**In simple words:** a robot that checks the campus weather station every five minutes and writes down what it sees. The website only reads the robot's notebook.

### 7.11 Database migrations — `alembic/versions/`

Run in order with `alembic upgrade head`.

| Migration | What it adds |
| --- | --- |
| `0001_business_schema` | All core schemas and tables, role seeds, the metric catalogue, and database triggers that (a) keep a manager's domain matching their submissions, (b) stop managers writing calculated metrics, (c) recompute grid/renewable/water totals automatically. |
| `0002_outreach_vertical_slice` | Outreach domain, programme table, review snapshots, release ↔ period link. |
| `0003_outreach_impact` | Internal outreach fields: waste collected, species identified and verification notes. |
| `0004_submission_evidence` | Private evidence metadata table. |
| `0005_evidence_committed_at` | Temporary vs committed evidence. |
| `0006_emission_factor_governance` | Factor-set lifecycle and frozen `calculation_results`; renames `GRID` → `GRID_ELECTRICITY`. |
| `0007_lpg_kg_governance` | Made LPG kilograms the governed activity (later superseded). |
| `0008_lpg_litre_governance` | Final decision: **LPG litres** is governed; kg becomes reference only. Seeds the LPG baseline factor (1.5571 kgCO₂e/L) into the draft factor set. |
| `0009_waste_domain` | Waste as the sixth domain, its metrics, catalogue (7 categories, 19 materials) and item table. |
| `0010_publication_1_3` | Release schema 1.3 and the population reference (6,991 people for 2026). |
| `0011_historical_data_layer` | The `history` schema and release classification (`official`/`test`). |
| `0012_environment_readings` | The `environment` schema for Aeron readings and worker runs. |

### 7.12 Backend tests — `tests/`

Run with `pytest` (many need a real PostgreSQL; unit tests use in-memory SQLite).

| File | Checks |
| --- | --- |
| `conftest.py`, `integration_support.py`, `environment_support.py` | Shared fixtures: test settings, app instance, Postgres engine. |
| `test_app.py`, `test_health.py`, `test_config.py` | App boots, health endpoints, production config refuses unsafe settings. |
| `test_auth_integration.py` | Login, lockout, session, logout, password change. |
| `test_admin_security_integration.py` | Admin-only routes reject managers; user management. |
| `test_current_month_security.py` | Managers can't touch past/future months. |
| `test_database_contract.py` | Tables, constraints and triggers behave as designed. |
| `test_generic_submission_integration.py`, `test_generic_submission_domain_matrix.py` | Draft → submit → review → approve for each generic domain. |
| `test_outreach_integration.py` | Outreach programmes workflow. |
| `test_waste_integration.py` | Waste inventory, derived totals, consistency blockers. |
| `test_evidence_integration.py`, `test_evidence_repository_integration.py` | Upload validation, lifecycle, admin repository. |
| `test_emission_factor_governance.py` | Factor-set activation rules and frozen calculations. |
| `test_publication_readiness_integration.py`, `test_publication_integration.py` | Readiness, prepare, publish, checksum, public endpoints. |
| `test_derived_kpi_contract.py` | Schema 1.4 derived indicators match the contract. |
| `test_historical_integration.py` | Import, reconciliation, timeline. |
| `test_environment_*.py` | Normaliser, freshness, worker cycle, API, Postgres persistence. |
| `fixtures/aeron/aeron_real_sample_sanitized.json` | A real Aeron response with secrets removed. |

---

## 8. Manager/Admin portal: `apps/manager-admin`

Plain HTML, CSS and JavaScript (no build step). Served locally on **port 3000** by `serve-portal.py`, and talks to the API on port 8000 with cookies.

### 8.1 How a user gets in

```
index.html  (choose your portal)
   ├── admin-login.html      → admin-overview.html
   ├── transport-login.html  → transport-entry.html
   ├── energy-login.html     → energy-entry.html
   ├── lpg-login.html        → lpg-entry.html
   ├── water-login.html      → water-entry.html
   ├── waste-login.html      → waste-entry.html
   └── outreach-login.html   → community-outreach-entry.html
             (must_change_password → change-password.html first)
```

Each login page checks the account really has that role and domain; a Water manager signing in on the Energy page is logged straight back out.

### 8.2 Pages

| Page | Who | What it does |
| --- | --- | --- |
| `index.html` | anyone | Portal chooser with seven buttons. |
| `*-login.html` (7 files) | anyone | Role-specific sign-in. Identical structure; `data-login-role`, `data-login-domain` and `data-destination` on `<body>` set the behaviour. |
| `change-password.html` | logged in | Forced first-login password change. |
| `manager-home.html` | manager | Welcome page with a quick action and the manager's recent submissions. |
| `transport-entry.html` | transport | Petrol, transport diesel, vehicle counts, EV kWh, DG diesel, DG count; evidence per field; backend emission preview. |
| `energy-entry.html` | energy | Section A grid (HT, commercial, temporary); Section B renewables (on-campus, procured, solar water heater); Section C details; emission preview. |
| `lpg-entry.html` | lpg | Cylinders, weight (reference), litres (governed); emission preview. |
| `water-entry.html` | water | Section A sources (TWAD, borewell, private); Section B wastewater/recycled; Sections C–D inlet/outlet lab quality; STP analytics; sustainability preview. |
| `waste-entry.html` | waste | Section A wet waste; Section B dry-waste inventory (pick category → material → kg); Section C details; waste summary from the server. |
| `community-outreach-entry.html` | outreach | Add/edit/delete programme records (name, date, theme, partner, participants by group and gender, saplings, waste collected, species, volunteers), then submit the month. |
| `submission-history.html` | manager | The manager's past submissions with status badges. |
| `outreach-history.html` | outreach | Past outreach submissions. |
| `admin-overview.html` | admin | Counts and a table of submissions awaiting review. |
| `admin-queue.html` | admin | **Main admin workspace.** Review queue per period; submission detail (metrics, authoritative calculations, waste inventory, evidence); Begin Review / Request Correction / Approve; publication readiness (x / 6); prepare a release and open its preview. |
| `admin-preview.html` | admin | Shows a prepared release's JSON and the **Publish** button. |
| `admin-factors.html` | admin | Emission factor sets: create, edit draft, activate. |
| `admin-evidence.html` | admin | Searchable Evidence Repository with download. |
| `admin-users.html` | admin | Managers & Access: create manager, reset password, activate/deactivate, revoke sessions. |
| `admin-audit.html` | admin | Audit log with filters and paging. |

### 8.3 Shared scripts

| File | What it does | In simple words |
| --- | --- | --- |
| `auth-client.js` | Defines `apiRequest()` (adds `credentials: include` and the CSRF header on writes), `login`, `getSession`, `changePassword`, `logout`. Works out the API base: port 3000 → port 8000. | The phone line to the API. |
| `role-auth.js` | `KCosmosAuth`: maps each role/domain to its login page and landing page, guards protected pages by reading `data-auth-*` on `<body>`, redirects wrong users. | The page-level bouncer. |
| `role-login.js` | Drives every `*-login.html` form. | Login-form behaviour. |
| `app.js` | Toast notifications and small shared UI helpers. | Pop-up messages. |
| `manager-submissions-api.js` | The engine of the Transport/Energy/LPG/Water/Waste entry pages: maps HTML fields to metric codes, loads the current period and current submission, Save Draft, Submit, handles `row_version` conflicts and read-only states. | Connects the form to the backend workflow. |
| `calculation-preview.js` | The **only** code that writes the "Emission Preview" box — always from the backend's result. Typing marks the preview stale; it never invents a number. | Shows the server's calculation, never its own. |
| `evidence-api.js` | Upload/list/delete/download calls for evidence. | Evidence API wrapper. |
| `evidence-manager.js` | Evidence UI next to each field: upload, replace, remove while editable; read-only afterwards. | Paper-clip buttons. |
| `waste-inventory.js` | Dry-waste table editor using the catalogue fetched from the API. | Waste material picker. |
| `outreach-api.js`, `outreach-integration.js` | Outreach API wrapper and the programme form logic (theme mapping, nullable numbers, save/submit). | Outreach form wiring. |
| `manager-history.js` | Renders the manager's history table. | History list. |
| `admin-overview-api.js`, `admin-factors.js`, `admin-evidence.js`, `admin-users.js`, `admin-audit.js` | One script per admin page. (The review queue's logic is inline in `admin-queue.html`.) | Admin page logic. |
| `styles.css`, `role-login.css` | Portal styles and login styles. | Look and feel. |
| `serve-portal.py` | Local server on `127.0.0.1:3000` with `Cache-Control: no-store` so browsers never run stale JS. | Run `python serve-portal.py`. |
| `package.json` | `npm run test:contracts` runs the frontend contract tests. | Test command. |
| `tests/frontend-contract.test.js` | 30 checks that pages exist, inline scripts parse, login pages are complete, entry pages have guards and mapped fields, admin pages are protected. | Keeps the HTML wiring honest. |

### 8.4 Assets and leftovers in this folder

| Item | Status |
| --- | --- |
| Logos (`microcosm-*.svg/png`, `kumaraguru-microcosm-logo.png`), `background.png` | Used by pages. |
| `*.mp4` videos, `walkthrough.js/.css`, `mobile.js/.css`, `data-loader.js`, `vendor/gsap-scrolltrigger.min.js`, `data/*.csv|json` | Copied from the old dashboard; **not loaded by any portal page**. The CSVs are also historical import sources (§7.9). |
| `login.html`, `admin.html`, `portal-router.js`, `portal-guard.js` | **Legacy** login path; routes managers to `manager.html`, which does not exist. The active path is the role-specific logins. |
| `broken-login-backup/`, `transport-login.broken-backup.html` | Backups of broken login pages; not used. |
| `*.md` (`BACKEND_REQUIREMENTS`, `DEVELOPMENT_GOVERNANCE`, `PHASE_*`, `PROJECT_GUIDE`, `README`) | Earlier design notes from the Supabase phase. `README.md` still describes a UI-only prototype. |

---

## 9. Public dashboard (current): `apps/public-dashboard-final-staging`

The public website. A single HTML page with ten sections, fed **only** by the public API. Served locally on **port 3001** by `serve-staging.py`.

### 9.1 Pages (tabs)

| Tab (`data-page`) | Shows |
| --- | --- |
| `overview` | Hero carbon card and headline KPIs across all domains. |
| `weather` | Live station: temperature, humidity, rainfall, wind, pressure first; air quality (AQI, PM, gases) and noise underneath; LIVE/STALE/OFFLINE pill. |
| `ghg` | Scope 1, Scope 2, operational GHG, per-capita; emission profile, electricity mix and fossil-fuel mix donuts. |
| `energy` | Grid and renewable electricity, renewable share, avoided emissions, solar water heater as a separate thermal reference. |
| `water` | Consumption, source breakdown (TWAD/borewell/private), recycled, per capita. |
| `waste` | Wet/dry/total, category treemap, landfill diversion (static 88.1%). |
| `green` | Green-cover map and static institutional figures. |
| `outreach` | Programmes, participants, themes, partners, saplings, volunteers. |
| `explorer` | Data table of the selected period. |
| `about` | About the observatory. |

A year and month selector drives every page; "All" means the backend's Full-Year/YTD aggregate.

### 9.2 Files

| File | What it does | In simple words |
| --- | --- | --- |
| `index.html` | Page shell. Loads, in order: Chart.js + treemap plugin (vendored), GSAP, model-viewer, `public-api.js`, `public-data-loader.js`, `app.js`, `weather.js`, ScrollTrigger, `walkthrough.js`, `mobile.js`. | The page skeleton. |
| `public-api.js` | The single adapter for `/api/public/dashboard`, `/history` and `/timeline`. Normalises numbers; missing stays `null`. | Talks to the public API. |
| `public-data-loader.js` | Turns the timeline into the per-year, per-month arrays `app.js` expects, attaching the backend's aggregates (with coverage) and display context. Annual/YTD records are never put into a month. Green cover is the only data still read from a CSV (`data/green_master.csv`). | Reshapes API data for the charts. |
| `app.js` | The dashboard core (≈2,260 lines): KPI cards with source badges and trend arrows, the GHG hero, all Chart.js charts, data explorer, green map, period controls, KPI detail modal, page switching (`go()`), animations. Formats — never calculates — official values. | Draws everything. |
| `weather.js` | Weather page: polls `/api/environment/latest` and `/status` every 20 s, history charts, IST display; degrades to `--` and OFFLINE if the API is unreachable. | Live weather widgets. |
| `walkthrough.js`, `walkthrough.css` | "The Carbon Story" — a cinematic, scroll-driven tour that reads numbers off the rendered KPI cards and adds everyday equivalents (trees, homes, car-km). | Guided storytelling mode. |
| `mobile.js`, `mobile.css` | Phone-only extras (collapsible filter bar, etc.). No effect on desktop. | Mobile layout helpers. |
| `styles.css` | Main styles. | Look and feel. |
| `serve-staging.py` | Local server on `127.0.0.1:3001` that proxies **only** the six read-only routes (`/api/public/dashboard[/history|/timeline]`, `/api/environment/latest|history|status`) to the API; everything else is static. Mirrors how Nginx will work in production. | Local stand-in for the production web server. |
| `vendor/` | Local copies of Chart.js, the treemap plugin and GSAP ScrollTrigger. | No CDN dependency for charts. |
| `media/` | Background videos (fuel, electricity, water, waste, nature, rain, sunny…), background images, logos, green map. | Visual assets. |
| `tests/public-api-contract.test.js` | 56 checks: script order, vendored charts, failure isolation, adapter behaviour for every schema version, missing-value handling, period semantics, labels. | Guards the "display, don't calculate" contract. |
| `calculations.js`, `data-loader.js`, most of `data/` | Carried over from the original dashboard; **not loaded** by `index.html`. The CSVs are historical import sources. | Leftovers. |
| `.claude/skills/`, `.agents/skills/`, `skills-lock.json` | AI-assistant design skills (duplicated in two folders). Not part of the website. | Tooling. |

---

## 10. Public dashboard (original): `apps/public-dashboard`

The earlier version of the same site, and the one `README.md` at the root still calls "the" public dashboard.

- **Key difference:** it computes figures **in the browser** from the CSV files in `data/` using `calculations.js` (emission formulas) and `data-loader.js` (CSV parsing plus an optional `dashboard_master.json` overlay), with built-in default factors (petrol 2.388, diesel 2.701, grid 0.727, LPG 1.5571). This is exactly what the current rules forbid, which is why the staging version replaced it.
- Loads Chart.js from CDN instead of vendored copies.
- `weather.js` already uses the same-origin `/api/environment/*` routes.
- Extra files: `About_page.md` (copy for the About page), `KCT_Sustainability_Dashboard_Calculation_Formulas.md` (the formula reference the browser engine followed), `PROJECT_GUIDE.md` (how the old CSV pipeline worked), `docs/docker-decisions.md` (records that the separate `aeron-api` service was retired and the worker design adopted), `test_crash.py` (a Selenium smoke script), a screenshot, background images and videos.

**In simple words:** the original look-and-feel prototype. Keep it for reference; the staging folder is the one being made production-ready.

---

## 11. Portal backup: `apps/manager-admin-backup-before-recovery`

A frozen copy of the portal as it was before the backend was wired in: demo role buttons, `localStorage` "logins", browser-side totals, Supabase-phase design notes. **Do not edit or deploy.** Useful only to compare against the original design.

---

## 12. Report generation: `services/report-generation`

A standalone engine that turns dashboard data into a designed PDF sustainability report.

| File / folder | What it does |
| --- | --- |
| `report_engine/generators/data_provider.py` | Reads legacy CSVs (transport, DG, electricity, renewable, emission factors) from a configured folder, builds per-year arrays, renders charts with Matplotlib, and writes insights. |
| `report_engine/generators/pdf_generator.py` | Renders Jinja2 templates and produces the PDF with **WeasyPrint**. |
| `report_engine/generators/asset_manager.py` | Finds images and fonts and embeds them. |
| `report_engine/templates/` | `report_assembler.html` and `report_template.html`, a UI-components partial, and ten page templates: cover, introduction, executive summary, highlights, Scope 1 analysis, Scope 2 analysis, comparison, methodology, recommendations, appendix. |
| `assets/report/` | Cover images, a reference report PDF, a template image, Archivo and Public Sans fonts. |
| `report_engine/exports/` | ~18 previously generated PDFs and a `debug.html`. |
| `README_PDF_SETUP.md` | Windows setup: install MSYS2 + GTK3 so WeasyPrint works. |
| `msys2-x86_64-20260611.exe` | The MSYS2 installer itself (≈90 MB). |
| `test_pdf_gen.py` | Manual test script. |

**Status:** not connected to the Main API or the publication workflow. It still reads the old CSVs via a `config` object that is not in this repository, and `test_pdf_gen.py` imports a function (`enhance_report_data`) that doesn't exist. Treat it as a design asset awaiting integration.

---

## 13. Root-level documents and reports

| File | What it is |
| --- | --- |
| `README.md` | Short overview of apps, services, schemas and security. |
| `PROJECT_MAP.md` | One-page folder map with responsibilities. |
| `TRANSFER_CHECKLIST.md` | Steps for moving the project to a new machine safely. |
| `PROJECT_PROGRESS_HANDOFF.md` (untracked) | Narrative of work so far. **Its Aeron sections are out of date** — they describe Phase 2 as blocked, but the contract and acceptance reports below show it was later verified and built. |
| `DERIVED_KPI_CALCULATION_CONTRACT.md` | **The authoritative formula contract** for schema 1.4 (grid, renewable, total electricity, renewable share, avoided emissions, water per capita, static landfill diversion) with a worked September 2026 example. |
| `CALCULATION_CONTRACT_REPORT.md` | Historical data audit and calculation contract (at `0009`). |
| `FINAL_CALCULATION_ACCEPTANCE.md` | End-to-end calculation and live acceptance audit for September 2026 (at `0010`). |
| `HISTORICAL_DATA_ARCHITECTURE.md` | How history is stored, reconciled, resolved and corrected. |
| `HISTORICAL_SOURCE_INVENTORY.md` | Every source file considered, its hash, and whether it was imported (12 batches). |
| `HISTORICAL_IMPORT_DRY_RUN.md` | Output of the dry run and proof the commit is idempotent. |
| `HISTORICAL_RECONCILIATION_REPORT.md` | Conflicts found: 27 total, 23 still unresolved (not published). |
| `HISTORICAL_COVERAGE_REPORT.md` | What months/years each metric covers, by granularity. |
| `AERON_INTEGRATION_AUDIT.md` | Phase 1 read-only audit of the supplied Aeron Playwright code. |
| `AERON_REAL_API_CONTRACT.md` | Phase 2: verified live contract (authentication, endpoints, 35 parameters, UTC timestamps, no +330 fix). |
| `AERON_INTEGRATION_ARCHITECTURE.md` | Final design: worker → PostgreSQL → read-only API → Weather UI. |
| `AERON_ACCEPTANCE_REPORT.md` | Pipeline accepted on real data (25 Sep 2026); a *fresh* LIVE reading was not yet observed because the station had stopped reporting. |

---

## 14. Other folders

| Folder | What it is |
| --- | --- |
| `tests/manager-admin/` | Three older Node tests (`data-loader`, `phase-b2-migrations`, `ui-contract`) moved here from the portal. They currently fail (see §17). |
| `docs/legacy/supabase-reference/` | The abandoned Supabase design: 17 SQL migrations, a checksum manifest, verification SQL, config. Reference only. |
| `docs/architecture`, `docs/backup`, `docs/database`, `docs/deployment`, `docs/operations`, `docs/security`, `database/*`, `deployment/*`, `config/` | Empty placeholders for the production phase (Nginx, Compose, backups). |
| `recovery-backups/` | Git-ignored local snapshots taken before risky changes, plus four PostgreSQL `.dump` files. Not in version control. |
| `.claude/agents/`, `.claude/skills/impeccable/`, `.impeccable/` | Configuration for AI design-assistant tools (the "Impeccable" design workflow). Not part of the product. |
| `.ruff_cache/`, `.local/`, `.pytest-tmp/` | Tool caches. |

---

## 15. How to run it locally

```bash
# 1. Database + API  (from services/main-api)
docker compose up --build              # Postgres + API on 127.0.0.1:8000
docker compose exec api alembic upgrade head
docker compose exec -e MICROCOSM_DEV_BOOTSTRAP_PASSWORD='<12+ chars>' api \
    python -m app.bootstrap development   # demo.admin, demo.transport, ...

# 2. Aeron worker (optional; needs AERON_* variables in your environment)
docker compose -f compose.yaml -f compose.worker.yaml up environment-worker
#    or a single cycle:  python -m app.environment.worker --once

# 3. Manager/Admin portal  (from apps/manager-admin)
python serve-portal.py                 # http://127.0.0.1:3000

# 4. Public dashboard  (from apps/public-dashboard-final-staging)
python serve-staging.py                # http://127.0.0.1:3001

# Checks
cd services/main-api && ruff check . && mypy app && pytest
node --test apps/manager-admin/tests/ apps/public-dashboard-final-staging/tests/
```

Health check: `curl http://localhost:8000/health/ready`. API docs: `http://localhost:8000/docs`.

Note: `compose.yaml` targets the database `microcosm_clean_20260922`. The older `microcosm` database is kept only for forensics (it was polluted by test data) — never point the runtime back at it by accident.

---

## 16. Where the work stands today

**Completed and in the code:**
- Authentication, sessions, CSRF, role/domain authorization, forced password change, lockout.
- Generic monthly workflow for Transport, Energy, LPG, Water, Waste; programme-based workflow for Outreach.
- Evidence lifecycle and admin Evidence Repository.
- Emission-factor governance and frozen calculations.
- Six-domain readiness, prepare/preview/publish, checksummed immutable releases, release schema 1.4.
- Historical data layer with reconciliation and the public timeline.
- Aeron ingestion worker and read-only environment API.
- API-driven public dashboard (staging).

**In progress (uncommitted on this branch):** changes to the staging dashboard's `app.js`, `index.html`, `styles.css` and its contract test. The composition charts (Emission Profile, Electricity Mix, Fossil-Fuel Mix, Water Source) now show the **selected period's own record** — the month, or the backend's Full-Year/YTD aggregate — instead of summing months in the browser, and each chart gets a note naming parts that are missing or only partially covered. The staging and portal JS contract suites pass (86/86) with these changes.

**Still to do (from the project's own documents):**
- Production packaging: Nginx, full Docker Compose, backups (the `deployment/` and `docs/` folders are empty).
- Observe a fresh LIVE Aeron reading once the station reports again.
- Resolve the 23 unresolved historical conflicts, with owner decisions.
- Connect report generation to published data, if it is to be kept.

---

## 17. Known issues and clean-up candidates

Found while preparing this guide. Most urgent first.

| # | Issue | Where | Suggested action |
| --- | --- | --- | --- |
| 1 | **A tracked template file contains what appear to be real Aeron login credentials.** | `services/main-api/.env.example` (the `AERON_USERNAME` / `AERON_PASSWORD` lines) | Rotate the Aeron password, replace the values with placeholders, and consider scrubbing git history. The worker is designed to read these from the environment only. |
| 2 | Root JS tests fail 11/11: they look for `app.js`, `data-loader.js` etc. in `tests/` instead of the app folder. | `tests/manager-admin/*.test.js` (`root = path.resolve(__dirname, '..')`) | Fix the path, or retire them if the app-local suites already cover them. |
| 3 | Waste is missing from some admin/manager helpers: overview counts, history entry links and evidence labels list only five domains. | `admin-overview-api.js`, `manager-history.js`, `admin-evidence.js` | Add `waste`. |
| 4 | Legacy login route points to a page that doesn't exist (`manager.html`). | `login.html`, `admin.html`, `portal-router.js`, `portal-guard.js` | Remove, or clearly mark as legacy. |
| 5 | Report generation is not connected and its test imports a missing function. | `services/report-generation` | Decide: integrate with `/api/public/dashboard/timeline`, or archive. |
| 6 | Large binaries in git: a ≈90 MB MSYS2 installer, ≈18 MB of exported PDFs, many duplicated `.mp4` files across app folders. | `services/report-generation`, `apps/*` | Move installers and generated output out of git; share media from one place. |
| 7 | Unused copies of the old CSV engine and data in the staging dashboard and portal. | `calculations.js`, `data-loader.js`, `data/`, videos, walkthrough in `manager-admin` | Remove from the deployable app once the history importer no longer needs them there. |
| 8 | Out-of-date docs: root `README.md` names the old dashboard; `services/main-api/README.md` says there are no migrations; `apps/manager-admin/README.md` describes a UI-only prototype; the handoff's Aeron status is stale. | various `*.md` | Refresh to match this guide. |
| 9 | Backup files kept alongside live code. | `compose.yaml.before-aeron-worker`, `broken-login-backup/`, `transport-login.broken-backup.html`, `apps/manager-admin-backup-before-recovery/` | Move to `recovery-backups/` (git-ignored) or delete. |
| 10 | AI design skills duplicated in two folders inside the public app. | `apps/public-dashboard-final-staging/.claude/skills` and `.agents/skills` | Keep one, outside the deployable app folder. |
