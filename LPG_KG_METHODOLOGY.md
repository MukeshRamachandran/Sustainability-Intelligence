# LPG kg Methodology

Effective: migration `0013_lpg_kg_governance_v2`, applied 2026-09-30.
Decision: project owner, 2026-09-30.

## Rules

- **Active LPG unit is kg.** The governed activity is `lpg_weight_kg`
  ("LPG consumption (kg)"). It is required, Manager-editable, Scope 1 and
  public.
- **The historical 2025 values were mislabeled as litres.** The source column
  `consumption_litre` in `lpg_master.csv` and the earlier normalization
  (`lpg_consumption_litres` / L, `lpg_staging` v1) were wrong about the unit.
  The numbers were always kilograms.
- **Numeric source values were NOT converted.** No density and no litre→kg
  factor was applied anywhere. 8,778 "L" became 8,778 kg.
- **Corrected metric: `lpg_weight_kg`.**
- **Governed factor: `LPG_KG` = 2.98 kgCO2e/kg.** Source: "Existing K-COSMOS
  institutional LPG kg calculation baseline supplied with the historical LPG
  source (project owner, 2026-09-30)". It is not attributed to IPCC, DEFRA or
  the GHG Protocol.
- **Historical provenance is preserved.** Raw source rows and the litre-era
  metric values are append-only and still present. Each corrected value
  supersedes the one it replaces.
- **Old frozen litre-era releases and calculations remain immutable for
  audit.** Factor set `existing-project-draft-v1` (with `LPG` 1.5571 kgCO2e/L)
  is retired, not edited. The Sep 2026 v1/v2/v3 TEST releases are unchanged.
- **The new and future workflow does not use litres.**

## Formula

```
lpg_emissions (tCO2e) = lpg_weight_kg × LPG_KG factor (kgCO2e/kg) ÷ 1000
```

The factor always comes from the governed factor set that applies to the
period. It is never hardcoded in the frontend, the historical calculator,
`publication.py` or the Manager UI. The shared formula
(`sustainability_formulas.activity_emissions_tco2e`) uses `Decimal` and
quantizes to 6 decimal places, exactly as frozen submissions do.

Aggregation: monthly = that month's kg. YTD and Full Year = the sum of genuine
monthly kg. Emission aggregates are sums of monthly results, each calculated
with its own month's factor. LPG is never averaged.

Dependent indicators (formulas unchanged):
- Scope 1 = Petrol + Fleet Diesel + DG Diesel + LPG (all four required).
- Operational GHG = Scope 1 + Scope 2 (both required).
- Per capita = Operational GHG × 1000 / population.
- Avoided grid emissions stay separate and are never subtracted.

## Factor governance

| Factor set | Status | Effective | LPG factor |
|---|---|---|---|
| `existing-project-draft-v1` | **retired** (unchanged) | 2025-01-01 | `LPG` 1.5571 kgCO2e/L (legacy) |
| `kcosmos-factors-2025-v2-lpg-kg` (`20000000-…-0002`) | **active** | 2025-01-01 | `LPG_KG` 2.98 kgCO2e/kg |

Why a new set and a new code:

1. ACTIVE factor sets are immutable. The API refuses edits (409), and adding a
   row would silently change a set that frozen calculations cite.
2. Only one ACTIVE set may hold a given effective date. The corrected 2025
   data needs a kg factor from 2025-01-01, so the old set was retired and the
   new set takes the same date.
3. A distinct code `LPG_KG` makes it impossible to confuse the kg factor with
   the litre factor that frozen calculations reference.

Petrol, Diesel and Grid were copied into the new set unchanged, with the same
values and source references. Their methodology did not change. Because the
set version changed, their historical calculation provenance was re-versioned
(append-only), but the resulting values are identical.

The legacy code `LPG` stays in the enum only so retired sets and frozen results
remain readable. Any new or edited factor set that uses it is rejected (422).
The Admin UI offers only `LPG_KG` (kg) and shows a retired set's `LPG` row
read-only.

A litre activity can never meet a kg factor. The submission calculator
already required matching units. The historical calculator now does too: a
mismatch returns `incompatible_unit`.

## Metric catalog after 0013

| Code | Display | Class | Unit | Required | Active | Public | Factor |
|---|---|---|---|---|---|---|---|
| `lpg_weight_kg` | LPG consumption (kg) | scope1_inventory | kg | yes | yes | public_aggregate | `LPG_KG` |
| `lpg_cylinder_count` | LPG cylinders (reference) | activity_only | count | **no** | yes | admin_only | — |
| `lpg_consumption_litres` | LPG consumption (litres, deprecated – legacy audit only) | activity_only | L | no | **no** | admin_only | — |

The litre metric is not dropped: frozen litre-era submissions and calculations
still reference it. Because it is inactive, both the API and the database
trigger reject any new write to it.

## Manager → Admin → Publish

The workflow itself is unchanged. The LPG entry page collects one required
field, **LPG Consumption (kg)**, plus an optional cylinder count for reference.
There is no cylinder×size derivation in the browser or the backend. The
Manager enters the weighed kg, and that value is frozen as the calculation
input (`activity_metric_code = lpg_weight_kg`, `activity_unit = kg`,
`factor_unit = kgCO2e/kg`).

## Publication

New releases use **schema 1.5**. The LPG block publishes `lpg_weight_kg` (kg)
and the kg-based `lpg_emissions`. It never includes litres or the cylinder
count. A release blocker (`lpg_payload_blockers`) refuses to prepare or
publish any payload that carries the litre metric, a litre activity, or a
non-kg LPG factor. For example, a period whose LPG submission was frozen
against the litre factor must be corrected and resubmitted first.

Already-published releases are never re-validated or rewritten. Schema 1.2,
1.3 and 1.4 payloads stay readable as they were frozen.

## Public dashboard

- The GHG page shows **LPG consumption (kg)** next to **LPG emissions (tCO₂e)**,
  both from backend display items with their true period label.
- The Data Explorer shows `lpg_weight_kg` in kg.
- The browser performs no LPG calculation, and no factor constant exists in
  the active dashboard code.
- The default period is the latest month reported by at least two domains, so
  an LPG-only month (such as July 2026) never becomes the default.
