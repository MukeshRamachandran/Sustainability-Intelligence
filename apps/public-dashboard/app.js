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
const EF = { petrol: 2.388, diesel: 2.701, grid: 0.727 };

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

/* ---- master data ---- populated at boot by loadDashboardData() (data-loader.js),
   which fetches data/*.csv (+ the optional data/dashboard_master.json overlay)
   and computes every field below from that source data. See PROJECT_GUIDE.md. */
let data = {};
/* Green cover: a one-time campus survey, not year/month filtered - see
   data-loader.js's block-section parser and green_master.csv. */
let green = {};
/* Community outreach is populated only from the active backend release. */
let outreach = {};

/* null/NaN-safe number coercion - the master data uses null for months with no reading. */
function n(v) { return v == null || Number.isNaN(+v) ? 0 : +v }
/* Sum a monthly array over [s, e) with null-safety. */
function sum(a, s = 0, e = 12) { return a.slice(s, e).reduce((x, y) => x + n(y), 0) }
/* Indian-locale number formatting at d decimals. */
function fmt(v, d = 0) { return n(v).toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d }) }
/* Percent change vs a baseline (0 when there is no baseline). Doc §17/§18/§20/§27. */
function pct(cur, prev) { return Calculations.percentageChange(cur, prev) }
/* How many leading months a metric actually has readings for - sources don't
   all report the same number of months for a YTD year (fuel/Fleet still
   stop at April 2026, energy/water now run through June), so each array's
   own extent is used instead of one hardcoded cutoff. */
function monthsWithData(arr) { let last = 0; for (let i = 0; i < 12; i++) if (arr[i] != null) last = i + 1; return last }
/* Value of a monthly metric under the month filter ('all' = whole period, summed
   only over the months that array actually has; a specific month otherwise). */
function valFor(d, arr, m) { return m === 'all' ? sum(arr, 0, d.frequency === 'ytd' ? monthsWithData(arr) : 12) : n(arr[+m]) }
/* The active toolbar selection plus its year dataset. */
function currentPeriod() { return { year: +yearFilter.value, month: monthFilter.value, d: data[yearFilter.value] } }
/* Human label for the selection - "Mar 2025" or the year dataset's own label. */
function periodLabel(year, month) { return month === 'all' ? data[year].label : `${months[+month]} ${year}` }
/* Comparison baseline for a metric: same period, one year back. null = nothing to compare against (no prior-year data). */
function previousValue(arrName) { const { year, month, d } = currentPeriod(); const py = data[year - 1]; if (!py) return null; if (month === 'all') { const end = d.frequency === 'ytd' ? monthsWithData(d[arrName]) : 12; return sum(py[arrName], 0, end); } return valFor(py, py[arrName], month) }
/* The up/down trend chip; lowerGood flips which direction counts as green. */
function trendHtml(cur, prev, lowerGood = true) { if (prev == null || prev === 0) return `<b class="neutral">base</b><span>no comparison</span>`; const p = pct(cur, prev); const good = lowerGood ? p <= 0 : p >= 0; return `<b class="${good ? 'good' : 'bad'}">${p >= 0 ? '↑' : '↓'} ${Math.abs(p).toFixed(1)}%</b><span>vs last year</span>` }
/* Build one KPI card: optional ambient FX layer (looping video, canvas
   particles or SVG scene per fxType), icon, counter (animated later by
   initKpiAnimations) and trend chip. Clicking opens the detail sidebar. */
function kpi(title, value, unit, accent, icon, prev, lowerGood = true, dec = 2, fxType = null) { const fx = fxType && !reduceMotion; const cls = fx ? ` kpi-fx kpi-fx-${fxType}` : ''; const pSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>'; const inner = (fx && (fxType === 'smoke' || fxType === 'leaves' || fxType === 'lightning') ? `<canvas class="kpi-fx-canvas" data-fx="${fxType}"></canvas>` : '') + (fx && fxType === 'peoplefade' ? `<div class="kpi-fx-people">${pSvg}${pSvg}${pSvg}</div>` : '') + (fx && fxType === 'solarvideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="solar-kpi.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'leavesvideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="leavesfall.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'fuelpourvideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="fuelpour.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'electricsparkvideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="electricspark.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'quepervideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="queper.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'earthvideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="earth.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'industrynewvideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="industrynew.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'elecmetervideo' ? `<video autoplay loop muted playsinline class="kpi-fx-video"><source src="elecmeter.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>` : '') + (fx && fxType === 'sunrays' ? `<div class="kpi-fx-solar-bg"><svg viewBox="0 0 100 100" preserveAspectRatio="xMaxYMax meet"><defs><radialGradient id="sunGlow" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#fbbf24" stop-opacity="0.7"/><stop offset="100%" stop-color="#fbbf24" stop-opacity="0"/></radialGradient><linearGradient id="panelGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#1e3a8a"/><stop offset="100%" stop-color="#1e40af"/></linearGradient></defs><g class="solar-sun"><circle cx="75" cy="25" r="30" fill="url(#sunGlow)"/><circle cx="75" cy="25" r="10" fill="#f59e0b"/><g class="solar-rays" stroke="#fbbf24" stroke-width="2" stroke-linecap="round"><line x1="75" y1="5" x2="75" y2="45"/><line x1="55" y1="25" x2="95" y2="25"/><line x1="61" y1="11" x2="89" y2="39"/><line x1="61" y1="39" x2="89" y2="11"/></g></g><g class="solar-panel" transform="translate(45, 50) scale(0.65)"><rect x="42" y="30" width="4" height="15" fill="#64748b"/><line x1="25" y1="45" x2="63" y2="45" stroke="#64748b" stroke-width="4" stroke-linecap="round"/><path d="M10,30 L35,5 L85,5 L60,30 Z" fill="url(#panelGrad)" stroke="#94a3b8" stroke-width="2" stroke-linejoin="round"/><line x1="22" y1="18" x2="72" y2="18" stroke="#60a5fa" stroke-width="1.5"/><line x1="30" y1="5" x2="18" y2="30" stroke="#60a5fa" stroke-width="1.5"/><line x1="50" y1="5" x2="38" y2="30" stroke="#60a5fa" stroke-width="1.5"/><line x1="70" y1="5" x2="58" y2="30" stroke="#60a5fa" stroke-width="1.5"/></g></svg></div>` : '') + (fx && fxType === 'smoke' ? `<div class="kpi-fx-factory"><svg viewBox="0 0 100 100" preserveAspectRatio="xMaxYMax meet"><rect x="70" y="30" width="10" height="60" fill="#e0e0e0"/><rect x="70" y="35" width="10" height="8" fill="#d94b41"/><rect x="70" y="50" width="10" height="8" fill="#d94b41"/><rect x="70" y="65" width="10" height="8" fill="#d94b41"/><rect x="40" y="10" width="12" height="80" fill="#e0e0e0"/><rect x="40" y="15" width="12" height="10" fill="#d94b41"/><rect x="40" y="35" width="12" height="10" fill="#d94b41"/><rect x="40" y="55" width="12" height="10" fill="#d94b41"/><rect x="40" y="75" width="12" height="10" fill="#d94b41"/><rect x="15" y="50" width="8" height="40" fill="#e0e0e0"/><rect x="15" y="55" width="8" height="6" fill="#d94b41"/><rect x="15" y="70" width="8" height="6" fill="#d94b41"/><path d="M 5,90 L 95,90 L 95,75 L 80,75 L 80,80 L 60,80 L 60,70 L 30,70 L 30,85 L 5,85 Z" fill="#c43d34"/></svg></div>` : '') + (fx && fxType === 'lightning' ? `<div class="kpi-fx-tower"><svg viewBox="0 0 100 100" preserveAspectRatio="xMaxYMax meet"><g stroke="#3a4a5a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="30" y1="90" x2="45" y2="20"/><line x1="70" y1="90" x2="55" y2="20"/><line x1="45" y1="20" x2="50" y2="10"/><line x1="55" y1="20" x2="50" y2="10"/><line x1="20" y1="40" x2="80" y2="40"/><line x1="25" y1="60" x2="75" y2="60"/><line x1="35" y1="80" x2="65" y2="80"/><line x1="42" y1="40" x2="33" y2="60"/><line x1="58" y1="40" x2="67" y2="60"/><line x1="42" y1="40" x2="58" y2="60"/><line x1="58" y1="40" x2="42" y2="60"/></g></svg></div>` : ''); const animMap = { 'Scope 1: Fleet + DG + LPG': 'anim-pulse', 'Petrol consumption': 'anim-fuel', 'Petrol emissions': 'anim-smoke', 'Fleet diesel consumption': 'anim-bus', 'Fleet diesel emissions': 'anim-bus-smoke', 'DG diesel consumption': 'anim-vibrate', 'DG diesel emissions': 'anim-generator-smoke', 'LPG consumption': 'anim-fuel', 'LPG emissions': 'anim-smoke', 'Combined diesel emissions': 'anim-combined-smoke' }; const iconClass = animMap[title] ? `icon kpi-icon ${animMap[title]}` : 'icon'; return `<article class="kpi${cls}" style="--a:${accent}" onclick="openKpiModal(this)">${inner}<div class="${iconClass}">${ic(icon)}</div><div class="label">${title}</div><div class="value"><span class="counter-val" data-val="${value}" data-dec="${dec}">${fmt(value, dec)}</span><small>${unit}</small></div><div class="trend">${trendHtml(value, prev, lowerGood)}</div></article>` }

/* Recompute the headline figures for the current filters and rebuild
   every page's KPI grid plus the public highlights strip. */
function makeKpis() {
  const { year, month, d } = currentPeriod();
  const outreachForPeriod = outreach.published && outreach.year === year && month !== 'all' && outreach.month === (+month + 1);
  const scope1 = valFor(d, d.scope1Full, month), diesel = valFor(d, d.dieselCombo, month), petrol = valFor(d, d.petrolEm, month), scope2 = valFor(d, d.elecEm, month), elec = valFor(d, d.elecKwh, month);
  const re = valFor(d, d.reKwh, month), avoid = valFor(d, d.avoidEm, month);
  const gross = Calculations.grossEmissions(scope1, scope2), net = Calculations.netCarbonIndicator(gross, avoid);

  /* Shared with the Waste/Water KPI blocks further down - computed once
     here so the Overview strip and those pages can't drift apart. */
  const wasteTot = (d.totalWaste || (d.wetWaste + d.dryWaste) || 0) / 1000;
  // Diverted = the itemised dry-waste stream - see the Waste block below for why.
  const wasteDiverted = (d.dryWaste || 0) / 1000;
  const waterMonths = monthsWithData(d.waterKL);
  const waterKL = month === 'all'
    ? (d.waterTotalAnnual != null ? d.waterTotalAnnual : sum(d.waterKL, 0, waterMonths))
    : n(d.waterKL[+month]);

  periodText.textContent = `Viewing ${periodLabel(year, month)}`;
  heroGHG(gross, year, month, d, avoid, net);
  const hsSolar = document.getElementById('hs-solar-val'), hsAdmin = document.getElementById('hs-admin-val'), hsDg = document.getElementById('hs-dg-val');
  if (hsSolar) hsSolar.textContent = fmt(re, 0) + ' kWh';
  if (hsAdmin) hsAdmin.textContent = fmt(elec, 0) + ' kWh';
  if (hsDg) hsDg.textContent = fmt(valFor(d, d.dgEm, month), 2) + ' tCO₂e';
  document.getElementById('overviewKpis').innerHTML = [
    kpi('Renewable energy used', re, 'kWh', colors.emerald, 'sun', previousValue('reKwh'), false, 0, 'solarvideo'),
    kpi('Total grid electricity consumed', elec, 'kWh', colors.cyan, 'bolt', previousValue('elecKwh'), true, 0, 'elecmetervideo'),
    kpi('Total water recycled', d.waterRecycledKL, 'KL', colors.cyan, 'repeat', null, false, 0),
    kpi('Total waste generated', wasteTot, 'tons', colors.orange, 'trash', null, true, 1),
    kpi('Landfill diversion', Calculations.safeRatioPct(wasteDiverted, wasteTot), '%', colors.lime, 'shield', null, false, 1),
    kpi('Total water usage', waterKL, 'KL', colors.cyan, 'droplet', null, true, 0),
    kpi('Total green cover', green.totalGreenCoverPct, '%', colors.emerald, 'tree', null, false, 0),
    kpi('Outreach impact', outreachForPeriod ? outreach.participantsServed : 0, 'people', colors.gold, 'users', null, false, 0)
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
    </style>
    <div class="ghg-hero">
      
      <!-- Top Section -->
      <div class="ghg-top">
        <div>
          <div class="ghg-title-row">
            <div class="icon">${ic('globe')}</div>
            Gross Organizational Emissions
          </div>
          <div class="ghg-value-row">
            <span class="counter-val" data-val="${gross}" data-dec="2">0</span>
            <span style="font-size:1.2rem; font-weight:500; color:var(--muted);">tCO₂e</span>
          </div>
        </div>
        <div class="ghg-badge">* Scope 3 emissions not included</div>
      </div>

      <!-- Middle Progress Bar -->
      <div class="ghg-bar-container">
        <div class="ghg-bar-1" style="width: ${gross > 0 ? (scope1 / gross) * 100 : 0}%;"></div>
        <div class="ghg-bar-2" style="width: ${gross > 0 ? (scope2 / gross) * 100 : 0}%;"></div>
      </div>

      <!-- Bottom Splits -->
      <div class="ghg-splits">
        
        <!-- Scope 1 -->
        <div class="ghg-split">
          <div class="ghg-split-icon">${ic('factory')}</div>
          <div>
            <div class="ghg-split-head">
              <div class="ghg-split-dot" style="background: ${colors.emerald};"></div>
              Scope 1 Emissions
            </div>
            <div class="ghg-split-val">
              <span class="counter-val" data-val="${scope1}" data-dec="2">0</span>
              <span style="font-size:13px; font-weight:500; color:var(--muted);">tCO₂e</span>
            </div>
            <div class="ghg-split-note">* fugitive, process emissions excluded</div>
          </div>
        </div>

        <!-- Scope 2 -->
        <div class="ghg-split">
          <div class="ghg-split-icon">${ic('bolt')}</div>
          <div>
            <div class="ghg-split-head">
              <div class="ghg-split-dot" style="background: var(--muted);"></div>
              Scope 2 Emissions
            </div>
            <div class="ghg-split-val">
              <span class="counter-val" data-val="${scope2}" data-dec="2">0</span>
              <span style="font-size:13px; font-weight:500; color:var(--muted);">tCO₂e</span>
            </div>
            <div class="ghg-split-note">* Market based</div>
          </div>
        </div>

      </div>

    </div>`,
    kpi('Per capita emissions', d.perCapita || 0, d.perCapita ? 'tCO₂e/person' : 'N/A', colors.blue, 'users', null, true, 3, 'quepervideo'),
    kpi('Reduction through renewables', avoid, 'tCO₂e', colors.emerald, 'leaf', previousValue('avoidEm'), true),
    kpi('Carbon saved by green cover', null, 'tCO₂e', colors.emerald, 'tree', null, true)
  ].join('');

  const totalMix = elec + re;
  const gridPctStr = totalMix > 0 ? ((elec / totalMix) * 100).toFixed(0) : 0;
  const rePctStr = totalMix > 0 ? ((re / totalMix) * 100).toFixed(0) : 0;
  // Real on-campus/procured columns from energy_master.csv, not an estimated split of re.
  const onSiteVal = valFor(d, d.reOnCampusKwh, month);
  const procuredVal = valFor(d, d.reProcuredKwh, month);

  const elecMixWidget = document.getElementById('elecMixWidget');
  if (elecMixWidget) {
    elecMixWidget.innerHTML = `
      <style>
      .elec-mix-widget { display: flex; align-items: center; justify-content: center; background: var(--surface); border: 1px solid var(--line); border-radius: 16px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05); padding: 24px; position: relative; }
      .elec-mix-title-box { position: absolute; top: 20px; left: 24px; display: flex; align-items: center; gap: 12px; }
      .elec-mix-icon { width: 40px; height: 40px; border-radius: 10px; background: rgba(217, 160, 91, 0.1); color: var(--gold, #d9a05b); display: flex; align-items: center; justify-content: center; font-size: 20px; }
      .elec-mix-chart-area { display: flex; align-items: center; justify-content: center; position: relative; gap: 24px; margin-top: 64px; }
      .elec-mix-chart-container { width: 240px; height: 240px; position: relative; transition: transform 0.3s ease; }
      .elec-mix-chart-container:hover { transform: scale(1.02); }
      .elec-mix-center-icon { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: var(--gold, #d9a05b); opacity: 0.8; transition: transform 0.3s ease; }
      .elec-mix-chart-container:hover .elec-mix-center-icon { transform: translate(-50%, -50%) scale(1.1); }
      .elec-label-block { display: flex; flex-direction: column; gap: 6px; width: 110px; }
      .elec-label-left { text-align: right; }
      .elec-label-right { text-align: left; }
      .elec-pct { font-size: 28px; font-weight: 700; line-height: 1; }
      .elec-pct-grid { color: var(--gold, #d9a05b); }
      .elec-pct-re { color: var(--emerald, #1c7a4b); }
      .elec-sub { font-size: 13px; color: var(--ink); font-weight: 600; line-height: 1.2; }
      .elec-desc { font-size: 11px; color: var(--ink); opacity: 0.6; line-height: 1.3; }
      @media (max-width: 1200px) {
        .elec-mix-chart-area { flex-direction: column; gap: 24px; }
        .elec-label-left, .elec-label-right { text-align: center; }
        .elec-mix-title-box { position: relative; top: 0; left: 0; margin-bottom: 16px; margin-top: 0; }
        .elec-mix-widget { flex-direction: column; padding: 20px; }
      }
      </style>
      <div class="elec-mix-widget">
        <div class="elec-mix-title-box">
          <div class="elec-mix-icon">${ic('bolt')}</div>
          <div>
            <h3 style="margin: 0 0 4px 0;">Electricity Mix</h3>
            <p class="hint" style="margin: 0;">Grid vs Renewable — ${periodLabel(year, month)}</p>
          </div>
        </div>
        
        <div class="elec-mix-chart-area">
          <div class="elec-label-block elec-label-left">
            <div class="elec-pct elec-pct-re">${rePctStr}%</div>
            <div class="elec-sub">Renewable<br>energy</div>
            <div class="elec-desc">On-site Solar PV & Procured Green Energy</div>
          </div>
          
          <div class="elec-mix-chart-container">
            <canvas id="elecMixChartCanvas"></canvas>
          </div>
          
          <div class="elec-label-block elec-label-right">
            <div class="elec-pct elec-pct-grid">${gridPctStr}%</div>
            <div class="elec-sub">Grid<br>electricity</div>
            <div class="elec-desc">Higher carbon intensity</div>
          </div>
        </div>
      </div>
    `;
  }

  const fuelMixWidget = document.getElementById('fuelMixWidget');
  if (fuelMixWidget) {
    const lpg = valFor(d, d.lpgEm, month) || 0;
    const petrolEm = valFor(d, d.petrolEm, month) || 0;
    const dieselEm = valFor(d, d.dieselCombo, month) || 0;
    const totalFuel = dieselEm + petrolEm + lpg;
    const dieselPct = totalFuel > 0 ? ((dieselEm / totalFuel) * 100).toFixed(0) : 0;
    const petrolPct = totalFuel > 0 ? ((petrolEm / totalFuel) * 100).toFixed(0) : 0;
    const lpgPct = totalFuel > 0 ? ((lpg / totalFuel) * 100).toFixed(0) : 0;

    fuelMixWidget.innerHTML = `
      <div class="elec-mix-widget">
        <div class="elec-mix-title-box">
          <div class="elec-mix-icon" style="background: rgba(221, 107, 32, 0.1); color: var(--orange, #dd6b20);">${ic('flame')}</div>
          <div>
            <h3 style="margin: 0 0 4px 0;">Fossil Fuel Mix</h3>
            <p class="hint" style="margin: 0;">Diesel vs Others — ${periodLabel(year, month)}</p>
          </div>
        </div>
        
        <div class="elec-mix-chart-area">
          <div class="elec-label-block elec-label-left" style="gap: 20px;">
            <div>
              <div class="elec-pct" style="color: var(--violet, #6b5b95);">${lpgPct}%</div>
              <div class="elec-sub">LPG<br>fuel</div>
            </div>
            <div>
              <div class="elec-pct" style="color: var(--teal, #319795);">${petrolPct}%</div>
              <div class="elec-sub">Petrol<br>fuel</div>
            </div>
          </div>
          
          <div class="elec-mix-chart-container">
            <canvas id="fuelMixChartCanvas"></canvas>
          </div>
          
          <div class="elec-label-block elec-label-right">
            <div class="elec-pct" style="color: var(--orange, #dd6b20);">${dieselPct}%</div>
            <div class="elec-sub">Diesel<br>fuel</div>
            <div class="elec-desc">Fleet & DG Diesel split</div>
          </div>
        </div>
      </div>
    `;
  }

  const wasteKpisEl = document.getElementById('wasteKpis');
  if (wasteKpisEl) {
    const perPerson = d.population ? (wasteTot * 1000 / d.population) : 0;

    wasteKpisEl.innerHTML = [
      kpi('Total waste generated', wasteTot, 'tons', colors.orange, 'trash', null, true, 1),
      kpi('Total waste diverted from landfill', wasteDiverted, 'tons', colors.emerald, 'shield', null, false, 1),
      kpi('Waste contribution per person', perPerson, 'kg/person', colors.teal, 'users', null, true, 1)
    ].join('');
  }

  const waterKpisEl = document.getElementById('waterKpis');
  if (waterKpisEl) {
    const waterPerCapitaL = d.population ? (waterKL * 1000 / d.population) : 0;
    const waterPy = data[year - 1];
    /* The trend chip needs a same-window comparison (this year's month count
       against last year's), so it always uses the monthly arrays even when
       the headline value above prefers the more complete annual total -
       mixing a partial-year sum against a full annual total would show a
       misleading "decrease" purely from comparing fewer months to twelve. */
    const waterPrev = waterPy ? (month === 'all' ? sum(waterPy.waterKL, 0, waterMonths) : n(waterPy.waterKL[+month])) : null;
    waterKpisEl.innerHTML = [
      kpi('Total water consumption', waterKL, 'KL', colors.cyan, 'droplet', waterPrev, true, 0),
      kpi('Consumption per capita', waterPerCapitaL, 'L/person', colors.teal, 'users', null, true, 0),
      kpi('Total water recycled', d.waterRecycledKL, 'KL', colors.emerald, 'repeat', null, false, 0)
    ].join('');
  }

  const greenKpisEl = document.getElementById('greenKpis');
  if (greenKpisEl) {
    greenKpisEl.innerHTML = [
      kpi('Total green cover', green.totalGreenCoverPct, '%', colors.emerald, 'globe', null, false, 0),
      kpi('Maintained vegetation', green.maintainedVegetationAcres, 'acres', colors.teal, 'leaf', null, false, 0),
      kpi('Natural vegetation', green.naturalVegetationAcres, 'acres', colors.lime, 'tree', null, false, 0),
      kpi('Total tree species identified', green.totalSpecies, 'species', colors.cyan, 'sprout', null, false, 0)
    ].join('');
  }

  const outreachKpisEl = document.getElementById('outreachKpis');
  if (outreachKpisEl) {
    if (!outreachForPeriod) {
      outreachKpisEl.innerHTML = `
        <div class="card" style="grid-column:1/-1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:6px; text-align:center; color:var(--faint); min-height:220px;">
          <div style="font-size:13px; font-weight:600; color:var(--muted);">No published outreach data available</div>
          <div style="font-size:12px; max-width:420px;">Choose the exact published year and month. Draft and approved-but-unpublished records are never shown here.</div>
        </div>
      `;
    } else {
      const volunteersKpi = `
        <article class="kpi kpi-duo" style="--a:${colors.orange}" onclick="openKpiModal(this)">
          <div class="icon">${ic('spark')}</div>
          <div class="label">Volunteers engaged</div>
          <div class="duo-grid">
            <div>
              <div class="duo-num"><span class="counter-val" data-val="${outreach.volunteersEngaged}" data-dec="0">${fmt(outreach.volunteersEngaged, 0)}</span></div>
              <div class="duo-label">Volunteers</div>
            </div>
            <div>
              <div class="duo-num"><span class="counter-val" data-val="${outreach.volunteerHours}" data-dec="0">${fmt(outreach.volunteerHours, 0)}</span><small>hrs</small></div>
              <div class="duo-label">Hours contributed</div>
            </div>
          </div>
          <div class="trend"><b class="neutral">base</b><span>no comparison</span></div>
        </article>
      `;
      outreachKpisEl.innerHTML = [
        kpi('Total outreach programs delivered', outreach.programsDelivered, 'programs', colors.gold, 'check', null, false, 0),
        kpi('Total participants served', outreach.participantsServed, 'people', colors.cyan, 'users', null, false, 0),
        kpi('Partner organizations', outreach.partnerOrganizations, 'organizations', colors.violet, 'building', null, false, 0),
        kpi('Saplings planted', outreach.saplingsPlanted, 'saplings', colors.emerald, 'sprout', null, false, 0),
        kpi('Experts involved', outreach.expertsInvolved, 'experts', colors.teal, 'globe', null, false, 0),
        volunteersKpi
      ].join('');
    }
  }

  const scope1KpisEl = document.getElementById('scope1Kpis');
  if (scope1KpisEl) {
    scope1KpisEl.innerHTML = [
      kpi('Scope 1: Fleet + DG + LPG', scope1, 'tCO₂e', colors.orange, 'cloud', previousValue('scope1Full'), true),
      kpi('Petrol consumption', valFor(d, d.petrolL, month), 'L', colors.teal, 'car', previousValue('petrolL'), true, 0),
      kpi('Petrol emissions', petrol, 'tCO₂e', colors.teal, 'fuel', previousValue('petrolEm'), true),
      kpi('Fleet diesel consumption', valFor(d, d.trDieselL, month), 'L', colors.gold, 'bus', previousValue('trDieselL'), true, 0),
      kpi('Fleet diesel emissions', valFor(d, d.trDieselEm, month), 'tCO₂e', colors.gold, 'cloud', previousValue('trDieselEm'), true),
      kpi('DG diesel consumption', valFor(d, d.dgL, month), 'L', colors.orange, 'gear', previousValue('dgL'), true, 0),
      kpi('DG diesel emissions', valFor(d, d.dgEm, month), 'tCO₂e', colors.orange, 'factory', previousValue('dgEm'), true),
      kpi('LPG consumption', valFor(d, d.lpgL, month), 'L', colors.violet, 'battery', previousValue('lpgL'), true, 0),
      kpi('LPG emissions', valFor(d, d.lpgEm, month), 'tCO₂e', colors.violet, 'flame', previousValue('lpgEm'), true),
      kpi('Combined diesel emissions', diesel, 'tCO₂e', colors.red, 'flame', previousValue('dieselCombo'), true)
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
      kpi('Grid emission factor', EF.grid, 'kgCO₂e/kWh', colors.gold, 'ruler', null, true, 3),
      kpi('Electricity contribution', Calculations.scopeContributionPct(scope2, gross), '%', colors.cyan, 'chart', null, true),
      kpi('Scope 2 offset', Calculations.safeRatioPct(avoid, scope2), '%', colors.emerald, 'check', null, false)
    ].join('');
  }
  const energyProgressWidget = document.getElementById('energyProgressWidget');
  if (energyProgressWidget) {
    const totalElec = elec + re;
    const reProgressPct = totalElec > 0 ? (re / totalElec) * 100 : 0;

    energyProgressWidget.innerHTML = `
      <style>
        @keyframes epBarGrow { from { width: 0; } }
        @keyframes epShimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }
        .ep-hero-row { display: flex; gap: 24px; margin-bottom: 24px; }
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
        <div class="ep-hero">
        
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
              <div class="ep-tt-label">Total Demand</div>
              <div class="ep-tt-val">${Intl.NumberFormat('en-US').format(Math.round(totalElec))} <span>kWh</span></div>
            </div>
          </div>
        </div>
        </div>

        <!-- New Source Breakdown Card -->
        <div class="ep-hero" style="display: flex; flex-direction: column; padding: 32px 32px 24px 32px;">
          <div class="ep-top" style="margin-bottom: 24px;">
            <div>
              <div class="ep-title-row">
                <div class="icon">${ic('bolt')}</div>
                Energy Source Breakdown
              </div>
            </div>
          </div>
          
          <div class="ep-src-breakdown" style="flex: 1; position: relative; min-height: 180px;">
            <canvas id="energySrcBreakdownChart"></canvas>
          </div>
        </div>

      </div>
    `;
  }

  const energyKpisEl = document.getElementById('energyKpis');
  if (energyKpisEl) {
    energyKpisEl.innerHTML = [
      kpi('Total electricity consumption', elec + re, 'kWh', colors.cyan, 'bolt', null, true, 0),
      kpi('Total grid electricity consumption', elec, 'kWh', colors.cyan, 'plug', previousValue('elecKwh'), true, 0),
      kpi('Solar PV electricity generation', onSiteVal, 'kWh', colors.emerald, 'sun', null, false, 0),
      kpi('Procured green energy', procuredVal, 'kWh', colors.emerald, 'leaf', null, false, 0)
    ].join('');
  }

}
/* Which figure the hero balance card is showing: gross / net / avoid. */
let currentHeroView = 'net';

/* Fill the hero balance card and wire its three tabs; every call replays
   the count-up and the indicator-line sweep for the active tab. */
function heroGHG(gross, year, month, d, avoid, net) {
  // static figures on the card
  document.getElementById('balGrossVal').textContent = fmt(gross, 1);
  document.getElementById('balNetVal').textContent = fmt(d.perCapita, 2);
  document.getElementById('balAvoidVal').textContent = fmt(avoid, 1);
  document.getElementById('balPeriod').textContent = periodLabel(year, month);

  // the bar is a real composition of gross emissions: avoided-by-renewables + still net-emitted.
  // it always tells the true story, regardless of which tab is active.
  const avoidedPct = Math.min(100, Math.max(0, Calculations.safeRatioPct(avoid, gross)));
  const netPct = Math.max(0, 100 - avoidedPct);
  // gross = perCapita * population, so population falls straight out of the two figures already on the card
  const population = d.perCapita > 0 ? Math.round(gross / d.perCapita) : null;

  const segAvoid = document.getElementById('balSegAvoid');
  const segNet = document.getElementById('balSegNet');
  const caption = document.getElementById('balBarCaption');

  // snap the segments back to 0 with transitions off, then force a reflow so the fill re-sweeps
  segAvoid.style.transition = segNet.style.transition = 'none';
  segAvoid.style.width = segNet.style.width = '0%';
  void segAvoid.offsetWidth;
  segAvoid.style.transition = segNet.style.transition = '';
  segAvoid.style.width = avoidedPct.toFixed(1) + '%';
  segNet.style.width = netPct.toFixed(1) + '%';

  // repaint the big number + caption for the selected tab
  function updateDisplayView() {
    const mainValueEl = document.getElementById('hero-ghg');
    const labelEl = document.getElementById('balLabel');
    const unitEl = document.getElementById('hero-unit');

    // clear tab highlights
    document.querySelectorAll('.bal-item').forEach(item => item.classList.remove('active'));

    let targetValue = 0;

    // pick the figure for the active view; the bar's fill never changes, only which slice is emphasized (via CSS)
    if (currentHeroView === 'net') {
      targetValue = d.perCapita;
      labelEl.textContent = "Carbon Footprint per Person";
      unitEl.textContent = "tCO₂e/Individual";
      document.getElementById('tab-net').classList.add('active');
      caption.innerHTML = population
        ? `Gross footprint split evenly across <b>  ≈ ${Intl.NumberFormat('en-US').format(population)}</b> people on campus`
        : `Each person's share of the gross footprint`;
    } else if (currentHeroView === 'avoid') {
      targetValue = avoid;
      labelEl.textContent = "Emissions Avoided by Renewables";
      unitEl.textContent = "tCO₂e";
      document.getElementById('tab-avoid').classList.add('active');
      caption.innerHTML = `Renewables cut <b>${avoidedPct.toFixed(1)}%</b> off the gross footprint`;
    } else {
      targetValue = gross;
      labelEl.textContent = "Total Carbon Footprint (Gross)";
      unitEl.textContent = "tCO₂e";
      document.getElementById('tab-gross').classList.add('active');
      caption.innerHTML = `<b>${avoidedPct.toFixed(1)}%</b> avoided by renewables · <b>${netPct.toFixed(1)}%</b> still net-emitted`;
    }

    if (typeof reduceMotion !== 'undefined' && !reduceMotion) {
      let obj = { val: 0 };
      gsap.to(obj, {
        val: targetValue,
        duration: 1.5,
        ease: 'power2.out',
        onUpdate: () => { mainValueEl.textContent = fmt(obj.val, 2); },
        onComplete: () => { mainValueEl.textContent = fmt(targetValue, 2); }
      });
    } else {
      mainValueEl.textContent = fmt(targetValue, 2);
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
    const mergedIndices = isElecMix ? [0] : (isFuelMix ? [2, 3] : []);

    chart.data.datasets.forEach((dataset, dIdx) => {
      const meta = chart.getDatasetMeta(dIdx);
      meta.data.forEach((el, eIdx) => {
        let isActive = hasActive && active.some(a => a.datasetIndex === dIdx && a.index === eIdx);

        // Link the active state if this index is a "merged" single segment
        if (hasActive && !isActive && mergedIndices.includes(eIdx)) {
          isActive = active.some(a => a.index === eIdx);
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
  killCharts(); const mk = (id, cfg) => { const el = document.getElementById(id); if (el && el.closest('.page.active')) charts[id] = new Chart(el, cfg); }; const { year, month, d } = currentPeriod(); const d25 = data[2025], d26 = data[2026];
  /* Combined Scope1+Scope2 charts need one shared month window - capped to
     whichever contributing source has reported the fewest months so far
     (fuel/Fleet/DG typically lag grid electricity), not a hardcoded cutoff.
     Sources with zero months (not yet reporting at all, e.g. LPG some years)
     are excluded rather than zeroing the whole window out. */
  const s1s2Months = [d.trDieselL, d.dgL, d.petrolL, d.lpgL, d.htKwh, d.commKwh, d.tempKwh].map(monthsWithData).filter(m => m > 0);
  const available = d.frequency === 'ytd' && s1s2Months.length ? Math.min(...s1s2Months) : 12;
  const labels = months.slice(0, available); const sl = a => a.slice(0, available);
  const home = document.body.classList.contains('home'); const axc = home ? '#cbe2d6' : '#5c6b62'; const grc = home ? 'rgba(255,255,255,.1)' : colors.grid;
  const oopt = (yTitle) => ({ responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { color: axc } } }, scales: { x: { grid: { display: false }, ticks: { color: axc } }, y: { grid: { color: grc }, border: { display: false }, ticks: { color: axc }, title: { display: !!yTitle, text: yTitle, color: axc } } } });
  const dleg = { responsive: true, maintainAspectRatio: false, cutout: '66%', plugins: { legend: { position: 'bottom', labels: { color: axc } } } }; const dborder = home ? 'rgba(4,19,12,.25)' : '#fff';
  let ghgLabels = [], ghgData = [], ghgColors = [];
  const view = window.currentGhgProfileView || 'all';
  if (view === 'all' || view === 's1') {
    ghgLabels.push('Fleet diesel', 'DG diesel', 'Petrol', 'LPG');
    ghgData.push(sum(sl(d.trDieselEm)), sum(sl(d.dgEm)), sum(sl(d.petrolEm)), sum(sl(d.lpgEm)));
    ghgColors.push(colors.gold, colors.orange, colors.teal, colors.violet);
  }
  if (view === 'all' || view === 's2') {
    ghgLabels.push('HT Grid', 'Comm Grid', 'Temp Grid');
    ghgData.push(sum(sl(d.htEm)), sum(sl(d.commEm)), sum(sl(d.tempEm)));
    ghgColors.push(colors.cyan, '#6e97c7', '#4f9a8c');
  }
  mk('ghgProfileChart', { type: 'doughnut', data: { labels: ghgLabels, datasets: [{ data: ghgData, backgroundColor: ghgColors, borderWidth: 2, borderColor: dborder }] }, options: dleg });

  /* energy_master.csv's grid+renewable columns typically run further than the
     shared 'available' above (fuel/Fleet/DG usually lag electricity) - these
     feed the mix donut + source-breakdown bar below, so they get their own
     month count instead of being capped to the combined S1+S2 window. */
  const energyAvailable = Math.max(monthsWithData(d.htKwh), monthsWithData(d.reOnCampusKwh), monthsWithData(d.reProcuredKwh));
  const esl = a => a.slice(0, energyAvailable);
  const gridVal = (sum(esl(d.htKwh)) || 0) + (sum(esl(d.commKwh)) || 0) + (sum(esl(d.tempKwh)) || 0);
  const reVal = sum(esl(d.reKwh)) || 0;
  // Real on-campus/procured split from energy_master.csv, not an estimated ratio of reVal.
  const reOnCampusVal = sum(esl(d.reOnCampusKwh)) || 0;
  const reProcuredVal = sum(esl(d.reProcuredKwh)) || 0;

  mk('elecMixChartCanvas', {
    type: 'doughnut',
    data: {
      labels: ['Grid Electricity', 'On-site Solar PV', 'Procured Green Energy'],
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
            '#63b3ed', // Solar - Sky Blue
            'rgba(34, 153, 94, 0.9)'   // Procured - Green
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
              return idx === 0 ? 'Grid Electricity' : 'Total Renewable Energy';
            },
            label: function (context) {
              const dsIndex = context.datasetIndex;
              const idx = context.dataIndex;
              if (idx === 0) {
                return ' Grid Electricity: ' + Math.round(context.raw).toLocaleString() + ' kWh';
              }
              let label = '';
              if (dsIndex === 0) {
                label = 'Overall Renewable';
              } else {
                label = context.chart.data.labels[idx];
              }
              return ' ' + label + ': ' + Math.round(context.raw).toLocaleString() + ' kWh';
            }
          }
        }
      }
    }
  });

  mk('energySrcBreakdownChart', {
    type: 'bar',
    data: {
      labels: ['Grid', 'Solar PV', 'Procured Green'],
      datasets: [{
        label: 'Energy (kWh)',
        data: [gridVal, reOnCampusVal, reProcuredVal],
        backgroundColor: [colors.cyan, '#63b3ed', colors.emerald],
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

  const dgVal = sum(sl(d.dgEm)) || 0;
  const trDieselVal = sum(sl(d.trDieselEm)) || 0;
  const petrolVal = sum(sl(d.petrolEm)) || 0;
  const lpgVal = sum(sl(d.lpgEm)) || 0;

  const dgL = sum(sl(d.dgL)) || 0;
  const trDieselL = sum(sl(d.trDieselL)) || 0;
  const petrolL = sum(sl(d.petrolL)) || 0;
  const lpgL = sum(sl(d.lpgL)) || 0;
  const fuelVolumes = [dgL, trDieselL, petrolL, lpgL];

  mk('fuelMixChartCanvas', {
    type: 'doughnut',
    data: {
      labels: ['DG Diesel', 'Fleet Diesel', 'Petrol', 'LPG'],
      datasets: [
        {
          data: [dgVal + trDieselVal, 0, petrolVal, lpgVal],
          backgroundColor: [colors.orange, 'transparent', colors.teal, colors.violet],
          borderColor: [colors.orange, 'transparent', colors.teal, colors.violet],
          borderWidth: 2,
          hoverOffset: 0
        },
        {
          data: [dgVal, trDieselVal, petrolVal, lpgVal],
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
              const idx = context[0].dataIndex;
              if (idx === 0 || idx === 1) return 'Total Diesel Fuel';
              return context[0].chart.data.labels[idx];
            },
            label: function (context) {
              const dsIndex = context.datasetIndex;
              const idx = context.dataIndex;
              if (dsIndex === 0 && idx === 0) {
                const totalVol = fuelVolumes[0] + fuelVolumes[1];
                return ' Overall Diesel: ' + Math.round(context.raw).toLocaleString() + ' tCO₂e (' + Math.round(totalVol).toLocaleString() + ' L)';
              }
              const vol = fuelVolumes[idx];
              return ' ' + context.chart.data.labels[idx] + ': ' + Math.round(context.raw).toLocaleString() + ' tCO₂e (' + Math.round(vol).toLocaleString() + ' L)';
            }
          }
        }
      }
    }
  });

  let hStack = null;
  mk('ghgTrendChart', {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'S1: Petrol', data: sl(d.petrolEm), backgroundColor: colors.teal, borderRadius: 0, stack: 'Scope1' },
        { label: 'S1: Tr. Diesel', data: sl(d.trDieselEm), backgroundColor: colors.gold, borderRadius: 0, stack: 'Scope1' },
        { label: 'S1: DG Diesel', data: sl(d.dgEm), backgroundColor: colors.orange, borderRadius: 0, stack: 'Scope1' },
        { label: 'S1: LPG', data: sl(d.lpgEm), backgroundColor: colors.violet, borderRadius: 0, stack: 'Scope1' },
        { label: 'S2: HT Grid', data: sl(d.htEm), backgroundColor: colors.cyan, borderRadius: 0, stack: 'Scope2' },
        { label: 'S2: Comm Grid', data: sl(d.commEm), backgroundColor: '#6e97c7', borderRadius: 0, stack: 'Scope2' },
        { label: 'S2: Temp Grid', data: sl(d.tempEm), backgroundColor: '#4f9a8c', borderRadius: 0, stack: 'Scope2' }
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
          filter: (item) => hStack ? item.dataset.stack === hStack : true
        }
      },
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { color: axc } },
        y: { stacked: true, grid: { color: grc }, border: { display: false }, ticks: { color: axc }, title: { display: true, text: 'tCO₂e', color: axc } }
      }
    }
  });

  mk('s1Fuel', { type: 'bar', data: { labels, datasets: [{ label: 'Petrol', data: sl(d.petrolL), backgroundColor: colors.teal, borderRadius: 5 }, { label: 'Fleet diesel', data: sl(d.trDieselL), backgroundColor: colors.gold, borderRadius: 5 }] }, options: chartOptions('Litres') });
  mk('s1Breakdown', { type: 'doughnut', data: { labels: ['Fleet diesel', 'DG diesel', 'Petrol'], datasets: [{ data: [sum(sl(d.trDieselEm)), sum(sl(d.dgEm)), sum(sl(d.petrolEm))], backgroundColor: [colors.gold, colors.orange, colors.teal], borderWidth: 2, borderColor: '#fff' }] }, options: { responsive: true, maintainAspectRatio: false, cutout: '64%', plugins: { legend: { position: 'bottom' } } } });
  mk('s1DG', { type: 'bar', data: { labels, datasets: [{ type: 'bar', label: 'DG diesel (L)', data: sl(d.dgL), backgroundColor: 'rgba(193,138,46,.4)', borderRadius: 5, yAxisID: 'y' }, { type: 'line', label: 'DG emissions', data: sl(d.dgEm), borderColor: colors.orange, backgroundColor: colors.orange, tension: .35, yAxisID: 'y1', pointRadius: 0, borderWidth: 2 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } }, scales: { x: { grid: { display: false } }, y: { grid: { color: colors.grid }, border: { display: false }, title: { display: true, text: 'Litres', color: '#8a988f' } }, y1: { position: 'right', grid: { display: false }, border: { display: false }, title: { display: true, text: 'tCO₂e', color: '#8a988f' } } } } });
  mk('s1Diesel', { type: 'line', data: { labels, datasets: [{ label: 'Fleet diesel', data: sl(d.trDieselEm), borderColor: colors.gold, backgroundColor: 'rgba(193,138,46,.08)', fill: true, tension: .35, pointRadius: 0, borderWidth: 2 }, { label: 'DG diesel', data: sl(d.dgEm), borderColor: colors.orange, backgroundColor: 'rgba(184,98,58,.08)', fill: true, tension: .35, pointRadius: 0, borderWidth: 2 }] }, options: chartOptions('tCO₂e') });
  mk('s2Stack', { type: 'bar', data: { labels, datasets: [{ label: 'HT', data: sl(d.htKwh), backgroundColor: colors.cyan, borderRadius: 4 }, { label: 'Commercial', data: sl(d.commKwh), backgroundColor: '#6e97c7', borderRadius: 4 }, { label: 'Temporary', data: sl(d.tempKwh), backgroundColor: colors.teal, borderRadius: 4 }] }, options: { ...chartOptions('kWh'), scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, grid: { color: colors.grid }, border: { display: false }, title: { display: true, text: 'kWh', color: '#8a988f' } } } } });
  mk('s2Trend', { type: 'line', data: { labels, datasets: [{ label: 'Scope 2 emissions', data: sl(d.elecEm), borderColor: colors.cyan, backgroundColor: 'rgba(58,111,168,.1)', fill: true, tension: .35, pointRadius: 0, borderWidth: 2 }] }, options: chartOptions('tCO₂e') });
  mk('s2Share', { type: 'doughnut', data: { labels: ['HT', 'Commercial', 'Temporary'], datasets: [{ data: [sum(sl(d.htKwh)), sum(sl(d.commKwh)), sum(sl(d.tempKwh))], backgroundColor: [colors.cyan, '#6e97c7', colors.teal], borderWidth: 2, borderColor: '#fff' }] }, options: { responsive: true, maintainAspectRatio: false, cutout: '64%', plugins: { legend: { position: 'bottom' } } } });
  mk('s2VsRE', { type: 'doughnut', data: { labels: ['Electricity CO₂ emitted', 'RE CO₂ avoided'], datasets: [{ data: [sum(sl(d.elecEm)), d.avoided], backgroundColor: [colors.cyan, colors.emerald], borderWidth: 2, borderColor: '#fff' }] }, options: { responsive: true, maintainAspectRatio: false, cutout: '64%', plugins: { legend: { position: 'bottom' } } } });


  const wWet = d.wetWaste || 0;
  const wDry = d.dryWaste || 0;
  mk('wastePieChartCanvas', { type: 'pie', data: { labels: ['Wet waste', 'Dry waste'], datasets: [{ data: [wWet / 1000, wDry / 1000], backgroundColor: [colors.blue, colors.gold], borderWidth: 2, borderColor: '#fff' }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: function (context) { return ' ' + context.label + ': ' + context.raw.toFixed(1) + ' tons'; } } } } } });

  // Link to the main top bar year selection
  const tmD = d || { wasteBreakdown: [] };
  const treemapData = (tmD.wasteBreakdown || []).map(item => ({ name: item.name, value: item.value }));

  mk('wasteTreemapCanvas', {
    type: 'treemap',
    data: {
      datasets: [{
        tree: treemapData,
        key: 'value',
        groups: ['name'],
        spacing: 1,
        borderWidth: 0,
        backgroundColor: (ctx) => {
          if (ctx.type !== 'data') return 'transparent';
          const colorsArr = [colors.blue, colors.teal, colors.emerald, colors.gold, colors.orange, '#6e97c7', '#8a988f'];
          const idx = ctx.dataIndex !== undefined ? ctx.dataIndex : (ctx.index || 0);
          return colorsArr[idx % colorsArr.length];
        },
        labels: {
          display: true,
          color: '#fff',
          font: { family: 'Archivo', weight: 'bold', size: 10 },
          formatter: (ctx) => {
            if (ctx.type !== 'data' || !ctx.raw || !ctx.raw._data) return '';
            return [ctx.raw._data.name || '', (ctx.raw.v || 0).toLocaleString() + ' kg'];
          }
        }
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        dimInactive: false,
        tooltip: {
          callbacks: {
            title: (items) => {
              const raw = items[0]?.raw;
              return raw && raw._data ? raw._data.name : '';
            },
            label: (item) => {
              const raw = item?.raw;
              return raw && raw.v ? ' ' + raw.v.toLocaleString() + ' kg' : '';
            }
          }
        }
      }
    }
  });

  /* water_master.csv usually runs further into the year than the fuel/Fleet/DG
     sources gating the shared 'available' above, so every water chart slices
     by its own actual month count instead of 'available'/labels/sl. */
  const waterMonths = monthsWithData(d.waterKL);
  const waterLabels = months.slice(0, waterMonths);
  const wsl = arr => arr.slice(0, waterMonths);

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

  /* 2026 rows split consumption by source per month (TWAD / borewell /
     procured) - waterSourceTotal (monthly) also gates the 3-card monthly
     trend row further down, so it must stay strictly "do we have monthly
     source data", not fall back to the annual-only split below it. 2025
     instead reports TWAD/Borewell as one annual total (waterTWADAnnual/
     waterBorewellAnnual, see data-loader.js) with no monthly resolution,
     so the donut falls back to that when there's no monthly split; only
     when NEITHER exists does it fall back further to a single
     "Total consumption" slice. */
  const waterTWAD = sum(wsl(d.waterTWAD)), waterBorewell = sum(wsl(d.waterBorewell)), waterProcured = sum(wsl(d.waterProcured));
  const waterSourceTotal = waterTWAD + waterBorewell + waterProcured;
  const hasAnnualSourceSplit = d.waterTWADAnnual != null || d.waterBorewellAnnual != null;
  let waterSourceLabels, waterSourceData, waterSourceColors;
  if (waterSourceTotal > 0) {
    waterSourceLabels = ['TWAD supply', 'Borewell', 'Procured'];
    waterSourceData = [waterTWAD, waterBorewell, waterProcured];
    waterSourceColors = [colors.cyan, colors.teal, colors.gold];
  } else if (hasAnnualSourceSplit) {
    waterSourceLabels = ['TWAD supply', 'Borewell'];
    waterSourceData = [d.waterTWADAnnual || 0, d.waterBorewellAnnual || 0];
    waterSourceColors = [colors.cyan, colors.teal];
  } else {
    waterSourceLabels = ['Total consumption'];
    waterSourceData = [sum(wsl(d.waterKL))];
    waterSourceColors = [colors.cyan];
  }

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

  /* Per-source monthly trend only exists where waterSourceTotal > 0 (2026
     onward) - swap the three trend cards for a plain-language empty state on
     years that only ever recorded a single monthly total (2025). */
  const wstRow = document.getElementById('waterSourceTrendRow');
  const wstEmptyRow = document.getElementById('waterSourceTrendEmptyRow');
  if (wstRow && wstEmptyRow) {
    const hasSourceTrend = waterSourceTotal > 0;
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
        data: { labels: waterLabels, datasets: [{ label: 'Procured', data: wsl(d.waterProcured), borderColor: colors.gold, backgroundColor: 'rgba(193,138,46,.1)', fill: true, tension: .35, borderWidth: 2, pointRadius: 3, pointBackgroundColor: '#fff', pointBorderWidth: 2 }] },
        options: singleTrendOpts()
      });
    }
  }

  /* Outreach charts use only the active immutable public release. */
  const outreachChartsRow = document.getElementById('outreachChartsRow');
  if (outreachChartsRow) {
    const outreachForPeriod = outreach.published && outreach.year === year && month !== 'all' && outreach.month === (+month + 1);
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

      const audience = (outreach.audienceReach || []).filter(a => a.reach != null);
      mk('outreachAudienceChart', {
        type: 'doughnut',
        data: { labels: audience.map(a => a.category), datasets: [{ data: audience.map(a => a.reach), backgroundColor: palette, borderWidth: 2, borderColor: '#fff' }] },
        options: sliceOpts('reach', '62%') // a true donut, per the ask
      });

      const thematic = outreach.thematicAreas || [];
      mk('outreachThematicChart', {
        type: 'pie',
        data: { labels: thematic.map(t => t.category), datasets: [{ data: thematic.map(t => t.programs), backgroundColor: palette, borderWidth: 2, borderColor: '#fff' }] },
        options: sliceOpts('programmes', '0%') // a solid pie - Chart.js applies `cutout` to pie too, so this must be explicit
      });

      const genderWrap = document.getElementById('outreachGenderWrap');
      const genderEmpty = document.getElementById('outreachGenderEmpty');
      if (outreach.gender?.available) {
        genderWrap.style.display = '';
        genderEmpty.style.display = 'none';
        mk('outreachGenderChart', {
          type: 'doughnut',
          data: {
            labels: ['Male', 'Female', 'Other / Not disclosed'],
            datasets: [{
              data: [outreach.gender.male, outreach.gender.female, outreach.gender.other_not_disclosed],
              backgroundColor: [colors.cyan, colors.violet, colors.gold], borderWidth: 2, borderColor: '#fff'
            }]
          },
          options: sliceOpts('participants', '62%')
        });
      } else {
        genderWrap.style.display = 'none';
        genderEmpty.style.display = '';
      }
    }
  }

  // Compute full-year arrays for Energy line charts
  const cleanZero = arr => arr.map(v => v === 0 ? null : v);
  const total25 = cleanZero(d25.elecKwh.map((v, i) => v + (d25.reKwh[i] || 0)));
  const total26 = cleanZero(d26.elecKwh.map((v, i) => v + (d26.reKwh[i] || 0)));
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

  mk('energyTotalLineChart', {
    type: 'line',
    data: {
      labels: months,
      datasets: [
        { label: '2025', data: total25, ...ds25Opts },
        { label: '2026', data: total26, ...ds26Opts(colors.lime, 'rgba(90,165,82,.08)') }
      ]
    },
    options: lineOpts
  });

  mk('energyGridLineChart', {
    type: 'line',
    data: {
      labels: months,
      datasets: [
        { label: '2025', data: cleanZero(d25.elecKwh), ...ds25Opts },
        { label: '2026', data: cleanZero(d26.elecKwh), ...ds26Opts(colors.cyan, 'rgba(58,111,168,.08)') }
      ]
    },
    options: lineOpts
  });

  mk('energySolarLineChart', {
    type: 'line',
    data: {
      labels: months,
      datasets: [
        { label: '2025', data: solar25, ...ds25Opts },
        { label: '2026', data: solar26, ...ds26Opts('#63b3ed', 'rgba(99,179,237,.08)') }
      ]
    },
    options: lineOpts
  });

  mk('energyProcuredLineChart', {
    type: 'line',
    data: {
      labels: months,
      datasets: [
        { label: '2025', data: procured25, ...ds25Opts },
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
      let target = parseFloat(el.getAttribute('data-val')) || 0;
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
      el.textContent = fmt(parseFloat(el.getAttribute('data-val')) || 0, parseInt(el.getAttribute('data-dec')) || 0);
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
  if (reduceMotion) return;
  const page = document.querySelector('.page.active');
  if (!page) return;
  page.querySelectorAll('.card').forEach(card => {
    if (!card.querySelector('.chart')) return; // Only tilt cards that contain charts
    card.classList.add('card-3d');
    card.onmousemove = e => {
      const r = card.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
      const xPct = (x / r.width - 0.5) * 2, yPct = (y / r.height - 0.5) * 2;
      card.style.transform = `perspective(1000px) rotateX(${-yPct * 4}deg) rotateY(${xPct * 4}deg) scale3d(1.01,1.01,1.01)`;
    };
    card.onmouseleave = () => card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) scale3d(1,1,1)';
  });
}

/* Master re-render for the active page: KPIs, charts, table, then the
   entrance animations. Runs on load, on every filter change, and on
   every page switch. */
function refresh() {
  // rebuild everything the active page shows
  makeKpis();
  drawCharts();
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

/* Dark mode toggle, persisted across visits in localStorage. */
const themeToggle = document.getElementById('themeToggle');
if (localStorage.getItem('theme') === 'dark') {
  document.body.classList.add('dark-mode');
}
themeToggle.onclick = () => {
  document.body.classList.toggle('dark-mode');
  const isDark = document.body.classList.contains('dark-mode');
  localStorage.setItem('theme', isDark ? 'dark' : 'light');
};

/* ---- data explorer tables ---- */
const tables = {};
/* Flatten the master data into the five explorer views (built once at
   startup - filtering and sorting happen in renderTable). */
function buildTables() {
  const rows = []; for (const [year, d] of Object.entries(data)) { months.forEach((m, i) => { if (d.petrolL[i] != null) { rows.push([year, m, 'S1', 'Petrol', d.petrolL[i], 'L', EF.petrol, d.petrolEm[i]]); rows.push([year, m, 'S1', 'Fleet Diesel', d.trDieselL[i], 'L', EF.diesel, d.trDieselEm[i]]); rows.push([year, m, 'S1', 'DG Diesel', d.dgL[i], 'L', EF.diesel, d.dgEm[i]]); rows.push([year, m, 'S2', 'Grid Electricity', d.elecKwh[i], 'kWh', EF.grid, d.elecEm[i]]); } if (d.lpgL[i] != null) rows.push([year, m, 'S1', 'LPG', d.lpgL[i], 'L', EF.lpg, d.lpgEm[i]]); }) }
  tables.unified = { cols: ['Year', 'Month', 'Scope', 'Source', 'Quantity', 'Unit', 'EF', 'Emissions tCO₂e'], rows };
  tables.fleet = { cols: ['Year', 'Month', 'Petrol L', 'Petrol tCO₂e', 'Diesel L', 'Diesel tCO₂e'], rows: Object.entries(data).flatMap(([year, d]) => months.map((m, i) => d.petrolL[i] != null ? [year, m, d.petrolL[i], d.petrolEm[i], d.trDieselL[i], d.trDieselEm[i]] : null).filter(Boolean)) };
  tables.dg = { cols: ['Year', 'Month', 'DG Diesel L', 'DG Emissions tCO₂e'], rows: Object.entries(data).flatMap(([year, d]) => months.map((m, i) => d.dgL[i] != null ? [year, m, d.dgL[i], d.dgEm[i]] : null).filter(Boolean)) };
  tables.electricity = { cols: ['Year', 'Month', 'HT kWh', 'Commercial kWh', 'Temporary kWh', 'Emissions tCO₂e'], rows: Object.entries(data).flatMap(([year, d]) => months.map((m, i) => d.htKwh[i] != null ? [year, m, d.htKwh[i], d.commKwh[i], d.tempKwh[i], d.elecEm[i]] : null).filter(Boolean)) };
  tables.re = { cols: ['Year', 'Month', 'RE kWh', 'Emission Avoided tCO₂e'], rows: Object.entries(data).flatMap(([year, d]) => months.map((m, i) => d.reKwh[i] != null ? [year, m, d.reKwh[i], d.avoidEm[i]] : null).filter(Boolean)) };
}
let curTable = 'unified', sortCol = null, sortDir = 1;
/* Render the current explorer view through the live search box filter
   and any active column sort. */
function renderTable() { if (!tables.unified) return; const t = tables[curTable], q = (document.getElementById('search')?.value || '').toLowerCase(); let rows = t.rows.filter(r => r.some(c => String(c).toLowerCase().includes(q))); if (sortCol !== null) { rows = [...rows].sort((a, b) => { let x = a[sortCol], y = b[sortCol]; let nx = parseFloat(String(x).replace(/,/g, '')), ny = parseFloat(String(y).replace(/,/g, '')); return (!isNaN(nx) && !isNaN(ny) ? nx - ny : String(x).localeCompare(String(y))) * sortDir }) } const head = document.querySelector('#dataTable thead'), body = document.querySelector('#dataTable tbody'); if (!head) return; head.innerHTML = '<tr>' + t.cols.map((c, i) => `<th data-c="${i}">${c}${sortCol === i ? (sortDir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr>'; body.innerHTML = rows.map(r => '<tr>' + r.map((c, i) => `<td class="${typeof c === 'number' ? 'num' : ''}">${t.cols[i] === 'Scope' ? `<span class="pill ${c === 'S1' ? 's1' : 's2'}">${c}</span>` : typeof c === 'number' ? fmt(c, Math.abs(c) < 10 ? 3 : 2) : c}</td>`).join('') + '</tr>').join(''); head.querySelectorAll('th').forEach(th => th.onclick = () => { const c = +th.dataset.c; if (sortCol === c) sortDir *= -1; else { sortCol = c; sortDir = 1 } renderTable() }); }
document.getElementById('search')?.addEventListener('input', renderTable);
document.querySelectorAll('#tableTabs button').forEach(b => b.onclick = () => { document.querySelectorAll('#tableTabs button').forEach(x => x.classList.remove('active')); b.classList.add('active'); curTable = b.dataset.t; sortCol = null; renderTable(); });
/* Download the current explorer view as CSV. */
document.getElementById('exportBtn').onclick = () => { const t = tables[curTable] || tables.unified; const csv = [t.cols.join(',')].concat(t.rows.map(r => r.map(c => `"${c}"`).join(','))).join('\n'); const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); a.download = `kct_${curTable}.csv`; a.click(); };

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

/* Boot: build the tables, first render, entrance sweep. */
function start() { buildTables(); refresh(); initGreenMap(); if (!reduceMotion) { gsap.from('.showcase', { y: 14, opacity: 0, duration: .55, ease: 'power2.out' }); gsap.from('.topbar,.toolbar', { y: -16, opacity: 0, duration: .5, stagger: .08 }); } }
/* Fetch + compute the master dataset (data-loader.js) before booting -
   everything below this point in the file only reads `data` from inside
   functions that run after start(), never at parse time. */
(async function boot() {
  const loaded = await loadDashboardData();
  data = loaded.data;
  Object.assign(EF, loaded.EF); // EF stays `const` above - mutate in place, don't reassign
  green = loaded.green;
  outreach = loaded.outreach;
  start();
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
  "Total carbon footprint (gross)": {
    def: "The absolute sum of all greenhouse gas emissions produced before any offsets are applied.",
    impact: "Provides the foundational baseline for all sustainability efforts, representing the total unmitigated environmental burden.",
    trend: "Targeting a 15% reduction year-over-year through operational efficiency.",
    trendValue: 15
  },
  "Total electricity consumption": {
    def: "The aggregate electrical energy consumed across all campus facilities and operations.",
    impact: "Electricity is typically the largest driver of Scope 2 emissions. Reducing this directly shrinks the carbon footprint.",
    trend: "Currently transitioning 40% of grid dependency to local solar.",
    trendValue: 40
  },
  "Renewable energy used": {
    def: "Energy generated from naturally replenishing resources like solar, wind, or hydro power.",
    impact: "Every unit of renewable energy directly displaces fossil-fuel generated power, accelerating the path to net-zero.",
    trend: "Capacity has grown by 25% since the last quarter.",
    trendValue: 25
  },
  "Emission avoided": {
    def: "The calculated volume of CO2 emissions prevented from entering the atmosphere due to green initiatives.",
    impact: "A direct measure of the effectiveness and ROI of the institution's sustainability investments.",
    trend: "On track to reach 75% of the 1,000 tCO₂e avoided goal by year end.",
    trendValue: 75
  },
  "Scope 1 emissions": {
    def: "Direct emissions from owned or controlled sources, including company vehicles and on-site fuel combustion.",
    impact: "Requires direct operational changes, such as fleet electrification, rather than just purchasing green energy.",
    trend: "Fleet electrification is set to reduce this by 30% by 2028.",
    trendValue: 30
  },
  "Scope 2 emissions": {
    def: "Indirect emissions associated with the purchase of electricity, steam, heat, or cooling.",
    impact: "Highlights the carbon intensity of the local grid and the necessity for power purchase agreements (PPAs).",
    trend: "Grid efficiency improvements have lowered this by 5%.",
    trendValue: 5
  },
  "Per capita emissions": {
    def: "The total carbon footprint divided by the institution's active population (students and staff).",
    impact: "Normalizes the data, making it easier to track efficiency even as the institution grows in size.",
    trend: "Aiming to drop below 2.0 tCO₂e per capita (80% to goal).",
    trendValue: 80
  },
  "Net carbon impact": {
    def: "The true environmental footprint calculated by subtracting avoided emissions from the gross footprint.",
    impact: "The ultimate bottom-line metric that defines the institution's true progress towards carbon neutrality.",
    trend: "Decreased by 12% compared to the 2023 baseline.",
    trendValue: 12
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
    def: "Detailed metric tracking operational data for campus sustainability analysis.",
    impact: "Provides critical insight into sustainability performance and resource optimization.",
    trend: "Monitoring continuous improvement over time.",
    trendValue: 60
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
