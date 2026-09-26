# Historical reconciliation report

The importer reconciles every source copy before anything is stored (rules R0–R5, see `HISTORICAL_DATA_ARCHITECTURE.md`). Only RESOLVED or uncontested values become AUTHORITATIVE. Contested values are stored with full provenance and status `CONFLICT`, and are **not published**. Nothing was chosen silently.

State in `microcosm_clean_20260922`: **27 conflicts**.
- 23 UNRESOLVED.
- 1 RESOLVED by rule R1 (rounding only).
- 1 RESOLVED by owner approval (2025 annual water total).
- 2 REJECTED_SOURCE (the source declares itself superseded).

Batch abbreviations: **S** = `energy_staging` (final-staging copy), **L** = `energy_legacy_public` (older public copy), **M** = `energy_manager_electricity` (Manager prototype copy).

## 1. Energy – competing copies (23 conflicts, UNRESOLVED)

| Period | Metric | S (staging) | L (legacy public) | M (manager) | Status |
|---|---|---|---|---|---|
| Jan 2025 | grid_ht_kwh | 165,836 | 155,222 | 155,222 | UNRESOLVED |
| Jan 2025 | grid_commercial_kwh | 774 | 1,023 | 1,023 | UNRESOLVED |
| Jun 2025 | grid_commercial_kwh | 983 | 1,023 | 1,023 | UNRESOLVED |
| Jun 2025 | grid_temporary_kwh | 248 | 0 | 0 | UNRESOLVED |
| Aug 2025 | grid_ht_kwh | 1,347 | 424,410 | 424,410 | UNRESOLVED |
| Sep 2025 | grid_ht_kwh | 22,965 | 450,216 | 450,216 | UNRESOLVED |
| Jan 2026 | grid_commercial_kwh | 905 | (= S) | 3,100 | UNRESOLVED |
| Jan 2026 | grid_temporary_kwh | 329 | (= S) | 0 | UNRESOLVED |
| Feb 2026 | grid_ht_kwh / commercial / temporary | 51,465 / 1,002 / 300 | (= S) | 49,822 / 3,042 / 0 | UNRESOLVED |
| Mar 2026 | grid_ht_kwh / commercial / temporary | 52,295 / 1,274 / 296 | (= S) | 53,200 / 3,200 / 0 | UNRESOLVED |
| Apr 2026 | grid_ht_kwh / commercial / temporary | 47,362 / 1,150 / 236 | (= S) | 52,065 / 3,185 / 0 | UNRESOLVED |

(Each row is stored as one conflict per disagreeing pair: 12 for 2025, where S disagrees with both L and M, and 11 for 2026, 23 in total.)

**Effect:** grid total, total electricity, renewable share, Scope 2 and Operational GHG are unavailable for those months. Renewable electricity (on-campus + procured) is uncontested and still published.

**Evidence for the owner (not a decision):**
- 2025: two copies (L, M) agree against S. L's printed "Total Grid Consumption" column equals its own HT + Commercial + Temporary in every month (18/18 checks pass), so L is internally consistent. S's Aug/Sep 2025 HT (1,347 / 22,965) are close to the adjacent months (May 1,321; Jun 690; Jul 5,934; Oct 76,958). L/M's 424,410 / 450,216 would be the two largest HT months of the year; the next highest is Mar at 261,397.
- 2026: S and L agree. M's Jan–Apr 2026 values are round-number estimates (Commercial 3,100 / 3,042 / 3,200 / 3,185; Temporary 0) and M stops at April, matching the older Manager prototype snapshot.

## 2. Water 2025 – annual total vs monthly column (1 conflict, RESOLVED 2026-09-25)

| Period | Metric | Reported | Computed | Status |
|---|---|---|---|---|
| 2025 Full Year | water_consumed_kl | 195,708 (annual "Total Consumption" = TWAD 39,708 + Borewell 156,000) | 39,835 (sum of the monthly "Water Consumption (KL)" column; the column's own printed total is also 39,835) | RESOLVED |

**Resolution (project owner, 2026-09-25):** 195,708 KL is the authoritative 2025 ANNUAL Total Water Usage. It is recorded in `resolutions.json` and applied through the importer: the annual value got a new VERIFIED/AUTHORITATIVE version, and the 12 monthly values got new REJECTED versions. Earlier versions are kept. The annual total is shown in 2025 Full Year and, as labelled "2025 Annual Data" context, in 2025 month views. It is never stored, plotted or summed as a month. 2025 water per person = 195,708 × 1000 / 6,991 = 27,994.28 L/person/year.

**Previous effect (before resolution):** neither 2025 monthly water consumption nor the 2025 annual total was published. Annual TWAD (39,708 KL), Borewell (156,000 KL) and recycled (169,404 KL) are uncontested and published in 2025 Full Year.

**Evidence:**
- The monthly column sums to 39,835, which is within 127 KL of the annual TWAD figure (39,708). That suggests the monthly column may be TWAD only, not total consumption.
- Recycled water of 169,404 KL would exceed a total consumption of 39,835 KL, but is plausible against 195,708 KL.

## 3. Auto-resolved and rejected

| Type | Period | Metric | A | B | Status | Reason |
|---|---|---|---|---|---|---|
| precision_difference | Apr 2026 | dg_diesel_litres | dg_staging 2,136.83 | dg_manager 2,136.8 | RESOLVED | Rule R1: values differ only by rounding; the more precise value is kept. |
| aggregate_vs_monthly | 2025 Full Year | renewable_total_reported_kwh | 3,373,368 (manager period total) | 3,204,283 (sum of monthly on-campus + procured) | REJECTED_SOURCE | The source row says "Period total. Replace with monthly rows when monthly RE data is available." |
| aggregate_vs_monthly | 2026 YTD Jan–Apr | renewable_total_reported_kwh | 324,744 | 1,276,246 | REJECTED_SOURCE | Same self-declared placeholder. |

## 4. Values held back as UNVERIFIED (not conflicts)

| Values | Why |
|---|---|
| 2026 waste (wet 3,000; dry 76,590.6; total 79,590.6; 14 materials) | The column is headed only "2026". The coverage end month is not stated, so it is stored as a *proposed* YTD Jan–Jun and not published. |
| 2026 outreach (20+ programmes, 1,951+ participants, …) | Same: coverage end not stated. The 2026 audience figures (3, 15, 2, …) also look like programme counts rather than reach, against 1,951+ participants. |
| 2026 water recycled (47,256 KL) | Labelled "Total Water Recyled" with no coverage period. |
| Solar water heater (62,500 every month) | The header says "same for all month"; the monthly basis is undocumented. It is a thermal reference only and never electricity. |

## 5. Source-reported vs calculated

Every internal check the sources allow passes (29/29):
- Legacy energy printed totals.
- Water 2026 TWAD + Borewell + Procured = printed total, in all 6 months.
- The water 2025 monthly column equals its printed total.
- Waste materials sum to dry, and wet + dry = total, for 2025 and 2026.

No source reports emissions, so there is nothing to compare against the governed calculations.

## How to resolve a conflict

1. The project owner decides which source is correct, for example by checking the meter bill for Aug 2025 HT.
2. Add an entry to `services/main-api/app/historical/mappings/resolutions.json`:

   ```json
   {"granularity": "MONTHLY", "coverage_start": "2025-08-01", "coverage_end": "2025-08-31",
    "domain": "energy", "metric_code": "grid_ht_kwh", "chosen_mapping_code": "energy_staging",
    "reason": "Checked against the August 2025 TNEB bill", "approved_by": "<name>", "approved_at": "<date>"}
   ```

3. Run the importer with `--dry-run`, review the result, then run it with `--commit`. The chosen value gets a new AUTHORITATIVE version, and the others get REJECTED versions. The previous CONFLICT versions stay in the database via `supersedes_id`. The conflict row records the resolution. Calculations for that month are recalculated, and the replaced results are retired, not deleted.

The same mechanism resolves an aggregate-vs-monthly conflict: selecting the aggregate's source makes the reported total authoritative and rejects the monthly values it contradicts. This is how the 2025 water total was resolved.
