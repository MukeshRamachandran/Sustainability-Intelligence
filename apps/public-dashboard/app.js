/* =====================================================================
   MICROCOSM - DASHBOARD CORE (app.js)
   Single-page dashboard. The master dataset lives in `data` below; the
   two toolbar filters (year / month) drive refresh(), which
   rebuilds the KPI cards, the charts and the data-explorer table for
   whichever page is active. go() switches pages and re-runs refresh().
   Everything else is presentation: Chart.js configs, GSAP entrance
   animations, canvas particle FX, and the KPI detail sidebar.
   walkthrough.js and mobile.js are self-contained addons layered on top;
   they read this DOM but nothing in this file depends on them.
   ===================================================================== */
const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const colors = {
  emerald: '#1c7a4b',  // renewable / good / net-good
  lime: '#5aa552',     // secondary green
  cyan: '#3a6fa8',     // electricity / scope 2 (steel blue)
  blue: '#3a6fa8',
  teal: '#4f9a8c',     // petrol
  gold: '#c18a2e',     // Fleet diesel (amber)
  orange: '#b8623a',   // DG diesel / gross (rust)
  violet: '#6b5b95',   // LPG
  red: '#be4b3b',      // emissions / unfavourable
  muted: 'rgba(21,32,26,.16)',
  grid: 'rgba(21,32,26,.07)'
};

/* ---- clean line-icon set (replaces emoji) ---- */
const ICONS = {
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
  bolt: '<path d="M13 3 5 14h6l-1 7 8-11h-6z"/>',
  droplet: '<path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.7L12 2 8 9.3C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"/>',
  trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  tree: '<path d="M12 22V14"/><path d="M7 14s-3-2-3-5a5 5 0 0 1 10 0c0 3-3 5-3 5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  leaf: '<path d="M5 19c0-8 6-13 14-13 0 8-6 14-14 13Z"/><path d="M5 19c3-4 6-6 9-7"/>',
  fuel: '<path d="M5 21V5a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2v16M4 21h11M7 8h5"/><path d="M14 9h2a2 2 0 0 1 2 2v5a1.5 1.5 0 0 0 3 0V8l-2-2"/>',
  plug: '<path d="M9 3v5M15 3v5M7 8h10v3a5 5 0 0 1-10 0z M12 16v5"/>',
  users: '<circle cx="9" cy="8" r="3"/><path d="M3 20a6 6 0 0 1 12 0M16 6a3 3 0 0 1 0 6M21 20a6 6 0 0 0-4-5.6"/>',
  scale: '<path d="M12 3v18M5 7h14M5 7 3 13a3 3 0 0 0 6 0L7 7M19 7l-2 6a3 3 0 0 0 6 0l-2-6M8 21h8"/>',
  cloud: '<path d="M7 18a4 4 0 0 1 0-8 5 5 0 0 1 9.6-1A3.5 3.5 0 0 1 17 18z"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
  flame: '<path d="M12 3c4 4 5 7 5 10a5 5 0 0 1-10 0c0-1.5.5-3 1.5-4 .5 1 1.5 1.5 2 1.5C9 8 10 5 12 3Z"/>',
  ruler: '<path d="M3 16 16 3l5 5L8 21z"/><path d="M7 8l2 2M10 5l2 2M13 11l2 2M16 8l2 2"/>',
  chart: '<path d="M4 20V4M4 20h16"/><rect x="7" y="12" width="3" height="5"/><rect x="12" y="8" width="3" height="9"/><rect x="17" y="5" width="3" height="12"/>',
  check: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  sprout: '<path d="M12 21v-8M12 13c0-4 3-6 7-6 0 4-3 6-7 6ZM12 13C12 9 9 7 5 7c0 4 3 6 7 6Z"/>',
  shield: '<path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6z"/><path d="m9 12 2 2 4-4"/>',
  repeat: '<path d="M4 9a5 5 0 0 1 5-5h7M20 15a5 5 0 0 1-5 5H8"/><path d="M16 1l3 3-3 3M8 23l-3-3 3-3"/>',
  spark: '<path d="M12 3v6M12 15v6M3 12h6M15 12h6"/><path d="m6 6 3 3M15 15l3 3M18 6l-3 3M9 15l-3 3"/>',
  truck: '<path d="M3 6h11v9H3zM14 9h4l3 3v3h-7z"/><circle cx="7" cy="18" r="1.6"/><circle cx="17" cy="18" r="1.6"/>',
  car: '<path d="M3 13l2-5h14l2 5v5h-3M6 18H3v-5M7 18h10"/><circle cx="7.5" cy="18" r="1.5"/><circle cx="16.5" cy="18" r="1.5"/>',
  bus: '<rect x="4" y="4" width="16" height="13" rx="2"/><path d="M4 11h16M9 17v2M15 17v2"/><circle cx="8" cy="14" r="1"/><circle cx="16" cy="14" r="1"/>',
  factory: '<path d="M3 21V10l6 4V10l6 4V6h3v15z"/><path d="M7 17h2M13 17h2"/>',
  building: '<rect x="5" y="3" width="14" height="18" rx="1"/><path d="M9 7h2M13 7h2M9 11h2M13 11h2M10 21v-3h4v3"/>',
  store: '<path d="M4 9 5 4h14l1 5M4 9h16M4 9v11h16V9M9 20v-6h6v6"/>',
  battery: '<rect x="3" y="8" width="16" height="8" rx="2"/><path d="M21 11v2M7 12h6"/>',
  wind: '<path d="M3 8h10.5a3 3 0 1 0-3-3"/><path d="M3 16h13.5a3 3 0 1 1-3 3"/><path d="M3 12h17"/>',
  rain: '<path d="M7 16a4.5 4.5 0 0 1 0-9 5.5 5.5 0 0 1 10.6-1.6A4 4 0 0 1 17 16z"/><path d="M8 19v1M12 19v2M16 19v1"/>',
  gauge: '<path d="M12 12 16.2 7.8"/><circle cx="12" cy="12" r="9"/><path d="M6.5 15.5a7 7 0 0 1 11 0"/>',
  dot: '<circle cx="12" cy="12" r="4"/>'
};
/* Wrap an ICONS path in the shared inline-SVG shell. */
function ic(n) { return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" width="19" height="19">${ICONS[n] || ICONS.dot}</svg>` }

/* ---- dashboard data ---- populated at boot by public-data-loader.js.
   Governed domains come only from the active immutable public release. */
let data = {};
/* Green cover: a one-time campus survey, not year/month filtered - see
   data-loader.js's block-section parser and green_master.csv. */
let green = {};
/* Community outreach aggregate from the active published release. */
let outreach = {};
let publication = { state: 'loading', release: null, period: null };

/* null/NaN-safe number coercion - the master data uses null for months with no reading. */
function n(v) { return v == null || Number.isNaN(+v) ? 0 : +v }
/* Sum a monthly array over [s, e) with null-safety. */
function sum(a, s = 0, e = 12) { const values = a.slice(s, e).filter(value => value != null); return values.length ? values.reduce((x, y) => x + n(y), 0) : null }
/* Indian-locale number formatting at d decimals. */
function fmt(v, d = 0) { return v == null ? '' : n(v).toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d }) }
/* Show published positive sub-centitonne values without rounding them to 0.00. */
function emissionDecimals(value) { return value != null && value > 0 && value < 0.01 ? 6 : 2 }
/* Decimals a published activity value actually carries (769.5 kg -> 1, 7429 kg -> 0), capped at 3. Presentation only. */
function activityDecimals(value) { const text = value == null ? '' : String(value); return text.includes('.') ? Math.min(text.split('.')[1].length, 3) : 0 }
/* Waste is published in kg. Tonnes hide small real values (0.38 kg reads as
   "0.0 tons"), so a figure below one tonne is shown in kg. Presentation only. */
function wasteDisplay(tons) { return tons != null && tons < 1 ? { factor: 1000, unit: 'kg', dec: 2 } : { factor: 1, unit: 'tons', dec: 1 } }
/* ---- Outreach chart wording, driven by what the backend reports ----
   The audience table is participant reach (unit "people") for Manager
   programme data, but a historical source can report a plain count per
   audience category that is NOT participants (unit "count"). The chart's title,
   hint and tooltip follow the unit; a count is never labelled as reach. */
function outreachAudienceText(unit) {
  if (unit === 'people') {
    return { title: 'Participants by Category', hint: 'Approx. reach per audience - hover a slice for the figure', unit: 'reach' };
  }
  if (unit === 'count') {
    return { title: 'Audience Categories', hint: 'Source-reported count per audience category - not participant numbers', unit: '(source count)' };
  }
  return { title: 'Audience Categories', hint: 'Reported figure per audience category', unit: unit || '' };
}
/* When the per-theme counts add up to more than the programme total, say so:
   a programme can be counted under more than one theme. Display text only. */
function outreachThematicNote(thematic, programmes, qualifier) {
  const counted = thematic.reduce((total, row) => total + (row.programs || 0), 0);
  if (programmes == null || counted <= programmes) return '';
  return `Theme counts total ${counted}; a programme can be counted under more than one theme (${programmes}${qualifier === 'AT_LEAST' ? '+' : ''} programmes).`;
}
/* ---- end outreach chart wording ---- */
/* Underscore codes from the published outreach payload as readable labels. */
function humanizeCode(code) { const text = String(code).replace(/_/g, ' '); return text.length <= 4 ? text.toUpperCase() : text.charAt(0).toUpperCase() + text.slice(1) }
const HISTORY_NOTE = 'Insufficient published history: only one month has been published so far. Trends and year comparisons appear as more months are published.';
/* Status line under a chart. Zero published points -> emptyText; exactly one
   -> the insufficient-history note; otherwise nothing. Missing months are
   never drawn as zero, and an unpublished year is never implied to exist. */
function chartNote(canvasId, arrays, emptyText) {
  const canvas = document.getElementById(canvasId), host = canvas && canvas.closest('.chart'); if (!host) return;
  const points = arrays.reduce((total, arr) => total + arr.filter(v => v != null).length, 0);
  setChartNote(canvasId, points === 0 ? emptyText : (points === 1 ? HISTORY_NOTE : ''));
}
/* Write (or clear) the status line under a chart's .chart container. */
function setChartNote(canvasId, text) {
  const canvas = document.getElementById(canvasId), host = canvas && canvas.closest('.chart'); if (!host) return;
  let note = host.nextElementSibling; if (!(note && note.classList.contains('chart-note'))) { if (!text) return; note = document.createElement('p'); note.className = 'hint chart-note'; host.after(note); }
  note.textContent = text; note.style.display = text ? '' : 'none';
}
/* Display-only percent change; trendHtml calls this only with a nonzero baseline. */
function pct(cur, prev) { return ((cur - prev) / prev) * 100 }
/* How many leading months a metric actually has readings for - sources don't
   all report the same number of months for a YTD year (fuel/Fleet still
   stop at April 2026, energy/water now run through June), so each array's
   own extent is used instead of one hardcoded cutoff. */
function monthsWithData(arr) { let last = 0; for (let i = 0; i < 12; i++) if (arr[i] != null) last = i + 1; return last }
/* Value of a metric for the selection. A month reads that month's genuine
   value only; 'all' (Full Year / YTD) reads the backend's aggregate for the
   year, whose coverage is stated by the API. Nothing is summed here. */
function valFor(d, arr, m) {
  if (!d || !Array.isArray(arr)) return null;
  if (m === 'all') return arr.aggregate == null ? null : n(arr.aggregate);
  return arr[+m] == null ? null : n(arr[+m]);
}
/* Energy Source Breakdown bars for the selection. Each bar is the selected
   period's own value (the month's record, or the Full Year / YTD aggregate
   record) read through valFor - never a sum of months. A missing value omits
   its bar rather than drawing 0; a partial aggregate keeps its coverage. */
function energySourceBreakdown(d, month) {
  const meta = d?.periodMeta?.[month === 'all' ? 'all' : +month];
  return [
    ['Grid total', 'elecKwh', 'grid_total_kwh', colors.cyan],
    ['On-campus renewable', 'reOnCampusKwh', 'renewable_on_campus_kwh', '#63b3ed'],
    ['Procured renewable', 'reProcuredKwh', 'renewable_procured_kwh', colors.emerald],
    ['Solar water heater', 'solarWaterHeaterKwh', 'solar_water_heater_kwh', colors.gold]
  ].map(([label, arr, code, color]) => {
    const value = valFor(d, d?.[arr], month);
    if (value == null) return null;
    const item = meta?.values?.[code];
    const partial = item?.coverage_status === 'partial';
    return { label, value, color, partial, monthsCovered: partial ? (item.months_covered || []).length : null };
  }).filter(Boolean);
}

/* Components of a chart that shows ONE reporting period (a mix / split donut).
   Each value is the selected period's own record - the month, or the
   backend's Full Year / YTD aggregate - read through valFor, never a sum of
   months. parts: [label, arrayName, valueCode, color]. A missing value stays
   null (never 0); a partial aggregate keeps its coverage. */
function periodComposition(d, month, parts) {
  const meta = d?.periodMeta?.[month === 'all' ? 'all' : +month];
  return parts.map(([label, arr, code, color]) => {
    const value = valFor(d, d?.[arr], month);
    const item = meta?.values?.[code];
    const partial = value != null && item?.coverage_status === 'partial';
    return { label, value, color, partial, monthsCovered: partial ? (item.months_covered || []).length : null };
  });
}
/* Plain-language coverage line for a composition: which parts are not
   published for this period and which cover only part of it. */
function compositionNote(parts, period) {
  const missing = parts.filter(part => part.value == null).map(part => part.label);
  const partial = parts.filter(part => part.partial).map(part => `${part.label} (${part.monthsCovered} month(s) reported)`);
  return [
    missing.length ? `Not published for ${period}: ${missing.join(', ')}.` : '',
    partial.length ? `Partial: ${partial.join(', ')}.` : ''
  ].filter(Boolean).join(' ');
}
/* A month with no genuine value for ANY part may still carry the backend's
   labelled context for it (e.g. "2025 Annual Data" from the annual record),
   exactly as the KPI cards show. Used only when every shown part comes from
   the same source record, so the chart is one coherent period. */
function contextComposition(d, month, parts) {
  if (month === 'all') return null;
  const display = d?.display?.[+month] || {};
  const shown = parts.map(([label, , code, color]) => {
    const item = display[code];
    return { label, value: item && item.value != null ? n(item.value) : null, color, partial: false, monthsCovered: null, item };
  });
  const items = shown.filter(part => part.value != null).map(part => part.item);
  if (!items.length || !items.every(item => item.display_context && item.source_key === items[0].source_key)) return null;
  return { parts: shown.map(({ item, ...part }) => part), label: items[0].display_label };
}
/* Components of the single-period GHG / Water composition charts. Order is
   the chart's slot order (the mix donuts key hover styling by index). */
const ELEC_MIX_PARTS = [
  ['Grid electricity', 'elecKwh', 'grid_total_kwh'],
  ['Renewable electricity', 'reKwh', 'renewable_electricity_kwh'],
  ['On-campus renewable', 'reOnCampusKwh', 'renewable_on_campus_kwh'],
  ['Procured renewable', 'reProcuredKwh', 'renewable_procured_kwh']
];
const FUEL_MIX_PARTS = [
  ['DG diesel', 'dgEm', 'dg_diesel_emissions'],
  ['Fleet diesel', 'trDieselEm', 'transport_diesel_emissions'],
  ['Petrol', 'petrolEm', 'transport_petrol_emissions'],
  ['LPG', 'lpgEm', 'lpg_emissions']
];
/* "42.0%": a governed value as a share of a governed total. Display only -
   nothing is stored, and a missing value or total gives no percentage. */
function sharePct(value, total) {
  if (!(total > 0) || value == null) return '';
  const percentage = value / total * 100;
  return `${percentage.toFixed(percentage > 0 && percentage < 0.1 ? 3 : 1)}%`;
}
/* Electricity Mix labels for the selection. The widget needs the two top-level
   backend values (grid and renewable electricity); a missing one is never
   treated as zero. Renewable % is the backend's renewable_share_pct; grid % is
   the backend grid total as a share of the backend electricity total. */
function elecMixView(d, month) {
  const grid = valFor(d, d?.elecKwh, month), renewable = valFor(d, d?.reKwh, month);
  const total = valFor(d, d?.totalElectricityKwh, month), share = valFor(d, d?.renewableSharePct, month);
  return {
    available: grid != null && renewable != null,
    rePct: share != null ? `${share.toFixed(1)}%` : sharePct(renewable, total),
    gridPct: sharePct(grid, total)
  };
}
/* Fossil Fuel Emissions Mix for the selection: two rings and their labels.
   Inner ring = the four governed contributors. Outer ring = the fuel groups,
   where Diesel is the grouping of Fleet diesel and DG diesel (a presentation
   grouping of two backend results, not a stored value). Every percentage is a
   share of the backend Scope 1 total, so Fleet % + DG % = Diesel %. A missing
   contributor stays missing: its slice is empty, it has no percentage, and the
   combined Diesel percentage is then not shown. */
function fuelMixView(d, month) {
  const [dg, fleet, petrol, lpg] = periodComposition(d, month, FUEL_MIX_PARTS).map(part => part.value);
  const scope1 = valFor(d, d?.scope1Full, month);
  const present = [fleet, dg].filter(value => value != null);
  const dieselComplete = present.length === 2;
  const dieselShown = present.length ? present.reduce((total, value) => total + value, 0) : null;
  return {
    inner: [dg, fleet, petrol, lpg],
    outer: [dieselShown, petrol, lpg],
    dieselComplete,
    lpgPct: sharePct(lpg, scope1), petrolPct: sharePct(petrol, scope1),
    fleetPct: sharePct(fleet, scope1), dgPct: sharePct(dg, scope1),
    dieselPct: dieselComplete ? sharePct(dieselShown, scope1) : ''
  };
}
const GHG_PROFILE_PARTS = {
  s1: [
    ['Fleet diesel', 'trDieselEm', 'transport_diesel_emissions', colors.gold],
    ['DG diesel', 'dgEm', 'dg_diesel_emissions', colors.orange],
    ['Petrol', 'petrolEm', 'transport_petrol_emissions', colors.teal],
    ['LPG', 'lpgEm', 'lpg_emissions', colors.violet]
  ],
  // One governed grid-electricity result; the HT / Commercial / Temporary split is not published.
  s2: [['Grid electricity', 'elecEm', 'scope2_tco2e', colors.cyan]]
};
const WATER_SOURCE_PARTS = [
  ['TWAD supply', 'waterTWAD', 'water_twad_kl', colors.cyan],
  ['Borewell', 'waterBorewell', 'water_borewell_kl', colors.teal],
  ['Private water supply', 'waterProcured', 'water_private_kl', colors.gold]
];

/* A single factor is meaningful for an all-month view only when every
   published calculation in that selection used the same factor. */
function factorFor(d, arr, m) {
  if (!d || !Array.isArray(arr)) return null;
  if (m !== 'all') return arr[+m] == null ? null : n(arr[+m]);
  const values = arr.filter(value => value != null);
  return values.length && values.every(value => value === values[0]) ? n(values[0]) : null;
}
/* The active toolbar selection plus its year dataset. */
function currentPeriod() {
  const year = +yearFilter.value, value = monthFilter.value, d = data[yearFilter.value];
  // 'agg:<key>' selects a secondary aggregate view (e.g. an annual-only record).
  if (value && value.startsWith('agg:')) return { year, month: 'all', d: d?.secondary?.[value.slice(4)] || d };
  return { year, month: value, d };
}
/* True when at least one monthly immutable release contributes to the
   selected reporting window. Values are still taken from their own month. */
function selectionHasPublication(d, month) {
  if (month === 'all') return Boolean(d?.aggregateKey);
  const published = Array.isArray(d?.publishedMonths) ? d.publishedMonths : [];
  return published[+month] === true;
}
/* The backend's per-domain state for the selection, e.g. "Monthly Waste data
   unavailable. 2025 annual data is available under 2025 Full Year." */
function domainNote(domain) {
  const { month, d } = currentPeriod();
  const state = d?.domainStatus?.[month === 'all' ? 'all' : +month]?.[domain];
  return state && state.state !== 'available' ? state.message : '';
}
/* Human label for the selection - "Mar 2025" or the year dataset's own label. */
function periodLabel(year, month) { return month === 'all' ? (currentPeriod().d || data[year]).label : `${months[+month]} ${year}` }
/* Comparison baseline for a metric: same period, one year back. null = nothing to compare against (no prior-year data). */
function previousValue(arrName) {
  const { year, month, d } = currentPeriod();
  const py = data[year - 1];
  if (!d || !py || !Array.isArray(d[arrName]) || !Array.isArray(py[arrName])) return null;
  if (month === 'all') {
    // A YTD window is never compared against a different window (e.g. a full year).
    return py.aggregateEndMonth === d.aggregateEndMonth ? valFor(py, py[arrName], 'all') : null;
  }
  return valFor(py, py[arrName], month);
}
/* The up/down trend chip; lowerGood flips which direction counts as green. */
const NO_COMPARISON_HTML = '<b class="neutral">base</b><span>no comparison</span>';
function trendHtml(cur, prev, lowerGood = true) { if (cur == null) return ''; if (prev == null || prev === 0) return NO_COMPARISON_HTML; const p = pct(cur, prev); const good = lowerGood ? p <= 0 : p >= 0; return `<b class="${good ? 'good' : 'bad'}">${p >= 0 ? '↑' : '↓'} ${Math.abs(p).toFixed(1)}%</b><span>vs last year</span>` }
/* Build one KPI card: optional ambient FX layer (looping video, canvas
   particles or SVG scene per fxType), icon, counter (animated later by
   initKpiAnimations) and trend chip. Clicking opens the detail sidebar. */
function kpi(title, value, unit, accent, icon, prev, lowerGood = true, dec = 2, fxType = null) { const fx = fxType && !reduceMotion; const cls = fx ? ` kpi-fx kpi-fx-${fxType}` : ''; const pSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>'; const inner = (fx && (fxType === 'smoke' || fxType === 'leaves' || fxType === 'lightning') ? `<canvas class="kpi-fx-canvas" data-fx="${fxType}"></canvas>` : '') + (fx && fxType === 'peoplefade' ? `<div class="kpi-fx-people">${pSvg}${pSvg}${pSvg}</div>` : '') + (fx && fxType === 'solarvideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="media/solar-kpi.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'leavesvideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="media/leavesfall.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'fuelpourvideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="media/fuelpour.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'electricsparkvideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="media/electricspark.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'quepervideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="media/queper.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'earthvideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="media/earth.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'industrynewvideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="media/industrynew.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'elecmetervideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="media/elecmeter.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'convwastevideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="media/waste2.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'landfillvideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="media/convwaste.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'watervideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="media/water.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'rewatervideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="media/rewater.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'sunrays' ? `<div class="kpi-fx-solar-bg"><svg viewBox="0 0 100 100" preserveAspectRatio="xMaxYMax meet"><defs><radialGradient id="sunGlow" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#fbbf24" stop-opacity="0.7"/><stop offset="100%" stop-color="#fbbf24" stop-opacity="0"/></radialGradient><linearGradient id="panelGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#1e3a8a"/><stop offset="100%" stop-color="#1e40af"/></linearGradient></defs><g class="solar-sun"><circle cx="75" cy="25" r="30" fill="url(#sunGlow)"/><circle cx="75" cy="25" r="10" fill="#f59e0b"/><g class="solar-rays" stroke="#fbbf24" stroke-width="2" stroke-linecap="round"><line x1="75" y1="5" x2="75" y2="45"/><line x1="55" y1="25" x2="95" y2="25"/><line x1="61" y1="11" x2="89" y2="39"/><line x1="61" y1="39" x2="89" y2="11"/></g></g><g class="solar-panel" transform="translate(45, 50) scale(0.65)"><rect x="42" y="30" width="4" height="15" fill="#64748b"/><line x1="25" y1="45" x2="63" y2="45" stroke="#64748b" stroke-width="4" stroke-linecap="round"/><path d="M10,30 L35,5 L85,5 L60,30 Z" fill="url(#panelGrad)" stroke="#94a3b8" stroke-width="2" stroke-linejoin="round"/><line x1="22" y1="18" x2="72" y2="18" stroke="#60a5fa" stroke-width="1.5"/><line x1="30" y1="5" x2="18" y2="30" stroke="#60a5fa" stroke-width="1.5"/><line x1="50" y1="5" x2="38" y2="30" stroke="#60a5fa" stroke-width="1.5"/><line x1="70" y1="5" x2="58" y2="30" stroke="#60a5fa" stroke-width="1.5"/></g></svg></div>` : '') + (fx && fxType === 'smoke' ? `<div class="kpi-fx-factory"><svg viewBox="0 0 100 100" preserveAspectRatio="xMaxYMax meet"><rect x="70" y="30" width="10" height="60" fill="#e0e0e0"/><rect x="70" y="35" width="10" height="8" fill="#d94b41"/><rect x="70" y="50" width="10" height="8" fill="#d94b41"/><rect x="70" y="65" width="10" height="8" fill="#d94b41"/><rect x="40" y="10" width="12" height="80" fill="#e0e0e0"/><rect x="40" y="15" width="12" height="10" fill="#d94b41"/><rect x="40" y="35" width="12" height="10" fill="#d94b41"/><rect x="40" y="55" width="12" height="10" fill="#d94b41"/><rect x="40" y="75" width="12" height="10" fill="#d94b41"/><rect x="15" y="50" width="8" height="40" fill="#e0e0e0"/><rect x="15" y="55" width="8" height="6" fill="#d94b41"/><rect x="15" y="70" width="8" height="6" fill="#d94b41"/><path d="M 5,90 L 95,90 L 95,75 L 80,75 L 80,80 L 60,80 L 60,70 L 30,70 L 30,85 L 5,85 Z" fill="#c43d34"/></svg></div>` : '') + (fx && fxType === 'lightning' ? `<div class="kpi-fx-tower"><svg viewBox="0 0 100 100" preserveAspectRatio="xMaxYMax meet"><g stroke="#3a4a5a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="30" y1="90" x2="45" y2="20"/><line x1="70" y1="90" x2="55" y2="20"/><line x1="45" y1="20" x2="50" y2="10"/><line x1="55" y1="20" x2="50" y2="10"/><line x1="20" y1="40" x2="80" y2="40"/><line x1="25" y1="60" x2="75" y2="60"/><line x1="35" y1="80" x2="65" y2="80"/><line x1="42" y1="40" x2="33" y2="60"/><line x1="58" y1="40" x2="67" y2="60"/><line x1="42" y1="40" x2="58" y2="60"/><line x1="58" y1="40" x2="42" y2="60"/></g></svg></div>` : ''); const animMap = { 'Scope 1: Fleet + DG + LPG': 'anim-pulse', 'Petrol consumption': 'anim-fuel', 'Petrol emissions': 'anim-smoke', 'Fleet diesel consumption': 'anim-bus', 'Fleet diesel emissions': 'anim-bus-smoke', 'DG diesel consumption': 'anim-vibrate', 'DG diesel emissions': 'anim-generator-smoke', 'LPG consumption': 'anim-fuel', 'LPG emissions': 'anim-smoke', 'Combined diesel emissions': 'anim-combined-smoke' }; const iconClass = animMap[title] ? `icon kpi-icon ${animMap[title]}` : 'icon'; return `<article class="kpi${cls}" style="--a:${accent}" onclick="openKpiModal(this)">${inner}<div class="${iconClass}">${ic(icon)}</div><div class="label">${title}</div><div class="value"><span class="counter-val" data-val="${value}" data-dec="${dec}">0</span><small>${unit}</small></div><div class="trend">${trendHtml(value, prev, lowerGood)}</div></article>` }

const renderNumericKpi = kpi;
/* The domain whose cards are being rendered, so an unavailable card can show
   the backend's reason (for example "annual data available under Full Year"). */
let kpiDomain = null;
/* "20+ programs": the source reported a lower bound, not an exact count. */
function atLeast(field, unit) { return outreach.qualifiers?.[field] === 'AT_LEAST' ? `+ ${unit}` : unit }
function inDomain(domain, render) { kpiDomain = domain; try { return render(); } finally { kpiDomain = null; } }
/* KPI card -> timeline value code. The backend resolves, per selected period,
   which verified number a card shows (display item): the period's own value,
   else a complete annual value, else a complete YTD value, else a static
   reference. A card with no display item is omitted - never "Unavailable".
   The display value is presentation only: charts, exports and calculations
   keep reading the true-granularity `values`. */
/* Waste is published in kg and shown in kg (e.g. 55,339.55 kg). */
const kgOrTonnes = kg => ({ value: kg, unit: 'kg', dec: 2 });
const CARD_DISPLAY = {
  'Renewable energy used': { code: 'renewable_electricity_kwh' },
  'Total grid electricity consumed': { code: 'grid_total_kwh' },
  'Total water recycled': { code: 'water_recycled_kl' },
  'Total waste generated': { code: 'total_waste_generated_kg', transform: kgOrTonnes },
  'Landfill diversion': { code: 'landfill_diversion_pct' },
  'Total water usage': { code: 'water_consumed_kl' },
  'Outreach impact': { code: 'total_participants' },
  'Petrol emissions': { code: 'transport_petrol_emissions' },
  'Fleet diesel emissions': { code: 'transport_diesel_emissions' },
  'DG diesel emissions': { code: 'dg_diesel_emissions' },
  // DG activity. The backend states which pathway a period used: generation
  // (kWh) with litres DERIVED from it, or legacy source-reported litres. The
  // card titles follow that origin; nothing is converted in the browser.
  'DG generation': { code: 'dg_generation_kwh' },
  'Derived DG diesel': { code: 'dg_diesel_litres', when: item => item.activity_origin === 'DERIVED_FROM_KWH' },
  'DG diesel consumption': { code: 'dg_diesel_litres', when: item => item.activity_origin !== 'DERIVED_FROM_KWH' },
  'LPG emissions': { code: 'lpg_emissions', transform: v => ({ value: v, dec: emissionDecimals(v) }) },
  // Governed LPG activity: weight in kg (backend lpg_weight_kg; never converted in the browser).
  'LPG consumption': { code: 'lpg_weight_kg', transform: v => ({ value: v, unit: 'kg', dec: activityDecimals(v) }) },
  'Grid electricity emissions': { code: 'scope2_tco2e' },
  'Operational GHG per capita': { code: 'operational_ghg_per_capita_kgco2e' },
  // Public title (Overview + GHG) for the same governed per-person GHG value.
  'Per capita emissions': { code: 'operational_ghg_per_capita_kgco2e' },
  'Estimated avoided grid emissions': { code: 'estimated_avoided_grid_emissions_tco2e' },
  // GHG page title for the same governed metric (renewable kWh × grid factor).
  'Reduction through renewables': { code: 'estimated_avoided_grid_emissions_tco2e' },
  'Total water consumption': { code: 'water_consumed_kl' },
  'Consumption per capita': { code: 'water_per_capita_l' },
  'Total outreach programs delivered': { code: 'total_programs' },
  'Total participants served': { code: 'total_participants' },
  'Partner organizations': { code: 'partner_organizations' },
  'Saplings planted': { code: 'saplings_planted' },
  'Experts involved': { code: 'experts_involved' }
};
/* Energy page primary KPIs: ONE definition for every selection (a month, YTD,
   Full Year, any year). The selected period changes the values only - never
   which cards exist, their titles or their order. Each card is the backend's
   own value for its code; nothing is added up here, and the solar water heater
   (thermal) is not part of any of them. */
const ENERGY_PRIMARY_KPIS = [
  { title: 'Total electricity consumption', code: 'total_electricity_consumption_kwh', series: 'totalElectricityKwh', accent: 'cyan', icon: 'bolt', lowerGood: true },
  { title: 'Total grid electricity consumption', code: 'grid_total_kwh', series: 'elecKwh', accent: 'cyan', icon: 'plug', lowerGood: true, compare: true },
  { title: 'Solar PV electricity generation', code: 'renewable_on_campus_kwh', series: 'reOnCampusKwh', accent: 'emerald', icon: 'sun', lowerGood: false },
  { title: 'Procured green energy', code: 'renewable_procured_kwh', series: 'reProcuredKwh', accent: 'emerald', icon: 'leaf', lowerGood: false }
];
ENERGY_PRIMARY_KPIS.forEach(card => { CARD_DISPLAY[card.title] = { code: card.code }; });
/* A primary KPI the backend has no value for keeps its place: "—", never 0. */
function missingKpiHtml(title, unit, accent, icon) {
  return `<article class="kpi kpi-unreported" style="--a:${accent}"><div class="icon">${ic(icon)}</div><div class="label">${title}</div><div class="value"><span>—</span><small>${unit}</small></div><div class="trend"><span>No value for this period</span></div></article>`;
}
/* Always the same four cards. A value the backend does not have is shown as
   having no value - never as zero, and never by dropping or swapping the card. */
function energyPrimaryKpisHtml(d, month) {
  return ENERGY_PRIMARY_KPIS.map(card => {
    const accent = colors[card.accent];
    const prev = card.compare ? previousValue(card.series) : null;
    return kpi(card.title, valFor(d, d[card.series], month), 'kWh', accent, card.icon, prev, card.lowerGood, 0)
      || missingKpiHtml(card.title, 'kWh', accent, card.icon);
  }).join('');
}
/* Water page primary KPIs: ONE definition for every selection (a month, YTD,
   Full Year, any year). The period changes the values and their context
   label only - never which cards exist, their titles or their order. Each
   card is the backend's own value for its code: total consumption and per
   capita are backend calculations, recycled water is the governed source /
   resolved aggregate. Nothing is summed, divided or estimated here; the
   source components (TWAD, borewell, private) stay in the Water charts. */
const WATER_PRIMARY_KPIS = [
  { title: 'Total water consumption', code: 'water_consumed_kl', series: 'waterKL', unit: 'KL', dec: 0, accent: 'cyan', icon: 'droplet', lowerGood: true, compare: true },
  { title: 'Consumption per capita', code: 'water_per_capita_l', series: 'waterPerCapitaL', unit: 'L/person', dec: 2, accent: 'teal', icon: 'users', lowerGood: true },
  { title: 'Total water recycled', code: 'water_recycled_kl', series: 'waterRecycledKL', unit: 'KL', dec: 0, accent: 'emerald', icon: 'repeat', lowerGood: false }
];
WATER_PRIMARY_KPIS.forEach(card => { CARD_DISPLAY[card.title] = { code: card.code }; });
/* Always the same three cards; a value the backend does not have shows "—". */
function waterPrimaryKpisHtml(d, month) {
  return WATER_PRIMARY_KPIS.map(card => {
    const accent = colors[card.accent];
    // Same-window comparison with the previous year (previousValue), total consumption only.
    const prev = card.compare ? previousValue(card.series) : null;
    return kpi(card.title, valFor(d, d[card.series], month), card.unit, accent, card.icon, prev, card.lowerGood, card.dec)
      || missingKpiHtml(card.title, card.unit, accent, card.icon);
  }).join('');
}
/* Waste page primary KPIs: ONE definition for every selection. Waste is a
   year-aggregate domain, so each card shows the year's current Full Year / YTD
   value the backend resolved (its display item) whichever month is selected.
   The backend publishes kg and kg/person; `perUnit` is a unit conversion for
   display only (kg -> tons). Diverted from landfill is the backend's governed
   value (dry waste) - no percentage is applied here. */
const WASTE_PRIMARY_KPIS = [
  { title: 'Total waste generated', code: 'total_waste_generated_kg', unit: 'tons', perUnit: 1000, accent: 'orange', icon: 'trash', lowerGood: true },
  { title: 'Total waste diverted from landfill', code: 'waste_diverted_from_landfill_kg', unit: 'tons', perUnit: 1000, accent: 'emerald', icon: 'shield', lowerGood: false },
  { title: 'Waste contribution per person', code: 'waste_per_capita_kg', unit: 'kg/person', perUnit: 1, accent: 'teal', icon: 'users', lowerGood: true }
];
function wastePrimaryKpisHtml() {
  return WASTE_PRIMARY_KPIS.map(card => {
    const accent = colors[card.accent];
    const item = displayFor(card.code);
    if (!item) return missingKpiHtml(card.title, card.unit, accent, card.icon);
    const html = renderNumericKpi(card.title, item.value / card.perUnit, card.unit, accent, card.icon, null, card.lowerGood, 1);
    return html.replace('<div class="trend">', `${sourceBadge(item.display_label, item.display_context)}<div class="trend">`);
  }).join('');
}
/* Static institutional references (green_master.csv), shown for every period. */
const STATIC_CARDS = new Set([
  'Total green cover', 'Maintained vegetation', 'Natural vegetation', 'Total tree species identified',
  'Total trees', 'Green cover zones'
]);
const STATIC_LABEL = 'Institutional Reference';
/* The backend's display item for a value code in the current selection. */
function displayFor(code) {
  const { month, d } = currentPeriod();
  const item = code ? d?.display?.[month === 'all' ? 'all' : +month]?.[code] : null;
  return item && item.value != null ? item : null;
}
/* {value, label, context} for a code, or null when nothing trustworthy exists. */
function shownValue(code) {
  const item = displayFor(code);
  return item ? {
    value: item.value, label: item.display_label, context: item.display_context,
    calculation_status: item.calculation_status, contributors: item.contributors,
    missing_contributors: item.missing_contributors
  } : null;
}
/* ---- GHG completeness (available-data methodology) ----
   Scope 1, Scope 2, Operational GHG and per capita are calculated by the
   backend from the emission sources that exist, and each value states whether
   it is COMPLETE or PARTIAL. The summary areas stay minimal: a partial value
   gets one small footnote and a complete value gets nothing. The contributor
   detail the API also sends is shown in the Data Explorer, not here. */
const prettyUnit = unit => String(unit || '').replace('CO2', 'CO₂');
const PARTIAL_NOTE = '*Based on available reported contributors';
function completenessOf(item) {
  if (!item || !item.calculation_status) return null;
  return { status: item.calculation_status, partial: item.calculation_status === 'PARTIAL' };
}
/* The single footnote under a partial GHG number; empty for a complete one. */
function partialNoteHtml(item) {
  return completenessOf(item)?.partial ? `<div class="partial-note">${PARTIAL_NOTE}</div>` : '';
}
/* Tooltip lines for one month of a GHG chart: the total and its status only. */
function ghgStatusLines(d, index) {
  const item = d?.periodMeta?.[index]?.values?.operational_ghg_tco2e;
  const meta = completenessOf(item);
  if (!meta || item.value == null) return [];
  return [`Operational GHG: ${fmt(item.value, 3)} ${prettyUnit(item.unit)}`, `Status: ${meta.partial ? 'Partial' : 'Complete'}`];
}
/* ---- end GHG completeness ---- */
/* A Full Year / YTD DG litre total that spans the methodology change: some
   months are source-reported litres and some are derived from kWh. */
function dgOriginNoteHtml(item) {
  return item?.activity_origin === 'MIXED'
    ? '<div class="partial-note">*Includes diesel litres derived from DG generation (kWh)</div>' : '';
}
function sourceBadge(label, context) {
  return label ? `<div class="kpi-source${context ? ' is-context' : ''}">${label}</div>` : '';
}
kpi = function (title, value, unit, accent, icon, prev, lowerGood = true, dec = 2, fxType = null) {
  const spec = CARD_DISPLAY[title];
  let label = null, context = false, status = '';
  if (spec) {
    const item = displayFor(spec.code);
    if (!item) return '';  // no trustworthy number for this selection: omit the card
    if (spec.when && !spec.when(item)) return '';
    status = partialNoteHtml(item) + dgOriginNoteHtml(item);
    const out = spec.transform ? spec.transform(item.value, item) : {};
    value = out.value != null ? out.value : item.value;
    if (out.unit) unit = out.unit;
    if (out.dec != null) dec = out.dec;
    if (item.qualifier === 'AT_LEAST' && !String(unit).startsWith('+')) unit = `+ ${unit}`;
    label = item.display_label;
    context = item.display_context;
    if (context) prev = null;  // a contextual number is never compared as if it were this period's
  } else if (value == null) {
    return '';
  } else {
    label = STATIC_CARDS.has(title) ? STATIC_LABEL : null;
    context = STATIC_CARDS.has(title);
  }
  const html = renderNumericKpi(title, value, unit, accent, icon, prev, lowerGood, dec, fxType);
  return html.replace('<div class="trend">', `${sourceBadge(label, context)}${status}<div class="trend">`);
};
/* Public Overview card: same card, minus the "base / no comparison"
   placeholder and the static-reference badge. Values, real comparisons and
   period labels are untouched; other pages keep using kpi() directly. */
function withoutNoComparison(html) {
  return html.replace(`<div class="trend">${NO_COMPARISON_HTML}</div>`, '').replace('<div class="trend"></div>', '');
}
function overviewKpi(...args) {
  return withoutNoComparison(kpi(...args)).replace(sourceBadge(STATIC_LABEL, true), '');
}
/* GHG page card: same card without the "base / no comparison" placeholder. */
function ghgKpi(...args) { return withoutNoComparison(kpi(...args)) }

/* "Jun 2026 · Verified historical record" / "2025 Full Year · Aggregated from
   verified monthly records (some values partial)". */
function describeSelection(year, month, d) {
  if (publication.state === 'error') return 'Published data unavailable';
  const meta = d?.periodMeta?.[month === 'all' ? 'all' : +month];
  if (!meta) return `${periodLabel(year, month)} · No published or verified data`;
  const source = {
    published_release: `Published release ${meta.release_version || ''}`.trim(),
    historical_verified: 'Verified historical record',
    historical_aggregate: 'Aggregated from verified monthly records',
    published_release_aggregate: 'Aggregated from published releases',
    mixed_aggregate: 'Aggregated from published releases and verified history'
  }[meta.source_kind] || meta.source_kind;
  const partial = meta.coverage_status === 'partial' ? ' (some values cover part of the period)' : '';
  return `${meta.label} · ${source}${partial}`;
}

/* GHG page hero. Always the same structure: the total, the Scope contribution
   bar and both Scope splits. Each figure is the backend's display item, which
   may be PARTIAL (available emission sources only): it then carries one small
   footnote, never a contributor list. A figure without a display item shows
   "—" with the reason; it is never treated as zero, and nothing is summed here. */
function ghgHeroHtml() {
  const total = shownValue('operational_ghg_tco2e');
  const s1 = shownValue('scope1_tco2e'), s2 = shownValue('scope2_tco2e');
  const { year, month, d } = currentPeriod();
  const period = periodLabel(year, month);
  const raw = d?.periodMeta?.[month === 'all' ? 'all' : +month]?.values || {};
  // Why a figure is absent, from the API's own state: a partial value is
  // withheld (never shown), an unavailable one lacks inputs, else no record.
  const partial = code => raw[code]?.coverage_status === 'partial';
  const missingText = code => partial(code) ? `Incomplete for ${period}` : raw[code] ? `Not available for ${period}` : `No data for ${period}`;
  const missingClause = ([name, code]) => partial(code) ? `${name} incomplete` : raw[code] ? `${name} not available` : `no ${name} data`;
  const counter = (v, size) => `<span class="counter-val" data-val="${v}" data-dec="2">0</span><span style="font-size:${size}; font-weight:500; color:var(--muted);">tCO₂e</span>`;
  const dash = '<span style="color:var(--muted);">—</span>';
  const split = (item, code, icon, dot, title, note) => `
        <div class="ghg-split">
          <div class="ghg-split-icon">${ic(icon)}</div>
          <div>
            <div class="ghg-split-head"><div class="ghg-split-dot" style="background: ${dot};"></div>${title}</div>
            <div class="ghg-split-val">${item ? counter(item.value, '13px') : dash}</div>
            ${item ? `${sourceBadge(item.label, item.context)}
            ${partialNoteHtml(item)}
            <div class="ghg-split-note">${note}</div>` : `<div class="ghg-split-note">${missingText(code)}</div>`}
          </div>
        </div>`;
  const missing = [!s1 && ['Scope 1', 'scope1_tco2e'], !s2 && ['Scope 2', 'scope2_tco2e']].filter(Boolean);
  const totalNote = total ? '' : missing.length
    ? `Total not shown — ${missing.map(missingClause).join(', ')} for ${period}`
    : `Total not published for ${period}`;
  const sameSource = total && s1 && s2 && total.label === s1.label && total.label === s2.label;
  return `
    <div class="ghg-hero">
      <div class="ghg-top">
        <div>
          <div class="ghg-title-row"><div class="icon">${ic('globe')}</div>Gross Organizational Emissions</div>
          <div class="ghg-value-row">${total ? counter(total.value, '1.2rem') : dash}</div>
          ${total ? `${sourceBadge(total.label, total.context)}${partialNoteHtml(total)}` : `<div class="ghg-split-note">${totalNote}</div>`}
        </div>
        <div class="ghg-badge">* Scope 3 emissions not included</div>
      </div>
      <div class="ghg-bar-container"${sameSource ? '' : ' title="Scope contribution needs both Scope 1 and Scope 2 for the same period"'}>
        ${sameSource ? `<div class="ghg-bar-1" style="width: ${total.value > 0 ? (s1.value / total.value) * 100 : 0}%;"></div>
        <div class="ghg-bar-2" style="width: ${total.value > 0 ? (s2.value / total.value) * 100 : 0}%;"></div>` : ''}
      </div>
      <div class="ghg-splits">
        ${split(s1, 'scope1_tco2e', 'factory', colors.emerald, 'Scope 1 Emissions', '* Petrol, Fleet Diesel, DG Diesel, LPG')}
        ${split(s2, 'scope2_tco2e', 'bolt', 'var(--muted)', 'Scope 2 Emissions', '* Grid electricity')}
      </div>
    </div>`;
}

/* Recompute the headline figures for the current filters and rebuild
   every page's KPI grid plus the public highlights strip. */
function makeKpis() {
  const { year, month, d } = currentPeriod();
  const hasPublication = selectionHasPublication(d, month);
  const outreachForPeriod = outreach.published;
  const scope1 = valFor(d, d.scope1Full, month), petrol = valFor(d, d.petrolEm, month), scope2 = valFor(d, d.elecEm, month), elec = valFor(d, d.elecKwh, month);
  const re = valFor(d, d.reKwh, month), avoid = valFor(d, d.avoidEm, month);
  const reShare = valFor(d, d.renewableSharePct, month);
  const gross = valFor(d, d.operationalGHG, month);
  const operationalPerCapita = valFor(d, d.perCapita, month);

  /* Shared with the Waste/Water KPI blocks further down - computed once
     here so the Overview strip and those pages can't drift apart. */
  const publishedWaste = hasPublication && (month === 'all'
    ? d.totalWaste.aggregate != null
    : Boolean(d.wastePublishedMonths?.[+month]));
  const wasteTotalKg = valFor(d, d.totalWaste, month);
  const wasteHasData = publishedWaste && wasteTotalKg != null;
  /* Only the frozen total is authoritative; a missing total is not rebuilt
     from its inputs in the browser. */
  const wasteTot = wasteHasData ? wasteTotalKg / 1000 : null;
  // Static institutional reference; never inferred from monthly waste.
  const landfillDiversionPct = d.landfillDiversionPct;
  const wasteShow = wasteDisplay(wasteTot);
  const waterMonths = monthsWithData(d.waterKL);
  const waterRecycled = valFor(d, d.waterRecycledKL, month);
  const waterKL = valFor(d, d.waterKL, month);

  periodText.textContent = describeSelection(year, month, d);
  heroGHG(gross, year, month, d, avoid, operationalPerCapita);
  const hsSolar = document.getElementById('hs-solar-val'), hsAdmin = document.getElementById('hs-admin-val'), hsDg = document.getElementById('hs-dg-val');
  if (hsSolar) hsSolar.textContent = fmt(re, 0) + ' kWh';
  if (hsAdmin) hsAdmin.textContent = fmt(elec, 0) + ' kWh';
  if (hsDg) hsDg.textContent = fmt(valFor(d, d.dgEm, month), 2) + ' tCO₂e';
  document.getElementById('overviewKpis').innerHTML = [
    overviewKpi('Renewable energy used', re, 'kWh', colors.emerald, 'sun', previousValue('reKwh'), false, 0, 'solarvideo'),
    overviewKpi('Total grid electricity consumed', elec, 'kWh', colors.cyan, 'bolt', previousValue('elecKwh'), true, 0, 'elecmetervideo'),
    inDomain('water', () => overviewKpi('Total water recycled', hasPublication ? waterRecycled : null, 'KL', colors.cyan, 'repeat', null, false, 0, 'rewatervideo')),
    inDomain('waste', () => overviewKpi('Total waste generated', wasteTot == null ? null : wasteTot * wasteShow.factor, wasteShow.unit, colors.orange, 'trash', null, true, wasteShow.dec, 'convwastevideo')),
    overviewKpi('Landfill diversion', landfillDiversionPct, '%', colors.lime, 'shield', null, false, 1, 'landfillvideo'),
    inDomain('water', () => overviewKpi('Total water usage', waterKL, 'KL', colors.cyan, 'droplet', null, true, 0, 'watervideo')),
    overviewKpi('Total green cover', hasPublication ? green.totalGreenCoverPct : null, '%', colors.emerald, 'tree', null, false, 0, 'leavesvideo'),
    inDomain('outreach', () => overviewKpi('Outreach impact', outreachForPeriod ? outreach.participantsServed : null, outreach.qualifiers?.participantsServed === 'AT_LEAST' ? '+ people' : 'people', colors.gold, 'users', null, false, 0, 'earthvideo'))
  ].join('');
  document.getElementById('ghgKpis').innerHTML = [
    `<style>
      @keyframes ghgBarGrow { from { width: 0; } }
      @keyframes ghgFadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
      .ghg-hero {
        grid-column: 1 / -1;
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 20px;
        padding: 24px 32px;
        margin-bottom: 24px;
        box-shadow: var(--shadow);
        animation: ghgFadeIn 0.5s ease-out;
      }
      .ghg-top { display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 16px; margin-bottom: 24px; }
      .ghg-title-row { display: flex; align-items: center; gap: 8px; color: var(--ink); font-weight: 700; font-size: 15px; margin-bottom: 8px; opacity: 0.8; }
      .ghg-title-row .icon { width: 18px; height: 18px; }
      .ghg-value-row { font-size: clamp(36px, 5vw, 52px); font-family: 'IBM Plex Mono', monospace; font-weight: 700; color: var(--ink); display: flex; align-items: baseline; gap: 8px; line-height: 1; }
      .ghg-badge { background: var(--red-soft, rgba(239,68,68,0.1)); color: var(--red, #ef4444); padding: 6px 12px; border-radius: 6px; font-size: 11px; font-weight: 700; margin-bottom: 8px; }
      .ghg-bar-container { display: flex; height: 10px; border-radius: 99px; overflow: hidden; background: var(--line-strong); margin-bottom: 28px; box-shadow: inset 0 2px 4px rgba(0,0,0,0.05); }
      .ghg-bar-1 { background: ${colors.emerald}; height: 100%; animation: ghgBarGrow 1s cubic-bezier(0.25, 1, 0.5, 1) forwards; }
      .ghg-bar-2 { background: var(--muted); height: 100%; animation: ghgBarGrow 1s cubic-bezier(0.25, 1, 0.5, 1) forwards; }
      .ghg-splits { display: flex; flex-wrap: wrap; gap: 24px; }
      .ghg-split { flex: 1; min-width: 240px; display: flex; gap: 16px; }
      .ghg-split-icon { width: 44px; height: 44px; border-radius: 50%; background: var(--surface2); display: flex; align-items: center; justify-content: center; color: var(--ink); flex-shrink: 0; }
      .ghg-split-icon svg { width: 20px; height: 20px; }
      .ghg-split-head { display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--faint); font-weight: 600; margin-bottom: 4px; }
      .ghg-split-dot { width: 8px; height: 8px; border-radius: 50%; }
      .ghg-split-val { font-size: 28px; font-family: 'IBM Plex Mono', monospace; font-weight: 700; color: var(--ink); display: flex; align-items: baseline; gap: 6px; margin-bottom: 6px; }
      .ghg-split-note { font-size: 11.5px; color: var(--faint); }
      @media (max-width: 600px) {
        #ghgKpis { grid-template-columns: 1fr !important; }
        .ghg-hero { padding: 20px; }
        .ghg-split { min-width: 0; flex-basis: 100%; }
      }
    </style>
    ${ghgHeroHtml()}`,
    /* Governed component results straight from the frozen release. */
    inDomain('transport', () => ghgKpi('Petrol emissions', petrol, 'tCO₂e', colors.teal, 'fuel', previousValue('petrolEm'), true)),
    inDomain('transport', () => ghgKpi('Fleet diesel emissions', valFor(d, d.trDieselEm, month), 'tCO₂e', colors.gold, 'cloud', previousValue('trDieselEm'), true)),
    inDomain('transport', () => ghgKpi('DG diesel emissions', valFor(d, d.dgEm, month), 'tCO₂e', colors.orange, 'factory', previousValue('dgEm'), true)),
    // DG activity behind that emission: source kWh + derived litres, or legacy source litres.
    inDomain('transport', () => ghgKpi('DG generation', valFor(d, d.dgKwh, month), 'kWh', colors.orange, 'bolt', null, true, activityDecimals(valFor(d, d.dgKwh, month)))),
    inDomain('transport', () => ghgKpi('Derived DG diesel', valFor(d, d.dgL, month), 'L', colors.orange, 'fuel', null, true, 2)),
    inDomain('transport', () => ghgKpi('DG diesel consumption', valFor(d, d.dgL, month), 'L', colors.orange, 'fuel', previousValue('dgL'), true, 2)),
    inDomain('lpg', () => ghgKpi('LPG emissions', valFor(d, d.lpgEm, month), 'tCO₂e', colors.violet, 'flame', previousValue('lpgEm'), true, emissionDecimals(valFor(d, d.lpgEm, month)))),
    inDomain('lpg', () => ghgKpi('LPG consumption', valFor(d, d.lpgKg, month), 'kg', colors.violet, 'battery', previousValue('lpgKg'), true, activityDecimals(valFor(d, d.lpgKg, month)))),
    inDomain('energy', () => ghgKpi('Grid electricity emissions', scope2, 'tCO₂e', colors.cyan, 'bolt', previousValue('elecEm'), true)),
    ghgKpi('Per capita emissions', operationalPerCapita, 'kgCO₂e/person', colors.blue, 'users', null, true, 3),
    // More avoided emissions is the good direction (lowerGood = false).
    ghgKpi('Reduction through renewables', avoid, 'tCO₂e', colors.emerald, 'leaf', previousValue('avoidEm'), false, 3)
  ].join('');

  const elecMix = elecMixView(d, month);
  const gridPctStr = elecMix.gridPct, rePctStr = elecMix.rePct;
  // These source metrics are the values frozen in the active public release.
  const solarWaterHeaterVal = valFor(d, d.solarWaterHeaterKwh, month);

  const elecMixWidget = document.getElementById('elecMixWidget');
  if (elecMixWidget) {
    // Same selected-period components the donut draws (drawCharts).
    const elecNote = compositionNote(periodComposition(d, month, ELEC_MIX_PARTS), periodLabel(year, month));
    // Layout rules live in styles.css ("GHG mix widgets") so they never depend on which widget rendered.
    elecMixWidget.innerHTML = `
      <div class="elec-mix-widget">
        <div class="elec-mix-title-box">
          <div class="elec-mix-icon">${ic('bolt')}</div>
          <div>
            <h3 style="margin: 0 0 4px 0;">Electricity Mix</h3>
            <p class="hint" style="margin: 0;">Grid vs Renewable — ${periodLabel(year, month)}</p>
            ${elecNote ? `<p class="hint" style="margin: 4px 0 0;">${elecNote}</p>` : ''}
          </div>
        </div>
        
        <div class="elec-mix-chart-area">
          <div class="elec-label-block elec-label-left">
            <div class="elec-pct elec-pct-re">${rePctStr}</div>
            <div class="elec-sub">Renewable<br>energy</div>
            <div class="elec-desc">On-campus and procured renewable sources</div>
          </div>
          
          <div class="elec-mix-chart-container">
            <canvas id="elecMixChartCanvas"></canvas>
          </div>
          
          <div class="elec-label-block elec-label-right">
            <div class="elec-pct elec-pct-grid">${gridPctStr}</div>
            <div class="elec-sub">Grid<br>electricity</div>
            <div class="elec-desc">Higher carbon intensity</div>
          </div>
        </div>
      </div>
    `;
    if (!elecMix.available) {
      elecMixWidget.innerHTML = '';
    }
  }

  const fuelMixWidget = document.getElementById('fuelMixWidget');
  if (fuelMixWidget) {
    // Shares of the backend Scope 1 total (display ratios of governed results).
    const { dieselPct, petrolPct, lpgPct, fleetPct, dgPct } = fuelMixView(d, month);
    // Same selected-period components the donut draws (drawCharts).
    const fuelNote = compositionNote(periodComposition(d, month, FUEL_MIX_PARTS), periodLabel(year, month));

    fuelMixWidget.innerHTML = `
      <div class="elec-mix-widget fuel-mix-widget">
        <div class="elec-mix-title-box">
          <div class="elec-mix-icon" style="background: rgba(221, 107, 32, 0.1); color: var(--orange, #dd6b20);">${ic('flame')}</div>
          <div>
            <h3 style="margin: 0 0 4px 0;">Fossil Fuel Emissions Mix</h3>
            <p class="hint" style="margin: 0;">Share of published fuel-source emissions — ${periodLabel(year, month)}</p>
          </div>
        </div>
        
        <div class="fuel-mix-layout">
          <div class="fuel-mix-side left">
            <div class="fuel-mix-item">
              <div class="elec-pct" style="color: var(--violet, #6b5b95);">${lpgPct}</div>
              <div class="elec-sub">LPG<br>fuel</div>
            </div>
            <div class="fuel-mix-item">
              <div class="elec-pct" style="color: var(--teal, #319795);">${petrolPct}</div>
              <div class="elec-sub">Petrol<br>fuel</div>
            </div>
          </div>
          
          <div class="elec-mix-chart-container">
            <canvas id="fuelMixChartCanvas"></canvas>
          </div>
          
          <div class="fuel-mix-side right">
            <div class="fuel-mix-item">
              <div class="elec-pct" style="color: var(--orange, #dd6b20);">${dieselPct}</div>
              <div class="elec-sub">Diesel<br>emissions</div>
              <div class="fuel-mix-breakdown">
                ${fleetPct ? `<span><i style="background:${colors.gold}"></i>Fleet diesel <b>${fleetPct}</b></span>` : ''}
                ${dgPct ? `<span><i style="background:${colors.orange}"></i>DG diesel <b>${dgPct}</b></span>` : ''}
              </div>
            </div>
          </div>
        </div>
        ${fuelNote ? `<p class="hint" style="margin: 16px 0 0;">${fuelNote}</p>` : ''}
      </div>
    `;
  }

  const wasteKpisEl = document.getElementById('wasteKpis');
  if (wasteKpisEl) {
    wasteKpisEl.innerHTML = wastePrimaryKpisHtml();
  }

  const waterKpisEl = document.getElementById('waterKpis');
  if (waterKpisEl) {
    waterKpisEl.innerHTML = inDomain('water', () => waterPrimaryKpisHtml(d, month));
  }

  const greenKpisEl = document.getElementById('greenKpis');
  if (greenKpisEl) {
    greenKpisEl.innerHTML = [
      kpi('Total green cover', green.totalGreenCoverPct, '%', colors.emerald, 'globe', null, false, 0),
      kpi('Maintained vegetation', green.maintainedVegetationAcres, 'acres', colors.teal, 'leaf', null, false, 0),
      kpi('Natural vegetation', green.naturalVegetationAcres, 'acres', colors.lime, 'tree', null, false, 0),
      kpi('Total tree species identified', green.totalSpecies, 'species', colors.cyan, 'sprout', null, false, 0),
      kpi('Total trees', green.totalTrees, 'trees', colors.emerald, 'tree', null, false, 0),
      kpi('Green cover zones', green.zones.length || null, 'zones', colors.teal, 'globe', null, false, 0)
    ].join('');
  }

  const outreachKpisEl = document.getElementById('outreachKpis');
  if (outreachKpisEl) {
    {
      const volunteers = shownValue('volunteers_engaged'), hours = shownValue('volunteer_hours');
      const volunteersKpi = volunteers || hours ? `
        <article class="kpi kpi-duo" style="--a:${colors.orange}" onclick="openKpiModal(this)">
          <div class="icon">${ic('spark')}</div>
          <div class="label">Volunteers engaged</div>
          <div class="duo-grid">
            ${volunteers ? `<div>
              <div class="duo-num"><span class="counter-val" data-val="${volunteers.value}" data-dec="0">0</span>${displayFor('volunteers_engaged').qualifier === 'AT_LEAST' ? '<small>+</small>' : ''}</div>
              <div class="duo-label">Volunteers</div>
            </div>` : ''}
            ${hours ? `<div>
              <div class="duo-num"><span class="counter-val" data-val="${hours.value}" data-dec="1">0</span><small>${displayFor('volunteer_hours').qualifier === 'AT_LEAST' ? '+ ' : ''}hrs</small></div>
              <div class="duo-label">Hours contributed</div>
            </div>` : ''}
          </div>
          ${sourceBadge((volunteers || hours).label, (volunteers || hours).context)}
          <div class="trend"><b class="neutral">base</b><span>no comparison</span></div>
        </article>
      ` : '';
      outreachKpisEl.innerHTML = [
        kpi('Total outreach programs delivered', outreach.programsDelivered, atLeast('programsDelivered', 'programs'), colors.gold, 'check', null, false, 0),
        kpi('Total participants served', outreach.participantsServed, atLeast('participantsServed', 'people'), colors.cyan, 'users', null, false, 0),
        kpi('Partner organizations', outreach.partnerOrganizations, atLeast('partnerOrganizations', 'organizations'), colors.violet, 'building', null, false, 0),
        kpi('Saplings planted', outreach.saplingsPlanted, atLeast('saplingsPlanted', 'saplings'), colors.emerald, 'sprout', null, false, 0),
        kpi('Experts involved', outreach.expertsInvolved, atLeast('expertsInvolved', 'experts'), colors.teal, 'globe', null, false, 0),
        volunteersKpi
      ].join('');
    }
  }

  const scope1KpisEl = document.getElementById('scope1Kpis');
  if (scope1KpisEl) {
    scope1KpisEl.innerHTML = [
      kpi('Scope 1 emissions', scope1, 'tCO₂e', colors.orange, 'cloud', previousValue('scope1Full'), true),
      kpi('Petrol consumption', valFor(d, d.petrolL, month), 'L', colors.teal, 'car', previousValue('petrolL'), true, 0),
      kpi('Petrol emissions', petrol, 'tCO₂e', colors.teal, 'fuel', previousValue('petrolEm'), true),
      kpi('Fleet diesel consumption', valFor(d, d.trDieselL, month), 'L', colors.gold, 'bus', previousValue('trDieselL'), true, 0),
      kpi('Fleet diesel emissions', valFor(d, d.trDieselEm, month), 'tCO₂e', colors.gold, 'cloud', previousValue('trDieselEm'), true),
      kpi('DG diesel consumption', valFor(d, d.dgL, month), 'L', colors.orange, 'gear', previousValue('dgL'), true, 0),
      kpi('DG diesel emissions', valFor(d, d.dgEm, month), 'tCO₂e', colors.orange, 'factory', previousValue('dgEm'), true),
      kpi('LPG consumption', valFor(d, d.lpgKg, month), 'kg', colors.violet, 'battery', previousValue('lpgKg'), true, activityDecimals(valFor(d, d.lpgKg, month))),
      kpi('LPG emissions', valFor(d, d.lpgEm, month), 'tCO₂e', colors.violet, 'flame', previousValue('lpgEm'), true, emissionDecimals(valFor(d, d.lpgEm, month))),
      kpi('Combined diesel emissions', null, 'tCO₂e', colors.red, 'flame', null, true)
    ].join('');
  }
  const scope2KpisEl = document.getElementById('scope2Kpis');
  if (scope2KpisEl) {
    scope2KpisEl.innerHTML = [
      kpi('Scope 2 emissions', scope2, 'tCO₂e', colors.cyan, 'bolt', previousValue('elecEm'), true),
      kpi('Grid electricity consumption', elec, 'kWh', colors.cyan, 'plug', previousValue('elecKwh'), true, 0),
      kpi('HT connection', valFor(d, d.htKwh, month), 'kWh', colors.blue, 'building', previousValue('htKwh'), true, 0),
      kpi('Commercial connection', valFor(d, d.commKwh, month), 'kWh', colors.cyan, 'store', previousValue('commKwh'), true, 0),
      kpi('Temporary connection', valFor(d, d.tempKwh, month), 'kWh', colors.lime, 'battery', previousValue('tempKwh'), true, 0),
      kpi('Grid emission factor', factorFor(d, d.gridEF, month), 'kgCO₂e/kWh', colors.gold, 'ruler', null, true, 3),
      kpi('Electricity contribution', null, '%', colors.cyan, 'chart', null, true),
      kpi('Scope 2 offset', null, '%', colors.emerald, 'check', null, false)
    ].join('');
  }
  const energyProgressWidget = document.getElementById('energyProgressWidget');
  if (energyProgressWidget) {
    const reProgressPct = reShare;
    // The breakdown follows the same selected period but stands on its own:
    // a missing renewable share hides only the progress card.
    const breakdown = energySourceBreakdown(d, month);
    const partialSources = breakdown.filter(bar => bar.partial);

    if (reProgressPct == null && !breakdown.length) {
      energyProgressWidget.innerHTML = '';
    } else {

    energyProgressWidget.innerHTML = `
      <style>
        @keyframes epBarGrow { from { width: 0; } }
        @keyframes epShimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }
        .ep-hero-row { display: flex; gap: 24px; margin-bottom: 24px; }
        .ep-hero-row > .ep-hero:only-child { max-width: none; }
        .ep-hero {
          flex: 1;
          max-width: 50%;
          background: var(--surface);
          border: 1px solid var(--line);
          border-radius: 20px;
          padding: 32px;
          box-shadow: var(--shadow);
          position: relative;
          overflow: hidden;
        }
        .ep-hero::before {
          content: '';
          position: absolute;
          top: 0; left: 0; right: 0; height: 4px;
          background: linear-gradient(90deg, var(--green2), var(--green));
        }
        .ep-top { display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 16px; margin-bottom: 40px; }
        .ep-title-row { display: flex; align-items: center; gap: 10px; color: var(--ink); font-weight: 700; font-size: 16px; margin-bottom: 8px; }
        .ep-title-row .icon { width: 20px; height: 20px; color: var(--green); }
        .ep-value-row { font-size: clamp(36px, 5vw, 52px); font-family: 'IBM Plex Mono', monospace; font-weight: 700; color: var(--ink); display: flex; align-items: baseline; gap: 8px; line-height: 1; }
        
        .ep-bar-track-wrapper {
          position: relative;
          margin-bottom: 40px;
          padding-right: 2px; /* space for the target line */
        }
        .ep-bar-container { position: relative; height: 32px; border-radius: 99px; background: var(--line-strong); box-shadow: inset 0 2px 4px rgba(0,0,0,0.05); overflow: hidden; }
        .ep-bar-fill {
          position: absolute; top: 0; left: 0; bottom: 0;
          background: linear-gradient(90deg, var(--green2), var(--green));
          border-radius: 99px;
          animation: epBarGrow 1.5s cubic-bezier(0.25, 1, 0.5, 1) forwards;
          display: flex; align-items: center; justify-content: flex-end;
          padding-right: 14px;
        }
        .ep-bar-fill::after {
          content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0;
          background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
          background-size: 200% 100%;
          animation: epShimmer 2.5s infinite linear;
          border-radius: 99px;
        }
        .ep-pct-text {
          color: white; font-weight: 800; font-size: 14px; text-shadow: 0 1px 2px rgba(0,0,0,0.2); z-index: 2; position: relative;
        }
        
        /* Dotted Target Line */
        .ep-target-line {
          position: absolute;
          right: 0;
          top: -12px;
          bottom: -12px;
          width: 2px;
          border-right: 2px dashed var(--green);
          z-index: 5;
        }
        .ep-target-label {
          position: absolute;
          right: -10px;
          top: -36px;
          background: var(--green-soft);
          color: var(--green);
          font-size: 11px;
          font-weight: 800;
          padding: 4px 10px;
          border-radius: 6px;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .ep-target-label::after {
          content: '';
          position: absolute;
          bottom: -4px;
          right: 9px;
          border-width: 4px 4px 0;
          border-style: solid;
          border-color: var(--green-soft) transparent transparent;
        }

        /* Tooltip */
        .ep-bar-track-wrapper:hover .ep-tooltip {
          opacity: 1;
          visibility: visible;
          transform: translate(-50%, -10px);
        }
        .ep-tooltip {
          position: absolute;
          top: -55px;
          left: 50%;
          transform: translate(-50%, 0);
          background: rgba(21, 32, 26, 0.95);
          color: white;
          padding: 10px 16px;
          border-radius: 8px;
          font-size: 13px;
          font-family: 'Public Sans', sans-serif;
          opacity: 0;
          visibility: hidden;
          transition: all 0.2s cubic-bezier(0.25, 1, 0.5, 1);
          pointer-events: none;
          z-index: 10;
          white-space: nowrap;
          box-shadow: 0 4px 15px rgba(0,0,0,0.2);
          display: flex;
          gap: 16px;
        }
        .ep-tooltip::after {
          content: '';
          position: absolute;
          bottom: -5px;
          left: 50%;
          transform: translateX(-50%);
          border-width: 5px 5px 0;
          border-style: solid;
          border-color: rgba(21, 32, 26, 0.95) transparent transparent;
        }
        .ep-tt-item {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .ep-tt-label {
          font-size: 10px;
          text-transform: uppercase;
          color: var(--faint);
          font-weight: 700;
          letter-spacing: 0.05em;
        }
        .ep-tt-val {
          font-size: 16px;
          font-family: 'IBM Plex Mono', monospace;
          font-weight: 700;
        }
        .ep-tt-val span {
          font-size: 11px;
          color: #a1b0a8;
          font-family: 'Public Sans', sans-serif;
          font-weight: 500;
        }
      </style>
      <div class="ep-hero-row">
        ${reProgressPct == null ? '' : `<div class="ep-hero">

        <div class="ep-top">
          <div>
            <div class="ep-title-row">
              <div class="icon">${ic('sun')}</div>
              Renewable Energy Progress
            </div>
            <div class="ep-value-row">
              ${reProgressPct.toFixed(1)}%
              <span style="font-size:1.2rem; font-weight:600; color:var(--muted);">Achieved</span>
            </div>
            <div style="font-size: 13px; color: var(--faint); margin-top: 6px; font-weight: 500;">
              Target 100% renewable energy for our campus
            </div>
          </div>
        </div>

        <!-- Progress Bar -->
        <div class="ep-bar-track-wrapper">
          <div class="ep-bar-container">
            <div class="ep-bar-fill" style="width: ${reProgressPct}%;">
              ${reProgressPct >= 5 ? `<span class="ep-pct-text">${reProgressPct.toFixed(1)}%</span>` : ''}
            </div>
          </div>
          <div class="ep-target-line">
            <div class="ep-target-label">Target</div>
          </div>
          
          <!-- Tooltip -->
          <div class="ep-tooltip">
            <div class="ep-tt-item">
              <div class="ep-tt-label">Renewable</div>
              <div class="ep-tt-val">${Intl.NumberFormat('en-US').format(Math.round(re))} <span>kWh</span></div>
            </div>
            <div class="ep-tt-item">
              <div class="ep-tt-label">Grid total</div>
              <div class="ep-tt-val">${Intl.NumberFormat('en-US').format(Math.round(elec))} <span>kWh</span></div>
            </div>
          </div>
        </div>
        </div>`}

        <!-- New Source Breakdown Card -->
        ${breakdown.length ? `<div class="ep-hero" style="display: flex; flex-direction: column; padding: 32px 32px 24px 32px;">
          <div class="ep-top" style="margin-bottom: 24px;">
            <div>
              <div class="ep-title-row">
                <div class="icon">${ic('bolt')}</div>
                Energy Source Breakdown
              </div>
              <p class="hint" style="margin: 0;">${periodLabel(year, month)}</p>
            </div>
          </div>

          <div class="ep-src-breakdown" style="flex: 1; position: relative; min-height: 180px;">
            <canvas id="energySrcBreakdownChart"></canvas>
          </div>
          ${partialSources.map(bar => `<p class="hint" style="margin: 12px 0 0;">${bar.label} is partial: ${bar.monthsCovered} month(s) reported for this period.</p>`).join('')}
        </div>` : ''}

      </div>
    `;
    }
  }

  const energyKpisEl = document.getElementById('energyKpis');
  if (energyKpisEl) {
    energyKpisEl.innerHTML = energyPrimaryKpisHtml(d, month);
  }

}
/* Which figure the hero balance card is showing: gross / net / avoid. */
let currentHeroView = 'net';
/* The period the current hero view was chosen for. A manual tab click is kept
   only while this period stays selected; a new period re-runs the priority. */
let heroPeriodKey = null;
/* Hero priority for every newly selected period: per capita, then
   Operational GHG, then Reduction through renewables. */
const HERO_PRIORITY = ['net', 'gross', 'avoid'];

/* Fill the hero balance card and wire its three tabs; every call replays
   the count-up and the indicator-line sweep for the active tab. */
function heroGHG(gross, year, month, d, avoid, operationalPerCapita) {
  // static figures on the card
  const figures = {
    net: shownValue('operational_ghg_per_capita_kgco2e'),
    gross: shownValue('operational_ghg_tco2e'),
    avoid: shownValue('estimated_avoided_grid_emissions_tco2e')
  };
  const tabs = { net: 'tab-net', gross: 'tab-gross', avoid: 'tab-avoid' };
  const values = { net: 'balNetVal', gross: 'balGrossVal', avoid: 'balAvoidVal' };
  Object.keys(tabs).forEach(view => {
    document.getElementById(tabs[view]).style.display = figures[view] ? '' : 'none';
    document.getElementById(values[view]).textContent = figures[view] ? fmt(figures[view].value, 3) : '';
  });
  const balance = document.getElementById('tab-net').closest('section');
  // A figure is available when the backend supplied a value; 0 is a valid value.
  const available = HERO_PRIORITY.filter(view => figures[view]);
  if (balance) balance.style.display = available.length ? '' : 'none';
  if (!available.length) return;
  const periodKey = `${year}|${month}`;
  if (periodKey !== heroPeriodKey || !figures[currentHeroView]) currentHeroView = available[0];
  heroPeriodKey = periodKey;
  gross = figures.gross && figures.gross.value;
  operationalPerCapita = figures.net && figures.net.value;
  avoid = figures.avoid && figures.avoid.value;

  // repaint the big number for the selected tab
  function updateDisplayView() {
    const mainValueEl = document.getElementById('hero-ghg');
    const labelEl = document.getElementById('balLabel');
    const unitEl = document.getElementById('hero-unit');

    // clear tab highlights
    document.querySelectorAll('.bal-item').forEach(item => item.classList.remove('active'));

    let targetValue = 0;

    // pick the figure for the active view; the bar's fill never changes, only which slice is emphasized (via CSS)
    if (currentHeroView === 'net') {
      targetValue = operationalPerCapita;
      labelEl.textContent = "Per capita emissions";
      unitEl.textContent = "kgCO₂e/person";
      document.getElementById('tab-net').classList.add('active');
    } else if (currentHeroView === 'avoid') {
      targetValue = avoid;
      labelEl.textContent = "Reduction through renewables";
      unitEl.textContent = "tCO₂e";
      document.getElementById('tab-avoid').classList.add('active');
    } else {
      targetValue = gross;
      labelEl.textContent = "Operational GHG";
      unitEl.textContent = "tCO₂e";
      document.getElementById('tab-gross').classList.add('active');
    }

    document.getElementById('balPeriod').textContent = figures[currentHeroView]?.label || periodLabel(year, month);
    // One small footnote when the shown figure is partial; nothing when it is complete.
    const noteEl = document.getElementById('balPartialNote');
    if (noteEl) noteEl.innerHTML = partialNoteHtml(figures[currentHeroView]);
    if (targetValue == null) {
      mainValueEl.textContent = '';
    } else if (typeof reduceMotion !== 'undefined' && !reduceMotion) {
      let obj = { val: 0 };
      gsap.to(obj, {
        val: targetValue,
        duration: 1.5,
        ease: 'power2.out',
        onUpdate: () => { mainValueEl.textContent = fmt(obj.val, 3); },
        onComplete: () => { mainValueEl.textContent = fmt(targetValue, 3); }
      });
    } else {
      mainValueEl.textContent = fmt(targetValue, 3);
    }
  }

  // tab clicks re-render in place
  document.getElementById('tab-gross').onclick = () => { currentHeroView = 'gross'; updateDisplayView(); };
  document.getElementById('tab-net').onclick = () => { currentHeroView = 'net'; updateDisplayView(); };
  document.getElementById('tab-avoid').onclick = () => { currentHeroView = 'avoid'; updateDisplayView(); };

  // initial paint for the current selection
  updateDisplayView();
}

/* ---- charts ---- */
/* Live Chart.js instances by canvas id; destroyed before every rebuild. */
let charts = {}; function killCharts() { Object.values(charts).forEach(c => c.destroy()); charts = {}; }
/* Chart.js measures axis/legend text when a chart is built. On a cold load
   the chart web font can still be loading, leaving fallback-font metrics;
   draw now and rebuild once when that font is ready (drawCharts destroys first). */
let chartFontPending = null;
function redrawWhenChartFontLoads() {
  const font = `${Chart.defaults.font.size}px ${Chart.defaults.font.family}`;
  if (!document.fonts || chartFontPending || document.fonts.check(font)) return;
  chartFontPending = document.fonts.load(font).then(() => { chartFontPending = null; if (Object.keys(charts).length) drawCharts(); });
}
Chart.defaults.color = '#5c6b62';
Chart.defaults.font.family = "'Public Sans',sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.boxWidth = 8;
Chart.defaults.plugins.legend.labels.padding = 14;
Chart.defaults.plugins.tooltip.backgroundColor = '#ffffff';
Chart.defaults.plugins.tooltip.borderColor = '#e5e9e4';
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.titleColor = '#15201a';
Chart.defaults.plugins.tooltip.bodyColor = '#3a463f';
Chart.defaults.plugins.tooltip.padding = 11;
Chart.defaults.plugins.tooltip.cornerRadius = 10;
Chart.defaults.plugins.tooltip.titleFont = { weight: '700' };
Chart.defaults.plugins.tooltip.footerColor = '#3a463f';
Chart.defaults.plugins.tooltip.footerFont = { weight: '500' };
Chart.defaults.elements.arc.hoverOffset = 12;
Chart.defaults.hover.mode = 'nearest';
Chart.register({
  id: 'dimInactive',
  beforeDatasetsDraw(chart) {
    const active = chart.getActiveElements();
    const hasActive = active.length > 0;

    // For our specific double-doughnut charts, some indices represent a single unbroken segment across both datasets.
    // If one dataset's segment is hovered, we want to treat the other dataset's identical segment as active so it doesn't dim!
    const isElecMix = chart.canvas.id === 'elecMixChartCanvas';
    const isFuelMix = chart.canvas.id === 'fuelMixChartCanvas';
    const mergedIndices = isElecMix ? [0] : [];
    // Fossil mix: a fuel group reads as one segment across both rings (outer
    // Diesel with inner DG + Fleet, Petrol with Petrol, LPG with LPG).
    const fuelGroup = (dIdx, eIdx) => (dIdx === 0 ? eIdx : Math.max(0, eIdx - 1));

    chart.data.datasets.forEach((dataset, dIdx) => {
      const meta = chart.getDatasetMeta(dIdx);
      meta.data.forEach((el, eIdx) => {
        let isActive = hasActive && active.some(a => a.datasetIndex === dIdx && a.index === eIdx);

        // Link the active state if this index is a "merged" single segment
        if (hasActive && !isActive && mergedIndices.includes(eIdx)) {
          isActive = active.some(a => a.index === eIdx);
        }
        if (hasActive && !isActive && isFuelMix) {
          isActive = active.some(a => fuelGroup(a.datasetIndex, a.index) === fuelGroup(dIdx, eIdx));
        }

        if (!el._originalDraw) {
          el._originalDraw = el.draw;
          el.draw = function (ctx) {
            const saveAlpha = ctx.globalAlpha;
            if (this._shouldDim) ctx.globalAlpha = 0.2;
            this._originalDraw(ctx);
            ctx.globalAlpha = saveAlpha;
          };
        }
        el._shouldDim = hasActive && !isActive;
      });
    });
  }
});
/* Shared cartesian options with an optional y-axis title. */
function chartOptions(yTitle) { return { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } }, scales: { x: { grid: { display: false }, border: { color: colors.grid } }, y: { grid: { color: colors.grid }, border: { display: false }, title: { display: !!yTitle, text: yTitle, color: '#8a988f' } } } } }
const baseline = 'rgba(21,32,26,.16)';
/* Rebuild charts for the ACTIVE page only - mk() skips canvases on
   hidden pages, cutting a refresh from 20 charts to at most 4. Hidden
   pages get theirs on arrival, since go() always calls refresh(). */
function drawCharts() {
  killCharts();
  redrawWhenChartFontLoads();
  const mk = (id, cfg) => { const el = document.getElementById(id); if (el && el.closest('.page.active')) charts[id] = new Chart(el, cfg); };
  const { year, month, d } = currentPeriod();
  if (!d) return;
  const blankTrendYear = () => ({
    elecKwh: Array(12).fill(null), reKwh: Array(12).fill(null),
    reOnCampusKwh: Array(12).fill(null), reProcuredKwh: Array(12).fill(null),
    totalElectricityKwh: Array(12).fill(null)
  });
  const trendYear = value => ({ ...blankTrendYear(), ...(value || {}) });
  const d25 = trendYear(data[2025]), d26 = trendYear(data[2026]);
  /* Combined Scope1+Scope2 charts share one month window, derived from the
     genuine monthly records rather than a hardcoded cutoff. Sources with zero
     months (not reporting at all in a year) are excluded. */
  const s1s2Months = [d.trDieselL, d.dgL, d.petrolL, d.lpgKg, d.htKwh, d.commKwh, d.tempKwh].map(monthsWithData).filter(m => m > 0);
  // Run to the last month with any genuine value; a source that stops earlier
  // leaves gaps (null), never zeros, and never hides later genuine months.
  const available = d.frequency === 'ytd' && s1s2Months.length ? Math.max(...s1s2Months) : 12;
  const labels = months.slice(0, available); const sl = a => a.slice(0, available);
  const home = document.body.classList.contains('home'); const axc = home ? '#cbe2d6' : '#5c6b62'; const grc = home ? 'rgba(255,255,255,.1)' : colors.grid;
  const oopt = (yTitle) => ({ responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { color: axc } } }, scales: { x: { grid: { display: false }, ticks: { color: axc } }, y: { grid: { color: grc }, border: { display: false }, ticks: { color: axc }, title: { display: !!yTitle, text: yTitle, color: axc } } } });
  const dleg = { responsive: true, maintainAspectRatio: false, cutout: '66%', plugins: { legend: { position: 'bottom', labels: { color: axc } } } }; const dborder = home ? 'rgba(4,19,12,.25)' : '#fff';
  // Emission Profile: the selected period's emission split (the Scope toggle picks which sources).
  const view = window.currentGhgProfileView || 'all';
  const profileParts = periodComposition(d, month, [
    ...(view === 'all' || view === 's1' ? GHG_PROFILE_PARTS.s1 : []),
    ...(view === 'all' || view === 's2' ? GHG_PROFILE_PARTS.s2 : [])
  ]);
  const profileShown = profileParts.filter(part => part.value != null);
  const ghgProfilePeriod = document.getElementById('ghgProfilePeriod');
  if (ghgProfilePeriod) ghgProfilePeriod.textContent = ` — ${periodLabel(year, month)}`;
  // The profile's total for the active Scope toggle, with the backend's COMPLETE / PARTIAL state.
  const profileTotal = completenessOf(displayFor({ all: 'operational_ghg_tco2e', s1: 'scope1_tco2e', s2: 'scope2_tco2e' }[view]));
  setChartNote('ghgProfileChart', profileShown.length
    ? [profileTotal?.partial ? `${PARTIAL_NOTE}.` : '', compositionNote(profileParts, periodLabel(year, month))].filter(Boolean).join(' ')
    : `No emission sources published for ${periodLabel(year, month)}.`);
  mk('ghgProfileChart', { type: 'doughnut', data: { labels: profileShown.map(part => part.label), datasets: [{ data: profileShown.map(part => part.value), backgroundColor: profileShown.map(part => part.color), borderWidth: 2, borderColor: dborder }] }, options: dleg });

  /* Electricity Mix: the selected period's grid and renewable electricity (the
     month, or the Full Year / YTD record) - the same period as its caption and
     renewable share. Backend-published renewable components, not an estimated
     ratio; a missing component stays null. */
  const [gridVal, reVal, reOnCampusVal, reProcuredVal] = periodComposition(d, month, ELEC_MIX_PARTS).map(part => part.value);

  mk('elecMixChartCanvas', {
    type: 'doughnut',
    data: {
      labels: ['Grid electricity', 'On-campus Solar PV', 'Procured Green Energy'],
      datasets: [
        {
          // Outer Ring: Top-level Category
          data: [gridVal, reVal],
          backgroundColor: [
            '#d9a05b', // Grid outer - Solid Gold to merge with inner
            'rgba(28, 122, 75, 0.9)'   // RE outer
          ],
          borderColor: ['#d9a05b', '#1c7a4b'],
          borderWidth: 2,
          hoverOffset: 0
        },
        {
          // Inner Ring: Detailed Breakdown
          data: [gridVal, reOnCampusVal, reProcuredVal],
          backgroundColor: [
            '#d9a05b', // Grid inner - Solid Gold to merge with outer
            '#63b3ed', // On-campus renewable - Sky Blue
            'rgba(34, 153, 94, 0.9)', // Procured renewable - Green
          ],
          borderColor: ['#d9a05b', '#4299e1', '#22995e'],
          borderWidth: 2,
          hoverOffset: [0, 6, 6] // Keep Grid static so it visually merges with outer ring
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '50%',
      animation: { animateScale: true, animateRotate: true },
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: true,
          mode: 'nearest',
          intersect: true,
          callbacks: {
            title: function (context) {
              const idx = context[0].dataIndex;
              return idx === 0 ? 'Grid electricity' : 'Renewable electricity';
            },
            label: function (context) {
              // Outer ring: grid / renewable electricity. Inner ring: grid / on-campus / procured.
              const label = context.datasetIndex === 0
                ? ['Grid electricity', 'Renewable electricity'][context.dataIndex]
                : context.chart.data.labels[context.dataIndex];
              return ' ' + label + ': ' + (context.raw == null ? 'Not published' : Math.round(context.raw).toLocaleString() + ' kWh');
            }
          }
        }
      }
    }
  });

  // Same selected period as Renewable Energy Progress and the KPI cards.
  const sourceBars = energySourceBreakdown(d, month);
  mk('energySrcBreakdownChart', {
    type: 'bar',
    data: {
      labels: sourceBars.map(bar => bar.partial ? `${bar.label} (partial)` : bar.label),
      datasets: [{
        label: 'Energy (kWh)',
        data: sourceBars.map(bar => bar.value),
        backgroundColor: sourceBars.map(bar => bar.color),
        borderWidth: 0,
        borderRadius: 6
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: {
          grid: { color: grc },
          border: { display: false },
          ticks: { color: axc }
        },
        y: {
          grid: { display: false },
          ticks: { color: axc }
        }
      }
    }
  });

  // Fossil Fuel Emissions Mix: the selected period's fuel-source results, as
  // two rings. Outer = fuel groups (Diesel, Petrol, LPG); inner = the four
  // governed contributors, so the Diesel arc contains its DG and Fleet parts.
  // A missing component stays missing (null), never a measured 0.
  const fuelMix = fuelMixView(d, month);
  const fuelOuterLabels = [fuelMix.dieselComplete ? 'Total Diesel emissions' : 'Diesel emissions (published part only)', 'Petrol emissions', 'LPG emissions'];
  const fuelInnerLabels = ['DG Diesel emissions', 'Fleet Diesel emissions', 'Petrol emissions', 'LPG emissions'];

  mk('fuelMixChartCanvas', {
    type: 'doughnut',
    data: {
      labels: fuelInnerLabels,
      datasets: [
        {
          // Outer ring: fuel groups. Petrol and LPG share their inner colour so each reads as one segment.
          data: fuelMix.outer,
          backgroundColor: [colors.orange, colors.teal, colors.violet],
          borderColor: [colors.orange, colors.teal, colors.violet],
          borderWidth: 2,
          hoverOffset: 0
        },
        {
          // Inner ring: the governed contributors; DG and Fleet split the Diesel arc.
          data: fuelMix.inner,
          backgroundColor: [colors.orange, colors.gold, colors.teal, colors.violet],
          borderColor: [colors.orange, '#d69e2e', colors.teal, colors.violet],
          borderWidth: 2,
          hoverOffset: [6, 6, 0, 0]
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '50%',
      animation: { animateScale: true, animateRotate: true },
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: true,
          mode: 'nearest',
          intersect: true,
          callbacks: {
            title: function (context) {
              const item = context[0];
              return (item.datasetIndex === 0 ? fuelOuterLabels : fuelInnerLabels)[item.dataIndex];
            },
            label: function (context) {
              const label = (context.datasetIndex === 0 ? fuelOuterLabels : fuelInnerLabels)[context.dataIndex];
              return ' ' + label + ': ' + (context.raw == null ? 'Not published' : Number(context.raw).toLocaleString() + ' tCO₂e');
            }
          }
        }
      }
    }
  });

  let hStack = null;
  chartNote('ghgTrendChart', [sl(d.petrolEm).map((_, i) => [d.petrolEm, d.trDieselEm, d.dgEm, d.lpgEm, d.elecEm].some(a => a[i] != null) ? 1 : null)], 'Not published in the current release.');
  mk('ghgTrendChart', {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'S1: Petrol', data: sl(d.petrolEm), backgroundColor: colors.teal, borderRadius: 0, stack: 'Scope1' },
        { label: 'S1: Tr. Diesel', data: sl(d.trDieselEm), backgroundColor: colors.gold, borderRadius: 0, stack: 'Scope1' },
        { label: 'S1: DG Diesel', data: sl(d.dgEm), backgroundColor: colors.orange, borderRadius: 0, stack: 'Scope1' },
        { label: 'S1: LPG', data: sl(d.lpgEm), backgroundColor: colors.violet, borderRadius: 0, stack: 'Scope1' },
        { label: 'S2: Grid electricity', data: sl(d.elecEm), backgroundColor: colors.cyan, borderRadius: 0, stack: 'Scope2' }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'point', intersect: true },
      onHover: (e, el, chart) => { if (el.length) hStack = chart.data.datasets[el[0].datasetIndex].stack; },
      plugins: {
        legend: { position: 'bottom', labels: { color: axc } },
        tooltip: {
          mode: 'index', intersect: true,
          filter: (item) => hStack ? item.dataset.stack === hStack : true,
          // Operational GHG and Complete / Partial for the hovered month.
          callbacks: { footer: items => (items.length ? ghgStatusLines(d, items[0].dataIndex) : []) }
        }
      },
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { color: axc } },
        y: { stacked: true, grid: { color: grc }, border: { display: false }, ticks: { color: axc }, title: { display: true, text: 'tCO₂e', color: axc } }
      }
    }
  });

  // Months whose Operational GHG covers only the available sources stay on the chart, labelled.
  const partialMonths = labels.filter((_, i) => completenessOf(d?.periodMeta?.[i]?.values?.operational_ghg_tco2e)?.partial);
  if (partialMonths.length) setChartNote('ghgTrendChart', `Partial (available emission sources only): ${partialMonths.join(', ')}. Missing sources are not shown as zero.`);

  mk('s1Fuel', { type: 'bar', data: { labels, datasets: [{ label: 'Petrol', data: sl(d.petrolL), backgroundColor: colors.teal, borderRadius: 5 }, { label: 'Fleet diesel', data: sl(d.trDieselL), backgroundColor: colors.gold, borderRadius: 5 }] }, options: chartOptions('Litres') });
  mk('s1Breakdown', { type: 'doughnut', data: { labels: ['Fleet diesel', 'DG diesel', 'Petrol', 'LPG'], datasets: [{ data: [sum(sl(d.trDieselEm)), sum(sl(d.dgEm)), sum(sl(d.petrolEm)), sum(sl(d.lpgEm))], backgroundColor: [colors.gold, colors.orange, colors.teal, colors.violet], borderWidth: 2, borderColor: '#fff' }] }, options: { responsive: true, maintainAspectRatio: false, cutout: '64%', plugins: { legend: { position: 'bottom' } } } });
  // DG activity is methodology-aware: litres (source-reported, or derived for kWh
  // months) on the litre axis, source generation on its own kWh axis. A legacy
  // month has no kWh point - none is invented.
  mk('s1DG', { type: 'bar', data: { labels, datasets: [{ type: 'bar', label: 'DG diesel (L) — source reported, or derived from kWh', data: sl(d.dgL), backgroundColor: 'rgba(193,138,46,.4)', borderRadius: 5, yAxisID: 'y' }, { type: 'bar', label: 'DG generation (kWh)', data: sl(d.dgKwh), backgroundColor: 'rgba(58,111,168,.35)', borderRadius: 5, yAxisID: 'y2' }, { type: 'line', label: 'DG emissions', data: sl(d.dgEm), borderColor: colors.orange, backgroundColor: colors.orange, tension: .35, yAxisID: 'y1', pointRadius: 0, borderWidth: 2 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } }, scales: { x: { grid: { display: false } }, y: { grid: { color: colors.grid }, border: { display: false }, title: { display: true, text: 'Litres', color: '#8a988f' } }, y1: { position: 'right', grid: { display: false }, border: { display: false }, title: { display: true, text: 'tCO₂e', color: '#8a988f' } }, y2: { position: 'right', grid: { display: false }, border: { display: false }, title: { display: true, text: 'kWh', color: '#8a988f' } } } } });
  mk('s1Diesel', { type: 'line', data: { labels, datasets: [{ label: 'Fleet diesel', data: sl(d.trDieselEm), borderColor: colors.gold, backgroundColor: 'rgba(193,138,46,.08)', fill: true, tension: .35, pointRadius: 0, borderWidth: 2 }, { label: 'DG diesel', data: sl(d.dgEm), borderColor: colors.orange, backgroundColor: 'rgba(184,98,58,.08)', fill: true, tension: .35, pointRadius: 0, borderWidth: 2 }] }, options: chartOptions('tCO₂e') });
  mk('s2Stack', { type: 'bar', data: { labels, datasets: [{ label: 'HT', data: sl(d.htKwh), backgroundColor: colors.cyan, borderRadius: 4 }, { label: 'Commercial', data: sl(d.commKwh), backgroundColor: '#6e97c7', borderRadius: 4 }, { label: 'Temporary', data: sl(d.tempKwh), backgroundColor: colors.teal, borderRadius: 4 }] }, options: { ...chartOptions('kWh'), scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, grid: { color: colors.grid }, border: { display: false }, title: { display: true, text: 'kWh', color: '#8a988f' } } } } });
  mk('s2Trend', { type: 'line', data: { labels, datasets: [{ label: 'Scope 2 emissions', data: sl(d.elecEm), borderColor: colors.cyan, backgroundColor: 'rgba(58,111,168,.1)', fill: true, tension: .35, pointRadius: 0, borderWidth: 2 }] }, options: chartOptions('tCO₂e') });
  mk('s2Share', { type: 'doughnut', data: { labels: ['HT', 'Commercial', 'Temporary'], datasets: [{ data: [sum(sl(d.htKwh)), sum(sl(d.commKwh)), sum(sl(d.tempKwh))], backgroundColor: [colors.cyan, '#6e97c7', colors.teal], borderWidth: 2, borderColor: '#fff' }] }, options: { responsive: true, maintainAspectRatio: false, cutout: '64%', plugins: { legend: { position: 'bottom' } } } });
  mk('s2VsRE', { type: 'doughnut', data: { labels: ['Electricity CO₂ emitted', 'Estimated grid CO₂e avoided'], datasets: [{ data: [sum(sl(d.elecEm)), sum(sl(d.avoidEm))], backgroundColor: [colors.cyan, colors.emerald], borderWidth: 2, borderColor: '#fff' }] }, options: { responsive: true, maintainAspectRatio: false, cutout: '64%', plugins: { legend: { position: 'bottom' } } } });


  /* Waste is a year-aggregate domain: the charts show the year's current
     Full Year / YTD waste as the backend resolved it, for every selection
     inside that year. A missing value is absent, never drawn as 0 kg. */
  const wasteYear = d.wasteYear?.[month === 'all' ? 'all' : +month] || { label: null, wet: null, dry: null, materials: [] };
  const wasteKg = value => `${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })} kg`;
  const wasteContext = document.getElementById('wasteContext');
  if (wasteContext) wasteContext.textContent = wasteYear.label ? ` — ${wasteYear.label}` : '';
  const wasteMaterialContext = document.getElementById('wasteMaterialContext');
  if (wasteMaterialContext) wasteMaterialContext.textContent = wasteYear.label ? ` — ${wasteYear.label}` : '';
  mk('wastePieChartCanvas', { type: 'pie', data: { labels: ['Wet waste', 'Dry waste'], datasets: [{ data: [wasteYear.wet, wasteYear.dry], backgroundColor: [colors.blue, colors.gold], borderWidth: 2, borderColor: '#fff' }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: function (context) { return ' ' + context.label + ': ' + (context.raw == null ? 'Not published' : wasteKg(context.raw) + (context.raw >= 1000 ? ' (' + (context.raw / 1000).toFixed(1) + ' tons)' : '')); } } } } } });
  chartNote('wastePieChartCanvas', [[wasteYear.wet, wasteYear.dry]], 'No wet / dry waste data for this year.');

  /* Material breakdown: one horizontal bar per material:* value the backend
     reports, largest first. Categories and order come from the data. */
  const wasteMaterials = wasteYear.materials.filter(row => row.value > 0);
  const wasteMaterialBox = document.getElementById('wasteMaterialBox');
  if (wasteMaterialBox) wasteMaterialBox.style.height = `${Math.max(280, wasteMaterials.length * 26 + 70)}px`;
  const wasteBarColors = [colors.blue, colors.teal, colors.emerald, colors.gold, colors.orange, '#6e97c7', '#8a988f'];
  mk('wasteMaterialChartCanvas', {
    type: 'bar',
    data: {
      labels: wasteMaterials.map(row => row.name),
      datasets: [{ label: 'Quantity (kg)', data: wasteMaterials.map(row => row.value), backgroundColor: wasteMaterials.map((_, index) => wasteBarColors[index % wasteBarColors.length]), borderRadius: 4 }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: item => ' ' + wasteKg(item.raw) + (item.raw >= 1000 ? ' (' + (item.raw / 1000).toFixed(2) + ' tons)' : '') } }
      },
      scales: {
        x: { beginAtZero: true, title: { display: true, text: 'kg' }, grid: { color: colors.grid } },
        y: { grid: { display: false }, ticks: { autoSkip: false } }
      }
    }
  });
  chartNote('wasteMaterialChartCanvas', [wasteMaterials.map(row => row.value)], 'No material breakdown for this year.');

  /* water_master.csv usually runs further into the year than the fuel/Fleet/DG
     sources gating the shared 'available' above, so every water chart slices
     by its own actual month count instead of 'available'/labels/sl. */
  const waterMonths = monthsWithData(d.waterKL);
  const waterLabels = months.slice(0, waterMonths);
  const wsl = arr => arr.slice(0, waterMonths);

  chartNote('waterTrendChartCanvas', [wsl(d.waterKL)], 'Not published in the current release.');
  mk('waterTrendChartCanvas', {
    type: 'bar',
    data: {
      labels: waterLabels,
      datasets: [{
        label: 'Water consumption',
        data: wsl(d.waterKL),
        backgroundColor: 'rgba(58,111,168,.45)',
        borderRadius: 5,
        maxBarThickness: 24
      }]
    },
    options: chartOptions('KL')
  });

  /* Water Source Breakdown: the selected period's source split - the month, or
     the Full Year / YTD record. Published zeros stay distinct from missing
     values. A month with no source values of its own (2025 is recorded only
     as an annual total) shows the backend's labelled context instead (e.g.
     "2025 Annual Data"), exactly as the KPI cards do, and says so; only when
     neither exists does it fall back to the period's single total. */
  const waterPeriod = periodLabel(year, month);
  let waterSources = periodComposition(d, month, WATER_SOURCE_PARTS), waterSourceBasis = waterPeriod, waterSourceNote;
  if (waterSources.some(part => part.value != null)) {
    waterSourceNote = compositionNote(waterSources, waterPeriod);
  } else {
    const context = contextComposition(d, month, WATER_SOURCE_PARTS);
    if (context) {
      waterSources = context.parts;
      waterSourceBasis = context.label;
      waterSourceNote = `No monthly source split for ${waterPeriod}; showing ${context.label}.`;
    } else {
      waterSources = periodComposition(d, month, [['Total consumption', 'waterKL', 'water_consumed_kl', colors.cyan]]);
      waterSourceNote = waterSources[0].value == null ? `No water data published for ${waterPeriod}.` : 'No source split published for this period.';
    }
  }
  const waterSourceShown = waterSources.filter(part => part.value != null);
  const waterSourceLabels = waterSourceShown.map(part => part.label);
  const waterSourceData = waterSourceShown.map(part => part.value);
  const waterSourceColors = waterSourceShown.map(part => part.color);
  const waterSourcePeriod = document.getElementById('waterSourcePeriod');
  if (waterSourcePeriod) waterSourcePeriod.textContent = ` — ${waterSourceBasis}`;
  setChartNote('waterSourceChartCanvas', waterSourceNote);
  // Per-source trend cards below still follow the year's monthly series (unchanged).
  const hasMonthlySourceData = [d.waterTWAD, d.waterBorewell, d.waterProcured].some(arr => sum(wsl(arr)) != null);

  mk('waterSourceChartCanvas', {
    type: 'doughnut',
    data: { labels: waterSourceLabels, datasets: [{ data: waterSourceData, backgroundColor: waterSourceColors, borderWidth: 2, borderColor: '#fff' }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '64%',
      plugins: {
        legend: { position: 'bottom' },
        tooltip: { callbacks: { label: (ctx) => ' ' + ctx.label + ': ' + ctx.raw.toLocaleString() + ' KL' } }
      }
    }
  });

  /* Per-source monthly trend exists where monthly source values are published (2026
     onward) - swap the three trend cards for a plain-language empty state on
     years that only ever recorded a single monthly total (2025). */
  const wstRow = document.getElementById('waterSourceTrendRow');
  const wstEmptyRow = document.getElementById('waterSourceTrendEmptyRow');
  if (wstRow && wstEmptyRow) {
    const hasSourceTrend = hasMonthlySourceData;
    wstRow.style.display = hasSourceTrend ? '' : 'none';
    wstEmptyRow.style.display = hasSourceTrend ? 'none' : '';
    if (hasSourceTrend) {
      const singleTrendOpts = () => { const o = chartOptions('KL'); o.plugins.legend = { display: false }; return o; };
      mk('waterTWADTrendCanvas', {
        type: 'line',
        data: { labels: waterLabels, datasets: [{ label: 'TWAD supply', data: wsl(d.waterTWAD), borderColor: colors.cyan, backgroundColor: 'rgba(58,111,168,.1)', fill: true, tension: .35, borderWidth: 2, pointRadius: 3, pointBackgroundColor: '#fff', pointBorderWidth: 2 }] },
        options: singleTrendOpts()
      });
      mk('waterBorewellTrendCanvas', {
        type: 'line',
        data: { labels: waterLabels, datasets: [{ label: 'Borewell', data: wsl(d.waterBorewell), borderColor: colors.teal, backgroundColor: 'rgba(79,154,140,.1)', fill: true, tension: .35, borderWidth: 2, pointRadius: 3, pointBackgroundColor: '#fff', pointBorderWidth: 2 }] },
        options: singleTrendOpts()
      });
      mk('waterProcuredTrendCanvas', {
        type: 'line',
        data: { labels: waterLabels, datasets: [{ label: 'Private water supply', data: wsl(d.waterProcured), borderColor: colors.gold, backgroundColor: 'rgba(193,138,46,.1)', fill: true, tension: .35, borderWidth: 2, pointRadius: 3, pointBackgroundColor: '#fff', pointBorderWidth: 2 }] },
        options: singleTrendOpts()
      });
    }
  }

  /* Outreach charts use only the active published aggregate. */
  const outreachChartsRow = document.getElementById('outreachChartsRow');
  if (outreachChartsRow) {
    const outreachForPeriod = outreach.published;
    outreachChartsRow.style.display = outreachForPeriod ? '' : 'none';
    if (outreachForPeriod) {
      const sliceOpts = (unit, cutout) => ({
        responsive: true, maintainAspectRatio: false, cutout,
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 10, padding: 8, font: { size: 10.5 }, usePointStyle: true } },
          tooltip: { callbacks: { label: (ctx) => ' ' + ctx.label + ': ' + ctx.raw.toLocaleString() + ' ' + unit } }
        }
      });
      const palette = [colors.cyan, colors.teal, colors.gold, colors.orange, colors.violet, colors.lime, colors.emerald, colors.red, '#6e97c7'];

      const setText = (id, text) => { const node = document.getElementById(id); if (node) node.textContent = text; };
      const audience = (outreach.audienceReach || []).filter(a => a.reach != null);
      const audienceText = outreachAudienceText(outreach.audienceUnit);
      // One shared context label for the three charts ("2026 YTD").
      const context = outreach.coverageLabel ? `${outreach.coverageLabel} · ` : '';
      setText('outreachAudienceTitle', audienceText.title);
      setText('outreachAudienceHint', context + audienceText.hint);
      setText('outreachThematicHint', `${context}Programmes delivered per theme - hover a slice for the count`);
      mk('outreachAudienceChart', {
        type: 'doughnut',
        data: { labels: audience.map(a => humanizeCode(a.category)), datasets: [{ data: audience.map(a => a.reach), backgroundColor: palette, borderWidth: 2, borderColor: '#fff' }] },
        options: sliceOpts(audienceText.unit, '62%') // a true donut, per the ask
      });

      const thematic = outreach.thematicAreas || [];
      setText('outreachThematicNote', outreachThematicNote(thematic, outreach.programsDelivered, outreach.qualifiers?.programsDelivered));
      mk('outreachThematicChart', {
        type: 'pie',
        data: { labels: thematic.map(t => humanizeCode(t.category)), datasets: [{ data: thematic.map(t => t.programs), backgroundColor: palette, borderWidth: 2, borderColor: '#fff' }] },
        options: sliceOpts(outreach.thematicUnit || 'programmes', '0%') // a solid pie - Chart.js applies `cutout` to pie too, so this must be explicit
      });
    }
  }

  // Compute full-year arrays for Energy line charts
  // Published zeros stay zeros and missing months stay missing (null).
  const cleanZero = arr => (Array.isArray(arr) ? arr : Array(12).fill(null)).slice();
  // The backend freezes each monthly combined total; the chart only displays it.
  const total25 = cleanZero(d25.totalElectricityKwh);
  const total26 = cleanZero(d26.totalElectricityKwh);
  // Real on-campus/procured columns from energy_master.csv - no longer an
  // estimated 60/30 split of the combined reKwh total.
  const solar25 = cleanZero(d25.reOnCampusKwh);
  const solar26 = cleanZero(d26.reOnCampusKwh);
  const procured25 = cleanZero(d25.reProcuredKwh);
  const procured26 = cleanZero(d26.reProcuredKwh);

  const lineOpts = chartOptions('kWh');
  lineOpts.plugins.legend = { position: 'top', labels: { boxWidth: 12, usePointStyle: true } };
  lineOpts.interaction = { mode: 'index', intersect: false };
  lineOpts.plugins.tooltip = { mode: 'index', intersect: false };

  const ds25Opts = { borderColor: '#a1b0a8', backgroundColor: 'transparent', tension: 0.4, borderWidth: 2, borderDash: [4, 4], pointRadius: 0 };
  const ds26Opts = (color, bg) => ({ borderColor: color, backgroundColor: bg, fill: true, tension: 0.4, borderWidth: 3, pointRadius: 4, pointHoverRadius: 6, pointBackgroundColor: '#fff', pointBorderColor: color, pointBorderWidth: 2 });

  chartNote('energyTotalLineChart', [total25, total26], 'No combined electricity total for this selection.');
  mk('energyTotalLineChart', {
    type: 'line',
    data: {
      labels: months,
      datasets: [
        ...(total25.some(v => v != null) ? [{ label: '2025', data: total25, ...ds25Opts }] : []),
        { label: '2026', data: total26, ...ds26Opts(colors.lime, 'rgba(90,165,82,.08)') }
      ]
    },
    options: lineOpts
  });

  chartNote('energyGridLineChart', [cleanZero(d25.elecKwh), cleanZero(d26.elecKwh)], 'Not published in the current release.');
  mk('energyGridLineChart', {
    type: 'line',
    data: {
      labels: months,
      datasets: [
        ...(cleanZero(d25.elecKwh).some(v => v != null) ? [{ label: '2025', data: cleanZero(d25.elecKwh), ...ds25Opts }] : []),
        { label: '2026', data: cleanZero(d26.elecKwh), ...ds26Opts(colors.cyan, 'rgba(58,111,168,.08)') }
      ]
    },
    options: lineOpts
  });

  chartNote('energySolarLineChart', [solar25, solar26], 'Not published separately in the current release.');
  mk('energySolarLineChart', {
    type: 'line',
    data: {
      labels: months,
      datasets: [
        ...(solar25.some(v => v != null) ? [{ label: '2025', data: solar25, ...ds25Opts }] : []),
        { label: '2026', data: solar26, ...ds26Opts('#63b3ed', 'rgba(99,179,237,.08)') }
      ]
    },
    options: lineOpts
  });

  chartNote('energyProcuredLineChart', [procured25, procured26], 'Not published separately in the current release.');
  mk('energyProcuredLineChart', {
    type: 'line',
    data: {
      labels: months,
      datasets: [
        ...(procured25.some(v => v != null) ? [{ label: '2025', data: procured25, ...ds25Opts }] : []),
        { label: '2026', data: procured26, ...ds26Opts(colors.emerald, 'rgba(28,122,75,.08)') }
      ]
    },
    options: lineOpts
  });

}

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
/* ---- KPI FX: particle engine for the smoke / leaves / lightning cards.
   One _KPar per .kpi-fx-canvas, all driven by a single shared rAF loop
   started in initKpiAnimations. ---- */
let _kfxRAF = null; const _kfxSys = [];
class _KPar {
  constructor(c, t) { this.c = c; this.x = c.getContext('2d'); this.t = t; this.p = []; this._rs(); this._sd(); }
  _rs() {
    const r = this.c.parentElement.getBoundingClientRect(), d = window.devicePixelRatio || 1;
    this.w = r.width; this.h = r.height; if (!this.w) return;
    this.c.width = this.w * d; this.c.height = this.h * d; this.x.scale(d, d);
  }
  _sd() { const n = this.t === 'smoke' ? 25 : this.t === 'lightning' ? 2 : 12; for (let i = 0; i < n; i++)this.p.push(this._mk(1)); }
  _mk(init) {
    if (this.t === 'smoke') { const isLeft = Math.random() > .4; const bx = isLeft ? this.w - 45 : this.w - 20; const by = isLeft ? this.h - 72 : this.h - 56; return { x: bx + (Math.random() - .5) * 8, y: init ? Math.random() * by : by, sz: 8 + Math.random() * 15, vy: -(0.6 + Math.random() * 1), vx: (Math.random() - .5) * 1.5, o: .05 + Math.random() * .08, l: 0, ml: 150 + Math.random() * 150 }; }
    if (this.t === 'lightning') { const tx = this.w - 45 + Math.random() * 15; const ty = this.h - 80; let cx = Math.random() * this.w, cy = -10; const pts = [{ x: cx, y: cy }]; while (cy < ty) { cy += 10 + Math.random() * 15; cx += (tx - cx) * (cy / ty) + (Math.random() - .5) * 20; pts.push({ x: cx, y: cy }); } pts.push({ x: tx, y: ty }); return { l: 0, ml: 60 + Math.random() * 150, pts }; }
    return {
      x: init ? Math.random() * this.w : -10, y: 10 + Math.random() * this.h * .5,
      sz: 3 + Math.random() * 4, vx: .15 + Math.random() * .35, vy: .03 + Math.random() * .1,
      a: Math.random() * Math.PI * 2, ra: (Math.random() - .5) * .04,
      wa: 8 + Math.random() * 18, wf: .01 + Math.random() * .01,
      o: .04 + Math.random() * .08, l: 0, ml: 140 + Math.random() * 130, by: 0
    };
  }
  tick() {
    for (let i = this.p.length - 1; i >= 0; i--) {
      const p = this.p[i]; p.l++;
      if (this.t === 'smoke') {
        p.x += p.vx + Math.sin(p.l * .02) * .3; p.y += p.vy;
        if (p.l > p.ml || p.y < -20 || p.x > this.w + 20 || p.x < -20) this.p[i] = this._mk(0);
      } else if (this.t === 'lightning') {
        if (p.l > p.ml) this.p[i] = this._mk(0);
      } else {
        if (p.l === 1) p.by = p.y; p.x += p.vx; p.y = p.by + Math.sin(p.l * p.wf) * p.wa + p.vy * p.l * .25;
        p.a += p.ra; if (p.x > this.w + 14 || p.l > p.ml) this.p[i] = this._mk(0);
      }
    }
  }
  draw() {
    if (!this.w) return; this.x.clearRect(0, 0, this.w, this.h);
    for (const p of this.p) {
      const lp = p.l / p.ml, f = lp < .15 ? lp / .15 : lp > .6 ? (1 - lp) / .4 : 1, a = p.o * f;
      this.x.save();
      if (this.t === 'smoke') {
        if (a <= .001) { this.x.restore(); continue; }
        this.x.globalAlpha = a; this.x.fillStyle = '#3a3a3a';
        this.x.beginPath(); this.x.arc(p.x, p.y, p.sz, 0, Math.PI * 2); this.x.fill();
        this.x.globalAlpha = a * .2; this.x.beginPath(); this.x.arc(p.x, p.y, p.sz * 3, 0, Math.PI * 2); this.x.fill();
      } else if (this.t === 'lightning') {
        if (p.l > 15) { this.x.restore(); continue; }
        this.x.globalAlpha = 1 - (p.l / 15); this.x.strokeStyle = '#e0f7fa'; this.x.lineWidth = 2 + Math.random() * 2;
        this.x.shadowColor = '#00ffff'; this.x.shadowBlur = 15; this.x.beginPath(); this.x.moveTo(p.pts[0].x, p.pts[0].y);
        for (let i = 1; i < p.pts.length; i++)this.x.lineTo(p.pts[i].x, p.pts[i].y); this.x.stroke();
        this.x.lineWidth = 1; for (let i = 1; i < p.pts.length - 1; i++) { if (Math.random() < 0.3) { this.x.beginPath(); this.x.moveTo(p.pts[i].x, p.pts[i].y); this.x.lineTo(p.pts[i].x + (Math.random() - .5) * 40, p.pts[i].y + 20 + Math.random() * 20); this.x.stroke(); } }
      } else {
        if (a <= .001) { this.x.restore(); continue; }
        this.x.globalAlpha = a; this.x.translate(p.x, p.y); this.x.rotate(p.a);
        this.x.fillStyle = '#5aa552'; this.x.beginPath();
        this.x.ellipse(0, 0, p.sz, p.sz * .38, 0, 0, Math.PI * 2); this.x.fill();
        this.x.strokeStyle = '#1c7a4b'; this.x.globalAlpha = a * .35; this.x.lineWidth = .5;
        this.x.beginPath(); this.x.moveTo(-p.sz * .7, 0); this.x.lineTo(p.sz * .7, 0); this.x.stroke();
      } this.x.restore();
    }
  }
}
/* Animate the counter values on the active page and (re)start the
   particle FX loop for the overview cards. Under reduced motion the
   final values render instantly instead. */
function initKpiAnimations() {
  if (_kfxRAF) { cancelAnimationFrame(_kfxRAF); _kfxRAF = null; } _kfxSys.length = 0;

  const activePage = document.querySelector('.page.active');
  if (!activePage) return;

  if (!reduceMotion) {
    activePage.querySelectorAll('.counter-val').forEach(el => {
      const raw = el.getAttribute('data-val');
      if (raw === 'null' || raw === '' || raw === 'undefined') { el.textContent = ''; return; }
      let target = parseFloat(raw);
      let dec = parseInt(el.getAttribute('data-dec')) || 0;
      let obj = { val: 0 };
      gsap.to(obj, {
        val: target,
        duration: 1.5,
        ease: 'power2.out',
        onUpdate: () => { el.textContent = fmt(obj.val, dec); },
        onComplete: () => { el.textContent = fmt(target, dec); }
      });
    });
  } else {
    activePage.querySelectorAll('.counter-val').forEach(el => {
      const raw = el.getAttribute('data-val');
      el.textContent = raw === 'null' || raw === '' || raw === 'undefined'
        ? '' : fmt(parseFloat(raw), parseInt(el.getAttribute('data-dec')) || 0);
    });
  }

  if (reduceMotion) return;
  const ct = document.getElementById('overviewKpis');
  if (ct && ct.closest('.page.active')) {
    ct.querySelectorAll('.kpi-fx-canvas').forEach(c => { _kfxSys.push(new _KPar(c, c.dataset.fx)); });
    if (_kfxSys.length) {
      (function lp() {
        if (!ct.closest('.page.active')) { _kfxRAF = null; return; }
        _kfxSys.forEach(s => { s.tick(); s.draw(); }); _kfxRAF = requestAnimationFrame(lp);
      })();
    }
  }
}

/* ---- Chart FX: 3D interactive tilt ---- */
/* Pointer-tracked 3D tilt on chart cards. */
function initChartAnimations() {
  // Parallax removed
}

/* Master re-render for the active page: KPIs, charts, table, then the
   entrance animations. Runs on load, on every filter change, and on
   every page switch. */
function refresh() {
  syncMonthOptions();
  outreach = outreachFor(+yearFilter.value, monthFilter.value);
  // rebuild everything the active page shows
  makeKpis();
  try {
    // A chart-dependency failure must not take the rest of the page down
    // with it: renderTable(), the KPI/chart animation hooks below, and (via
    // start()/boot()) initGreenMap() and query-string page routing all run
    // unconditionally after this line, whether or not charts drew. Chart.js
    // is vendored locally now (see index.html), so this is a last-resort
    // guard, not the primary fix - chart rendering logic itself is unchanged.
    drawCharts();
  } catch (error) {
    console.error('[K-COSMOS] Chart rendering failed; continuing without charts.', error);
  }
  renderTable();
  initKpiAnimations();
  initChartAnimations();

  // KPI cards rise in with a small stagger
  if (!reduceMotion && window.gsap) {
    gsap.killTweensOf('.page.active .kpi'); // Clear out stale, interrupted animations

    gsap.fromTo('.page.active .kpi',
      {
        y: 12,
        opacity: 0
      },
      {
        y: 0,
        opacity: 1,
        stagger: 0.02,
        duration: 0.32,
        ease: 'power2.out',
        // drop the inline styles when done so CSS hover states take over
        clearProps: 'transform,opacity'
      }
    );
  }
}
/* Switch pages: flip .active on the page and dock button, move the dock
   indicator, scroll to top, re-render. */
function go(id) { document.body.setAttribute('data-page', id); document.querySelectorAll('.page').forEach(p => p.classList.remove('active')); document.querySelectorAll('.bottom-dock button').forEach(b => b.classList.toggle('active', b.dataset.page === id)); const activeBtn = document.getElementById(id); activeBtn.classList.add('active'); const dockBtn = document.querySelector(`.bottom-dock button[data-page='${id}']`); if (dockBtn) updateIndicator(dockBtn); window.scrollTo({ top: 0, behavior: 'smooth' }); refresh(); if (id === 'green') requestAnimationFrame(fitGreenMapImage); }
document.querySelectorAll('.bottom-dock button').forEach(b => b.onclick = () => go(b.dataset.page));
['yearFilter', 'monthFilter'].forEach(id => document.getElementById(id).addEventListener('change', refresh));


/* ---- data explorer tables ---- */
/* The backend's DG pathway for a month: DERIVED_FROM_KWH or SOURCE_REPORTED_LITRES. */
function dgOrigin(d, i) { return d?.periodMeta?.[i]?.values?.dg_diesel_litres?.activity_origin || null }
const tables = {};
/* Flatten the master data into the five explorer views (built once at
   startup - filtering and sorting happen in renderTable). */
function buildTables() {
  const rows = [];
  for (const [year, d] of Object.entries(data)) {
    months.forEach((m, i) => {
      if (d.petrolL[i] != null) rows.push([year, m, 'S1', 'Petrol', d.petrolL[i], 'L', d.petrolEF[i], d.petrolEm[i]]);
      if (d.trDieselL[i] != null) rows.push([year, m, 'S1', 'Fleet Diesel', d.trDieselL[i], 'L', d.trDieselEF[i], d.trDieselEm[i]]);
      // DG: a kWh-methodology month lists its source generation and its derived litres;
      // a legacy month lists its source-reported litres. Both are the backend's values.
      const dgDerived = dgOrigin(d, i) === 'DERIVED_FROM_KWH';
      if (d.dgKwh[i] != null) rows.push([year, m, 'S1', 'DG Generation (source)', d.dgKwh[i], 'kWh', null, null]);
      if (d.dgL[i] != null) rows.push([year, m, 'S1', dgDerived ? 'DG Diesel (derived from kWh)' : 'DG Diesel', d.dgL[i], 'L', d.dgEF[i], d.dgEm[i]]);
      if (d.elecKwh[i] != null) rows.push([year, m, 'S2', 'Grid Electricity', d.elecKwh[i], 'kWh', d.gridEF[i], d.elecEm[i]]);
      if (d.lpgKg[i] != null) rows.push([year, m, 'S1', 'LPG', d.lpgKg[i], 'kg', d.lpgEF[i], d.lpgEm[i]]);
    });
  }
  tables.unified = { cols: ['Year', 'Month', 'Scope', 'Source', 'Quantity', 'Unit', 'EF', 'Emissions tCO₂e'], rows };
  tables.fleet = { cols: ['Year', 'Month', 'Petrol L', 'Petrol tCO₂e', 'Diesel L', 'Diesel tCO₂e'], rows: Object.entries(data).flatMap(([year, d]) => months.map((m, i) => d.petrolL[i] != null ? [year, m, d.petrolL[i], d.petrolEm[i], d.trDieselL[i], d.trDieselEm[i]] : null).filter(Boolean)) };
  tables.dg = {
    cols: ['Year', 'Month', 'DG Generation kWh', 'DG Diesel L', 'Diesel litres origin', 'DG Emissions tCO₂e'],
    rows: Object.entries(data).flatMap(([year, d]) => months.map((m, i) => d.dgL[i] != null || d.dgKwh[i] != null
      ? [year, m, d.dgKwh[i], d.dgL[i], { DERIVED_FROM_KWH: 'Derived from kWh', SOURCE_REPORTED_LITRES: 'Source reported' }[dgOrigin(d, i)] || '', d.dgEm[i]]
      : null).filter(Boolean))
  };
  tables.electricity = { cols: ['Year', 'Month', 'Grid kWh', 'Emissions tCO₂e'], rows: Object.entries(data).flatMap(([year, d]) => months.map((m, i) => d.elecKwh[i] != null ? [year, m, d.elecKwh[i], d.elecEm[i]] : null).filter(Boolean)) };
  tables.re = { cols: ['Year', 'Month', 'RE kWh', 'Emission Avoided tCO₂e'], rows: Object.entries(data).flatMap(([year, d]) => months.map((m, i) => d.reKwh[i] != null ? [year, m, d.reKwh[i], d.avoidEm[i]] : null).filter(Boolean)) };
  const derivedFields = [
    ['Scope 1', 'scope1Full', 'tCO₂e', 'scope1_tco2e'],
    ['Scope 2', 'elecEm', 'tCO₂e', 'scope2_tco2e'],
    ['Operational GHG', 'operationalGHG', 'tCO₂e', 'operational_ghg_tco2e'],
    ['Operational GHG per Capita', 'perCapita', 'kgCO₂e/person', 'operational_ghg_per_capita_kgco2e'],
    ['Total Electricity Consumption', 'totalElectricityKwh', 'kWh'],
    ['Renewable Electricity', 'reKwh', 'kWh'],
    ['Renewable Share', 'renewableSharePct', '%'],
    ['Estimated Avoided Grid Emissions', 'avoidEm', 'tCO₂e'],
    ['Water per Person', 'waterPerCapitaL', 'L/person']
  ];
  tables.records = {
    cols: ['Year', 'Period', 'Granularity', 'Domain', 'Metric', 'Value', 'Unit', 'Source kind', 'Coverage',
      'Verification', 'Qualifier', 'Calculation status', 'Contributors', 'Missing contributors'],
    rows: explorerRecordRows
  };
  tables.derived = {
    cols: ['Year', 'Month', 'Indicator', 'Published value', 'Unit', 'Calculation status'],
    rows: Object.entries(data).flatMap(([year, d]) => months.flatMap((m, i) =>
      derivedFields.map(([label, key, unit, code]) => d[key][i] == null ? null
        : [year, m, label, d[key][i], unit, (code && d.periodMeta?.[i]?.values?.[code]?.calculation_status) || '']).filter(Boolean)))
  };
}
let curTable = 'unified', sortCol = null, sortDir = 1;
/* Filled at boot from the timeline: one row per published value. */
let explorerRecordRows = [];
function tableDecimals(column, value) {
  return column.includes('tCO₂e') && value > 0 && value < 0.01 ? 6 : (Math.abs(value) < 10 ? 3 : 2);
}
/* Render the current explorer view through the live search box filter
   and any active column sort. */
function renderTable() {
  if (!tables.unified) return;
  const t = tables[curTable], q = (document.getElementById('search')?.value || '').toLowerCase();
  let rows = t.rows.filter(r => r.some(c => String(c).toLowerCase().includes(q)));
  if (sortCol !== null) {
    rows = [...rows].sort((a, b) => {
      const x = a[sortCol], y = b[sortCol];
      const nx = parseFloat(String(x).replace(/,/g, '')), ny = parseFloat(String(y).replace(/,/g, ''));
      return (!isNaN(nx) && !isNaN(ny) ? nx - ny : String(x).localeCompare(String(y))) * sortDir;
    });
  }
  const head = document.querySelector('#dataTable thead'), body = document.querySelector('#dataTable tbody');
  if (!head) return;
  head.innerHTML = '<tr>' + t.cols.map((c, i) => `<th data-c="${i}">${c}${sortCol === i ? (sortDir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr>';
  body.innerHTML = rows.map(r => '<tr>' + r.map((c, i) => {
    const value = t.cols[i] === 'Scope'
      ? `<span class="pill ${c === 'S1' ? 's1' : 's2'}">${c}</span>`
      : typeof c === 'number' ? fmt(c, tableDecimals(t.cols[i], c))
        : c == null ? '' : c;
    return `<td class="${typeof c === 'number' ? 'num' : ''}">${value}</td>`;
  }).join('') + '</tr>').join('');
  head.querySelectorAll('th').forEach(th => th.onclick = () => {
    const column = +th.dataset.c;
    if (sortCol === column) sortDir *= -1;
    else { sortCol = column; sortDir = 1; }
    renderTable();
  });
}
document.getElementById('search')?.addEventListener('input', renderTable);
document.querySelectorAll('#tableTabs button').forEach(b => b.onclick = () => { document.querySelectorAll('#tableTabs button').forEach(x => x.classList.remove('active')); b.classList.add('active'); curTable = b.dataset.t; sortCol = null; renderTable(); });
/* Download the current explorer view as CSV. */
document.getElementById('exportBtn').onclick = () => { const t = tables[curTable] || tables.unified; const csv = [t.cols.join(',')].concat(t.rows.map(r => r.map(c => `"${c == null ? '' : c}"`).join(','))).join('\n'); const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); a.download = `kct_${curTable}.csv`; a.click(); };

/* Green Cover zone map: hover/focus pins showing per-zone tree+species
   counts (from green.zones, keyed by the pin's data-zone) plus a cursor-tilt
   parallax on the whole image. The 7 pins are static markup (their left/top
   % are hand-measured against the baked-in pin graphics in green_map.png,
   not data - see the chat where each was pinpointed), so this wires up
   behavior once rather than rebuilding anything per refresh(). */
/* Sizes the zone-map image to whatever vertical space is actually left
   between the card and the floating bottom dock, instead of guessing a
   fixed budget - so it renders as large as it can while still fitting
   the viewport with no scroll. Only measurable while the page is visible
   (`.page:not(.active)` is display:none), so callers must ensure that
   first - see the go()/boot() call sites below. */
function fitGreenMapImage() {
  const stage = document.getElementById('gmStage');
  if (!stage) return;
  const stageRect = stage.getBoundingClientRect();
  if (stageRect.width === 0) return; // page not visible yet
  const dock = document.querySelector('.bottom-dock-wrapper');
  const dockH = dock ? dock.getBoundingClientRect().height : 0;
  const available = window.innerHeight - stageRect.top - dockH - 24;
  /* Prefer the real available space (so it fits with no scroll on most
     screens), but never render it cramped: on short windows this floor
     wins instead, and the card scrolls a little rather than the photo
     shrinking to a thumbnail. Capped so ultra-tall monitors don't blow it
     up past what still reads well next to the KPI row above. */
  const target = Math.min(Math.max(available, 460), window.innerHeight * 0.62);
  stage.style.setProperty('--gm-max-h', Math.round(target) + 'px');
}
window.addEventListener('resize', fitGreenMapImage);

function initGreenMap() {
  const stage = document.getElementById('gmStage');
  const plane = document.getElementById('gmPlane');
  const tooltip = document.getElementById('gmTooltip');
  if (!stage || !plane || !tooltip) return;

  const zoneByName = {};
  (green.zones || []).forEach(z => { zoneByName[z.zone] = z; });

  function positionTooltip(pin) {
    const stageRect = stage.getBoundingClientRect(), pinRect = pin.getBoundingClientRect();
    const spaceAbove = pinRect.top - stageRect.top;
    const below = spaceAbove < 90; // not enough room for the card above - flip it under the pin instead
    tooltip.classList.toggle('gm-tt-below', below);
    tooltip.style.left = (pinRect.left + pinRect.width / 2 - stageRect.left) + 'px';
    tooltip.style.top = (below ? pinRect.bottom - stageRect.top : pinRect.top - stageRect.top) + 'px';
  }

  let activePin = null;
  function showTooltip(pin) {
    const z = zoneByName[pin.dataset.zone];
    tooltip.innerHTML = `<div class="gm-tt-zone">${pin.dataset.zone}</div>
      <div class="gm-tt-row"><span>Trees</span><b>${z ? fmt(z.trees, 0) : '—'}</b></div>
      <div class="gm-tt-row"><span>Species</span><b>${z ? fmt(z.species, 0) : '—'}</b></div>`;
    positionTooltip(pin);
    tooltip.classList.add('visible');
    activePin = pin;
    pin.classList.add('gm-active');
  }
  function hideTooltip() {
    tooltip.classList.remove('visible');
    if (activePin) activePin.classList.remove('gm-active');
    activePin = null;
  }

  stage.querySelectorAll('.gm-pin').forEach(pin => {
    pin.addEventListener('mouseenter', () => showTooltip(pin));
    pin.addEventListener('mouseleave', hideTooltip);
    pin.addEventListener('focus', () => showTooltip(pin));
    pin.addEventListener('blur', hideTooltip);
  });

  if (!reduceMotion && window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
    const MAX_TILT = 2; // degrees - subtle, not a full "tilt card" effect
    stage.addEventListener('mousemove', (e) => {
      const r = stage.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
      plane.style.transform = `rotateX(${((0.5 - py) * MAX_TILT * 2).toFixed(2)}deg) rotateY(${((px - 0.5) * MAX_TILT * 2).toFixed(2)}deg) scale(1.005)`;
      if (activePin) positionTooltip(activePin);
    });
    stage.addEventListener('mouseleave', () => { plane.style.transform = ''; hideTooltip(); });
  } else {
    stage.addEventListener('mouseleave', hideTooltip);
  }
}

/* Period controls reflect genuine granularity: each year offers its
   aggregate (Full Year, or YTD with its real end month) and only the months
   that have genuine monthly records. */
let periodSelector = [];
let outreachFor = () => ({ published: false });
function monthOptionsFor(year) {
  const entry = periodSelector.find(item => String(item.year) === String(year));
  let primary = true;
  return (entry ? entry.options : []).map(option => {
    if (option.granularity === 'MONTHLY') return { value: String(Number(option.key.slice(5, 7)) - 1), label: option.label };
    const value = primary ? 'all' : `agg:${option.key}`;
    primary = false;
    return { value, label: option.label };
  });
}
function syncMonthOptions(preferred) {
  if (monthFilter.dataset.year === yearFilter.value && preferred === undefined) return;
  const options = monthOptionsFor(yearFilter.value);
  if (!options.length) options.push({ value: 'all', label: 'Full year' });
  const keep = preferred !== undefined ? preferred : monthFilter.value;
  monthFilter.innerHTML = '';
  options.forEach(option => monthFilter.add(new Option(option.label, option.value)));
  monthFilter.value = options.some(option => option.value === keep) ? keep : (options[0]?.value || 'all');
  monthFilter.dataset.year = yearFilter.value;
}
function populatePeriodControls(defaultKey) {
  if (!periodSelector.length) return;
  // ?period=2025-FY / 2025-03 deep-links a period, but only one the timeline offers.
  const requested = new URLSearchParams(window.location.search).get('period');
  if (requested && periodSelector.some(item => item.options.some(option => option.key === requested))) {
    defaultKey = requested;
  }
  yearFilter.innerHTML = '';
  periodSelector.forEach(item => yearFilter.add(new Option(String(item.year), String(item.year))));
  const [year, rest] = defaultKey ? [defaultKey.slice(0, 4), defaultKey.slice(5)] : [String(periodSelector[periodSelector.length - 1].year), ''];
  yearFilter.value = year;
  const aggregateValue = monthOptionsFor(year).find(option => option.value === `agg:${defaultKey}`);
  syncMonthOptions(/^\d{2}$/.test(rest) ? String(Number(rest) - 1) : (aggregateValue ? aggregateValue.value : 'all'));
}

/* Boot: build the tables, first render, entrance sweep. */
function start() { buildTables(); refresh(); initGreenMap(); if (!reduceMotion) { gsap.from('.showcase', { y: 14, opacity: 0, duration: .55, ease: 'power2.out' }); gsap.from('.topbar,.toolbar', { y: -16, opacity: 0, duration: .5, stagger: .08 }); } }
/* Fetch and normalize the active public release before booting -
   everything below this point in the file only reads `data` from inside
   functions that run after start(), never at parse time. */
(async function boot() {
  const loaded = await loadDashboardData();
  data = loaded.data;
  green = loaded.green;
  outreachFor = loaded.outreachFor;
  publication = loaded.publication;
  periodSelector = loaded.selector;
  explorerRecordRows = loaded.explorerRows;
  populatePeriodControls(loaded.defaultKey);
  start();
  const requestedPage = new URLSearchParams(window.location.search).get('page');
  if (requestedPage && document.getElementById(requestedPage)) go(requestedPage);
})();


/* Slide the dock's dark pill under the active nav button. */
function updateIndicator(btn) {
  const ind = document.getElementById('indicator');
  if (ind && btn) {
    ind.style.width = btn.offsetWidth + 'px';
    ind.style.transform = `translateX(${btn.offsetLeft}px)`;
  }
}

// Initial setup
window.addEventListener('load', () => {
  const activeBtn = document.querySelector('.bottom-dock button.active');
  if (activeBtn) updateIndicator(activeBtn);
});
window.addEventListener('resize', () => {
  const activeBtn = document.querySelector('.bottom-dock button.active');
  if (activeBtn) updateIndicator(activeBtn);
});

// Direct load animation
window.addEventListener('load', () => {
  gsap.fromTo('.page.active, .topbar', { y: 50, opacity: 0 }, { y: 0, opacity: 1, duration: 1.2, ease: 'power3.out' });
});


/* ---- KPI detail sidebar. Copy keyed by exact card title; titles not
   listed here fall back to a generic blurb in openKpiModal. ---- */
const kpiDescriptions = {
  "Operational GHG emissions — Scope 1 + Scope 2": {
    def: "The published Scope 1 and Scope 2 results for the selected reporting period, provided by the immutable release.",
    impact: "This bounded operational indicator is not a complete Scope 3 or universal institutional GHG inventory.",
    trend: "No target or trend narrative is asserted here."
  },
  "Per capita emissions": {
    def: "The backend-published operational GHG result converted to kilograms and divided by the approved population reference for the reporting year.",
    impact: "Shown only when both the operational GHG result and a positive year-specific population reference exist; otherwise the card is omitted.",
    trend: "No target or trend narrative is asserted here."
  },
  "Waste per person": {
    def: "The backend-published total waste generated in kilograms divided by the approved population reference for the reporting year.",
    impact: "Shown only when a waste total and a positive population reference exist for the same period; otherwise the card is omitted.",
    trend: "No target or trend narrative is asserted here."
  },
  "Scope 1 emissions": {
    def: "The published sum of Petrol CO₂e, Transport Diesel CO₂e, DG Diesel CO₂e, and LPG CO₂e.",
    impact: "Scope 1 is shown only when every required component result exists; a partial Scope 1 is never shown.",
    trend: "No target or trend narrative is asserted here."
  },
  "Total waste diverted from landfill": {
    def: "The institution's dry waste for the year. By the approved methodology, dry waste is the waste diverted from landfill.",
    impact: "Calculated by the backend from the dry-waste figure; no diversion percentage is applied.",
    trend: "No target or trend narrative is asserted here."
  },
  "Waste contribution per person": {
    def: "Total waste generated in kilograms divided by the approved population reference for the reporting year.",
    impact: "Shown for the year's current Full Year or year-to-date waste; the selected month does not filter it.",
    trend: "No target or trend narrative is asserted here."
  },
  "Scope 2 emissions": {
    def: "The frozen published grid-electricity CO₂e result for the selected reporting period.",
    impact: "Scope 2 is shown only when the governed grid-electricity result exists for the whole period.",
    trend: "No target or trend narrative is asserted here."
  }
};

let activeTimelines = [];

/* Open the detail sidebar for a tapped KPI card: clone the card (with
   its live canvas frame and video position), fill the narrative blocks
   and play the entrance timeline. Wired via each card's onclick. */
function openKpiModal(kpiCard) {
  activeTimelines.forEach(tl => tl.kill());
  activeTimelines = [];

  const titleEl = kpiCard.querySelector('.label');
  const title = titleEl ? titleEl.textContent.trim() : "";
  const data = kpiDescriptions[title] || {
    def: `${title || 'This metric'} is shown from source data for the selected reporting period where available.`,
    impact: "No additional methodology, target, or impact claim is inferred from this value.",
    trend: "No target or trend narrative is asserted here."
  };

  const clone = kpiCard.cloneNode(true);
  clone.removeAttribute('onclick');

  const originalCanvas = kpiCard.querySelector('canvas');
  const clonedCanvas = clone.querySelector('canvas');
  if (originalCanvas && clonedCanvas) {
    clonedCanvas.getContext('2d').drawImage(originalCanvas, 0, 0);
  }

  const originalVideo = kpiCard.querySelector('video');
  const clonedVideo = clone.querySelector('video');
  if (originalVideo && clonedVideo) {
    clonedVideo.currentTime = originalVideo.currentTime;
    clonedVideo.play();
  }

  const kpiModalCloneContainer = document.getElementById('kpiModalCloneContainer');
  kpiModalCloneContainer.innerHTML = '';
  kpiModalCloneContainer.appendChild(clone);

  document.getElementById('kpiDefText').textContent = data.def;
  document.getElementById('kpiImpactText').textContent = data.impact;
  document.getElementById('kpiTrendText').textContent = data.trend;

  const storyDef = document.getElementById('storyDef');
  const storyImpact = document.getElementById('storyImpact');
  const storyTrend = document.getElementById('storyTrend');
  const kpiTrendBar = document.getElementById('kpiTrendBar');
  const storyBarContainer = document.querySelector('.story-bar-container');

  if (storyDef) storyDef.classList.remove('active');
  if (storyImpact) storyImpact.classList.remove('active');
  if (storyTrend) storyTrend.classList.remove('active');
  if (kpiTrendBar) kpiTrendBar.style.width = '0%';
  if (storyBarContainer) storyBarContainer.style.display = data.trendValue ? 'block' : 'none';

  document.body.classList.add('sidebar-active');

  const masterTl = gsap.timeline();
  activeTimelines.push(masterTl);

  masterTl.fromTo(kpiModalCloneContainer,
    { opacity: 0, scale: 0.8, y: 20 },
    { opacity: 1, scale: 1, y: 0, duration: 0.5, ease: "back.out(1.2)" }
  );

  const cloneCounter = clone.querySelector('.counter-val');
  if (cloneCounter) {
    const finalVal = parseFloat(cloneCounter.getAttribute('data-val') || "0");
    const dec = parseInt(cloneCounter.getAttribute('data-dec') || "0");
    masterTl.fromTo(cloneCounter,
      { innerHTML: 0 },
      {
        innerHTML: finalVal,
        duration: 1.5,
        ease: "power2.out",
        onUpdate: function () {
          cloneCounter.innerHTML = Number(this.targets()[0].innerHTML).toFixed(dec);
        }
      },
      "<"
    );
  }

  const blocks = [storyDef, storyImpact, storyTrend].filter(b => b !== null);
  if (blocks.length > 0) {
    masterTl.fromTo(blocks,
      { opacity: 0, y: 20 },
      { opacity: 1, y: 0, duration: 0.5, stagger: 0.15, ease: "power2.out" },
      "-=0.2"
    );
    blocks.forEach((block, index) => {
      gsap.delayedCall(0.5 + (index * 0.15), () => block.classList.add('active'));
    });
  }

  if (data.trendValue && kpiTrendBar) {
    masterTl.to(kpiTrendBar, {
      width: data.trendValue + '%',
      duration: 1,
      ease: "power3.out"
    }, "-=0.2");
  }

  const kpiModalClose = document.getElementById('kpiModalClose');
  if (kpiModalClose) {
    gsap.fromTo(kpiModalClose,
      { opacity: 0, scale: 0.8, rotation: -90 },
      { opacity: 1, scale: 1, rotation: 0, duration: 0.4, delay: 0.5 }
    );
  }
}

/* Close the sidebar and reset its animated pieces. */
function closeKpiModal() {
  activeTimelines.forEach(tl => tl.kill());
  activeTimelines = [];
  document.body.classList.remove('sidebar-active');

  const storyDef = document.getElementById('storyDef');
  const storyImpact = document.getElementById('storyImpact');
  const storyTrend = document.getElementById('storyTrend');
  const blocks = [storyDef, storyImpact, storyTrend].filter(b => b !== null);

  if (blocks.length > 0) {
    gsap.to(blocks, { opacity: 0, y: 20, duration: 0.3, stagger: -0.05 });
  }
  const kpiModalClose = document.getElementById('kpiModalClose');
  if (kpiModalClose) {
    gsap.to(kpiModalClose, { opacity: 0, scale: 0.8, duration: 0.3 });
  }

  const kpiModalCloneContainer = document.getElementById('kpiModalCloneContainer');
  gsap.to(kpiModalCloneContainer, {
    opacity: 0, scale: 0.9, duration: 0.3,
    onComplete: () => {
      if (kpiModalCloneContainer) kpiModalCloneContainer.innerHTML = '';
      blocks.forEach(b => b.classList.remove('active'));
      const kpiTrendBar = document.getElementById('kpiTrendBar');
      if (kpiTrendBar) kpiTrendBar.style.width = '0%';
    }
  });
}

const kpiModalCloseBtn = document.getElementById('kpiModalClose');
if (kpiModalCloseBtn) {
  kpiModalCloseBtn.addEventListener('click', closeKpiModal);
}

document.addEventListener('click', e => {
  if (e.target.matches('.ghg-tgl')) {
    document.querySelectorAll('.ghg-tgl').forEach(b => {
      b.classList.remove('active');
      b.style.background = 'transparent';
      b.style.color = 'var(--faint)';
    });
    e.target.classList.add('active');
    e.target.style.background = 'var(--surface)';
    e.target.style.color = 'var(--ink)';

    window.currentGhgProfileView = e.target.id.replace('btnGhg', '').toLowerCase();
    refresh();
  }
});
