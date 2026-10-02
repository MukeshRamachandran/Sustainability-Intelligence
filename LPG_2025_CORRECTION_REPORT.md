# LPG 2025 Correction Report

Database: `microcosm_clean_20260922`. Applied 2026-09-30, after the same run
passed on the isolated copy `microcosm_lpg_kg_test_20260930_121635`.

## Owner-approved resolution

Entry `lpg-2025-source-values-are-kg` in
`services/main-api/app/historical/mappings/resolutions.json` → `unit_corrections`:

> Project owner confirmed on 2026-09-30 that historical LPG source activity
> values are kilograms. The previous litre normalization was incorrect. Numeric
> source values are preserved unchanged; only metric/unit interpretation is
> corrected to lpg_weight_kg / kg.

It is recorded in the database as 12 `history.conflicts` rows of type
`unit_reinterpretation`, status RESOLVED, with the approval in
`resolution_reason`. Each row links the v1 batch (value A) to the v2 batch
(value B).

## Source and batches

| | Batch | Batch id | Mapping | SHA-256 | Raw rows |
|---|---|---|---|---|---|
| Original (litre interpretation) | `lpg_staging v1` | `00402b04-cd8d-4931-b6a6-19dcd7ab7140` | v1: `consumption_litre` → `lpg_consumption_litres` / L | `5c7aedb0f10622a831064b61ae50163d92c421b93baf7b3b04b823bb0935efcb` | 16 |
| Correction (kg interpretation) | `lpg_staging v2` | `20a7df85-1c32-4b16-bd9f-11c12c62b748` | v2: `consumption_litre` → `lpg_weight_kg` / kg | **same** `5c7aedb0…efcb` | 16 |

Source file: `apps/public-dashboard-final-staging/data/lpg_master.csv`.

The working copy had an uncommitted edit that renamed the header to
`consumption_kg`. That changed the file hash, so the importer would have
recorded the correction as if the source had changed. The file was restored to
the committed bytes that v1 imported. The edited copy was kept outside the
repository (session scratchpad, `lpg_master.working-copy-before-restore.csv`).
The importer now refuses any reinterpretation whose file bytes differ from the
batch it reinterprets.

## Rows corrected: 12

| Month | Old (v1, superseded) | New (v2, authoritative) | Numeric value changed? |
|---|---|---|---|
| Jan 2025 | 8,778 L | 8,778 kg | No |
| Feb 2025 | 8,816 L | 8,816 kg | No |
| Mar 2025 | 8,322 L | 8,322 kg | No |
| Apr 2025 | 6,897 L | 6,897 kg | No |
| May 2025 | 8,930 L | 8,930 kg | No |
| Jun 2025 | 8,854 L | 8,854 kg | No |
| Jul 2025 | 9,006 L | 9,006 kg | No |
| Aug 2025 | 7,942 L | 7,942 kg | No |
| Sep 2025 | 8,417 L | 8,417 kg | No |
| Oct 2025 | 9,595 L | 9,595 kg | No |
| Nov 2025 | 7,429 L | 7,429 kg | No |
| Dec 2025 | 9,101 L | 9,101 kg | No |
| **2025 Full Year** | 102,087 L | **102,087 kg** | No |

Each v2 row has `version = 2` and a `supersedes_id` pointing at the v1 row.
The v1 rows are still present, unchanged (the table is append-only and
enforced by trigger). They are no longer authoritative, because
`current_authoritative_values` and the public resolver exclude any superseded
row. No history row was updated or deleted.

## Recalculated emissions (2.98 kgCO2e/kg, `kcosmos-factors-2025-v2-lpg-kg`)

The old litre-era results are retained with `is_current = false`.

| Month | LPG t (old, 1.5571/L) | **LPG t (kg)** | Scope 1 old | **Scope 1** | Op. GHG old | **Op. GHG** | Per capita old | **Per capita** |
|---|---|---|---|---|---|---|---|---|
| Jan | 13.668224 | **26.158440** | 46.094192 | **58.584408** | unavailable | unavailable | — | — |
| Feb | 13.727394 | **26.271680** | 37.973759 | **50.518045** | 180.013565 | **192.557851** | 25.749330 | **27.543678** |
| Mar | 12.958186 | **24.799560** | 39.355328 | **51.196702** | 230.204460 | **242.045834** | 32.928688 | **34.622491** |
| Apr | 10.739319 | **20.553060** | 30.369100 | **40.182841** | 132.302497 | **142.116238** | 18.924688 | **20.328456** |
| May | 13.904903 | **26.611400** | 36.734380 | **49.440877** | 38.422474 | **51.128971** | 5.495991 | **7.313542** |
| Jun | 13.786563 | **26.384920** | 42.150883 | **54.749240** | unavailable | unavailable | — | — |
| Jul | 14.023243 | **26.837880** | 40.826135 | **53.640772** | 46.271365 | **59.086002** | 6.618705 | **8.451724** |
| Aug | 12.366488 | **23.667160** | 44.335789 | **55.636461** | unavailable | unavailable | — | — |
| Sep | 13.106111 | **25.082660** | 46.976579 | **58.953128** | unavailable | unavailable | — | — |
| Oct | 14.940374 | **28.593100** | 67.047344 | **80.700070** | 123.974352 | **137.627078** | 17.733422 | **19.686322** |
| Nov | 11.567696 | **22.138420** | 56.906947 | **67.477671** | 134.879151 | **145.449875** | 19.293256 | **20.805303** |
| Dec | 14.171167 | **27.120980** | 59.299534 | **72.249347** | 94.314762 | **107.264575** | 13.490883 | **15.343238** |

Per capita is in kgCO2e/person, with population 6,991 for 2025.

2025 Full Year (sums of monthly results): LPG **102,087 kg → 304.21926 tCO2e**
(was 158.959668), and Scope 1 **693.329562 tCO2e** (complete, 12 months).
Operational GHG is shown only where Scope 2 exists (8 of 12 months). The
official Full Year Operational GHG is therefore not presented as complete, and
Full Year per capita stays unavailable.

Operational GHG and per capita remain **unavailable** for Jan, Jun, Aug and
Sep 2025, because Scope 2 (grid) is incomplete in those months. Fixing LPG
does not manufacture a complete GHG figure.

## Idempotency

A second `--commit` run inserted 0 batches, 0 values, 0 conflicts and 0
calculations (33 values and 240 calculations unchanged).

## Commands

```
python -m app.historical.importer --source-root <repo> --dry-run --only lpg_staging --only lpg_2026_owner_source
python -m app.historical.importer --source-root <repo> --commit  --only lpg_staging --only lpg_2026_owner_source
```

`--only` was used because other mapped sources have uncommitted working-copy
edits (for example `population_master.csv`), and those must not be imported
as part of this LPG-only change.
