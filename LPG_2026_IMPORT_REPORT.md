# LPG 2026 Jan–Jul Import Report

Database: `microcosm_clean_20260922`. Applied 2026-09-30, after the same run
passed on the isolated copy `microcosm_lpg_kg_test_20260930_121635`.

## Source

- File: `database/historical-sources/lpg/lpg_2026_jan_jul.csv`. It is kept
  outside any runtime app, and `.gitattributes` `-text` pins its bytes so a
  checkout cannot change the hash.
- SHA-256: `60999d91eba5a846ce5568b49b1f682515882caf75647427d2f24c52fcd608c0`
- Batch: `lpg_2026_owner_source v1`, id `ce8ce837-ef36-478b-b4af-b43d770ab76b`,
  status VERIFIED, 8 raw rows (header + 7 months)
- Mapping: `services/main-api/app/historical/mappings/lpg_2026_owner_source.json`
  (parser `wide_monthly`, `fixed_year` 2026)

All supplied columns are preserved in the raw source rows: MONTH, OPENING
STOCK, PURCHASE, CLOSING STOCK, BRAND, NO OF CYLINDER USED, CYLINDER SIZE KG,
KG, EMISSION FACTOR, EMISSIONS TCO2E. Opening, purchase and closing stock were
supplied for February only, and no brand was supplied. Those cells are blank,
not invented.

| Column | Treatment |
|---|---|
| KG | `lpg_weight_kg` / kg — **governed activity** (VERIFIED, AUTHORITATIVE) |
| NO OF CYLINDER USED | `lpg_cylinder_count` / count — reference only (never authoritative, public or calculated) |
| EMISSIONS TCO2E | `lpg_emissions_source_reported` / tCO2e — reference only; compared with the backend result |
| CYLINDER SIZE KG, EMISSION FACTOR, stock columns, BRAND | kept in the raw source row only |

## Results (backend, Decimal, factor `LPG_KG` 2.98 kgCO2e/kg)

| Month | kg | Backend tCO2e | Source-reported tCO2e | Comparison |
|---|---|---|---|---|
| Jan 2026 | 7,429 | 22.138420 | 22.13842 | match |
| Feb 2026 | 9,082 | 27.064360 | 27.06436 | match |
| Mar 2026 | 769.5 | 2.293110 | 2.29311 | match |
| Apr 2026 | 798 | 2.378040 | 2.37804 | match |
| May 2026 | 782.8 | 2.332744 | 2.332744 | match |
| Jun 2026 | 769.5 | 2.293110 | 2.29311 | match |
| Jul 2026 | 1,453.5 | 4.331430 | 4.33143 | match |
| **Jan–Jul (YTD)** | **21,084.3** | **62.831214** | | complete, 7 months |

Every month is stored as genuine MONTHLY data. No reconciliation conflict was
raised. Had any source-reported figure disagreed, the importer would have
recorded an UNRESOLVED `source_reported_vs_calculated` conflict, and the
backend value would have stayed authoritative.

## February stock discrepancy

Opening 11 + Purchase 489 − Closing 21 = **479**, while the source states
**478** cylinders used and **9,082 kg** (478 × 19). As instructed, KG is
authoritative and was not recomputed from stock. The discrepancy is kept as a
quality note on the Feb 2026 `lpg_weight_kg` value:

> quality note (advisory, not used in any calculation): Feb 2026: cylinders used
> equals opening stock + purchase - closing stock: source states 478, arithmetic
> gives 479

The check is advisory, so it did not block the import. The other advisory
check, KG = cylinders × 19 kg, passes for all seven months.

## Dependent GHG (where the other inputs exist)

| Month | Scope 1 (tCO2e) | Operational GHG |
|---|---|---|
| Jan 2026 | 52.707776 | unavailable (Scope 2 incomplete) |
| Feb 2026 | 56.801670 | unavailable (Scope 2 incomplete) |
| Mar 2026 | 33.968880 | unavailable (Scope 2 incomplete) |
| Apr 2026 | 33.063824 | unavailable (Scope 2 incomplete) |
| May–Jul 2026 | unavailable (no 2026 transport/DG data after April) | unavailable |

No complete GHG figure was fabricated.

## Public default period

The default stays **June 2026**. July 2026 has LPG only, so it is selectable
and queryable (timeline, Data Explorer, GHG page) but is never the default. The
resolver rule is: the latest month reported by at least two operational
domains.

Side effect: because July now has a genuine month, the existing 2026 YTD
window runs Jan–Jul, so energy and water YTD sums state "6 of 7 months".
That comes from the unchanged YTD logic and is accurate.

## Idempotency

A second `--commit` run inserted nothing (0 batches, 0 values, 0 conflicts,
0 calculations).

## Observation for the owner

Jan 2026 (7,429 kg) equals Nov 2025 (7,429 kg) exactly. Both were imported as
supplied. Please confirm this is a genuine coincidence.
