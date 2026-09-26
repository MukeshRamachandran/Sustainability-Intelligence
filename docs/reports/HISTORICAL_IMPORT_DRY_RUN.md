# Historical import dry run

Dry run of `python -m app.historical.importer --source-root /tmp/kcosmos-sources --dry-run` against `microcosm_clean_20260922` after migration 0011 and before the committed import. The same plan was first rehearsed on the isolated database `microcosm_historical_test_20260924214958`, restored from `services/main-api/recovery-backups/microcosm_clean_20260922_pre_historical_20260924-212316.dump`, with identical results.

After review, the plan was committed, then committed a second time: 0 new batches, 0 new values, 455 unchanged values, 0 new calculations, 225 unchanged calculations.


Dry run: the database was only read. Nothing was inserted, updated or deleted.

## Sources

| Mapping | File | SHA-256 | Rows read | Observations | Already imported |
|---|---|---|---|---|---|
| dg_manager | `apps/manager-admin/data/dg_master.csv` | `83a81f8443ada91d12d9b1a83c64c578ee8e6b8dcaa6a50c5c4e86390fbbed3a` | 17 | 16 | no |
| dg_staging | `apps/public-dashboard-final-staging/data/dg_master.csv` | `f451c1f5f5874989891e466ff3887df4cd6a3222d1538f11e297ea372ac7da4d` | 17 | 16 | no |
| energy_legacy_public | `apps/public-dashboard/data/energy_master.csv` | `ddc42bc6c0c72df1416c814bd4b3ec0712e1ffdca15b98e9141a557b1faa9a17` | 21 | 102 | no |
| energy_manager_electricity | `apps/manager-admin/data/electricity_master.csv` | `cc114a489922f4d47862dd01d9a39c1ac196e58545228641cdec4c4df62b9ae7` | 49 | 48 | no |
| energy_staging | `apps/public-dashboard-final-staging/data/energy_master.csv` | `088c6912885a6f7a8b60c1eb9a163a680d820a003fe42c5e974bf2b524a32967` | 19 | 108 | no |
| lpg_staging | `apps/public-dashboard-final-staging/data/lpg_master.csv` | `5c7aedb0f10622a831064b61ae50163d92c421b93baf7b3b04b823bb0935efcb` | 16 | 12 | no |
| outreach_staging | `apps/public-dashboard-final-staging/data/outreach_master.csv` | `17b492c5fd36630cf4bec863b71936baee873a1d357f6a31e7dba43a5b4b974e` | 36 | 45 | no |
| population_staging | `apps/public-dashboard-final-staging/data/population_master.csv` | `4e773d1f5527932cacd38b585f79e061bf5c2d6f13745e73a2ea8640a94101e7` | 2 | 1 | no |
| renewable_manager_period_totals | `apps/manager-admin/data/renewable_master.csv` | `338e074561d83a6c31e5a8cab1d390c19c7b9ebfb39f2dafb8f912d9d707b39e` | 3 | 2 | no |
| transport_staging | `apps/public-dashboard-final-staging/data/transport_master.csv` | `1ee6d682e8ee47c7d29daeb149b758cb8331ea9b5a58dece546d19015ff770ab` | 18 | 32 | no |
| waste_staging | `apps/public-dashboard-final-staging/data/waste_master.csv` | `c3e743f4de389231afc4f904f8c76c7db0720d89c40d60ef4959a87db906d138` | 29 | 38 | no |
| water_staging | `apps/public-dashboard-final-staging/data/water_master.csv` | `525a8a4bfaca7cfeebca7fb8c3b3b45df490503b00749452878f0b4454f5a0a2` | 30 | 35 | no |

## Periods, granularity and metrics

### dg_manager

- Periods detected (16): MONTHLY Apr 2025, MONTHLY Apr 2026, MONTHLY Aug 2025, MONTHLY Dec 2025, MONTHLY Feb 2025, MONTHLY Feb 2026, MONTHLY Jan 2025, MONTHLY Jan 2026, MONTHLY Jul 2025, MONTHLY Jun 2025, MONTHLY Mar 2025, MONTHLY Mar 2026, MONTHLY May 2025, MONTHLY Nov 2025, MONTHLY Oct 2025, MONTHLY Sep 2025
- Metrics mapped (1): dg_diesel_litres
- Units (no unit conversion applied; source units are canonical units): dg_diesel_litres: L
- Ignored: none
- Invalid rows: none
- Qualifiers: {'EXACT': 16}
- Internal checks: 0/0 passed

### dg_staging

- Periods detected (16): MONTHLY Apr 2025, MONTHLY Apr 2026, MONTHLY Aug 2025, MONTHLY Dec 2025, MONTHLY Feb 2025, MONTHLY Feb 2026, MONTHLY Jan 2025, MONTHLY Jan 2026, MONTHLY Jul 2025, MONTHLY Jun 2025, MONTHLY Mar 2025, MONTHLY Mar 2026, MONTHLY May 2025, MONTHLY Nov 2025, MONTHLY Oct 2025, MONTHLY Sep 2025
- Metrics mapped (1): dg_diesel_litres
- Units (no unit conversion applied; source units are canonical units): dg_diesel_litres: L
- Ignored: none
- Invalid rows: none
- Qualifiers: {'EXACT': 16}
- Internal checks: 0/0 passed

### energy_legacy_public

- Periods detected (18): MONTHLY Apr 2025, MONTHLY Apr 2026, MONTHLY Aug 2025, MONTHLY Dec 2025, MONTHLY Feb 2025, MONTHLY Feb 2026, MONTHLY Jan 2025, MONTHLY Jan 2026, MONTHLY Jul 2025, MONTHLY Jun 2025, MONTHLY Jun 2026, MONTHLY Mar 2025, MONTHLY Mar 2026, MONTHLY May 2025, MONTHLY May 2026, MONTHLY Nov 2025, MONTHLY Oct 2025, MONTHLY Sep 2025
- Metrics mapped (6): grid_commercial_kwh, grid_ht_kwh, grid_temporary_kwh, renewable_on_campus_kwh, renewable_procured_kwh, solar_water_heater_kwh
- Units (no unit conversion applied; source units are canonical units): grid_commercial_kwh: kWh, grid_ht_kwh: kWh, grid_temporary_kwh: kWh, renewable_on_campus_kwh: kWh, renewable_procured_kwh: kWh, solar_water_heater_kwh: kWh
- Ignored: column 4 'Total Grid Consumption' (not mapped); column 7 'Solar Water Heater(same for all month)' (not mapped); column 8 'Total' (not mapped)
- Invalid rows: none
- Qualifiers: {'EXACT': 102}
- Internal checks: 18/18 passed

### energy_manager_electricity

- Periods detected (16): MONTHLY Apr 2025, MONTHLY Apr 2026, MONTHLY Aug 2025, MONTHLY Dec 2025, MONTHLY Feb 2025, MONTHLY Feb 2026, MONTHLY Jan 2025, MONTHLY Jan 2026, MONTHLY Jul 2025, MONTHLY Jun 2025, MONTHLY Mar 2025, MONTHLY Mar 2026, MONTHLY May 2025, MONTHLY Nov 2025, MONTHLY Oct 2025, MONTHLY Sep 2025
- Metrics mapped (3): grid_commercial_kwh, grid_ht_kwh, grid_temporary_kwh
- Units (no unit conversion applied; source units are canonical units): grid_commercial_kwh: kWh, grid_ht_kwh: kWh, grid_temporary_kwh: kWh
- Ignored: none
- Invalid rows: none
- Qualifiers: {'EXACT': 48}
- Internal checks: 0/0 passed

### energy_staging

- Periods detected (18): MONTHLY Apr 2025, MONTHLY Apr 2026, MONTHLY Aug 2025, MONTHLY Dec 2025, MONTHLY Feb 2025, MONTHLY Feb 2026, MONTHLY Jan 2025, MONTHLY Jan 2026, MONTHLY Jul 2025, MONTHLY Jun 2025, MONTHLY Jun 2026, MONTHLY Mar 2025, MONTHLY Mar 2026, MONTHLY May 2025, MONTHLY May 2026, MONTHLY Nov 2025, MONTHLY Oct 2025, MONTHLY Sep 2025
- Metrics mapped (6): grid_commercial_kwh, grid_ht_kwh, grid_temporary_kwh, renewable_on_campus_kwh, renewable_procured_kwh, solar_water_heater_kwh
- Units (no unit conversion applied; source units are canonical units): grid_commercial_kwh: kWh, grid_ht_kwh: kWh, grid_temporary_kwh: kWh, renewable_on_campus_kwh: kWh, renewable_procured_kwh: kWh, solar_water_heater_kwh: kWh
- Ignored: none
- Invalid rows: none
- Qualifiers: {'EXACT': 108}
- Internal checks: 0/0 passed

### lpg_staging

- Periods detected (12): MONTHLY Apr 2025, MONTHLY Aug 2025, MONTHLY Dec 2025, MONTHLY Feb 2025, MONTHLY Jan 2025, MONTHLY Jul 2025, MONTHLY Jun 2025, MONTHLY Mar 2025, MONTHLY May 2025, MONTHLY Nov 2025, MONTHLY Oct 2025, MONTHLY Sep 2025
- Metrics mapped (1): lpg_consumption_litres
- Units (no unit conversion applied; source units are canonical units): lpg_consumption_litres: L
- Ignored: none
- Invalid rows: none
- Qualifiers: {'EXACT': 12}
- Internal checks: 0/0 passed

### outreach_staging

- Periods detected (2): ANNUAL 2025 Full Year, YTD 2026 YTD · Jan–Jun
- Metrics mapped (25): audience:college_students, audience:community_general, audience:entrepreneurs_startup_founders, audience:farmers_agriculture, audience:government, audience:industrial_experts, audience:international_exchange, audience:researchers_experts, audience:school_students, experts_involved, partner_organizations, saplings_planted, theme:afforestation, theme:biodiversity_conservation, theme:campus_sustainability, theme:climate_change, theme:climate_smart_agriculture, theme:hwcc, theme:livelihood_development, theme:waste_management, theme:water_conservation, total_participants, total_programs, volunteer_hours, volunteers_engaged
- Units (no unit conversion applied; source units are canonical units): audience:college_students: people, audience:community_general: people, audience:entrepreneurs_startup_founders: people, audience:farmers_agriculture: people, audience:government: people, audience:industrial_experts: people, audience:international_exchange: people, audience:researchers_experts: people, audience:school_students: people, experts_involved: people, partner_organizations: organizations, saplings_planted: saplings, theme:afforestation: programmes, theme:biodiversity_conservation: programmes, theme:campus_sustainability: programmes, theme:climate_change: programmes, theme:climate_smart_agriculture: programmes, theme:hwcc: programmes, theme:livelihood_development: programmes, theme:waste_management: programmes, theme:water_conservation: programmes, total_participants: people, total_programs: programmes, volunteer_hours: hours, volunteers_engaged: people
- Ignored: none
- Invalid rows: none
- Qualifiers: {'AT_LEAST': 20, 'EXACT': 25}
- Internal checks: 0/0 passed

### population_staging

- Periods detected (1): ANNUAL 2025 Full Year
- Metrics mapped (1): population
- Units (no unit conversion applied; source units are canonical units): population: people
- Ignored: none
- Invalid rows: none
- Qualifiers: {'EXACT': 1}
- Internal checks: 0/0 passed

### renewable_manager_period_totals

- Periods detected (2): ANNUAL 2025 Full Year, YTD 2026 YTD · Jan–Apr
- Metrics mapped (1): renewable_total_reported_kwh
- Units (no unit conversion applied; source units are canonical units): renewable_total_reported_kwh: kWh
- Ignored: none
- Invalid rows: none
- Qualifiers: {'EXACT': 2}
- Internal checks: 0/0 passed

### transport_staging

- Periods detected (16): MONTHLY Apr 2025, MONTHLY Apr 2026, MONTHLY Aug 2025, MONTHLY Dec 2025, MONTHLY Feb 2025, MONTHLY Feb 2026, MONTHLY Jan 2025, MONTHLY Jan 2026, MONTHLY Jul 2025, MONTHLY Jun 2025, MONTHLY Mar 2025, MONTHLY Mar 2026, MONTHLY May 2025, MONTHLY Nov 2025, MONTHLY Oct 2025, MONTHLY Sep 2025
- Metrics mapped (2): transport_diesel_litres, transport_petrol_litres
- Units (no unit conversion applied; source units are canonical units): transport_diesel_litres: L, transport_petrol_litres: L
- Ignored: none
- Invalid rows: none
- Qualifiers: {'EXACT': 32}
- Internal checks: 0/0 passed

### waste_staging

- Periods detected (2): ANNUAL 2025 Full Year, YTD 2026 YTD · Jan–Jun
- Metrics mapped (22): dry_waste_generated_kg, material:ALUMINIUM, material:BLACK_PLASTIC_PP, material:CARDBOARD, material:COCONUT_SHELL, material:COLOUR_PAPER, material:E_WASTE, material:HDPE, material:IRON, material:LDPE, material:LITE_WEIGHT, material:MIXED_PLASTICS, material:NEWS_PAPER, material:PET, material:PP_CARDBOARDS, material:PVC_PIPE, material:STAINLESS_STEEL, material:TYRE, material:UNCLASSIFIED, material:WHITE_PAPER, total_waste_generated_kg, wet_waste_generated_kg
- Units (no unit conversion applied; source units are canonical units): dry_waste_generated_kg: kg, material:ALUMINIUM: kg, material:BLACK_PLASTIC_PP: kg, material:CARDBOARD: kg, material:COCONUT_SHELL: kg, material:COLOUR_PAPER: kg, material:E_WASTE: kg, material:HDPE: kg, material:IRON: kg, material:LDPE: kg, material:LITE_WEIGHT: kg, material:MIXED_PLASTICS: kg, material:NEWS_PAPER: kg, material:PET: kg, material:PP_CARDBOARDS: kg, material:PVC_PIPE: kg, material:STAINLESS_STEEL: kg, material:TYRE: kg, material:UNCLASSIFIED: kg, material:WHITE_PAPER: kg, total_waste_generated_kg: kg, wet_waste_generated_kg: kg
- Ignored: none
- Invalid rows: none
- Qualifiers: {'EXACT': 36, 'APPROXIMATE': 2}
- Internal checks: 4/4 passed

### water_staging

- Periods detected (20): ANNUAL 2025 Full Year, MONTHLY Apr 2025, MONTHLY Apr 2026, MONTHLY Aug 2025, MONTHLY Dec 2025, MONTHLY Feb 2025, MONTHLY Feb 2026, MONTHLY Jan 2025, MONTHLY Jan 2026, MONTHLY Jul 2025, MONTHLY Jun 2025, MONTHLY Jun 2026, MONTHLY Mar 2025, MONTHLY Mar 2026, MONTHLY May 2025, MONTHLY May 2026, MONTHLY Nov 2025, MONTHLY Oct 2025, MONTHLY Sep 2025, YTD 2026 YTD · Jan–Jun
- Metrics mapped (5): water_borewell_kl, water_consumed_kl, water_private_kl, water_recycled_kl, water_twad_kl
- Units (no unit conversion applied; source units are canonical units): water_borewell_kl: KL, water_consumed_kl: KL, water_private_kl: KL, water_recycled_kl: KL, water_twad_kl: KL
- Ignored: none
- Invalid rows: none
- Qualifiers: {'EXACT': 35}
- Internal checks: 7/7 passed

## Reconciliation outcome

| Verification | Authority | Values |
|---|---|---|
| CONFLICT | SOURCE_REPORTED | 64 |
| REJECTED | SOURCE_REPORTED | 2 |
| UNVERIFIED | SOURCE_REPORTED | 71 |
| VERIFIED | AUTHORITATIVE | 198 |
| VERIFIED | SOURCE_REPORTED | 120 |

Precision-only differences auto-resolved (rule R1): 1
- Apr 2026 dg_diesel_litres: 2136.83 vs 2136.8 (R1)

## Conflicts

| Type | Period | Metric | Source A | Value A | Source B | Value B | Status |
|---|---|---|---|---|---|---|---|
| precision_difference | Apr 2026 | transport.dg_diesel_litres | dg_staging | 2136.83 | dg_manager | 2136.8 | RESOLVED |
| source_copies_disagree | Jan 2025 | energy.grid_ht_kwh | energy_staging | 165836 | energy_legacy_public | 155222 | UNRESOLVED |
| source_copies_disagree | Jan 2025 | energy.grid_ht_kwh | energy_staging | 165836 | energy_manager_electricity | 155222 | UNRESOLVED |
| source_copies_disagree | Jan 2025 | energy.grid_commercial_kwh | energy_staging | 774 | energy_legacy_public | 1023 | UNRESOLVED |
| source_copies_disagree | Jan 2025 | energy.grid_commercial_kwh | energy_staging | 774 | energy_manager_electricity | 1023 | UNRESOLVED |
| source_copies_disagree | Jun 2025 | energy.grid_commercial_kwh | energy_staging | 983 | energy_legacy_public | 1023 | UNRESOLVED |
| source_copies_disagree | Jun 2025 | energy.grid_commercial_kwh | energy_staging | 983 | energy_manager_electricity | 1023 | UNRESOLVED |
| source_copies_disagree | Jun 2025 | energy.grid_temporary_kwh | energy_staging | 248 | energy_legacy_public | 0 | UNRESOLVED |
| source_copies_disagree | Jun 2025 | energy.grid_temporary_kwh | energy_staging | 248 | energy_manager_electricity | 0 | UNRESOLVED |
| source_copies_disagree | Aug 2025 | energy.grid_ht_kwh | energy_staging | 1347 | energy_legacy_public | 424410 | UNRESOLVED |
| source_copies_disagree | Aug 2025 | energy.grid_ht_kwh | energy_staging | 1347 | energy_manager_electricity | 424410 | UNRESOLVED |
| source_copies_disagree | Sep 2025 | energy.grid_ht_kwh | energy_staging | 22965 | energy_legacy_public | 450216 | UNRESOLVED |
| source_copies_disagree | Sep 2025 | energy.grid_ht_kwh | energy_staging | 22965 | energy_manager_electricity | 450216 | UNRESOLVED |
| source_copies_disagree | Jan 2026 | energy.grid_commercial_kwh | energy_staging | 905 | energy_manager_electricity | 3100 | UNRESOLVED |
| source_copies_disagree | Jan 2026 | energy.grid_temporary_kwh | energy_staging | 329 | energy_manager_electricity | 0 | UNRESOLVED |
| source_copies_disagree | Feb 2026 | energy.grid_ht_kwh | energy_staging | 51465 | energy_manager_electricity | 49822 | UNRESOLVED |
| source_copies_disagree | Feb 2026 | energy.grid_commercial_kwh | energy_staging | 1002 | energy_manager_electricity | 3042 | UNRESOLVED |
| source_copies_disagree | Feb 2026 | energy.grid_temporary_kwh | energy_staging | 300 | energy_manager_electricity | 0 | UNRESOLVED |
| source_copies_disagree | Mar 2026 | energy.grid_ht_kwh | energy_staging | 52295 | energy_manager_electricity | 53200 | UNRESOLVED |
| source_copies_disagree | Mar 2026 | energy.grid_commercial_kwh | energy_staging | 1274 | energy_manager_electricity | 3200 | UNRESOLVED |
| source_copies_disagree | Mar 2026 | energy.grid_temporary_kwh | energy_staging | 296 | energy_manager_electricity | 0 | UNRESOLVED |
| source_copies_disagree | Apr 2026 | energy.grid_ht_kwh | energy_staging | 47362 | energy_manager_electricity | 52065 | UNRESOLVED |
| source_copies_disagree | Apr 2026 | energy.grid_commercial_kwh | energy_staging | 1150 | energy_manager_electricity | 3185 | UNRESOLVED |
| source_copies_disagree | Apr 2026 | energy.grid_temporary_kwh | energy_staging | 236 | energy_manager_electricity | 0 | UNRESOLVED |
| aggregate_vs_monthly | 2025 Full Year | energy.renewable_total_reported_kwh | renewable_manager_period_totals | 3373368 | (computed) | 3204283 | REJECTED_SOURCE |
| aggregate_vs_monthly | 2026 YTD · Jan–Apr | energy.renewable_total_reported_kwh | renewable_manager_period_totals | 324744 | (computed) | 1276246 | REJECTED_SOURCE |
| aggregate_vs_monthly | 2025 Full Year | water.water_consumed_kl | water_staging | 195708 | (computed) | 39835 | UNRESOLVED |

## Records

- New batches: 12; already imported: 0
- Metric values to insert: 455; new versions: 0; unchanged (skipped): 0
- Conflicts to insert: 27; resolutions to record: 0

## Calculated indicators (preview from authoritative values only)

### 2025 Full Year
- total_waste_generated_kg: 55339.550000
- waste_per_capita_kg: 7.915827
- water_consumed_kl: unavailable (inputs_missing:water_private_kl)

### Jan 2025
- dg_diesel_emissions: 4.290863
- estimated_avoided_grid_emissions_tco2e: 88.612576
- grid_electricity_emissions: unavailable (inputs_missing:grid_total_kwh)
- grid_total_kwh: unavailable (inputs_missing:grid_commercial_kwh,grid_ht_kwh)
- lpg_emissions: 13.668224
- operational_ghg_tco2e: unavailable (inputs_missing:scope2_tco2e)
- renewable_electricity_kwh: 121888.000000
- renewable_share_pct: unavailable (inputs_missing:total_electricity_consumption_kwh)
- scope1_tco2e: 46.094192
- total_electricity_consumption_kwh: unavailable (inputs_missing:grid_total_kwh)
- transport_diesel_emissions: 26.353657
- transport_petrol_emissions: 1.781448

### Feb 2025
- dg_diesel_emissions: 3.563537
- estimated_avoided_grid_emissions_tco2e: 121.784132
- grid_electricity_emissions: 142.039806
- grid_total_kwh: 195378.000000
- lpg_emissions: 13.727394
- operational_ghg_per_capita_kgco2e: 25.749330
- operational_ghg_tco2e: 180.013565
- renewable_electricity_kwh: 167516.000000
- renewable_share_pct: 46.161138
- scope1_tco2e: 37.973759
- scope2_tco2e: 142.039806
- total_electricity_consumption_kwh: 362894.000000
- transport_diesel_emissions: 19.528230
- transport_petrol_emissions: 1.154598

### Mar 2025
- dg_diesel_emissions: 0.740695
- estimated_avoided_grid_emissions_tco2e: 135.366673
- grid_electricity_emissions: 190.849132
- grid_total_kwh: 262516.000000
- lpg_emissions: 12.958186
- operational_ghg_per_capita_kgco2e: 32.928688
- operational_ghg_tco2e: 230.204460
- renewable_electricity_kwh: 186199.000000
- renewable_share_pct: 41.496050
- scope1_tco2e: 39.355328
- scope2_tco2e: 190.849132
- total_electricity_consumption_kwh: 448715.000000
- transport_diesel_emissions: 24.479163
- transport_petrol_emissions: 1.177284

### Apr 2025
- dg_diesel_emissions: 3.440534
- estimated_avoided_grid_emissions_tco2e: 180.479204
- grid_electricity_emissions: 101.933397
- grid_total_kwh: 140211.000000
- lpg_emissions: 10.739319
- operational_ghg_per_capita_kgco2e: 18.924688
- operational_ghg_tco2e: 132.302497
- renewable_electricity_kwh: 248252.000000
- renewable_share_pct: 63.906215
- scope1_tco2e: 30.369100
- scope2_tco2e: 101.933397
- total_electricity_consumption_kwh: 388463.000000
- transport_diesel_emissions: 15.587471
- transport_petrol_emissions: 0.601776

### May 2025
- dg_diesel_emissions: 4.397822
- estimated_avoided_grid_emissions_tco2e: 255.557948
- grid_electricity_emissions: 1.688094
- grid_total_kwh: 2322.000000
- lpg_emissions: 13.904903
- operational_ghg_per_capita_kgco2e: 5.495991
- operational_ghg_tco2e: 38.422474
- renewable_electricity_kwh: 351524.000000
- renewable_share_pct: 99.343782
- scope1_tco2e: 36.734380
- scope2_tco2e: 1.688094
- total_electricity_consumption_kwh: 353846.000000
- transport_diesel_emissions: 17.380935
- transport_petrol_emissions: 1.050720

### Jun 2025
- dg_diesel_emissions: 2.569704
- estimated_avoided_grid_emissions_tco2e: 186.956047
- grid_electricity_emissions: unavailable (inputs_missing:grid_total_kwh)
- grid_total_kwh: unavailable (inputs_missing:grid_commercial_kwh,grid_temporary_kwh)
- lpg_emissions: 13.786563
- operational_ghg_tco2e: unavailable (inputs_missing:scope2_tco2e)
- renewable_electricity_kwh: 257161.000000
- renewable_share_pct: unavailable (inputs_missing:total_electricity_consumption_kwh)
- scope1_tco2e: 42.150883
- total_electricity_consumption_kwh: unavailable (inputs_missing:grid_total_kwh)
- transport_diesel_emissions: 24.805984
- transport_petrol_emissions: 0.988632

### Jul 2025
- dg_diesel_emissions: 0.578473
- estimated_avoided_grid_emissions_tco2e: 260.369234
- grid_electricity_emissions: 5.445230
- grid_total_kwh: 7490.000000
- lpg_emissions: 14.023243
- operational_ghg_per_capita_kgco2e: 6.618705
- operational_ghg_tco2e: 46.271365
- renewable_electricity_kwh: 358142.000000
- renewable_share_pct: 97.951492
- scope1_tco2e: 40.826135
- scope2_tco2e: 5.445230
- total_electricity_consumption_kwh: 365632.000000
- transport_diesel_emissions: 24.187455
- transport_petrol_emissions: 2.036964

### Aug 2025
- dg_diesel_emissions: 4.995013
- estimated_avoided_grid_emissions_tco2e: 258.055193
- grid_electricity_emissions: unavailable (inputs_missing:grid_total_kwh)
- grid_total_kwh: unavailable (inputs_missing:grid_ht_kwh)
- lpg_emissions: 12.366488
- operational_ghg_tco2e: unavailable (inputs_missing:scope2_tco2e)
- renewable_electricity_kwh: 354959.000000
- renewable_share_pct: unavailable (inputs_missing:total_electricity_consumption_kwh)
- scope1_tco2e: 44.335789
- total_electricity_consumption_kwh: unavailable (inputs_missing:grid_total_kwh)
- transport_diesel_emissions: 24.805984
- transport_petrol_emissions: 2.168304

### Sep 2025
- dg_diesel_emissions: 7.992556
- estimated_avoided_grid_emissions_tco2e: 258.654968
- grid_electricity_emissions: unavailable (inputs_missing:grid_total_kwh)
- grid_total_kwh: unavailable (inputs_missing:grid_ht_kwh)
- lpg_emissions: 13.106111
- operational_ghg_tco2e: unavailable (inputs_missing:scope2_tco2e)
- renewable_electricity_kwh: 355784.000000
- renewable_share_pct: unavailable (inputs_missing:total_electricity_consumption_kwh)
- scope1_tco2e: 46.976579
- total_electricity_consumption_kwh: unavailable (inputs_missing:grid_total_kwh)
- transport_diesel_emissions: 23.196188
- transport_petrol_emissions: 2.681724

### Oct 2025
- dg_diesel_emissions: 9.098697
- estimated_avoided_grid_emissions_tco2e: 206.559602
- grid_electricity_emissions: 56.927008
- grid_total_kwh: 78304.000000
- lpg_emissions: 14.940374
- operational_ghg_per_capita_kgco2e: 17.733422
- operational_ghg_tco2e: 123.974352
- renewable_electricity_kwh: 284126.000000
- renewable_share_pct: 78.394724
- scope1_tco2e: 67.047344
- scope2_tco2e: 56.927008
- total_electricity_consumption_kwh: 362430.000000
- transport_diesel_emissions: 40.677060
- transport_petrol_emissions: 2.331213

### Nov 2025
- dg_diesel_emissions: 5.841777
- estimated_avoided_grid_emissions_tco2e: 175.543601
- grid_electricity_emissions: 77.972204
- grid_total_kwh: 107252.000000
- lpg_emissions: 11.567696
- operational_ghg_per_capita_kgco2e: 19.293256
- operational_ghg_tco2e: 134.879151
- renewable_electricity_kwh: 241463.000000
- renewable_share_pct: 69.243652
- scope1_tco2e: 56.906947
- scope2_tco2e: 77.972204
- total_electricity_consumption_kwh: 348715.000000
- transport_diesel_emissions: 36.811929
- transport_petrol_emissions: 2.685545

### Dec 2025
- dg_diesel_emissions: 3.985136
- estimated_avoided_grid_emissions_tco2e: 201.574563
- grid_electricity_emissions: 35.015228
- grid_total_kwh: 48164.000000
- lpg_emissions: 14.171167
- operational_ghg_per_capita_kgco2e: 13.490883
- operational_ghg_tco2e: 94.314762
- renewable_electricity_kwh: 277269.000000
- renewable_share_pct: 85.200026
- scope1_tco2e: 59.299534
- scope2_tco2e: 35.015228
- total_electricity_consumption_kwh: 325433.000000
- transport_diesel_emissions: 38.419024
- transport_petrol_emissions: 2.724207

### Jan 2026
- dg_diesel_emissions: 4.861800
- estimated_avoided_grid_emissions_tco2e: 187.240304
- grid_electricity_emissions: unavailable (inputs_missing:grid_total_kwh)
- grid_total_kwh: unavailable (inputs_missing:grid_commercial_kwh,grid_temporary_kwh)
- renewable_electricity_kwh: 257552.000000
- renewable_share_pct: unavailable (inputs_missing:total_electricity_consumption_kwh)
- scope1_tco2e: unavailable (inputs_missing:lpg_emissions)
- total_electricity_consumption_kwh: unavailable (inputs_missing:grid_total_kwh)
- transport_diesel_emissions: 24.309000
- transport_petrol_emissions: 1.398556
- water_consumed_kl: 20215.000000
- water_per_capita_l: 2891.574882

### Feb 2026
- dg_diesel_emissions: 5.266950
- estimated_avoided_grid_emissions_tco2e: 217.175256
- renewable_electricity_kwh: 298728.000000
- renewable_share_pct: unavailable (inputs_missing:total_electricity_consumption_kwh)
- scope1_tco2e: unavailable (inputs_missing:lpg_emissions)
- total_electricity_consumption_kwh: unavailable (inputs_missing:grid_total_kwh)
- transport_diesel_emissions: 23.228600
- transport_petrol_emissions: 1.241760
- water_consumed_kl: 22332.000000
- water_per_capita_l: 3194.392791

### Mar 2026
- dg_diesel_emissions: 5.537050
- estimated_avoided_grid_emissions_tco2e: 258.702950
- renewable_electricity_kwh: 355850.000000
- renewable_share_pct: unavailable (inputs_missing:total_electricity_consumption_kwh)
- scope1_tco2e: unavailable (inputs_missing:lpg_emissions)
- total_electricity_consumption_kwh: unavailable (inputs_missing:grid_total_kwh)
- transport_diesel_emissions: 24.849200
- transport_petrol_emissions: 1.289520
- water_consumed_kl: 20608.000000
- water_per_capita_l: 2947.790016

### Apr 2026
- dg_diesel_emissions: 5.771578
- estimated_avoided_grid_emissions_tco2e: 264.712332
- renewable_electricity_kwh: 364116.000000
- renewable_share_pct: unavailable (inputs_missing:total_electricity_consumption_kwh)
- scope1_tco2e: unavailable (inputs_missing:lpg_emissions)
- total_electricity_consumption_kwh: unavailable (inputs_missing:grid_total_kwh)
- transport_diesel_emissions: 23.700195
- transport_petrol_emissions: 1.214011
- water_consumed_kl: 20176.000000
- water_per_capita_l: 2885.996281

### May 2026
- estimated_avoided_grid_emissions_tco2e: 247.712164
- grid_electricity_emissions: 32.944005
- grid_total_kwh: 45315.000000
- operational_ghg_tco2e: unavailable (inputs_missing:scope1_tco2e)
- renewable_electricity_kwh: 340732.000000
- renewable_share_pct: 88.261792
- scope2_tco2e: 32.944005
- total_electricity_consumption_kwh: 386047.000000
- water_consumed_kl: 20186.000000
- water_per_capita_l: 2887.426691

### Jun 2026
- estimated_avoided_grid_emissions_tco2e: 177.540670
- grid_electricity_emissions: 14.560356
- grid_total_kwh: 20028.000000
- operational_ghg_tco2e: unavailable (inputs_missing:scope1_tco2e)
- renewable_electricity_kwh: 244210.000000
- renewable_share_pct: 92.420469
- scope2_tco2e: 14.560356
- total_electricity_consumption_kwh: 264238.000000
- water_consumed_kl: 19388.000000
- water_per_capita_l: 2773.279931

