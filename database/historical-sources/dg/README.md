# DG generator historical sources

`dg_generation_2026.csv` holds the institutional DG Generator electricity
generation (kWh) for May–Jul 2026, supplied and approved for import by the
project owner on 2026-10-01. It is imported by mapping `dg_2026_owner_source`.

- The file is evidence. Never edit it: its SHA-256
  (`33aa2b90f5f34b22eb84f3bbc7a513a121d267899cc752a732682c1abf022c1c`) is
  recorded in the import batch. A correction or an additional month is a new
  file plus a new mapping version.
- It contains source activity only: generation in kWh. Diesel litres and
  emissions are never source data here. The backend derives litres with the
  governed `DG_SFC` parameter and calculates emissions with the governed
  `DIESEL` factor (`0015_dg_kwh_methodology`).
- August 2026 is deliberately absent: it has not been approved for import.
- DG records through April 2026 are source-reported diesel litres
  (`apps/public-dashboard-final-staging/data/dg_master.csv`, mapping
  `dg_staging`). They are not converted to kWh.
