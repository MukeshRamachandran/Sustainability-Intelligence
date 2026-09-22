# Microcosm — KCT Carbon Footprint Observatory

A single-page sustainability dashboard for Kumaraguru College of Technology.
It tracks campus fuel use, grid electricity, renewable energy, gross/avoided
emissions and net carbon impact from official monthly data, and presents them
as KPI cards, charts, a data explorer, and a cinematic guided tour
("The Carbon Story").

The front end is static — no build step. Open `index.html` through
any static file server and it runs. The KPI/chart numbers are no longer
hardcoded: `data-loader.js` fetches the CSVs in `data/` (plus the optional
`data/dashboard_master.json` live overlay) on load and computes everything
from there — see "How the dashboard works" below. An optional FastAPI
service in `../microcosm-dashboard-backend/` lets Power Automate push
approved form submissions into that overlay file; the dashboard runs fine
without it, on the CSVs alone.

```
# quickest way to run locally
python -m http.server 8000        # then open http://localhost:8000
```

> Note: Python's built-in server doesn't support HTTP Range requests, so
> video seeking is limited on it (the seamless-loop system detects this and
> degrades gracefully). Any real host — GitHub Pages, Netlify, nginx — is
> fully supported.

---

## What each file does

### Core site
| File | Role |
|---|---|
| `index.html` | The whole app shell: intro screen, topbar, filter toolbar, the six pages (Overview, Scope 1, Scope 2, Renewable, Comparison, Data Explorer, About), the KPI-detail sidebar, and the bottom navigation dock. Loads every script/stylesheet below with `?v=N` cache-busting. |
| `data-loader.js` | Fetches the master CSVs (and the optional `data/dashboard_master.json` overlay) from `data/`, converts fuel/electricity/renewable activity into emissions via the emission factors, and returns the `data` object app.js used to have hardcoded. Must load before `app.js`; `app.js`'s boot sequence awaits it. |
| `app.js` | Dashboard core. Holds the master `data` object (populated at boot by `data-loader.js`: 2025 full year + 2026 YTD, monthly arrays), the filter → `refresh()` pipeline that rebuilds KPI cards / Chart.js charts / the explorer table, page navigation (`go`), the hero balance card, dark-mode toggle, CSV export, KPI ambient FX (looping micro-videos + canvas particles), and the KPI-detail sidebar. Every function has a comment above it. |
| `styles.css` | All dashboard styling: theme variables (light + `body.dark-mode`), topbar/toolbar, KPI grids, chart cards, tables, bottom dock, KPI sidebar, intro screen, and the KPI FX layers. |
| `vendor/gsap-scrolltrigger.min.js` | Local copy of GSAP + ScrollTrigger (animation engine used by app.js and walkthrough.js). Chart.js loads from CDN in `index.html`. |

### The Carbon Story addon (pure overlay — the dashboard runs fine without it)
| File | Role |
|---|---|
| `walkthrough.js` | Builds the "Carbon Story" entry card in the hero row (video background, hover light-ring) and the full-screen 10-act scroll story: reads the eight overview KPI values live from the DOM, one cinematic act per metric. Also contains the seamless-loop engine (`makeSeamless` — a hidden twin video dissolves over each loop's wrap point so playback never stutters) and the phone landscape gate (portrait shows a "rotate your phone" prompt; rotating back exits). |
| `walkthrough.css` | All story styling: entry card, overlay, act plates/typography, progress rail, rotate gate, loop-twin dissolve classes, phone-landscape sizing. |

### Mobile addon (pure overlay — desktop is untouched by construction)
| File | Role |
|---|---|
| `mobile.js` | The few behaviours CSS can't do: the collapsed filter-accordion bar (mirrors the current selection, auto-folds after a pick), and the bottom dock's swipe edge-fade hints + active-button centering. |
| `mobile.css` | Every rule sits behind `@media (max-width: 820px)` / `(pointer: coarse)`: swipeable dock, collapsed filters, full-screen KPI sidebar sheet, 44px touch targets, 16px selects (stops iOS zoom), chart heights, safe paddings. |

### Media
| File | Used by |
|---|---|
| `background.png` | Site background (styles.css) |
| `micronew.mp4` | Intro screen video + the story's closing act |
| `entrykct.mp4` | Carbon Story entry card background + opening act (campus aerial) |
| `busdepot.mp4`, `electri.mp4`, `natureview.mp4`, `solarbuild.mp4` | Full-screen story act footage |
| `earth.mp4`, `elecmeter.mp4`, `electricspark.mp4`, `fuelpour.mp4`, `industrynew.mp4`, `leavesfall.mp4`, `queper.mp4`, `solar-kpi.mp4` | Small ambient loops inside the overview KPI cards |


### Everything else
| Item | Role |
|---|---|
| `reportgeneration/` | Separate PDF-report tool (own README inside). Not loaded by the website — keep or move independently.
---

## How the dashboard works (data flow)

```
data/*.csv                 data-loader.js               data {2025, 2026}
+ dashboard_master.json  ──►  fetch + parse CSVs   ──►    monthly arrays
  (optional live overlay)     compute emissions           + derived totals
                               overlay JSON on top
                                                                  │
                                                                  ▼
data {2025, 2026}          three <select> filters              active page
  monthly arrays     ──►   yearFilter / monthFilter /    ──►   .page.active
  + derived totals         compareMode
                                   │  change event
                                   ▼
                              refresh()
        ┌──────────────┬──────────┼─────────────┬──────────────┐
        ▼              ▼          ▼             ▼              ▼
   makeKpis()     drawCharts()  renderTable()  initKpi-    initChart-
   rebuilds KPI   rebuilds the  explorer with  Animations  Animations
   grids + hero   ACTIVE page's search + sort  (counters,  (3D tilt on
   balance card   charts only                  particles)  chart cards)
```

- **`data-loader.js`** runs once, before `app.js` calls `start()` — see
  `app.js`'s `boot()` IIFE at the bottom of the file. Editing the sustainability
  numbers means editing the CSVs in `data/` (or posting to the optional backend
  in `../microcosm-dashboard-backend/`), not editing `app.js`.
- **`refresh()`** runs on load, on every filter change, and on every page
  switch. `drawCharts()` only instantiates charts whose canvas is on the
  active page (max 4 instead of all 20) — hidden pages get theirs when you
  navigate there, because `go()` always calls `refresh()`.
- **KPI cards** are rebuilt as HTML strings; counters animate from 0 via
  GSAP; each card click opens the detail sidebar (`openKpiModal`), which
  clones the card and fills a narrative panel.
- **The Carbon Story** never computes anything: it reads the eight overview
  card values from the DOM after the dashboard renders, so it always matches
  whatever filter is selected.
- **Mobile behaviour** is layered on top the same way — the addons observe
  the DOM; app.js knows nothing about them.

### Conventions
- **Cache busting**: every stylesheet/script is loaded as `file.css?v=N`.
  When you edit a file, bump its `?v=` in `index.html`, or a browser that
  cached the old version will keep using it.
- **Addon isolation**: new features go in their own `something.js/css` pair
  wired into `index.html`, not into app.js/styles.css — that's what keeps
  the walkthrough and mobile layers safely removable.
- **Reduced motion**: everything animated checks
  `prefers-reduced-motion` and falls back to static rendering.

---

## Known issues / notes

- **Year 2026 filter**: selecting "2026 YTD" throws errors during
  `refresh()` (several 2026 fields are `null` — e.g. population and
  `totalEnergy` — and parts of the pipeline don't guard for them). This is
  pre-existing and intentionally left as-is for now.
- **KPI sidebar on non-overview pages** used to crash with a
  `ReferenceError` (`kpiDefinitions` was never defined); fixed 2026-07-19 —
  those cards now open the sidebar with a generic description.
- The story's landscape lock (`screen.orientation.lock`) only works on
  Android in fullscreen; on iPhone the rotate-gate prompt covers it.
