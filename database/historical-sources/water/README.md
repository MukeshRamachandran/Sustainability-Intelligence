# Water historical sources

`water_2026_july.csv` is a transcription of the institutional Water consumption
spreadsheet supplied (as a screenshot) and approved for import by the project
owner. It is imported by mapping `water_2026_july_owner_source`.

- The file is evidence. Never edit it: its SHA-256
  (`4e4aea9816bbe7d63fac1b2812bd4eb099962bae47f9d423aea0e5cd0c603736`) is
  recorded in the import batch. A correction or an additional month is a new
  file plus a new mapping version.
- Source: owner-supplied institutional Water consumption spreadsheet screenshot.
- Approved scope: **July 2026 only**.
- July source values:
  - TWAD Consumption = 3293 KL -> `water_twad_kl`
  - Borewell Consumption = 17050 KL -> `water_borewell_kl`
  - Quantity of Water Procured = 124.27 KL -> `water_private_kl` (the existing
    canonical metric for procured/private water supply)
- Spreadsheet Total Consumption: 20467.27 KL. The reported total is preserved
  here as source/reference validation only and is not imported. The
  authoritative K-COSMOS total (`water_consumed_kl`) is calculated by the
  backend from the three source components with the existing formula
  (TWAD + borewell + private). 3293 + 17050 + 124.27 = 20467.27.
- No July recycled-water value was supplied.
- No wastewater value was supplied.
- No water-quality or STP data was supplied.
- No missing metric was converted to zero; those metrics simply have no July
  value.
- The screenshot also shows Jan–Jun 2026. Those months are already governed
  (mapping `water_staging`) with the same values and were not re-imported.
- August 2026 and later months are out of scope and deliberately absent.
- The governed 2026 recycled-water year-to-date record is a separate source and
  is not affected by this file.
