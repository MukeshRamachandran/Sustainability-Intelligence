# Transport fuel historical sources

`transport_fuels_2026.csv` is a transcription of the institutional
transport-fuel sheet supplied (as a spreadsheet screenshot) and approved for
import by the project owner on 2026-10-01. It is imported by mapping
`transport_2026_owner_source`.

- The file is evidence. Never edit it: its SHA-256
  (`4474eb2222ed2aaada0f5a9d9a6ff79bf638579b6a1107c0780a2b54a26d9816`) is
  recorded in the import batch. A correction or an additional month is a new
  file plus a new mapping version.
- Only May–Jul 2026 were transcribed: petrol litres and fleet diesel litres.
- Jan–Apr 2026 are excluded because they are already held from
  `apps/public-dashboard-final-staging/data/transport_master.csv` (mapping
  `transport_staging`). They were not re-imported.
- August 2026 appears on the sheet but is outside the approved scope and is
  deliberately absent.
- The sheet's emission columns are informational only and were not
  transcribed. The sheet uses 2.38 kgCO2e/L for petrol; K-COSMOS calculates
  emissions with its governed factors (PETROL 2.388 kgCO2e/L, DIESEL
  2.701 kgCO2e/L), which remain authoritative.
