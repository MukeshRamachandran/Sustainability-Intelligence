# Waste historical source and owner confirmation

No new source file lives in this folder. The governed Waste source is the
existing Waste Inventory file, already imported as batch `waste_staging v1`:

- File: `apps/public-dashboard-final-staging/data/waste_master.csv`
- SHA-256: `c3e743f4de389231afc4f904f8c76c7db0720d89c40d60ef4959a87db906d138`
  (recorded in the import batch). The file is evidence and must not be edited;
  a correction or a later dump is a new file plus a new mapping.
- Mapping: `services/main-api/app/historical/mappings/waste_staging.json`

A second copy of the same figures was deliberately not created: two source
copies of one dataset would have to be reconciled against each other.

## Owner confirmation of the 2026 figures (2026-10-02)

Recorded as coverage confirmation `waste-2026-ytd-jan-jun-confirmed` in
`services/main-api/app/historical/mappings/resolutions.json`. The importer
applies it by appending a new VERIFIED / AUTHORITATIVE version of each value;
the original UNVERIFIED rows stay in the database as audit history, and one
`coverage_confirmation` audit record is written per value.

The project owner confirmed the supplied Waste Inventory image/data:

- The 2026 figures cover **1 January 2026 to 30 June 2026** (year to date).
  The coverage end is therefore stated. This supersedes the 2026-09-30
  confirmation of the total alone, whose end month was not then stated.
- Wet waste generated = **3000 kg**.
- Dry waste generated = **76590.6 kg**.
- The 14 material categories sum to **76590.6 kg** (= dry waste):
  Colour Paper 21174.10, White Paper 5178.07, Iron 7726.75, Lite Weight
  20226.25, Cardboard 1669.60, PP Cardboards 7759.33, Plastic (Mixed Plastics)
  3539.80, Black Plastic (PP) 5033.50, PET 1116.50, Aluminium 838.40, HDPE
  806.90, LDPE 784.10, News Paper 719.10, Tyre 18.20.
- Materials absent from the 2026 source (Coconut Shell, Stainless Steel, PVC
  Pipe, E-Waste, Unclassified) have no 2026 value. None was invented.
- The source's own total is **79590.6 kg**. K-COSMOS derives the total from
  wet + dry (3000 + 76590.6 = 79590.6); the source total is kept as a
  source-reported reference value.
- **Dry waste is defined by the owner as the waste diverted from landfill**:
  `waste_diverted_from_landfill_kg = dry_waste_generated_kg`. The legacy static
  88.1 % figure is not part of this methodology.
- Waste per person = total waste generated (kg) / the year's population.
- No monthly historical record was fabricated: 2026 remains one year-to-date
  record and 2025 one annual record.

## 2025

The verified 2025 annual values (wet 6577 kg, dry 48762.55 kg, 18 materials
summing to 48762.55 kg) are unchanged and were not re-imported.

## Later data

Waste is a year-aggregate domain. The public figure for a year is the newest
verified baseline that starts on 1 January plus the PUBLISHED Manager months
that start after that baseline's coverage end. A later dump that extends the
coverage (for example January to August) supersedes this baseline; the months
it covers are then no longer added.
