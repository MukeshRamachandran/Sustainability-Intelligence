# Historical source inventory

Scope: every CSV / JSON / spreadsheet in the repository that could hold institutional sustainability history (searched: `apps/public-dashboard/data/`, `apps/public-dashboard-final-staging/data/`, `apps/manager-admin/data/`, `apps/manager-admin-backup-before-recovery/data/`, `database/`, `docs/`, repository root). No `.xlsx`/`.xls` files exist. `node_modules`, virtual environments, `recovery-backups/` and vendored libraries were excluded.

Legacy dashboard output is **not** treated as authoritative. A file became an import source only through a mapping in `services/main-api/app/historical/mappings/`, and every value it provides is reconciled against the other copies before it can become authoritative.

SHA-256 values are full hashes of the files as committed at `db0eef0`. They are the same hashes recorded on `history.import_batches`.

## Imported sources (12 batches)

| Mapping (batch) | File | SHA-256 | Domain | Coverage / granularity | Role |
|---|---|---|---|---|---|
| `energy_staging` | `apps/public-dashboard-final-staging/data/energy_master.csv` | `088c6912885a6f7a…` | Energy | Jan 2025 – Jun 2026, MONTHLY (HT, Commercial, Temporary, On-campus RE, Procured RE, Solar water heater) | Primary energy copy |
| `energy_legacy_public` | `apps/public-dashboard/data/energy_master.csv` | `ddc42bc6c0c72df1…` | Energy | Jan 2025 – Jun 2026, MONTHLY (year header rows; printed totals) | Competing copy; differs in 2025 |
| `energy_manager_electricity` | `apps/manager-admin/data/electricity_master.csv` | `cc114a489922f4d4…` | Energy | Jan 2025 – Apr 2026, MONTHLY (HT/Commercial/Temporary only) | Competing copy; differs in 2025 and 2026 |
| `renewable_manager_period_totals` | `apps/manager-admin/data/renewable_master.csv` | `338e074561d83a6c…` | Energy | 2025 ANNUAL, 2026 YTD Jan–Apr period totals | Self-described placeholder; rejected by its own note |
| `transport_staging` | `apps/public-dashboard-final-staging/data/transport_master.csv` | `1ee6d682e8ee47c7…` | Transport | Jan 2025 – Apr 2026, MONTHLY (fleet diesel, petrol) | Primary |
| `dg_staging` | `apps/public-dashboard-final-staging/data/dg_master.csv` | `f451c1f5f5874989…` | Transport (DG) | Jan 2025 – Apr 2026, MONTHLY | Primary |
| `dg_manager` | `apps/manager-admin/data/dg_master.csv` | `83a81f8443ada91d…` | Transport (DG) | Jan 2025 – Apr 2026, MONTHLY | Competing copy (rounding difference only) |
| `lpg_staging` | `apps/public-dashboard-final-staging/data/lpg_master.csv` | `5c7aedb0f10622a8…` | LPG | Jan – Dec 2025, MONTHLY; **no 2026 rows** | Primary |
| `water_staging` | `apps/public-dashboard-final-staging/data/water_master.csv` | `525a8a4bfaca7cfe…` | Water | 2025: monthly consumption column + ANNUAL TWAD/Borewell/Total + ANNUAL recycled; 2026: Jan–Jun MONTHLY TWAD/Borewell/Procured + YTD recycled | Primary |
| `waste_staging` | `apps/public-dashboard-final-staging/data/waste_master.csv` | `c3e743f4de389231…` | Waste | 2025 ANNUAL (19 materials, wet, dry, total); 2026 column (coverage end not stated) | Primary |
| `outreach_staging` | `apps/public-dashboard-final-staging/data/outreach_master.csv` | `17b492c5fd36630c…` | Outreach | 2025 ANNUAL; 2026 column (coverage end not stated); aggregates only, values such as `20+` | Primary |
| `population_staging` | `apps/public-dashboard-final-staging/data/population_master.csv` | `4e773d1f5527932c…` | Population | `2025, 6991` | Primary |

## Candidate files not imported

| File | SHA-256 | Reason |
|---|---|---|
| `apps/public-dashboard/data/{transport,dg,lpg,water,waste,outreach}_master.csv` | various | Parsed values identical to the imported staging copies (byte differences are line endings/formatting only). Recorded as corroborating duplicates, not imported twice. |
| `apps/manager-admin/data/transport_master.csv` | `acd5ac32bf639c35…` | Long-format copy; every value identical to `transport_staging`. |
| `apps/manager-admin-backup-before-recovery/data/*` | same as `manager-admin/data` except `emission_factors.csv` | Byte-identical backup of the Manager prototype data. |
| `*/data/emission_factors.csv` (4 copies) | `5f34ae7a…`, `5f305af3…`, `7c837766…`, `31f968b6…` | **Not a factor authority.** Copies disagree (grid 0.71 vs 0.727; LPG 2.939 vs 1.5571). Historical emissions use the governed factor sets in `sustainability.emission_factor_sets`. |
| `*/data/dashboard_master.json` | `946c002f…`, `2aeb4fd3…`, `9802b327…` | Prototype overlays. The Manager copy contains synthetic June 2026 records ("Industrial 1250", "Vehicle_Count 16"). Never imported. |
| `*/data/dashboard_metadata.csv` | `91537db9…`, `d26f7e6d…` | Presentation labels only (`2025 annual`, `2026 ytd`); used as evidence that the 2026 columns are year-to-date, not as data. |
| `*/data/green_master.csv` | `2206a110…` (staging), `e1395bb2…` (legacy) | Static Green Cover reference (70% cover, 56/50 acres, 2703 trees, 54 species, 7 zones). Kept as the dashboard's static asset per the owner's decision; not historical period data. |
| `.claude/settings.local.json`, `services/*/.venv/**`, `services/aeron-api/api_response.json` | — | Tooling / unrelated. |

## Duplicate relationships

- The staging and legacy-public copies are identical for transport, DG, LPG, water, waste and outreach. They differ only for energy in 2025 (Jan, Jun, Aug, Sep).
- The legacy-public 2025 energy values equal the Manager `electricity_master.csv` values, so there are two copies against one. The 2026 legacy-public values equal the staging values.
- The Manager 2026 electricity values (Jan–Apr) differ from both other copies and look like round-number estimates (Commercial 3100/3042/3200/3185, Temporary 0).
- The Manager `dg_master.csv` equals the staging copy except Apr 2026 (2136.8 vs 2136.83).

## Suspected authority

The final-staging exports are the most complete and most recent (energy and water run to June 2026). They are treated as the primary copy (`priority 1`). **Priority never overrides a disagreement.** Wherever copies disagree, no value is published until the owner resolves it (see `HISTORICAL_RECONCILIATION_REPORT.md`).
