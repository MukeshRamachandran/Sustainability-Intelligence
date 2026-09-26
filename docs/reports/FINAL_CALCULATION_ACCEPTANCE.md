# K-COSMOS Final Calculation + Live Acceptance Audit

Audit date: 2026-09-24  
Branch: `feature-waste-domain`  
Audited period: September 2026  
Database: `microcosm_clean_20260922`  
Alembic head: `0010_publication_1_3`  
Active release: `sustainability-2026-09-v2` (schema 1.3)  
Active release checksum: `aeb997c1e420cf62b100ff263e4754e2c38a193dce71f83ce2fd4b10d7267581`

## Authority and integrity

The active `GET /api/public/dashboard` payload, the immutable v2 release, and
its source records are the calculation authority. Read-only health, release,
history, and database checks agreed: v1 remains superseded; v2 remains active;
the September public history resolves to v2; six September domain submissions
are approved; no draft/candidate records are exposed publicly. The clean
database contains no 2025 or 2027 submission rows (reporting periods exist,
but are not imported submissions). No release, submission, database, or
backend state was changed during this audit.

For every active API-backed series, `null` remains unavailable and numeric
zero remains a value. The public adapter distinguishes missing values from
zero; methodology-under-review indicators have a separate reason and display
copy. The active loader does not use operational historical CSVs. The only
CSV references loaded for public operational rendering are `data/dashboard_metadata.csv`
(display labels) and `data/green_master.csv` (static Green Cover reference).

## End-to-end calculation and mapping contract

| KPI / field | Manager/source input | Backend formula / stored value | Frozen publication and public API field | Frontend mapping and unit | Period, missing, and zero semantics | Status |
|---|---|---|---|---|---|---|
| Petrol consumption | `transport_petrol_litres` | Manager-entered litres, frozen on approved Transport submission | `transport.metrics.transport_petrol_litres` | `public-data-loader.js` → `petrolL`; Overview/GHG/Explorer, L | September 2026; null stays unavailable; 0 remains 0 | Pass |
| Petrol emissions | Petrol litres | Backend governed activity × PETROL factor; `activity_x_factor_kgco2e_v1`, factor set `existing-project-draft-v1`, 2.388 kgCO2e/L | `transport.calculations[].calculation_code=transport_petrol_emissions` (activity/factor/formula/result provenance; frozen result 8.221884 tCO2e) | `petrolEm`; GHG and Explorer render the frozen result, tCO2e | No browser factor application; missing result remains unavailable; zero remains zero | Pass |
| Transport diesel emissions | `transport_diesel_litres` | Backend governed activity × DIESEL factor; same formula/factor-set versions, 2.701 kgCO2e/L | `transport_diesel_emissions` calculation (0.332223 tCO2e) | `trDieselEm`; GHG and Explorer, tCO2e | Frozen result only; missing/zero preserved | Pass |
| DG diesel emissions | `dg_diesel_litres` | Backend governed activity × DIESEL factor; same formula/factor-set versions, 2.701 kgCO2e/L | `dg_diesel_emissions` calculation (0.632034 tCO2e) | `dgEm`; GHG and Explorer, tCO2e | Frozen result only; missing/zero preserved | Pass |
| LPG consumption | `lpg_consumption_litres`; `lpg_weight_kg` and `lpg_cylinder_count` are reference-only | Manager-entered litres; weight/cylinder values do not drive emissions | `lpg.metrics.lpg_consumption_litres` | `lpgL`; LPG/GHG/Explorer, L | Zero and missing are distinct | Pass |
| LPG emissions | LPG litres | Backend governed activity × LPG factor; `activity_x_factor_kgco2e_v1`, factor set `existing-project-draft-v1`, 1.5571 kgCO2e/L | `lpg_emissions` calculation (0.003114 tCO2e; API preserves factor/formula/result provenance) | `lpgEm`; LPG/GHG/Explorer, tCO2e | Positive results below 0.01 tCO2e display to six decimals in KPI and Explorer; no kg-based or browser-side emissions calculation | Repaired; contract-tested |
| Scope 1 | Petrol, Transport diesel, DG diesel, LPG frozen results | Backend indicator sums the four governed results; if a required component is unavailable, indicator is unavailable | `indicators.scope1_tco2e` = 9.189255 tCO2e | `scope1Full`; GHG page only (not Overview standalone KPI) | Null is not coerced to zero; live release has all required components | Pass |
| Grid connection inputs | `grid_ht_kwh`, `grid_commercial_kwh`, `grid_temporary_kwh` | Manager-entered source values | `energy.metrics` with the same keys: 34, 3,456, 45 kWh | `htKwh`, `commKwh`, `tempKwh`; Energy page, kWh | Source-level zero remains valid; a missing source is not filled in | Pass |
| Total grid electricity | Three grid connection inputs | Backend: HT + Commercial + Temporary | `energy.metrics.grid_total_kwh` = 3,535 kWh | `elecKwh`; Overview, Energy, GHG, Explorer, kWh | Published monthly value; no unreported months inferred | Pass |
| Renewable source inputs | `renewable_on_campus_kwh`, `renewable_procured_kwh`, `solar_water_heater_kwh` | Manager-entered source values | `energy.metrics` with those exact keys: 45, 45, and 2 kWh | `reOnCampusKwh`, `reProcuredKwh`, `solarWaterHeaterKwh`; Energy page, kWh | Zero remains zero; absent source stays null | Pass |
| Renewable total | Three renewable source inputs | Backend: on-campus + procured + solar-water-heater source values | `energy.metrics.renewable_total_kwh` = 92 kWh | `reKwh`; Overview, Energy, Carbon Story, kWh | September value only; no Jan–Aug values are synthesized | Pass |
| Scope 2 / grid emissions | `grid_total_kwh` | Backend frozen grid calculation; `activity_x_factor_kgco2e_v1`, GRID_ELECTRICITY 0.727 kgCO2e/kWh; 3,535 × factor / 1,000 | `energy.calculations[].calculation_code=grid_electricity_emissions`; `indicators.scope2_tco2e` = 2.569945 tCO2e | `elecEm`; GHG page and Explorer render backend result. Explorer factor is attached to the same published period as its activity/result. | No frontend emissions formula; zero/missing result are distinct | Pass |
| Total electricity consumption | Published grid total and renewable total | No separate approved `total_electricity_consumed` publication field was found; the former UI computed `grid_total_kwh + renewable_total_kwh` (= 3,627 kWh). That frontend sum was removed. | No single frozen combined-total field | Energy KPI stays in place but now reads unavailable; Total Consumption trend chart explains the combined metric is not published. | Do not present the former client-side sum as an authoritative KPI without an explicit contract or backend-published field. | Owner decision required before this KPI can be available |
| Operational GHG | Backend Scope 1 and Scope 2 results | Backend indicator: Scope 1 + Scope 2 | `indicators.operational_ghg_tco2e` = 11.759200 tCO2e | Overview hero and GHG page use the indicator; GHG heading now reads “Operational GHG Emissions — Scope 1 + Scope 2” | Only September is published; Scope 3 is excluded | GHG page title corrected; no Scope 3 claim | Repaired; contract-tested |
| Population | Approved effective-year institutional reference | Stored in `sustainability.institutional_population_references`; 2026 reference is 6,991 people | `population.value` = 6,991; source is the approved 2026 project-owner decision | Loader feeds the backend population reference; no frontend constant | Effective year 2026; missing or non-positive population must leave per-capita unavailable | Pass |
| Operational GHG per capita | Operational GHG and applicable population | Backend indicator: operational tCO2e × 1,000 / approved population | `indicators.operational_ghg_per_capita_kgco2e` ≈ 1.682048 kgCO2e/person | Overview hero, GHG KPI and Carbon Story use published value, kgCO2e/person | September release is a monthly value, not annualized; null population/result stays unavailable | Pass |
| Avoided emissions | No approved calculation input/method yet | `methodology_under_review`; no calculation | `indicators.avoided_emissions_tco2e` unavailable | Overview hero and GHG/Energy placeholders remain unavailable with methodology copy | Unavailable is not zero; no legacy renewable-factor estimate | Pass |
| Renewable share/progress | No approved denominator/contract yet | `methodology_under_review`; no calculation | `indicators.renewable_share_percent` unavailable | Overview/Energy mix and progress remain unavailable with methodology copy | Unavailable is not 0%; old 75.5% / 76:24 visuals are not authority | Pass |
| Water source values | `water_twad_kl`, `water_borewell_kl`, `water_private_kl` | Manager-entered source values | `water.metrics` with those exact keys: 123, 123, 134 KL | `waterTWAD`, `waterBorewell`, `waterProcured` (internal legacy variable name maps from `water_private_kl`); Water cards/charts, KL | Missing source remains missing; a published zero remains a source value and keeps its source category | Source and empty-state text now say “Private water supply”; zero/missing selection is based on field presence, not a positive total | Repaired; contract-tested |
| Total water consumed | Three source values | Backend: TWAD + Borewell + Private | `water.metrics.water_consumed_kl` = 380 KL | `waterKL`; Overview/Water, KL | Published total is preferred; September only; no historical source fallback | Pass |
| Wastewater / recycled water | `wastewater_generated_kl`, `water_recycled_kl` | Manager-entered values | `water.metrics` = 23 KL each | `wastewaterKL`, `waterRecycledKL`; Water/Overview, KL | Zero and null remain distinct | Pass |
| Wet waste | `wet_waste_generated_kg` | Manager-entered value | `waste.metrics.wet_waste_generated_kg` = 0.25 kg | `wetWaste`; Waste page and chart, kg | Missing stays unavailable; zero stays zero | Pass |
| Dry waste | Material item quantities | Backend material sum = 0.09 kg Colour Paper + 0.04 kg Mixed plastics = 0.13 kg | `waste.metrics.dry_waste_generated_kg`, category/material aggregates | `dryWaste`, categories, materials → Waste treemap, kg | Backend aggregates are displayed; no browser-side category/total authority | Pass |
| Total waste generated | Wet and dry waste inputs | Backend wet + dry = 0.25 + 0.13 = 0.38 kg | `waste.metrics.total_waste_generated_kg` = 0.38 kg | `totalWaste`; Overview/Waste, shown as 0.38 kg for this small value | Browser uses the frozen published total only. A missing total stays unavailable even if wet/dry are present; zero stays zero. | Repaired; contract-tested |
| Waste per person | Published waste total and approved population | Backend indicator: total waste kg / applicable population; 0.38 / 6,991 ≈ 0.000054355 kg/person before publication rounding | `indicators.waste_per_capita_kg` = 0.000054 kg/person in the current public payload | `wastePerCapita`; display-only kg-to-g conversion renders 0.054 g/person at three decimals | API null remains unavailable; zero remains zero; small positive values no longer round to 0.00 | Repaired; contract-tested |
| Waste emissions | No approved waste-emissions method | Unavailable | No published waste emissions calculation | No CO2e KPI/calculation should be displayed | Unavailable, not zero | Pass |
| Landfill diversion | Active staging/API has no value/source. Inactive legacy `apps/public-dashboard/data/waste_master.csv` contains annual `Dry waste Generared` and `Total waste Approximate` (kg) rows for 2025/2026. Legacy code maps dry waste to “diverted” and divides it by approximate total. | Legacy proxy is dry waste ÷ approximate total × 100; dry waste has not been verified as actually diverted from landfill | No `landfill_diversion` field in the current release/API | Current staging keeps the existing KPI/story shell and `%` unit, unavailable (“Methodology under review”); decorative video is not a numeric source | Legacy values are annual CSV/reference values, not September monthly release metrics; current staging does not load that CSV | Keep current display unchanged; do not restore the legacy proxy as landfill-diversion authority without owner confirmation of source, scope, and date |
| Outreach | Published Outreach submission/aggregate | Counts and categories are backend aggregate values; no CO2e calculation | `outreach` aggregate: 1 program, 1,065 participants, 1 partner; 34 volunteers, 34 volunteer-hours, 34 experts, 34 saplings; categories: government 34, school 73, college 345, industrial experts 34, farmers 345, researchers/experts 234; biodiversity-conservation theme 1; gender male 34, female 234, other/not disclosed 23 | Outreach KPI/page and charts consume active-release aggregate | September only; no historical annual CSV is loaded. Category totals equal 1,065; available gender values total 291 and are partial, not normalized | Pass with source-coverage caveat |
| Green Cover | Institutional survey/reference CSV | Static reference only; no monthly change, sequestration, or carbon-saved formula | Not part of the September operational release/API | `public-data-loader.js` → `data/green_master.csv`: 70% cover, 56 maintained acres, 50 natural acres, 2,703 trees, 54 species; seven zone records, and tree/species/phenology reference data | Static/institutional reference, not 2026 September monthly activity; no operational missing/zero inference | Pass with static-source/date caveat |

## Page acceptance and initial defects

Live staging at `http://127.0.0.1:3001` was checked after the repairs. The
Overview has eight KPI cards; its published September values settle to 1.682
kgCO2e/person, 11.759 tCO2e operational GHG, 92 kWh renewable, 3,535 kWh
grid, 23 KL recycled water, 0.38 kg waste, 380 KL water, 70% green cover,
and 1,065 outreach participants. The accessible page values were allowed to
finish their count-up animation before comparison; intermediate captures can
show partial values or zero and are not final readings.

Post-repair live page acceptance on the same port:

| Page | Settled values/state observed |
|---|---|
| GHG | Operational 11.76 tCO2e; Scope 1 9.19; Scope 2 2.57; LPG 0.003114; per capita 1.682 kgCO2e/person; reduction/renewable share unavailable with methodology status |
| Energy | Grid total 3,535 kWh; renewable total 92 kWh; source cards 34 / 3,456 / 45 kWh and 45 / 45 / 2 kWh; combined total unavailable and chart states it is not published |
| LPG | No standalone LPG page/section exists in the current public navigation; the governed 2 L and 0.003114 tCO2e values are visible under GHG and Data Explorer. No page was added. |
| Waste | Total 0.38 kg; per person 0.054 g/person; landfill diversion unavailable, not inferred |
| Water | Total 380 KL; TWAD 123, Borewell 123, Private water supply 134 KL; recycled/wastewater 23 KL; per-capita unavailable with methodology status |
| Outreach | 1 program; 1,065 participants; 1 partner; 34 saplings, 34 experts, 34 volunteers and 34 volunteer-hours |
| Green Cover | 70%; 56 maintained acres; 50 natural acres; 54 species |
| Data Explorer | Five September rows; petrol 3,443 L / EF 2.388 / 8.222 tCO2e; fleet diesel 123 L / 2.701 / 0.332; DG diesel 234 L / 2.701 / 0.632; grid 3,535 kWh / 0.727 / 2.570; LPG 2 L / displayed EF 1.557 / 0.003114. API provenance retains the exact LPG factor 1.5571; Explorer formats EF to three decimal places. |
| Carbon Story | All eight metric slides followed the Overview values after animation: 92 kWh, 3,535 kWh, 23 KL, 0.38 kg, landfill unavailable, 380 KL, 70%, and 1,065 people. It states no emissions estimate for renewables and no frontend emissions calculations. |

Charts have one published September point and show the insufficient-history
note rather than inventing Jan–Aug. The dashboard's current-period release
label is `sustainability-2026-09-v2`.

Deterministic findings observed before repair:

1. GHG headline “Gross Organizational Emissions” misstates the backend's
   governed operational Scope 1 + Scope 2 indicator.
2. Positive LPG emissions (0.003114 tCO2e) render as `0.00` in the GHG KPI;
   small positive fossil-mix LPG share similarly renders as `0.0%`.
3. Positive waste/person (~0.000054355 kg/person) renders as `0.00 kg/person`.
4. Water source `water_private_kl` is mapped correctly, but its donut/trend UI
   calls it “Procured”.
5. Missing published total waste is currently replaced by wet + dry values in
   `app.js`; the rendered September release has a published total, so this
   defect is latent but deterministic.
6. `calculations.js` is included by `index.html`; active app use is limited to
   percentage-change display, but the loaded file still exposes legacy CO2e,
   avoided-emissions and renewable-share calculations.
7. The Energy “Total electricity consumption” KPI and Total Consumption trend
   are formed by a browser-side grid + renewable sum. The active release has
   no published combined-total field.
8. “Combined diesel emissions” is a browser-side sum of two published CO2e
   source results, not a frozen publication field.
9. Explorer factors were read from one current-release scalar, which would
   apply the current factor to other months when release history grows.

Repairs now applied: correct Operational GHG heading; precision-preserving LPG
KPI/mix/Explorer display; g/person display conversion; private-water source
labels and zero-aware source presence; published-total-only Waste display;
remove the combined Energy total from the KPI/trend rather than infer it;
replace the calculated diesel subtotal KPI with “Not published”; map EF values
to each history month from that month's public calculation provenance; and
stop loading the legacy calculation engine while retaining its file on disk.

An earlier Chrome console capture showed repeated fetch/CORS errors and
warnings from the separately scoped weather/Aeron widget
(`/api/environment/latest` and `/api/environment/history?limit=500`,
`localhost:8000`, CORS from `127.0.0.1:3001`). A fresh post-repair live
console capture on the staging page returned no errors or warnings. No
public dashboard API, KPI/render, or Chart.js error was observed in that live
pass. Per request, the weather/Aeron integration is not changed here.
Background video “Unable to play media” accessibility messages are media
playback, not JavaScript errors.

## Fix and verification record

`FINAL_CALCULATION_ACCEPTANCE.md` was created from the read-only audit before
frontend semantic changes. Repairs are frontend-only and do not alter the
database, API, release, calculation methodology, CSS/layout, or backend.

- Staging contract tests: 34 passed.
- `node --check`: 7 active local JS files passed (public adapter, loader, app,
  weather, local GSAP ScrollTrigger, walkthrough, mobile).
- `git diff --check`: passed.
- No backend tests or migrations were run because backend code was untouched.
- A fresh in-app staging browser was used for the post-repair live pass after
  the Chrome window proved unavailable. The post-repair console capture was
  empty for errors/warnings. An earlier Chrome capture had weather/Aeron CORS
  failures noted above; this external widget remains out of scope.
- The active `index.html` no longer loads `calculations.js`; the old file is
  retained but dormant. `data-loader.js` is also not loaded. Those dormant
  legacy files still contain default EF constants (2.388, 2.701, 0.727,
  1.5571) and legacy CO2e/renewable calculations; they must remain excluded
  from the production-candidate script graph. Active production-candidate
  scripts contain no such hardcoded factors and no activity × EF emissions
  formula. Active Data Explorer/KPI factors come from the API's per-period
  `factor_value` provenance.
- Port 3001 served the `public-dashboard-final-staging/index.html` script graph
  (verified from the served HTML): it loads `public-data-loader.js` and
  `walkthrough.js`, not `calculations.js` or `data-loader.js`. A separate
  legacy `apps/public-dashboard/index.html` still loads those legacy files;
  its `walkthrough.js` retains tree/home/car-km equivalency factors and its
  loader/app read annual CSVs and derive a dry-waste/total proxy for landfill
  diversion. That sibling was not changed and must not be treated as the
  active 3001 staging implementation or merged into it without a separate
  audit.
- The public API normalization preserves numeric zero separately from null;
  the contract suite now exercises zero, missing, and methodology-unavailable
  values explicitly.
- Database and release integrity were checked read-only: active v2/checksum
  unchanged, six September submissions unchanged, one active plus one
  superseded September release, and zero 2025/2027 submission rows. No
  historical submission rows were imported.

Historical-import and missing-source decisions (the current September
calculation contract can be frozen with explicitly unavailable values):

1. For the current September contract, keep combined electricity unavailable.
   If it must become numeric, publish or formally define a combined-total
   field; do not restore a frontend grid + renewable sum.
2. Preserve the requested Landfill Diversion presentation. The older inactive
   dashboard derives a proxy from annual waste-master CSV dry/approximate-total
   values; that is not proof of landfill diversion. Keep the current metric
   unavailable unless the owner confirms the proxy or supplies a governed
   static source, scope, and date.
3. Before historical import, define YTD aggregation semantics for ratios such
   as operational GHG/person and waste/person. Current generic `month=all`
   display sums monthly metric arrays; summing per-capita ratios is not an
   approved YTD formula. Only September is currently published, so this edge
   is not yet exercised by real history.
4. Define historical period coverage and factor-version treatment, then test
   partial years and month-specific emission factors. Current staging has
   only the September 2026 release; no earlier months are fabricated.
