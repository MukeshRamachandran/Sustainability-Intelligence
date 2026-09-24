# K-COSMOS Historical Data Audit and Calculation Contract

Audit date: 2026-09-24 (Asia/Kolkata)
Repository: `C:\Projects\K-COSMOS-FINAL`
Branch / audited commit: `feature-waste-domain` / `265c63d8c5d0874665777d8e15cc01c21ae1587e`
Active database: `microcosm_clean_20260922`
Alembic head: `0009_waste_domain`

## Executive decision

The current schema 1.2 September release is internally consistent, immutable, and remains the sole public operational authority. Historical CSV files are reference evidence only. They are not safe to import yet because some copies conflict, some values are qualified approximations, and annual/YTD records cannot be represented honestly as monthly submissions.

The deterministic, already-governed calculations are transport, DG, LPG, and grid emissions plus the existing Energy, Water, and Waste additive totals. Operational Gross GHG is mathematically determinable as the complete governed Scope 1 component subtotal plus Scope 2, but it is not frozen in schema 1.2. It should become a backend-produced schema 1.3 indicator only after the proposed contract is accepted. Avoided emissions and renewable share remain `methodology_under_review`.

No historical data was imported. No database schema or stored release payload was changed.

## A. Git / baseline status

- Branch: `feature-waste-domain`.
- HEAD and accepted dashboard commit: `265c63d8c5d0874665777d8e15cc01c21ae1587e`.
- Pre-audit worktree: clean except pre-existing untracked `.claude/`.
- Migration files run through `0009_waste_domain`.
- A required pre-change custom-format backup was created and its archive catalog validated: `recovery-backups/microcosm_clean_20260922_pre_historical_audit_20260924-123527.dump`.

## B. Current September release status

- Version: `sustainability-2026-09-v1`.
- Status: `active`.
- Period: September 2026.
- Schema: `1.2`.
- Stored and API checksum: `f6f996ec2a42a2ceead5c0d7361b3b00ddb4b52083fe2099a90556bd5b99ba02`.
- All six domains report `approved`.
- The release is the only row in `publication.public_releases` and was not mutated.
- Frozen governed component results:
  - Petrol: 8.221884 tCO2e.
  - Fleet diesel: 0.332223 tCO2e.
  - DG diesel: 0.632034 tCO2e.
  - LPG: 0.003114 tCO2e.
  - Grid electricity: 2.569945 tCO2e.
- Complete display Scope 1 subtotal: 9.189255 tCO2e.
- Scope 2: 2.569945 tCO2e.
- Candidate Operational Gross GHG: 11.759200 tCO2e. This is an audit calculation, not a mutation of v1 and not yet an official schema 1.2 indicator.

## C. Historical source inventory

The repository contains three families of historical/static copies. None is currently authoritative for public operational data.

| Source family | Location | Current use | Audit status |
|---|---|---|---|
| Staging historical references | `apps/public-dashboard-final-staging/data/` | Only `population_master.csv`, `dashboard_metadata.csv`, and `green_master.csv` are read by `public-data-loader.js`; operational CSVs are deliberately ignored | Primary audit set because it accompanies the accepted staging UI, but not import authority |
| Older public dashboard | `apps/public-dashboard/data/` | Legacy CSV loader | Conflicts with staging/Manager copies for Energy and factors |
| Manager prototype/reference | `apps/manager-admin/data/` and byte-identical backup data except one factor file | Old prototype loader/reference | Normalized Transport/Energy files are useful evidence, but overlays contain prototype records and cannot be imported |
| Legacy SQL/design references | `docs/legacy/supabase-reference/` | Documentation/old schema only | Not data authority |
| Report-generation output | `services/report-generation/` | Generated report/debug artifacts | Presentation evidence only; not import authority |

Important conflicts:

- Energy HT values disagree across copies (for example 2025 January is 165,836 in staging but 155,222 in the older public/Manager normalized source; August and September differ materially).
- 2026 Energy source values disagree between staging and Manager normalized files.
- Static factor CSVs disagree with governed factors. The active frozen factor set is authoritative: Petrol 2.388, Diesel 2.701, Grid 0.727, LPG 1.5571 in kgCO2e per activity unit. Staging CSV values of Grid 0.71 and LPG 2.939 must not be used for governed calculations.
- `dashboard_master.json` contains prototype June 2026 records and is not reliable historical authority.
- 2025 Water monthly total (39,835 KL) does not reconcile with the separate annual TWAD + Borewell total (195,708 KL).

## D. Month x domain availability matrix

Legend: `RM` REAL MONTHLY, `AO` ANNUAL ONLY, `YTD` YTD ONLY, `M` MISSING, `CG` CURRENT GOVERNED. A suffix `*` means source conflict or restricted field detail requires validation before import.

| Period | Transport | Energy | LPG | Water | Outreach | Waste |
|---|---:|---:|---:|---:|---:|---:|
| 2025-01 | RM | RM* | RM | RM* | AO | AO |
| 2025-02 | RM | RM* | RM | RM* | AO | AO |
| 2025-03 | RM | RM* | RM | RM* | AO | AO |
| 2025-04 | RM | RM* | RM | RM* | AO | AO |
| 2025-05 | RM | RM* | RM | RM* | AO | AO |
| 2025-06 | RM | RM* | RM | RM* | AO | AO |
| 2025-07 | RM | RM* | RM | RM* | AO | AO |
| 2025-08 | RM | RM* | RM | RM* | AO | AO |
| 2025-09 | RM | RM* | RM | RM* | AO | AO |
| 2025-10 | RM | RM* | RM | RM* | AO | AO |
| 2025-11 | RM | RM* | RM | RM* | AO | AO |
| 2025-12 | RM | RM* | RM | RM* | AO | AO |
| 2026-01 | RM | RM* | M | RM | YTD | YTD |
| 2026-02 | RM | RM* | M | RM | YTD | YTD |
| 2026-03 | RM | RM* | M | RM | YTD | YTD |
| 2026-04 | RM | RM* | M | RM | YTD | YTD |
| 2026-05 | M | RM* | M | RM | YTD | YTD |
| 2026-06 | M | RM* | M | RM | YTD | YTD |
| 2026-07 | M | M | M | M | YTD | YTD |
| 2026-08 | M | M | M | M | YTD | YTD |
| 2026-09 | CG | CG | CG | CG | CG | CG |

The 2025 Water `RM*` designation applies only to aggregate monthly consumption. Source-level TWAD/Borewell/Private values are not monthly. Outreach and Waste annual/YTD records are shown once conceptually; they must not become repeated monthly records.

## E-F. Field-level historical mapping and granularity

### Transport

| Source field | Coverage / granularity | Unit | Backend mapping | Missing behavior | Import / public / trend decision |
|---|---|---:|---|---|---|
| `transport_master.csv` Diesel `consumption_litre` | 2025 Jan-Dec; 2026 Jan-Apr / MONTHLY | L | `transport_diesel_litres` | No later row means missing, not zero | Importable after source sign-off; public-safe; trend-safe |
| `transport_master.csv` Petrol `consumption_litre` | Same / MONTHLY | L | `transport_petrol_litres` | Missing row = missing | Importable after source sign-off; public-safe; trend-safe |
| `dg_master.csv consumption_litre` | 2025 Jan-Dec; 2026 Jan-Apr / MONTHLY | L | `dg_diesel_litres` | Missing row = missing | Importable after source sign-off; public-safe; trend-safe |
| `dashboard_master.json` Petrol/Diesel | June 2026 prototype overlay / UNKNOWN | L | Same metrics | Null metadata and conflict risk | Do not import; not trend-safe |

### Energy

| Source field | Coverage / granularity | Unit | Backend mapping | Missing behavior | Import / public / trend decision |
|---|---|---:|---|---|---|
| Grid HT | 2025 Jan-Dec; 2026 Jan-Jun / MONTHLY | kWh | `grid_ht_kwh` | Blank/missing row = missing | Source copies conflict; block import. Institution aggregate and proposed public-safe |
| Grid Commercial | Same / MONTHLY | kWh | `grid_commercial_kwh` | Explicit 0 is zero | Source copies conflict in 2026; block import pending sign-off |
| Grid Temporary | Same / MONTHLY | kWh | `grid_temporary_kwh` | Explicit 0 is zero | Source copies conflict; block import pending sign-off |
| Total Grid Consumption | Derived in older copy | kWh | `grid_total_kwh` | Must be null if any required component is missing | Recalculate in backend only; never import as competing authority |
| Renewable On Campus | 2025 Jan-Dec; 2026 Jan-Jun / MONTHLY | kWh | `renewable_on_campus_kwh` | Missing = unavailable | Import after source sign-off; label as on-campus renewable, not automatically Solar PV |
| Procured Renewable | Same / MONTHLY | kWh | `renewable_procured_kwh` | Missing = unavailable | Import after source sign-off; public-safe; trend-safe |
| Solar Water Heater | Repeated 62,500 in staging; absent for 2026 in another copy / UNKNOWN methodology | kWh | `solar_water_heater_kwh` | Blank is missing | Do not import until the repeated monthly basis is documented |
| Renewable Total | Derived; separate Manager `renewable_master.csv` also contains 2025 annual and 2026 Jan-Apr YTD totals | kWh | `renewable_total_kwh` | Missing components cannot be assumed zero | Backend derives monthly total; annual/YTD reference must not override monthly evidence |

### LPG

| Source field | Coverage / granularity | Unit | Backend mapping | Missing behavior | Import / public / trend decision |
|---|---|---:|---|---|---|
| `lpg_master.csv consumption_litre` | 2025 Jan-Dec / MONTHLY | L | `lpg_consumption_litres` | No 2026 rows = missing | Importable after sign-off; public-safe; trend-safe |

Historical factors are not imported with activity. Governed calculation factors come only from the applicable active factor set.

### Water

| Source field | Coverage / granularity | Unit | Backend mapping | Missing behavior | Import / public / trend decision |
|---|---|---:|---|---|---|
| 2025 monthly `Water Consumption` | Jan-Dec / MONTHLY aggregate | KL | Historical observation corresponding to `water_consumed_kl` | Missing month = missing | Current backend total is derived and not manager-editable; needs a historical import model, not fabricated source values |
| 2025 `Total water recycled` | 2025 / ANNUAL | KL | `water_recycled_kl` conceptually | No monthly allocation | Store once as annual historical aggregate; not monthly trend-safe |
| 2025 TWAD total | 2025 / ANNUAL | KL | `water_twad_kl` conceptually | Monthly breakdown unavailable | Store once as annual context only; conflicts with monthly aggregate total |
| 2025 Borewell total | 2025 / ANNUAL | KL | `water_borewell_kl` conceptually | Monthly breakdown unavailable | Same; never fabricate twelve rows |
| 2025 Private | MISSING | KL | `water_private_kl` | Must remain null | Not importable |
| 2026 TWAD | Jan-Jun / MONTHLY | KL | `water_twad_kl` | Explicit zero remains zero | Importable after source sign-off; public-safe proposal; trend-safe |
| 2026 Borewell | Jan-Jun / MONTHLY | KL | `water_borewell_kl` | Missing = unavailable | Importable after source sign-off; public-safe proposal; trend-safe |
| 2026 Quantity Procured | Jan-Jun / MONTHLY | KL | `water_private_kl` (terminology normalization required) | Explicit zero remains zero | Importable only after confirming “procured” equals backend Private supply |
| 2026 Total Consumption | Jan-Jun / MONTHLY derived | KL | `water_consumed_kl` | Derived components required | Backend derives; use only as reconciliation check |
| 2026 Total Water Recycled | 2026 to file cutoff / YTD | KL | `water_recycled_kl` conceptually | No monthly split | Preserve as YTD; do not divide by six |
| Wastewater | MISSING | KL | `wastewater_generated_kl` | Null | Not importable |

### Outreach

All 2025 values are ANNUAL aggregates; 2026 values are YTD/UNKNOWN-CUTOFF aggregates. Values containing `+` are lower-bound qualified figures, not exact integers.

| Source field | Backend aggregate mapping | Import decision |
|---|---|---|
| Program/event count | `total_programs` | Historical aggregate record only; do not create programme rows |
| Volunteers engaged | `volunteers_engaged` | Preserve `+` qualifier; not current programme submission input |
| Volunteering hours | `volunteer_hours` | Same |
| Experts involved | `experts_involved` | Same |
| Participants/reach | `total_participants` | Same |
| Partner organizations | `partner_organizations` | Same |
| Saplings/seedlings | `saplings_planted` | Same |
| Thematic counts | `themes.*` | Annual/YTD aggregate only |
| Audience category counts | `participants_by_category.*` | Annual/YTD aggregate only; blanks remain missing |

These records are public-safe only when labelled `ANNUAL HISTORICAL AGGREGATE` or `YTD HISTORICAL AGGREGATE`; they are not monthly trend points.

### Waste

`waste_master.csv` contains one 2025 ANNUAL inventory and one 2026 YTD inventory. `dashboard_metadata.csv` explicitly classifies 2026 as YTD. It is not genuine Jan-Jun monthly data.

- 2025: dry 48,762.55 kg, wet 6,577 kg, total 55,339.55 kg.
- 2026 YTD: dry 76,590.6 kg, wet 3,000 kg, total 79,590.6 kg.
- All 19 named historical items map directly to the governed Waste material catalog (including normalized `E WASTE` -> `E_WASTE`). Blank item values remain null, not zero.
- Import later as one annual 2025 record and one YTD 2026 record with explicit coverage metadata. Do not create monthly `Submission` rows.
- Annual/YTD totals are public-safe as contextual values but not monthly-trend-safe.

### Population

| Source field | Coverage / granularity | Unit | Mapping / decision |
|---|---|---:|---|
| `population_master.csv population` = 6991 | 2025 / STATIC annual reference | people | Not represented in backend. The project owner also supplied current population 6991, but an effective period and source reference are still required before authoritative per-capita calculation. |

### Green Cover

`green_master.csv` is STATIC, without effective date/source citation metadata.

| Field | Value/unit | Classification |
|---|---:|---|
| Total trees | 2,703 count | Institutional measurement/reference |
| Total species identified | 54 count | Institutional measurement/reference |
| Campus area | 150 acres | Institutional reference |
| Total green cover | 70% | Institutional measurement/reference, methodology/currency not stated |
| Maintained vegetation | 56 acres | Institutional measurement/reference |
| Natural vegetation | 50 acres | Institutional measurement/reference |
| Zone tree/species rows | Per-zone counts | Static institutional reference |
| Species/phenology | Taxonomy/calendar | Static reference |

No source evidence supports a governed carbon-sequestration result. Carbon-saving, household electricity, car-km, and national per-capita equivalences are illustrative only and must not drive official KPIs.

## G. Current calculation matrix

| Calculation | Authority | Formula | Missing rule | Status |
|---|---|---|---|---|
| Petrol emissions | Backend frozen calculation | `transport_petrol_litres × applicable PETROL kgCO2e/L ÷ 1000` | Unavailable if activity/factor missing | GOVERNED |
| Fleet diesel emissions | Backend frozen calculation | `transport_diesel_litres × DIESEL ÷ 1000` | Same | GOVERNED |
| DG diesel emissions | Backend frozen calculation | `dg_diesel_litres × DIESEL ÷ 1000` | Same | GOVERNED |
| LPG emissions | Backend frozen calculation | `lpg_consumption_litres × LPG ÷ 1000` | Same; kg reference never drives emissions | GOVERNED |
| Grid emissions / Scope 2 | Backend frozen calculation | `grid_total_kwh × GRID_ELECTRICITY ÷ 1000` | Same | GOVERNED |
| Grid total | Database trigger/backend model | `HT + Commercial + Temporary` | Required components retain blank semantics | GOVERNED |
| Renewable total | Database trigger/backend model | `On-campus + Procured + Solar-water-heater` | Required components retain blank semantics | GOVERNED activity total, not avoided CO2e |
| Water consumed | Database trigger/backend model | `TWAD + Borewell + Private` | Missing cannot become zero | GOVERNED |
| Waste dry | Backend Waste service/database trigger | Sum submitted Waste material quantities | Explicit empty item set can produce confirmed zero | GOVERNED |
| Waste total | Backend | `Wet + Dry` | Missing cannot become zero | GOVERNED |
| Display Scope 1 subtotal | Frontend display addition | Petrol + Fleet diesel + DG diesel + LPG | Every component required | DETERMINISTIC DISPLAY, not schema 1.2 indicator |
| Total/Gross GHG | Payload indicator | None; frozen as unavailable | `methodology_under_review` | UNAVAILABLE in schema 1.2 |
| Avoided emissions | Payload indicator | None | `methodology_under_review` | UNAVAILABLE |
| Renewable share | Payload indicator | None | `methodology_under_review` | UNAVAILABLE |

## H. Proposed calculation matrix

| Indicator | Proposed authoritative formula | Decision |
|---|---|---|
| Scope 1 | Complete sum of frozen Petrol + Fleet Diesel + DG Diesel + LPG results | Approve as backend-produced schema 1.3 indicator; any missing component makes result unavailable |
| Scope 2 | Frozen Grid Electricity result | Already governed; expose a single indicator alias only if useful |
| Operational Gross GHG | `Scope 1 + Scope 2` | Deterministic and consistent with agreed operational boundary; label “Operational GHG Emissions — Scope 1 + Scope 2”; do not imply Scope 3/all-source footprint |
| Per-capita Operational Emissions | `Operational Gross GHG tCO2e × 1000 / effective population` | Implement only after population reference governance exists |
| Estimated Grid Emissions Avoided | `renewable electricity × applicable grid factor ÷ 1000` | Keep unavailable until methodology and eligible renewable activity are approved |
| Renewable Share | `renewable_total / (grid_total + renewable_total) × 100` | Keep unavailable until non-overlap/double-counting is documented |
| Monthly Waste per Person | `monthly total waste kg / effective population` | Use only genuine governed monthly Waste |
| Annual Waste per Person | `annual waste kg / effective annual population` | Use only an explicitly annual historical record; never display as January |
| Water recycling ratio | `water_recycled_kl / water_consumed_kl × 100` | Deterministic only when both values cover the same period; current monthly release is suitable, historical annual/YTD requires matching coverage |
| Landfill diversion | Current UI uses `dry_waste / total_waste` | Methodology unsupported: dry waste is not proof of diversion. Rename/remove until disposition evidence exists |

## I-K. Scope and Operational Gross status

- **Scope 1:** WORKING as a complete frontend display subtotal for September (9.189255 tCO2e). Proposed for backend schema 1.3 authority.
- **Scope 2:** WORKING and backend-governed (2.569945 tCO2e).
- **Operational Gross GHG:** DETERMINISTIC BUT NOT PUBLISHED in schema 1.2. Candidate September value is 11.759200 tCO2e. Requires schema 1.3/new release to become official.

## L. Population / per-capita status

Status: METHODOLOGY/REFERENCE CONTRACT INCOMPLETE.

Recommended governed model: a new effective-dated reference table, not hardcoded JavaScript:

- `population`, positive integer.
- `effective_from` and optional `effective_to`.
- `source_reference` and optional `source_url`.
- `notes`, `created_at`, `created_by`, `approved_at`, `approved_by`.
- No overlapping effective ranges.
- Freeze the selected population and source metadata into a future release payload.

Do not calculate September per-capita officially until 6991 has a confirmed effective period/source. If 6991 is later accepted for September 2026, the candidate result is approximately 1.682 kgCO2e/person.

## M-N. Renewable methodology status

- **Avoided emissions:** METHODOLOGY UNDER REVIEW. Candidate arithmetic is not sufficient authority; keep unavailable.
- **Renewable share:** METHODOLOGY UNDER REVIEW due to possible overlap between procured renewable and grid totals. Keep unavailable.

## O. Energy public field gaps

`grid_ht_kwh`, `grid_commercial_kwh`, `grid_temporary_kwh`, `renewable_on_campus_kwh`, `renewable_procured_kwh`, and `solar_water_heater_kwh` are collected and persisted but classified `admin_only`. Only `grid_total_kwh`, `renewable_total_kwh`, and governed grid emissions enter schema 1.2.

Proposed schema 1.3 metadata change after owner approval: classify those six institution-level aggregate source metrics as `public_aggregate`, freeze them in new releases, and retain 1.0-1.2 readers. Do not call `renewable_on_campus_kwh` “Solar PV” unless its definition is narrowed or a dedicated Solar PV metric is added.

## P. Water public field gaps

`water_twad_kl`, `water_borewell_kl`, `water_private_kl`, and `wastewater_generated_kl` are persisted but `admin_only`. `water_consumed_kl` and `water_recycled_kl` are public.

Proposed schema 1.3 metadata change after owner approval: make the four institution-level aggregate source/flow metrics `public_aggregate`. Keep laboratory inlet/outlet values `internal_verification`.

## Q-R. Historical display rules

- **Waste 2025:** one ANNUAL record, coverage Jan-Dec. A month selected in 2025 may show contextual fallback labelled “2025 Annual Waste Data — Monthly breakdown unavailable.” Never include it as a monthly trend point, YTD component, or repeated export row.
- **Waste 2026:** one YTD record through the source file’s validated cutoff. Do not divide by six.
- **Outreach:** 2025 ANNUAL and 2026 YTD aggregate records must coexist separately from future monthly governed programme submissions. Never fabricate programme names/dates/participant rows.
- **Water 2025:** aggregate consumption has monthly values; source-level values are annual-only and internally inconsistent with the aggregate. Display source breakdown only as annual contextual data after reconciliation, never as monthly sources.

## S. Green Cover / Carbon Story status

- Green-cover measurements are STATIC SOURCE DATA and currently loaded from CSV, not frozen publication data.
- “Carbon saved by green cover” correctly renders unavailable; keep it unavailable without a cited sequestration model.
- `walkthrough.js` still contains unsupported narrative/equivalence constants and wording that calls net impact an “honest, settled figure.” These are not governed and should be removed or explicitly marked illustrative before production use.
- No Green Cover value may offset Operational Gross GHG.

## T-AB. Dashboard audit status

| Area | Status | Evidence / action |
|---|---|---|
| Overview | BUG FIXED + INTENTIONAL UNAVAILABILITY | The temporary port-3011 server did not provide the required same-origin `/api/public/*` proxy. The established staging server/proxy is on port 3001; no backend CORS widening for 3011 is retained. Gross/per-capita/avoided correctly lack schema 1.2 values |
| GHG | COMPONENTS WORKING; UI NULL-SAFE | All five frozen components exist. Missing Jan-Aug remain null. Scope 1 frontend subtotal requires all components; missing comparison-year data now renders safely |
| Energy | PUBLIC FIELD MISSING | Totals and grid emissions are published; source breakdown fields are admin-only; renewable methodology remains unresolved |
| LPG | WORKING IN PAYLOAD | 2 L and 0.003114 tCO2e use frozen governed factor 1.5571, not legacy CSV factors |
| Water | PARTIAL | Total consumed/recycled published; source and wastewater fields are not public |
| Waste | WORKING IN PAYLOAD | Wet/dry/total, category totals, and materials are frozen; no CO2e calculation. “Landfill diversion” semantics are unsupported |
| Outreach | WORKING IN PAYLOAD | Monthly governed aggregate exists for September; legacy annual/YTD data is not loaded |
| Data Explorer | LIMITED CONTRACT | Can show only published aggregate fields; detailed source fields await contract change |
| Green Cover | STATIC REFERENCE | Genuine inventory-style values display; no governed sequestration |
| Carbon Story | METHODOLOGY DEFECT | Contains unsupported avoided/net/equivalence narrative; must not present unavailable indicators as settled |
| History/trends | INSUFFICIENT PUBLISHED HISTORY | Exactly one published month. Jan-Aug must remain gaps, not zeros |
| About | PRESENTATION ONLY | Definitions should use “Operational GHG Emissions — Scope 1 + Scope 2” when indicator is adopted |

The live browser also exposed a secondary null-safety defect: after API failure, chart code dereferenced missing year datasets. This was repaired and covered by regression tests; empty/error state rendering no longer throws.

## AC. Publication schema change required?

**YES**, for any of the following: detailed Energy/Water public aggregates, governed population, backend Scope 1/Operational Gross indicators, or per-capita. The next version should be `1.3`, preserving 1.0/1.1/1.2 readers and never rewriting v1.

Schema 1.3 should only be activated by a newly prepared Admin release after explicit contract approval. Code readiness must not auto-publish it.

## Proposed historical storage contract (future import task)

Do not coerce annual/YTD evidence into monthly `Submission` rows. Add an explicit historical observation model with:

- domain and metric/material code;
- `period_year`, optional `period_month`;
- `granularity` enum: MONTHLY, ANNUAL, YTD, STATIC, UNKNOWN;
- `coverage_start`, `coverage_end`;
- numeric value, unit, and optional qualifier (`+`, approximate);
- source file, source column/row, checksum, source reference;
- validation status and notes.

Monthly facts may later be transformed into governed historical submissions only after source conflicts are resolved. Annual/YTD/static facts remain historical observations.

## AD-AH. Change and safety ledger

- Files changed/created:
  - `CALCULATION_CONTRACT_REPORT.md` (created).
  - `apps/public-dashboard-final-staging/app.js` (null-safe comparisons/charts and exact-month gating for scalar release blocks).
  - `apps/public-dashboard-final-staging/public-data-loader.js` (tracks the exact published months).
  - `apps/public-dashboard-final-staging/index.html` (cache-version bumps for the repaired loader/app).
  - `apps/public-dashboard-final-staging/tests/public-api-contract.test.js` (regression coverage).
  - `recovery-backups/microcosm_clean_20260922_pre_historical_audit_20260924-123527.dump` (validated safety backup; ignored recovery artifact).
- Frontend staging remains served through the established port 3001 same-origin proxy. A temporary verification CORS allowlist entry for port 3011 was not required application behavior and has been reverted; the existing 3000/3001 behavior is unchanged.
- Active clean database/application schema changes: none.
- Test-only databases: `microcosm_test_historical_audit_20260924`, `microcosm_test_finalize_20260924`, and the final fresh isolated `microcosm_test_finalize_fresh_20260924`; all are separate from the clean September database and were retained without destructive cleanup. The final full-suite run used the fresh database.
- Existing September release mutated: **NO**.
- Historical data imported: **NO**.
- Destructive Docker/database operations: none.

Test results:

- Backend Pytest on fresh isolated PostgreSQL database `microcosm_test_finalize_fresh_20260924`: **110 passed**, 1 dependency deprecation warning.
- Public staging contracts: **24 passed**.
- Manager/Admin contracts: **30 passed**.
- JavaScript syntax: staging **9 files passed**; Manager/Admin **23 files passed**.
- Ruff: **passed**.
- Mypy: **passed, 56 source files**.
- Live September acceptance: September v1 loads with exact API values; August reports `No published operational release`; no browser console errors.
- Test-count reconciliation: the earlier 109-test run used a stale API test image that lacked `test_release_listing_is_admin_only_metadata`. That exact test was added in commit `6a0ffdc` alongside the Admin release-listing behavior. The current repository collects 110 tests; a freshly built test image from current source ran all **110 passed**.
- Final syntax pass after cleanup: 23 Manager/Admin JavaScript files and 9 public-staging JavaScript files passed `node --check`.

## AI-AJ. Readiness

- Ready for historical import implementation: **NO**. Energy source conflicts, Water reconciliation, Outreach qualifiers/cutoff, Waste YTD cutoff, and population effective-date/source require owner/source validation first.
- Ready for Dockerization after historical import: **NO**. Historical contract approval/import verification must occur first. Current containerized development stack itself remains healthy.

## AK. Open methodology decisions requiring project-owner approval

1. Identify the authoritative Energy source for conflicting 2025/2026 HT, Commercial, and Temporary values.
2. Confirm whether `renewable_on_campus_kwh` is exclusively Solar PV or a broader on-campus renewable total.
3. Document whether the repeated 62,500 kWh Solar Water Heater value is a valid monthly energy equivalent and its source methodology.
4. Confirm that procured renewable is mutually exclusive from `grid_total_kwh` before enabling renewable share.
5. Approve or reject the Estimated Grid Emissions Avoided method and eligible renewable components.
6. Approve Energy and Water source metrics as public institutional aggregates for schema 1.3.
7. Provide population 6991’s effective date/range and source reference.
8. Reconcile 2025 Water monthly total (39,835 KL) with annual TWAD+Borewell total (195,708 KL), and confirm “procured” = backend Private supply.
9. Confirm the 2026 YTD cutoff dates for Waste and Outreach.
10. Decide whether qualified Outreach values such as `20+` should be stored as lower bounds plus qualifier or display text only.
11. Provide Green Cover measurement date/source/methodology; approve removal or explicit illustrative labelling of all equivalence constants.
12. Confirm that dry waste is not automatically “landfill diversion”; supply disposition evidence if that KPI is required.
13. Approve the backend Operational Gross boundary and wording: “Operational GHG Emissions — Scope 1 + Scope 2.”
