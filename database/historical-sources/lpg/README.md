# LPG historical sources

`lpg_2026_jan_jul.csv` holds the project-owner supplied LPG data for Jan–Jul
2026 (supplied 2026-09-30, 19 kg cylinders). It is imported by mapping
`lpg_2026_owner_source` (see `LPG_2026_IMPORT_REPORT.md`).

- The file is evidence. Never edit it: its SHA-256
  (`60999d91eba5a846ce5568b49b1f682515882caf75647427d2f24c52fcd608c0`) is
  recorded in the import batch. A correction is a new file plus a new mapping
  version.
- Opening, purchase and closing stock were supplied for February only, and no
  brand was supplied. Blank cells mean "not supplied", never zero.
- `KG` is the governed activity. Cylinder count and emissions are reference
  only, and the backend recalculates emissions with the governed `LPG_KG` factor.
