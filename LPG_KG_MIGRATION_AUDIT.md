# LPG kg Migration — Pre-change Audit

Audit date: 2026-09-30. All facts below were read from the live system
(`microcosm_clean_20260922`) and the repository **before** any change was made.

## Starting point

| Item | Value |
|---|---|
| Branch | `production-fix-2026-09-27` |
| Commit | `c94d10bc04606a7b09386c8f9db2389d81b39649` |
| Docker | Running; `api` and `postgres` healthy; `/health/ready` = ready / ready / ready |
| API database | `microcosm_clean_20260922` |
| Alembic head (repo and live DB) | `0012_environment_readings` |
| Pre-change backup | `services/main-api/recovery-backups/microcosm_clean_20260922_pre_lpg_kg_20260930-121635.dump` (281,386 bytes, 256 TOC entries, SHA-256 `775826795a018b36c3e47a917d9d47e9a606b197eca7418551f7c261e354205f`) |
| Isolated test database | `microcosm_lpg_kg_test_20260930_121635` (restored from that backup) |

## What exists

### Metric catalog (`sustainability.metric_definitions`, domain `lpg`)

| Code | Display name | Class | Unit | Required | Public | Factor |
|---|---|---|---|---|---|---|
| `lpg_consumption_litres` | LPG consumption (litres) | scope1_inventory | L | yes | public_aggregate | `LPG` |
| `lpg_weight_kg` | LPG weight (kg, reference only) | activity_only | kg | no | admin_only | — |
| `lpg_cylinder_count` | LPG cylinders | activity_only | count | **yes** | admin_only | — |

The Manager UI labels the cylinder count "optional, reference" while the
backend requires it — an existing inconsistency.

Migration history: `0007_lpg_kg_governance` made kg authoritative, then
`0008_lpg_litre_governance` reversed that to litres. Both remain in history.

### Factor governance

One factor set exists: `existing-project-draft-v1`
(`20000000-0000-0000-0000-000000000001`), status **active**, effective
2025-01-01. Its factors: `PETROL` 2.388 kgCO2e/L, `DIESEL` 2.701 kgCO2e/L,
`GRID_ELECTRICITY` 0.727 kgCO2e/kWh, `LPG` **1.5571 kgCO2e/L**.

* ACTIVE sets are immutable through the API (`PUT` returns 409).
* Only one ACTIVE set may exist per `effective_from` (unique index).
* `FactorCode` enum: `PETROL`, `DIESEL`, `GRID_ELECTRICITY`, `LPG`; `LPG` is
  validated as litres (`EXPECTED_UNITS[LPG] = "L"`).
* Referenced by 5 frozen submission calculations (Sep 2026 TEST data) and 93
  historical calculation results.

### Historical LPG (2025)

* Source: `apps/public-dashboard-final-staging/data/lpg_master.csv`, header
  `year,month,consumption_litre`, Jan–Dec 2025.
* Batch `lpg_staging v1` (`00402b04-cd8d-4931-b6a6-19dcd7ab7140`), SHA-256
  `5c7aedb0f10622a831064b61ae50163d92c421b93baf7b3b04b823bb0935efcb`,
  status VERIFIED, mapping `lpg_staging` version 1.
* 12 metric values, all `lpg_consumption_litres` / `L`, VERIFIED /
  AUTHORITATIVE, version 1: Jan 8,778 · Feb 8,816 · Mar 8,322 · Apr 6,897 ·
  May 8,930 · Jun 8,854 · Jul 9,006 · Aug 7,942 · Sep 8,417 · Oct 9,595 ·
  Nov 7,429 · Dec 9,101 (total 102,087).
* 12 current `lpg_emissions` calculations use `LPG` 1.5571 kgCO2e/L (for
  example Jan 2025 = 13.668224 tCO2e), and these feed Scope 1, Operational GHG
  and per capita for every 2025 month.
* No 2026 LPG exists in history.

### Working-tree state of the LPG source

The working copy of `lpg_master.csv` had an **uncommitted** edit: the header
was renamed `consumption_litre` → `consumption_kg` and a blank line was added.
That changes the file hash (`6fd59552…`) away from the imported evidence
(`5c7aedb0…`). The importer would refuse to run under v1, and under a new
version it would falsely record the source file as changed. Since only the
interpretation changed, the source bytes must stay as imported.

### Current / future workflow

* Manager (`apps/manager-admin/lpg-entry.html`): litres required; kg and
  cylinders are optional reference inputs. There is no cylinder×size
  derivation anywhere (browser or backend).
* Submission calculator (`app/services/emission_factors.py`):
  `lpg_consumption_litres → lpg_emissions` against factor `LPG` (L).
* Historical calculator (`app/historical/calculator.py`):
  `("lpg_emissions", "lpg_consumption_litres", "LPG")`. It does not check
  whether the activity unit matches the factor unit.
* Publication (`app/services/publication.py`): schema `1.4`; the LPG block
  publishes every `public_aggregate` LPG metric (the litres one).
* Public dashboard (`public-data-loader.js`): `lpgL: 'lpg_consumption_litres'`,
  "LPG consumption … L" card, and the Data Explorer export row uses `'L'`.

### Releases (must remain immutable)

| Version | Schema | Status | Classification | SHA-256 |
|---|---|---|---|---|
| sustainability-2026-09-v1 | 1.2 | superseded | test / hidden | `f6f996ec…ba02` |
| sustainability-2026-09-v2 | 1.3 | superseded | test / hidden | `aeb997c1…7581` |
| sustainability-2026-09-v3 | 1.4 | active | test / hidden | `0061b4d1…aec2` |

### Public default period

`build_timeline` sets `default_key` to the latest month with **any** data. It
is Jun 2026 today (energy + water). Importing Jul 2026 LPG alone would move it
to Jul 2026, which is not an institution-wide reporting month.

## What is wrong

1. 2025 LPG numbers are kilograms but are stored as `lpg_consumption_litres` / L.
2. 2025 LPG emissions (and therefore Scope 1, Operational GHG and per capita)
   were calculated with a litre factor (1.5571 kgCO2e/L) against kg values.
3. Active metric, factor, Manager, publication and dashboard code all treat
   litres as the governed LPG activity.
4. Nothing stops a kg value being multiplied by an L factor in history.
5. The default-period rule would promote a single-domain month.

## What must change

* A new forward migration (`0013`): `lpg_weight_kg` becomes the governed,
  required, public Scope-1 activity with factor code `LPG_KG`; litres is
  deprecated (inactive, admin-only, no factor); cylinder count becomes optional.
* A new governed factor identity `LPG_KG` = 2.98 kgCO2e/kg in a **new**
  versioned active factor set. The old set is retired unchanged.
* Historical correction: mapping `lpg_staging` v2 (same source bytes)
  re-normalizes the 12 values as `lpg_weight_kg` / kg. It is linked by
  `supersedes_id` to the litre rows and recorded as an owner-approved
  resolution.
* The 2026 Jan–Jul LPG source is imported through the importer.
* Calculators, publication (schema 1.5), Manager UI and dashboard move to kg.
* The default period ignores months with data from only one domain.

## What must remain immutable

* Migrations `0001`–`0012` (including `0007` and `0008`).
* Factor set `existing-project-draft-v1` and all its factor rows (including
  `LPG` 1.5571 kgCO2e/L). Only its status moves from active to retired.
* Frozen submission calculations and the Sep 2026 v1/v2/v3 TEST release
  payloads and checksums.
* `history.source_rows` and the 12 litre-normalized `history.metric_values`
  rows (append-only; they are superseded, never updated or deleted).
* The imported source bytes of `lpg_master.csv`.
