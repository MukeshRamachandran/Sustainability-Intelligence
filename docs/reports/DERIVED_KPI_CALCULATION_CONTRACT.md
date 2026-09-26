# Derived KPI calculation contract — release schema 1.4

This contract applies to newly prepared monthly releases. Accepted schema 1.3 and older release payloads remain immutable. The existing approved Manager submissions are the only monthly source authority; the existing Admin prepare/publish flow computes and freezes derived indicators. There is no additional Manager input, approval, override, or frontend calculation authority.

| Code / display | Source and exact formula | Unit | Type |
| --- | --- | --- | --- |
| `grid_total_kwh` / Grid electricity | Existing governed `grid_ht_kwh + grid_commercial_kwh + grid_temporary_kwh` | kWh | Existing calculated source metric |
| `renewable_electricity_kwh` / Renewable electricity | `renewable_on_campus_kwh + renewable_procured_kwh` | kWh | Release-derived |
| `total_electricity_consumption_kwh` / Total electricity consumption | `grid_total_kwh + renewable_electricity_kwh` | kWh | Release-derived |
| `renewable_share_pct` / Renewable share | `renewable_electricity_kwh / total_electricity_consumption_kwh * 100` | % | Release-derived |
| `estimated_avoided_grid_emissions_tco2e` / Estimated avoided grid emissions | `renewable_electricity_kwh * applicable governed GRID factor (kgCO2e/kWh) / 1000` | tCO2e | Release-derived, separate from inventory |
| `water_per_capita_l` / Water per person | `water_consumed_kl * 1000 / governed population reference for the reporting year` | L/person | Release-derived |
| `landfill_diversion_pct` / Landfill diversion | Existing institutional legacy reference `88.1` | % | Static reference, not a monthly calculation |

`renewable_procured_kwh` is additional electricity, separate from grid HT/commercial/temporary. `solar_water_heater_kwh` is solar thermal heat-equivalent reference data, **not electricity**. It is excluded from renewable electricity, total electricity, renewable share, and estimated avoided grid emissions. Retain the historical `renewable_total_kwh` field for older release compatibility; it includes solar water heater and is not the authoritative electricity KPI in schema 1.4. The legacy 1.3 indicator keys `avoided_emissions_tco2e` and `renewable_share_percent` remain in 1.4 payloads as unavailable with reasons `superseded_by_estimated_avoided_grid_emissions_tco2e` and `superseded_by_renewable_share_pct`, so no consumer sees a contradictory "methodology under review" value.

Estimated avoided grid emissions must use the GRID factor value and metadata from the same governed calculation provenance as the release's frozen `grid_electricity_emissions` / Scope 2 result. No factor is hardcoded in active calculation code. This estimated avoided indicator is **not subtracted** from Scope 1, Scope 2, or Operational GHG; Operational GHG remains Scope 1 + Scope 2. Waste emissions and green-cover carbon sequestration are outside the current calculation contract and have no KPI.

For each new governed release, an explicit source zero remains zero. An absent, invalid, or unavailable required source, factor provenance, or population reference is not replaced by zero: preparation is blocked. A zero denominator blocks renewable share or per-capita derivation. Older immutable releases may legitimately display unavailable fields without rewriting historical missing data.

Monthly cards show only the selected month's frozen results. For later YTD views, sum genuine monthly grid, renewable electricity, total electricity, and avoided-emissions amounts; calculate YTD renewable share from summed renewable electricity divided by summed total electricity, never by averaging monthly percentages. Calculate YTD water/person from summed monthly water KL times 1000 divided by the applicable governed population, never by averaging monthly per-capita figures. Do not fill missing historical months with zeros.

The frontend reads the published indicators and formats them. It may select and sum additive *published* monthly values for YTD presentation, but it must not reconstruct the authoritative monthly formulas or apply an emission factor. Landfill diversion is a single static dashboard reference shared by Overview and Waste, never `dry_waste / total_waste` and never affected by monthly Waste submissions. Solar water heater is displayed as a thermal reference and explicitly excluded from electricity totals. Historical genuinely unavailable values remain visibly unavailable.

September 2026 verification: grid `34 + 3456 + 45 = 3535` kWh; renewable electricity `45 + 45 = 90` kWh; total electricity `3625` kWh; renewable share `90 / 3625 * 100 = 2.482758620689655...%`; avoided `90 * 0.727 / 1000 = 0.065430` tCO2e using September's governed factor; water/person `380 * 1000 / 6991 = 54.3556000572...` L/person. The `2` kWh-equivalent solar-water-heater reference does not enter these results. Landfill diversion is static `88.1%`.
