# Energy historical sources

Two July 2026 owner-approved sources live here. Each file is evidence: never
edit it. Its SHA-256 is recorded in its import batch, and a correction or an
additional month is a new file plus a new mapping version.

## Grid electricity — `grid_2026_july.csv`

Transcription of the institutional electricity source supplied (as spreadsheet
screenshots) and approved for import by the project owner on 2026-10-01.
Imported by mapping `grid_2026_july_owner_source`.

- SHA-256: `5a028ca1ceaf424686fb8d7ed5cc9857c9e6c1caf1a00052080504a034e96981`
- Owner-approved scope is July 2026 only: three grid connection readings in kWh.
- Column mapping, by the sheet's consumption columns:
  - Industrial Consumption -> `grid_ht_kwh`
  - Commercial Consumption -> `grid_commercial_kwh`
  - Temp Consumption -> `grid_temporary_kwh`
- Rationale: the sheet's Equipment labels are inconsistent (repeated text), but
  its consumption columns reproduce the governed Jan–Jun 2026 K-COSMOS grid
  series exactly, so the connections are identified by the consumption-column
  identity and not by the Equipment text.
- The sheet's calculated emissions were not transcribed and are not imported.
  The grid total is summed by the backend from the three meters, and Scope 2
  is calculated with the governed `GRID_ELECTRICITY` factor, which remains
  authoritative.
- Jan–Jun 2026 are already governed (including their resolved source
  conflicts) and were not re-imported.
- August 2026 appears on the same sheet but is outside the approved scope and
  is deliberately absent.

## Renewable electricity — `renewable_2026_july.csv`

Source: owner-supplied institutional renewable-energy Excel screenshot,
approved for import by the project owner on 2026-10-01. Imported by mapping
`renewable_2026_july_owner_source`.

- SHA-256: `288cce86ba84a0ff231f09d471b93f08f19bbe81f359d2fd23f0dc17e6cedb90`
- Approved import scope: July 2026 only.
- Source activities (the only values transcribed):
  - On-campus solar electricity = 18595 kWh -> `renewable_on_campus_kwh`
  - Procured renewable electricity = 286334 kWh -> `renewable_procured_kwh`
- Not imported, recorded here for reference only:
  - Solar Water Heater 62500 is thermal energy. It is not imported and is
    never part of the electrical renewable calculations.
  - The sheet's Total RE KWH 367429 includes the Solar Water Heater
    (18595 + 286334 + 62500), so it is not the K-COSMOS electrical renewable
    total and is not imported.
  - The sheet's Emission Reduced 301.29178 is not imported.
- K-COSMOS backend calculations remain authoritative: renewable electricity
  (on-campus + procured), total electricity, renewable share and avoided grid
  emissions are derived by the existing backend formulas with the governed
  `GRID_ELECTRICITY` factor.
- Jan–Jun 2026 renewable records are already governed and were not re-imported.
- August 2026 values appear on the same sheet and are deliberately excluded.
