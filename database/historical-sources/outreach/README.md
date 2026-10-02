# Community Outreach historical sources

`outreach_2026_ytd.csv` holds the 2026 Community Outreach figures supplied by
the project owner on 2026-10-01, stated as "till August 17, 2026". It is
imported by mapping `outreach_2026_ytd_owner_source`.

- The file is evidence. Never edit it: its SHA-256
  (`58551538e5f12f1974c337de16d321c93050da154a280e5ad44f8e4bb599961a`) is
  recorded in the import batch. A correction or a later cumulative figure is a
  new file plus a new mapping version.

## Coverage

- Coverage is **01 Jan 2026 through 17 Aug 2026**.
- The source is **cumulative / year to date, not monthly**. It is stored as one
  YTD coverage-range record. No monthly values were inferred, the totals were
  not divided across months, and nothing was assigned to August.
- No programme records were fabricated. The Manager programme tables hold only
  programmes that a Manager actually entered.

## Lower bounds

A trailing `+` in the source ("20+", "2,009+") means **at least**. The number
is stored as the lower bound with the `AT_LEAST` qualifier and is shown with a
`+`; it is never presented as an exact measurement.

## What each table means

- **Summary** — seven totals for the coverage period: programmes/events,
  volunteers engaged, volunteering hours, experts involved, total
  participants/reach, partner organizations, saplings/seedlings.
- **Thematic counts** — programmes counted under each theme. The nine counts
  total **24**, while the summary reports **20+** programmes. The thematic
  total is therefore **not** treated as the number of unique programmes: a
  programme may be counted under more than one theme. The summary's 20+ remains
  the programme count. (The institution's earlier sheet,
  `apps/public-dashboard-final-staging/data/outreach_master.csv`, heads this
  same table "No. of programmes".)
- **Audience counts** — one source-reported count per audience category,
  stored with unit `count`. They are **not participant counts**: the ten values
  total 32 while the summary reports 2,009+ participants. The supplied figures
  do not define the measure further (for example, programmes per audience
  type), so no such meaning is asserted, and they are never shown as "reach".
  Explicit zeros (Government / Forest, Media / Press, Alumni) are kept as
  reported zeros.
- **Gender** — no gender figures were supplied. None are stored or inferred.

Source labels map to the existing category codes: "Human-Wildlife Conflict" →
`hwcc`, "Government / Forest" → `government`, "Entrepreneurs / Startup" →
`entrepreneurs_startup_founders`. "Media / Press" and "Alumni" are new
categories (`media_press`, `alumni`).

## Extending the year-to-date total

Future Manager outreach data is entered per programme and approved through the
normal workflow. A published month that **starts after 17 Aug 2026** (September
2026 onward) is added to this baseline to give the current 2026 year-to-date
figure, for values measured in the same unit.

**Overlap rule:** a month that overlaps the coverage period — including August
2026, which the baseline already covers through the 17th — is never added to
the baseline. The remainder of August is not assumed to be zero; it is simply
not combined.

## Earlier figure

An older 2026 column in `outreach_master.csv` (mapping `outreach_staging`) was
imported UNVERIFIED on a placeholder Jan–Jun period because its coverage was
never stated. It was never public and is left untouched; this owner-supplied
source, with its stated coverage, is the governed 2026 baseline.
