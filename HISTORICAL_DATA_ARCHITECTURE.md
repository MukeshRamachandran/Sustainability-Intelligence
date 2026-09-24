# Historical data architecture

K-COSMOS has two sources of public sustainability data. They are merged by one backend resolver and never by the browser.

```
HISTORICAL                                   CURRENT / FUTURE
CSV / institutional source                   Manager monthly entry
  → immutable import batch (SHA-256)           → Admin approval
  → raw source rows (JSONB)                    → Prepare (backend calculations, schema 1.4)
  → normalization (mapping JSON)               → Publish
  → reconciliation (rules R0–R5)               → published release (frozen payload + checksum)
  → metric values (true granularity)                 │
  → historical calculations (shared formulas)        │
                 └──────────── public timeline resolver ─┘
                                      → GET /api/public/dashboard/timeline → dashboard
```

Historical records never went through the Manager/Admin workflow, so they are **never** written into `sustainability.submissions` or approvals. Future months keep the existing Manager → Admin → Publish workflow. The importer is not used for monthly operations.

## Tables (migration `0011_historical_data_layer`)

All history tables are in schema `history`, which revokes all privileges from `public`.

| Table | Purpose | Mutability |
|---|---|---|
| `import_batches` | One row per imported source file + mapping version: `source_reference` (repository-relative), `source_sha256`, `mapping_code`, `mapping_version`, `status` (STAGED/RECONCILED/VERIFIED/REJECTED). Unique on (sha256, mapping, version). | Provenance columns immutable (trigger); only `status`/`notes` may change. No delete. |
| `source_rows` | Every raw CSV row as JSONB, numbered. | Append-only (trigger). |
| `periods` | `granularity` MONTHLY / YTD / ANNUAL / STATIC with `coverage_start`/`coverage_end`. `month` is required for MONTHLY and forbidden otherwise (check constraint). An annual record is one row, never twelve. | Append-only. |
| `metric_values` | One source-reported value: period, domain, metric code (current Manager codes reused), value, qualifier (EXACT / AT_LEAST for "20+" / APPROXIMATE), unit, batch, source row, source column, `verification_status` (UNVERIFIED/VERIFIED/REJECTED/CONFLICT), `authority_status` (SOURCE_REPORTED/NORMALIZED/AUTHORITATIVE), `version`, `supersedes_id`. AUTHORITATIVE requires VERIFIED (check constraint). | Append-only. Corrections are new versions. |
| `calculation_results` | Reproducible results per period: value, unit, methodology version, factor code/value/unit, factor set id + version, `input_snapshot` (each input's value and metric-value id), `provenance` (factor, population source), `input_hash`, `is_current`. | Only `is_current` true → false (retire); no delete. One current row per (period, code). |
| `conflicts` | Every disagreement: type, period, metric, source A/value A, source B/value B, detail, `resolution_status` (UNRESOLVED/RESOLVED/REJECTED_SOURCE), chosen batch, reason, resolved_at. | Only an UNRESOLVED row may be resolved, once. No delete. |

`publication.public_release_metadata` (release_id, classification official/test, public_visible, reason) sits **beside** the frozen release payload, so no checksum changes. A release without a row is official and public. A `test` release can never be public (check constraint).

## Reconciliation rules (`app/historical/validator.py`)

- **R0** – A failed internal source check (a printed total versus its parts) marks the affected values CONFLICT.
- **R1** – Copies agree when they are equal, or when one is exactly the other rounded to fewer decimals. The more precise value is kept, and a RESOLVED conflict records it.
- **R2** – Copies that genuinely disagree are all CONFLICT and UNRESOLVED, unless `mappings/resolutions.json` holds an owner-approved choice. That choice makes the selected copy AUTHORITATIVE and the others REJECTED.
- **R3** – A reported ANNUAL/YTD aggregate is compared with the sum of the genuine monthly values it covers. A mismatch is a CONFLICT for both, unless the aggregate's source declares itself superseded by monthly rows (REJECTED_SOURCE).
- **R4** – A value whose coverage is not stated in the source stays UNVERIFIED.
- **R5** – Only a VERIFIED value from the highest-priority agreeing copy becomes AUTHORITATIVE. Agreeing lower-priority copies stay SOURCE_REPORTED (corroborating).

## Shared calculation engine

`app/services/sustainability_formulas.py` holds the only implementation of the accepted formulas:
- grid total
- renewable electricity (on-campus + procured; **solar water heater excluded**)
- total electricity
- renewable share (ratio of sums)
- estimated avoided grid emissions
- activity × factor emissions
- Scope 1 (all four components required)
- Operational GHG
- the per-capita values
- water consumed (TWAD + Borewell + Private)
- waste total

Release preparation (`publication.py`, `emission_factors.py`) and the historical calculator (`app/historical/calculator.py`) both call it. The refactor left every accepted result unchanged: the full existing suite, including the schema-1.4 contract values, passes.

## Factor treatment

Every historical emission uses the governed factor set in `sustainability.emission_factor_sets` whose `effective_from` is the latest on or before the period start. That is currently `existing-project-draft-v1`, effective 2025-01-01: GRID 0.727, PETROL 2.388, DIESEL 2.701, LPG 1.5571 kgCO2e per unit.
- An ANNUAL or YTD activity value is refused if another active set becomes effective inside its window (`multiple_factor_sets_in_period`).
- Annual totals of emissions are sums of monthly results, each calculated with its own month's factor.
- If no set applies, the emission is unavailable (`no_applicable_factor_set`). A factor is never guessed.
- The legacy `emission_factors.csv` files are not used.

## Population treatment

For a year, population comes from the governed `institutional_population_references` row (2026 = 6,991, owner decision) first. If there is none, it comes from a VERIFIED historical population record for that year. `population_master.csv` states `2025, 6991`; it is imported with provenance and flagged for owner confirmation, because it equals the 2026 figure. Without a population, every per-capita value is unavailable.

## Public resolver (`app/historical/resolver.py`)

Priority per month:
1. OFFICIAL, publicly visible published release.
2. VERIFIED historical MONTHLY.
3. VERIFIED historical YTD.
4. VERIFIED historical ANNUAL.
5. Static reference.
6. Missing.

TEST releases never enter the chain.

Aggregate views:
- **Full Year** when all 12 genuine months exist; otherwise **YTD Jan–(last genuine month)**.
- Additive values are sums of genuine months, each with `months_covered` and `coverage_status` (complete/partial).
- Ratios and per-capita values are recomputed from summed inputs, and only with complete coverage.
- A source-reported ANNUAL/YTD record is merged only into the view with identical coverage. Otherwise it gets its own view (for example an annual-only waste record in a year with only some months).
- Month entries report each domain's state. `aggregate_only` carries a message pointing at the Full Year / YTD view.

`GET /api/public/dashboard/timeline` returns:
- `default_key` (latest month with any verified official data)
- `selector` (per year: aggregate option(s) + genuine months)
- `periods` (values with unit, qualifier, source kind, granularity, coverage, provenance: batch name + SHA-256 + source column, factor and factor-set version; no filesystem paths)
- `labels`
- `static_references` (landfill diversion 88.1%, one backend constant)

`/api/public/dashboard` and `/api/public/dashboard/history` now exclude non-public releases.

## Import procedure

```sh
# inside the API container; sources copied to /tmp/kcosmos-sources with repository-relative paths
python -m app.historical.importer --source-root /tmp/kcosmos-sources --dry-run --report /tmp/dry-run.md
python -m app.historical.importer --source-root /tmp/kcosmos-sources --commit  --report /tmp/commit.md
```

- **Dry run** only issues SELECTs. Its calculations are computed in memory from the reconciliation plan.
- **Commit** runs as one transaction: batches, raw rows, periods, values, conflicts, calculations.
- **Idempotent:** a batch already imported (same SHA-256 + mapping + version) is skipped. An unchanged calculation (same input hash) is skipped.
- A **changed file** under an existing mapping version is refused.
- Always back up the database (`pg_dump -Fc`) first, and rehearse on a fresh isolated database restored from that backup.

## Correction / versioning procedure

- **Owner resolves a conflict:** add an entry to `resolutions.json`, then dry-run and commit. The chosen value gets a new VERIFIED/AUTHORITATIVE version (`supersedes_id` → old row). Rejected copies get REJECTED versions. The conflict row records the resolution. Affected calculations are recalculated, and the old results are retired (`is_current = false`).
- **Source file corrected:** bump that mapping's `version`, then dry-run and commit. It becomes a new batch. The old batch and its rows remain for audit.
- **Coverage confirmed** (e.g. 2026 waste is Jan–Jun): set `coverage_confirmed: true` (or the confirmed end date) in the mapping, bump its version, and re-import. The values become VERIFIED and are published.
- History is never updated or deleted in place. Database triggers enforce this.

## Test-release treatment

September 2026 v1/v2/v3 were created to accept the publication workflow.
- The migration classifies them `test`, `public_visible = false`, with a reason.
- Their payloads, checksums, statuses and audit history are untouched. v3 remains the `active` row, so the Admin workflow is unaffected.
- They are excluded from `/dashboard`, `/history` and `/timeline`.
- Future releases need no extra step: a release without metadata is official and public. Publishing an official October 2026 release automatically outranks historical data for that month.

## Runtime CSV dependency

The final-staging dashboard no longer fetches operational or historical CSVs; every sustainability value comes from `/api/public/dashboard/timeline`. `data/green_master.csv` remains the static Green Cover asset. The other files in `data/` are legacy and not a runtime authority. They are kept, not deleted.
