# Historical coverage report

Generated from `microcosm_clean_20260922` after the committed import (current metric-value versions only). Legend:

- **MONTHLY** – genuine month-by-month records.
- **ANNUAL** – one full-year record; never shown as a month.
- **YTD** – one year-to-date record; never divided into months.
- **STATIC** – institutional reference, not period data.
- **CONFLICT** – copies disagree; stored but not published.
- **UNVERIFIED** – stored but not published (coverage or basis not confirmed).
- **MISSING** – no source value exists.

## Genuine coverage cutoff

Official historical data runs **through June 2026**, but only for Energy (renewables and part of grid) and Water. Transport and DG stop in **April 2026**. LPG stops in **December 2025**. No domain has genuine data for July–August 2026. The September 2026 releases v1/v2/v3 are workflow test data (see below), not history.

## Matrix

| Domain | 2025 | 2026 |
|---|---|---|
| Energy – on-campus RE, procured RE | MONTHLY Jan–Dec | MONTHLY Jan–Jun |
| Energy – Grid HT | MONTHLY Feb–Jul, Oct–Dec · CONFLICT Jan, Aug, Sep | MONTHLY Jan, May, Jun · CONFLICT Feb–Apr |
| Energy – Grid Commercial | MONTHLY Feb–May, Jul–Dec · CONFLICT Jan, Jun | MONTHLY May, Jun · CONFLICT Jan–Apr |
| Energy – Grid Temporary | MONTHLY Jan–May, Jul–Dec · CONFLICT Jun | MONTHLY May, Jun · CONFLICT Jan–Apr |
| Energy – grid total / Scope 2 (derived; needs all three connections) | Feb, Mar, Apr, May, Jul, Oct, Nov, Dec (8 months) | May, Jun |
| Energy – solar water heater | UNVERIFIED (same value every month; basis undocumented) | UNVERIFIED |
| Transport – petrol, fleet diesel | MONTHLY Jan–Dec | MONTHLY Jan–Apr |
| Transport – DG diesel | MONTHLY Jan–Dec | MONTHLY Jan–Apr (Apr: precision difference resolved, R1) |
| LPG | MONTHLY Jan–Dec | MISSING |
| Scope 1 (derived; needs petrol, diesel, DG and LPG) | Jan–Dec | MISSING (no 2026 LPG) |
| Operational GHG (Scope 1 + Scope 2) | Feb, Mar, Apr, May, Jul, Oct, Nov, Dec | MISSING |
| Water – consumption total | CONFLICT (monthly column 39,835 KL vs annual total 195,708 KL) | MONTHLY Jan–Jun (TWAD + Borewell + Private) |
| Water – TWAD / Borewell | ANNUAL (39,708 / 156,000 KL) | MONTHLY Jan–Jun |
| Water – Private | MISSING | MONTHLY Jan–Jun (source term "Quantity of Water Procured") |
| Water – recycled | ANNUAL 169,404 KL | YTD 47,256 KL — UNVERIFIED (coverage end not stated) |
| Water – wastewater | MISSING | MISSING |
| Waste – wet / dry / total, 19 materials | ANNUAL (6,577 / 48,762.55 / 55,339.55 kg) | YTD column — UNVERIFIED (coverage end not stated) |
| Outreach – programmes, participants, partners, saplings, experts, volunteers, hours, themes, audience | ANNUAL (reported as "at least", e.g. 20+) | YTD column — UNVERIFIED (coverage end not stated) |
| Population | ANNUAL 6,991 (source row states 2025) | 6,991 (governed owner decision, `institutional_population_references`) |
| Green cover | STATIC reference (unchanged) | STATIC reference (unchanged) |
| Landfill diversion | STATIC 88.1% (single backend constant) | STATIC 88.1% |

## Public periods exposed

- **2025:** Full Year + Jan … Dec (12 genuine months).
- **2026:** YTD · Jan–Jun + Jan … Jun (6 genuine months).
- **Default:** Jun 2026, the latest month with verified official data.
- **Not exposed:** Jul, Aug and Sep 2026. The September 2026 releases v1, v2 and v3 are classified TEST / not public.

## Full Year / YTD semantics

- Additive values are sums of genuine months only, and each carries its coverage. For example, 2025 grid electricity covers 8 of 12 months, and every card and export marks it *partial*.
- Ratios and per-capita values are recomputed from summed inputs, and only when every month in the window is present. 2025 renewable share and operational GHG per capita are therefore unavailable, because grid coverage is incomplete. They are never averaged.
- An ANNUAL or YTD source record is shown only in the matching Full Year / YTD view. A month view shows "Monthly X data unavailable. 2025 annual data is available under 2025 Full Year."
