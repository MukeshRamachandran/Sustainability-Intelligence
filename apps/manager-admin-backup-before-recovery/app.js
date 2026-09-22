/* =====================================================================
   MICROCOSM - DASHBOARD CORE (app.js)
   Single-page dashboard. The master dataset lives in `data` below; the
   three toolbar filters (year / month / compare) drive refresh(), which
   rebuilds the KPI cards, the charts and the data-explorer table for
   whichever page is active. go() switches pages and re-runs refresh().
   Everything else is presentation: Chart.js configs, GSAP entrance
   animations, canvas particle FX, and the KPI detail sidebar.
   walkthrough.js and mobile.js are self-contained addons layered on top;
   they read this DOM but nothing in this file depends on them.
   ===================================================================== */
const months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const colors={
  emerald:'#1c7a4b',  // renewable / good / net-good
  lime:'#5aa552',     // secondary green
  cyan:'#3a6fa8',     // electricity / scope 2 (steel blue)
  blue:'#3a6fa8',
  teal:'#4f9a8c',     // petrol
  gold:'#c18a2e',     // transport diesel (amber)
  orange:'#b8623a',   // DG diesel / gross (rust)
  red:'#be4b3b',      // emissions / unfavourable
  muted:'rgba(21,32,26,.16)',
  grid:'rgba(21,32,26,.07)'
};
const EF={petrol:2.388,diesel:2.701,grid:0.727};

/* ---- clean line-icon set (replaces emoji) ---- */
const ICONS={
 globe:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
 bolt:'<path d="M13 3 5 14h6l-1 7 8-11h-6z"/>',
 sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
 leaf:'<path d="M5 19c0-8 6-13 14-13 0 8-6 14-14 13Z"/><path d="M5 19c3-4 6-6 9-7"/>',
 fuel:'<path d="M5 21V5a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2v16M4 21h11M7 8h5"/><path d="M14 9h2a2 2 0 0 1 2 2v5a1.5 1.5 0 0 0 3 0V8l-2-2"/>',
 plug:'<path d="M9 3v5M15 3v5M7 8h10v3a5 5 0 0 1-10 0z M12 16v5"/>',
 users:'<circle cx="9" cy="8" r="3"/><path d="M3 20a6 6 0 0 1 12 0M16 6a3 3 0 0 1 0 6M21 20a6 6 0 0 0-4-5.6"/>',
 scale:'<path d="M12 3v18M5 7h14M5 7 3 13a3 3 0 0 0 6 0L7 7M19 7l-2 6a3 3 0 0 0 6 0l-2-6M8 21h8"/>',
 cloud:'<path d="M7 18a4 4 0 0 1 0-8 5 5 0 0 1 9.6-1A3.5 3.5 0 0 1 17 18z"/>',
 gear:'<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
 flame:'<path d="M12 3c4 4 5 7 5 10a5 5 0 0 1-10 0c0-1.5.5-3 1.5-4 .5 1 1.5 1.5 2 1.5C9 8 10 5 12 3Z"/>',
 ruler:'<path d="M3 16 16 3l5 5L8 21z"/><path d="M7 8l2 2M10 5l2 2M13 11l2 2M16 8l2 2"/>',
 chart:'<path d="M4 20V4M4 20h16"/><rect x="7" y="12" width="3" height="5"/><rect x="12" y="8" width="3" height="9"/><rect x="17" y="5" width="3" height="12"/>',
 check:'<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
 sprout:'<path d="M12 21v-8M12 13c0-4 3-6 7-6 0 4-3 6-7 6ZM12 13C12 9 9 7 5 7c0 4 3 6 7 6Z"/>',
 shield:'<path d="M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6z"/><path d="m9 12 2 2 4-4"/>',
 repeat:'<path d="M4 9a5 5 0 0 1 5-5h7M20 15a5 5 0 0 1-5 5H8"/><path d="M16 1l3 3-3 3M8 23l-3-3 3-3"/>',
 spark:'<path d="M12 3v6M12 15v6M3 12h6M15 12h6"/><path d="m6 6 3 3M15 15l3 3M18 6l-3 3M9 15l-3 3"/>',
 truck:'<path d="M3 6h11v9H3zM14 9h4l3 3v3h-7z"/><circle cx="7" cy="18" r="1.6"/><circle cx="17" cy="18" r="1.6"/>',
 car:'<path d="M3 13l2-5h14l2 5v5h-3M6 18H3v-5M7 18h10"/><circle cx="7.5" cy="18" r="1.5"/><circle cx="16.5" cy="18" r="1.5"/>',
 bus:'<rect x="4" y="4" width="16" height="13" rx="2"/><path d="M4 11h16M9 17v2M15 17v2"/><circle cx="8" cy="14" r="1"/><circle cx="16" cy="14" r="1"/>',
 factory:'<path d="M3 21V10l6 4V10l6 4V6h3v15z"/><path d="M7 17h2M13 17h2"/>',
 building:'<rect x="5" y="3" width="14" height="18" rx="1"/><path d="M9 7h2M13 7h2M9 11h2M13 11h2M10 21v-3h4v3"/>',
 store:'<path d="M4 9 5 4h14l1 5M4 9h16M4 9v11h16V9M9 20v-6h6v6"/>',
 battery:'<rect x="3" y="8" width="16" height="8" rx="2"/><path d="M21 11v2M7 12h6"/>',
 dot:'<circle cx="12" cy="12" r="4"/>'
};
/* Wrap an ICONS path in the shared inline-SVG shell. */
function ic(n){return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" width="19" height="19">${ICONS[n]||ICONS.dot}</svg>`}

/* ---- master data ---- populated at boot by loadDashboardData() (data-loader.js),
   which fetches data/*.csv (+ the optional data/dashboard_master.json overlay)
   and computes every field below from that source data. See PROJECT_GUIDE.md. */
let data={};

/* null/NaN-safe number coercion - the master data uses null for months with no reading. */
function n(v){return v==null||Number.isNaN(+v)?0:+v}
/* Sum a monthly array over [s, e) with null-safety. */
function sum(a,s=0,e=12){return Array.isArray(a)?a.slice(s,e).reduce((x,y)=>x+n(y),0):n(a)}
/* Indian-locale number formatting at d decimals. */
function fmt(v,d=0){return n(v).toLocaleString('en-IN',{minimumFractionDigits:d,maximumFractionDigits:d})}
/* Percent change vs a baseline (0 when there is no baseline). */
function pct(cur,prev){return prev?((cur-prev)/prev*100):0}
/* Ratios are unavailable when either input is missing or the denominator is zero. */
function safeRatio(numerator,denominator,scale=1){return numerator==null||denominator==null||denominator===0?null:numerator/denominator*scale}
/* Value of a monthly metric under the month filter ('all' = all approved months). */
function valFor(d,arr,m){if(m==='all')return sum(arr);const value=arr?.[+m];return value==null?null:n(value)}
/* Sum only the months represented by the selected dataset. */
function periodSum(arr,d,m='all'){if(m!=='all'){const value=arr?.[+m];return value==null?null:n(value)}return (d.availableMonths||[]).reduce((total,i)=>total+n(arr?.[i]),0)}
/* Renewable period totals are not fabricated into monthly readings. */
function renewableFor(d,m,emissions=false){
  if(m==='all') return emissions?d.avoided:d.reEnergy;
  const value=emissions?d.avoidEm?.[+m]:d.reKwh?.[+m];
  return value==null?null:n(value);
}
/* The active toolbar selection plus its year dataset. */
function currentPeriod(){return {year:+yearFilter.value,month:monthFilter.value,cmp:compareMode.value,d:data[yearFilter.value]}}
/* Human label for the selection - "Mar 2025" or the year dataset's own label. */
function periodLabel(year,month){
  const d=data[year];
  if(month!=='all') return `${months[+month]} ${year}`;
  if(d.frequency==='annual') return d.label;
  const end=d.latestMonthIndex==null?'No approved months':`Jan–${months[d.latestMonthIndex]} ${year}`;
  const gaps=d.missingMonths?.length?` · missing ${d.missingMonths.map(i=>months[i]).join(', ')}`:'';
  const partial=Object.entries(d.missingDomains||{}).length?` · incomplete ${Object.entries(d.missingDomains).map(([i,domains])=>`${months[+i]}: ${domains.join('/')}`).join('; ')}`:'';
  return `${end}${gaps}${partial}`;
}
/* Comparison baseline for a metric under the compare mode (previous month / last year same period / YTD). null = nothing to compare against. */
function previousValue(arrName){const {year,month,cmp,d}=currentPeriod();const cur=d[arrName];if(cmp==='mom'&&month!=='all'){if(!Array.isArray(cur))return null;let pm=+month-1;if(pm>=0&&cur[pm]!=null)return n(cur[pm]);return null;}const py=data[year-1];if(!py)return null;const prev=py[arrName];if(!Array.isArray(cur)||!Array.isArray(prev))return d.frequency==='annual'&&py.frequency==='annual'?n(prev):null;if(cmp==='ytd'||month==='all')return periodSum(prev,d);return prev[+month]!=null?n(prev[+month]):null}
/* The up/down trend chip; lowerGood flips which direction counts as green. */
function trendHtml(cur,prev,lowerGood=true){if(prev==null||prev===0)return `<b class="neutral">base</b><span>no comparison</span>`;const p=pct(cur,prev);const good=lowerGood?p<=0:p>=0;return `<b class="${good?'good':'bad'}">${p>=0?'↑':'↓'} ${Math.abs(p).toFixed(1)}%</b><span>vs ${compareMode.options[compareMode.selectedIndex].text.toLowerCase()}</span>`}
/* Build one KPI card: optional ambient FX layer (looping video, canvas
   particles or SVG scene per fxType), icon, counter (animated later by
   initKpiAnimations) and trend chip. Clicking opens the detail sidebar. */
function kpi(title,value,unit,accent,icon,prev,lowerGood=true,dec=2,fxType=null){const fx=fxType&&!reduceMotion;const cls=fx?` kpi-fx kpi-fx-${fxType}`:'';const pSvg='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>';const inner=(fx&&(fxType==='smoke'||fxType==='leaves'||fxType==='lightning')?`<canvas class="kpi-fx-canvas" data-fx="${fxType}"></canvas>`:'')+(fx&&fxType==='peoplefade'?`<div class="kpi-fx-people">${pSvg}${pSvg}${pSvg}</div>`:'')+(fx&&fxType==='solarvideo'?`<video autoplay loop muted playsinline class="kpi-fx-video"><source src="solar-kpi.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>`:'')+(fx&&fxType==='leavesvideo'?`<video autoplay loop muted playsinline class="kpi-fx-video"><source src="leavesfall.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>`:'')+(fx&&fxType==='fuelpourvideo'?`<video autoplay loop muted playsinline class="kpi-fx-video"><source src="fuelpour.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>`:'')+(fx&&fxType==='electricsparkvideo'?`<video autoplay loop muted playsinline class="kpi-fx-video"><source src="electricspark.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>`:'')+(fx&&fxType==='quepervideo'?`<video autoplay loop muted playsinline class="kpi-fx-video"><source src="queper.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>`:'')+(fx&&fxType==='earthvideo'?`<video autoplay loop muted playsinline class="kpi-fx-video"><source src="earth.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>`:'')+(fx&&fxType==='industrynewvideo'?`<video autoplay loop muted playsinline class="kpi-fx-video"><source src="industrynew.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>`:'')+(fx&&fxType==='elecmetervideo'?`<video autoplay loop muted playsinline class="kpi-fx-video"><source src="elecmeter.mp4" type="video/mp4"></video><div class="kpi-fx-video-overlay"></div>`:'')+(fx&&fxType==='sunrays'?`<div class="kpi-fx-solar-bg"><svg viewBox="0 0 100 100" preserveAspectRatio="xMaxYMax meet"><defs><radialGradient id="sunGlow" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#fbbf24" stop-opacity="0.7"/><stop offset="100%" stop-color="#fbbf24" stop-opacity="0"/></radialGradient><linearGradient id="panelGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#1e3a8a"/><stop offset="100%" stop-color="#1e40af"/></linearGradient></defs><g class="solar-sun"><circle cx="75" cy="25" r="30" fill="url(#sunGlow)"/><circle cx="75" cy="25" r="10" fill="#f59e0b"/><g class="solar-rays" stroke="#fbbf24" stroke-width="2" stroke-linecap="round"><line x1="75" y1="5" x2="75" y2="45"/><line x1="55" y1="25" x2="95" y2="25"/><line x1="61" y1="11" x2="89" y2="39"/><line x1="61" y1="39" x2="89" y2="11"/></g></g><g class="solar-panel" transform="translate(45, 50) scale(0.65)"><rect x="42" y="30" width="4" height="15" fill="#64748b"/><line x1="25" y1="45" x2="63" y2="45" stroke="#64748b" stroke-width="4" stroke-linecap="round"/><path d="M10,30 L35,5 L85,5 L60,30 Z" fill="url(#panelGrad)" stroke="#94a3b8" stroke-width="2" stroke-linejoin="round"/><line x1="22" y1="18" x2="72" y2="18" stroke="#60a5fa" stroke-width="1.5"/><line x1="30" y1="5" x2="18" y2="30" stroke="#60a5fa" stroke-width="1.5"/><line x1="50" y1="5" x2="38" y2="30" stroke="#60a5fa" stroke-width="1.5"/><line x1="70" y1="5" x2="58" y2="30" stroke="#60a5fa" stroke-width="1.5"/></g></svg></div>`:'')+(fx&&fxType==='smoke'?`<div class="kpi-fx-factory"><svg viewBox="0 0 100 100" preserveAspectRatio="xMaxYMax meet"><rect x="70" y="30" width="10" height="60" fill="#e0e0e0"/><rect x="70" y="35" width="10" height="8" fill="#d94b41"/><rect x="70" y="50" width="10" height="8" fill="#d94b41"/><rect x="70" y="65" width="10" height="8" fill="#d94b41"/><rect x="40" y="10" width="12" height="80" fill="#e0e0e0"/><rect x="40" y="15" width="12" height="10" fill="#d94b41"/><rect x="40" y="35" width="12" height="10" fill="#d94b41"/><rect x="40" y="55" width="12" height="10" fill="#d94b41"/><rect x="40" y="75" width="12" height="10" fill="#d94b41"/><rect x="15" y="50" width="8" height="40" fill="#e0e0e0"/><rect x="15" y="55" width="8" height="6" fill="#d94b41"/><rect x="15" y="70" width="8" height="6" fill="#d94b41"/><path d="M 5,90 L 95,90 L 95,75 L 80,75 L 80,80 L 60,80 L 60,70 L 30,70 L 30,85 L 5,85 Z" fill="#c43d34"/></svg></div>`:'')+(fx&&fxType==='lightning'?`<div class="kpi-fx-tower"><svg viewBox="0 0 100 100" preserveAspectRatio="xMaxYMax meet"><g stroke="#3a4a5a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="30" y1="90" x2="45" y2="20"/><line x1="70" y1="90" x2="55" y2="20"/><line x1="45" y1="20" x2="50" y2="10"/><line x1="55" y1="20" x2="50" y2="10"/><line x1="20" y1="40" x2="80" y2="40"/><line x1="25" y1="60" x2="75" y2="60"/><line x1="35" y1="80" x2="65" y2="80"/><line x1="42" y1="40" x2="33" y2="60"/><line x1="58" y1="40" x2="67" y2="60"/><line x1="42" y1="40" x2="58" y2="60"/><line x1="58" y1="40" x2="42" y2="60"/></g></svg></div>`:'');const animMap={'Scope 1: transport + DG':'anim-pulse','Petrol consumption':'anim-fuel','Petrol emissions':'anim-smoke','Transport diesel consumption':'anim-bus','Transport diesel emissions':'anim-bus-smoke','DG diesel consumption':'anim-vibrate','DG diesel emissions':'anim-generator-smoke','Combined diesel emissions':'anim-combined-smoke'};const iconClass=animMap[title]?`icon kpi-icon ${animMap[title]}`:'icon';return `<article class="kpi${cls}" style="--a:${accent}" onclick="openKpiModal(this)">${inner}<div class="${iconClass}">${ic(icon)}</div><div class="label">${title}</div><div class="value"><span class="counter-val" data-val="${value}" data-dec="${dec}">0</span><small>${unit}</small></div><div class="trend">${trendHtml(value,prev,lowerGood)}</div></article>`}

/* Render missing evidence as N/A instead of silently converting it to zero. */
function nullableKpi(title,value,unit,...rest){return value==null?kpi(title,0,'N/A',...rest):kpi(title,value,unit,...rest)}

/* Recompute the headline figures for the current filters and rebuild
   every page's KPI grid plus the public highlights strip. */
function makeKpis(){const {year,month,d}=currentPeriod();
 const scope1=valFor(d,d.scope1Selected,month), diesel=valFor(d,d.dieselCombo,month), petrol=valFor(d,d.petrolEm,month), scope2=valFor(d,d.elecEm,month), elec=valFor(d,d.elecKwh,month);
 const re=renewableFor(d,month), avoid=renewableFor(d,month,true);
 const gross=scope1==null||scope2==null?null:scope1+scope2, net=avoid==null||gross==null?null:gross-avoid;
 const perCapita=month==='all'?d.perCapita:(d.population&&gross!=null?gross/d.population:null);
 const selectedReShare=re==null||elec==null?null:safeRatio(re,re+elec,100);
 const fuelValues=[valFor(d,d.petrolL,month),valFor(d,d.trDieselL,month),valFor(d,d.dgL,month)];
 const fuelTotal=fuelValues.some(v=>v==null)?null:fuelValues.reduce((total,v)=>total+v,0);
 periodText.textContent=`Viewing ${periodLabel(year,month)} · compare: ${compareMode.options[compareMode.selectedIndex].text.toLowerCase()}`;
  heroGHG(gross,year,month,d,avoid,net);
  const hsSolar=document.getElementById('hs-solar-val'),hsAdmin=document.getElementById('hs-admin-val'),hsDg=document.getElementById('hs-dg-val');
  if(hsSolar)hsSolar.textContent=re==null?'N/A':fmt(re,0)+' kWh';
  if(hsAdmin)hsAdmin.textContent=elec==null?'N/A':fmt(elec,0)+' kWh';
  if(hsDg){const dgValue=valFor(d,d.dgEm,month);hsDg.textContent=dgValue==null?'N/A':fmt(dgValue,2)+' tCO₂e';}
 document.getElementById('overviewKpis').innerHTML=[
  nullableKpi('Total carbon footprint (gross)',gross,'tCO₂e',colors.orange,'globe',previousValue('grossSelected'),true,2,'industrynewvideo'),
  nullableKpi('Total electricity consumption',elec,'kWh',colors.cyan,'bolt',previousValue('elecKwh'),true,0,'elecmetervideo'),
  nullableKpi('Renewable energy used',re,'kWh',colors.emerald,'sun',previousValue('reEnergy'),false,0,'solarvideo'),
  nullableKpi('Emission avoided',avoid,'tCO₂e',colors.lime,'leaf',previousValue('avoided'),false,2,'leavesvideo'),
  nullableKpi('Scope 1 emissions',scope1,'tCO₂e',colors.gold,'fuel',previousValue('scope1Selected'),true,2,'fuelpourvideo'),
  nullableKpi('Scope 2 emissions',scope2,'tCO₂e',colors.cyan,'plug',previousValue('elecEm'),true,2,'electricsparkvideo'),
  nullableKpi('Per capita emissions',perCapita,'tCO₂e/person',colors.blue,'users',null,true,3,'quepervideo'),
  nullableKpi('Illustrative balance (non-inventory)',net,'tCO₂e',colors.emerald,'scale',null,true,2,'earthvideo')
 ].join('');
 document.getElementById('scope1Kpis').innerHTML=[
  nullableKpi('Scope 1: transport + DG',scope1,'tCO₂e',colors.orange,'cloud',previousValue('scope1Selected'),true),
  nullableKpi('Petrol consumption',valFor(d,d.petrolL,month),'L',colors.teal,'car',previousValue('petrolL'),true,0),
  nullableKpi('Petrol emissions',petrol,'tCO₂e',colors.teal,'fuel',previousValue('petrolEm'),true),
  nullableKpi('Transport diesel consumption',valFor(d,d.trDieselL,month),'L',colors.gold,'bus',previousValue('trDieselL'),true,0),
  nullableKpi('Transport diesel emissions',valFor(d,d.trDieselEm,month),'tCO₂e',colors.gold,'cloud',previousValue('trDieselEm'),true),
  nullableKpi('DG diesel consumption',valFor(d,d.dgL,month),'L',colors.orange,'gear',previousValue('dgL'),true,0),
  nullableKpi('DG diesel emissions',valFor(d,d.dgEm,month),'tCO₂e',colors.orange,'factory',previousValue('dgEm'),true),
  nullableKpi('Combined diesel emissions',diesel,'tCO₂e',colors.red,'flame',previousValue('dieselCombo'),true)
 ].join('');
 document.getElementById('scope2Kpis').innerHTML=[
  nullableKpi('Scope 2 emissions',scope2,'tCO₂e',colors.cyan,'bolt',previousValue('elecEm'),true),
  nullableKpi('Grid electricity consumption',elec,'kWh',colors.cyan,'plug',previousValue('elecKwh'),true,0),
  nullableKpi('HT connection',valFor(d,d.htKwh,month),'kWh',colors.blue,'building',previousValue('htKwh'),true,0),
  nullableKpi('Commercial connection',valFor(d,d.commKwh,month),'kWh',colors.cyan,'store',previousValue('commKwh'),true,0),
  nullableKpi('Temporary connection',valFor(d,d.tempKwh,month),'kWh',colors.lime,'battery',previousValue('tempKwh'),true,0),
  kpi('Grid emission factor',EF.grid,'kgCO₂e/kWh',colors.gold,'ruler',null,true,3),
  nullableKpi('Electricity contribution',safeRatio(scope2,gross,100),'%',colors.cyan,'chart',null,true),
  nullableKpi('Scope 2 avoided-impact ratio',safeRatio(avoid,scope2,100),'%',colors.emerald,'check',null,false)
 ].join('');
 document.getElementById('reKpis').innerHTML=[
  nullableKpi('Renewable energy',re,'kWh',colors.emerald,'sun',null,false,0),
  nullableKpi('Emission avoided',avoid,'tCO₂e',colors.lime,'leaf',null,false),
  nullableKpi('Renewable energy share',month==='all'?d.reShare:safeRatio(re,re==null||elec==null?null:re+elec,100),'%',colors.emerald,'sprout',null,false,1),
  nullableKpi('Grid dependency',safeRatio(elec,re==null||elec==null?null:elec+re,100),'%',colors.cyan,'plug',null,true),
  nullableKpi('Avoided impact vs Scope 2',safeRatio(avoid,scope2,100),'%',colors.lime,'shield',null,false),
  nullableKpi('Illustrative balance',net,'tCO₂e',colors.gold,'scale',null,true),
  nullableKpi('RE vs grid ratio',safeRatio(re,elec),'×',colors.emerald,'repeat',null,false,2),
  nullableKpi('Avoided vs gross',safeRatio(avoid,gross,100),'%',colors.lime,'spark',null,false)
 ].join('');
 document.getElementById('cmpKpis').innerHTML=[
  nullableKpi('Scope 1 comparison',scope1,'tCO₂e',colors.gold,'fuel',previousValue('scope1Selected'),true),
  nullableKpi('Scope 2 comparison',scope2,'tCO₂e',colors.cyan,'bolt',previousValue('elecEm'),true),
  nullableKpi('Electricity comparison',elec,'kWh',colors.cyan,'plug',previousValue('elecKwh'),true,0),
  nullableKpi('Fuel comparison',fuelTotal,'L',colors.orange,'truck',null,true,0),
  nullableKpi('Diesel emissions',diesel,'tCO₂e',colors.red,'flame',previousValue('dieselCombo'),true),
  nullableKpi('Petrol emissions',petrol,'tCO₂e',colors.teal,'car',previousValue('petrolEm'),true),
  nullableKpi('RE avoided',avoid,'tCO₂e',colors.lime,'leaf',null,false),
  nullableKpi('Illustrative balance (non-inventory)',net,'tCO₂e',colors.emerald,'scale',null,true)
 ].join('');
 document.getElementById('publicHighlights').innerHTML=[
  `<div class="highlight"><b>${selectedReShare!=null?fmt(selectedReShare,1)+'%':'—'}</b><span>renewable energy share</span></div>`,
  `<div class="highlight"><b>${scope2==null?'N/A':fmt(scope2,2)}</b><span>tCO₂e from grid electricity</span></div>`,
  `<div class="highlight"><b>${diesel==null?'N/A':fmt(diesel,2)}</b><span>tCO₂e combined diesel impact</span></div>`,
  `<div class="highlight"><b>${net==null?'N/A':fmt(net,2)}</b><span>tCO₂e illustrative balance (not inventory)</span></div>`
 ].join('');
}
/* Which figure the hero balance card is showing: gross / net / avoid. */
let currentHeroView = 'gross';

/* Fill the hero balance card and wire its three tabs; every call replays
   the count-up and the indicator-line sweep for the active tab. */
function heroGHG(gross, year, month, d, avoid, net) {
  // static figures on the card
  document.getElementById('balGrossVal').textContent = gross==null?'N/A':fmt(gross, 1);
  document.getElementById('balNetVal').textContent = net==null?'N/A':fmt(net, 1);
  document.getElementById('balAvoidVal').textContent = avoid==null?'N/A':fmt(avoid, 1);
  document.getElementById('balPeriod').textContent = periodLabel(year, month);

  // repaint the big number + indicator line for the selected tab
  function updateDisplayView() {
    const mainValueEl = document.getElementById('hero-ghg');
    const labelEl = document.getElementById('balLabel');
    const unitEl = document.getElementById('hero-unit');
    const indicatorLine = document.getElementById('balIndicatorLine');
    
    // snap the indicator back to 0 with transitions off...
    indicatorLine.style.transition = 'none';
    indicatorLine.style.width = '0%';
    
    // ...and force a reflow so the sweep re-plays from zero
    void indicatorLine.offsetWidth;
    
    // transitions back on
    indicatorLine.style.transition = '';

    // clear tab highlights
    document.querySelectorAll('.bal-item').forEach(item => item.classList.remove('active'));

    let targetedPercentage = 100;

    let targetValue = 0;

    // pick the figure and bar width for the active view
    if (currentHeroView === 'net') {
      targetValue = net;
      labelEl.textContent = "Illustrative gross minus avoided (not GHG inventory)";
      unitEl.textContent = net==null?"N/A":"tCO₂e";
      document.getElementById('tab-net').classList.add('active');
      targetedPercentage = gross > 0 ? Math.max(0, (net / gross) * 100) : 0;
    } else if (currentHeroView === 'avoid') {
      targetValue = avoid;
      labelEl.textContent = "Emissions avoided by renewables";
      unitEl.textContent = avoid==null?"N/A":"tCO₂e";
      document.getElementById('tab-avoid').classList.add('active');
      targetedPercentage = gross > 0 ? Math.min(100, (avoid / gross) * 100) : 0;
    } else {
      targetValue = gross;
      labelEl.textContent = "Gross emissions footprint";
      unitEl.textContent = gross==null?"N/A":"tCO₂e";
      document.getElementById('tab-gross').classList.add('active');
      targetedPercentage = 100; 
    }

    if (targetValue==null) {
      mainValueEl.textContent = 'N/A';
    } else if (typeof reduceMotion !== 'undefined' && !reduceMotion) {
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

    // fire the CSS width sweep
    indicatorLine.style.width = targetedPercentage.toFixed(1) + '%';
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
let charts={};function killCharts(){Object.values(charts).forEach(c=>c.destroy());charts={};}
Chart.defaults.color='#5c6b62';
Chart.defaults.font.family="'Public Sans',sans-serif";
Chart.defaults.font.size=12;
Chart.defaults.plugins.legend.labels.usePointStyle=true;
Chart.defaults.plugins.legend.labels.boxWidth=8;
Chart.defaults.plugins.legend.labels.padding=14;
Chart.defaults.plugins.tooltip.backgroundColor='#ffffff';
Chart.defaults.plugins.tooltip.borderColor='#e5e9e4';
Chart.defaults.plugins.tooltip.borderWidth=1;
Chart.defaults.plugins.tooltip.titleColor='#15201a';
Chart.defaults.plugins.tooltip.bodyColor='#3a463f';
Chart.defaults.plugins.tooltip.padding=11;
Chart.defaults.plugins.tooltip.cornerRadius=10;
Chart.defaults.plugins.tooltip.titleFont={weight:'700'};
Chart.defaults.elements.arc.hoverOffset=12;
Chart.defaults.hover.mode='nearest';
Chart.register({id:'dimInactive',beforeDatasetsDraw(chart){const active=chart.getActiveElements();const hasActive=active.length>0;chart.data.datasets.forEach((dataset,dIdx)=>{const meta=chart.getDatasetMeta(dIdx);meta.data.forEach((el,eIdx)=>{const isActive=hasActive&&active.some(a=>a.datasetIndex===dIdx&&a.index===eIdx);if(!el._originalDraw){el._originalDraw=el.draw;el.draw=function(ctx){const saveAlpha=ctx.globalAlpha;if(this._shouldDim)ctx.globalAlpha=0.2;this._originalDraw(ctx);ctx.globalAlpha=saveAlpha;};}el._shouldDim=hasActive&&!isActive;});});}});
/* Shared cartesian options with an optional y-axis title. */
function chartOptions(yTitle){return {responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},scales:{x:{grid:{display:false},border:{color:colors.grid}},y:{grid:{color:colors.grid},border:{display:false},title:{display:!!yTitle,text:yTitle,color:'#8a988f'}}}}}
const baseline='rgba(21,32,26,.16)';
/* Rebuild charts for the ACTIVE page only - mk() skips canvases on
   hidden pages, cutting a refresh from 20 charts to at most 4. Hidden
   pages get theirs on arrival, since go() always calls refresh(). */
function drawCharts(){killCharts();const mk=(id,cfg)=>{const el=document.getElementById(id);if(el&&el.closest('.page.active'))charts[id]=new Chart(el,cfg);};const {year,month,d}=currentPeriod();const prior=data[year-1]||null;const available=d.frequency==='annual'?12:Math.max(1,(d.latestMonthIndex??0)+1);const chartIndexes=month==='all'?Array.from({length:available},(_,i)=>i):[+month];const labels=chartIndexes.map(i=>months[i]);const sl=a=>chartIndexes.map(i=>a[i]);const cs=a=>{const values=sl(a);return month==='all'?sum(values):(values[0]??null)};
 const home=document.body.classList.contains('home');const axc=home?'#cbe2d6':'#5c6b62';const grc=home?'rgba(255,255,255,.1)':colors.grid;
 const chartRe=renewableFor(d,month),chartAvoid=renewableFor(d,month,true),chartGross=periodSum(d.grossSelected,d,month);
 const matchedLabel=y=>month==='all'?`${y} matched through ${months[d.latestMonthIndex??11]}`:`${months[+month]} ${y}`;
 const trendDatasets=[{label:`${year} gross`,data:sl(d.grossSelected),borderColor:colors.emerald,backgroundColor:'rgba(28,122,75,.08)',fill:true,tension:.35,pointRadius:0,borderWidth:2}];
 if(prior)trendDatasets.unshift({label:`${year-1} gross`,data:sl(prior.grossSelected),borderColor:colors.cyan,backgroundColor:'rgba(58,111,168,.08)',fill:true,tension:.35,pointRadius:0,borderWidth:2});
 const scopeDatasets=[{label:matchedLabel(year),data:[periodSum(d.scope1Selected,d,month),periodSum(d.elecEm,d,month),periodSum(d.grossSelected,d,month)],backgroundColor:colors.emerald,borderRadius:6}];
 if(prior)scopeDatasets.unshift({label:matchedLabel(year-1),data:[periodSum(prior.scope1Selected,d,month),periodSum(prior.elecEm,d,month),periodSum(prior.grossSelected,d,month)],backgroundColor:home?'rgba(255,255,255,.22)':baseline,borderRadius:6});
 const oopt=(yTitle)=>({responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{color:axc}}},scales:{x:{grid:{display:false},ticks:{color:axc}},y:{grid:{color:grc},border:{display:false},ticks:{color:axc},title:{display:!!yTitle,text:yTitle,color:axc}}}});
 const dleg={responsive:true,maintainAspectRatio:false,cutout:'66%',plugins:{legend:{position:'bottom',labels:{color:axc}}}};const dborder=home?'rgba(4,19,12,.25)':'#fff';
 mk('ovProfile',{type:'doughnut',data:{labels:['Scope 2 electricity','Transport diesel','DG diesel','Petrol'],datasets:[{data:[cs(d.elecEm),cs(d.trDieselEm),cs(d.dgEm),cs(d.petrolEm)],backgroundColor:[colors.cyan,colors.gold,colors.orange,colors.teal],borderWidth:2,borderColor:dborder}]},options:dleg});
 mk('ovEnergyMix',{type:'doughnut',data:{labels:['Renewable energy','Grid electricity'],datasets:[{data:[chartRe,periodSum(d.elecKwh,d,month)],backgroundColor:[colors.emerald,colors.blue],borderWidth:2,borderColor:dborder}]},options:dleg});
 mk('ovProgress',{type:'bar',data:{labels:['Scope 1','Scope 2','Gross inventory'],datasets:scopeDatasets},options:oopt('tCO₂e')});
 mk('ovTrend',{type:'line',data:{labels,datasets:trendDatasets},options:oopt('tCO₂e')});
 mk('s1Fuel',{type:'bar',data:{labels,datasets:[{label:'Petrol',data:sl(d.petrolL),backgroundColor:colors.teal,borderRadius:5},{label:'Transport diesel',data:sl(d.trDieselL),backgroundColor:colors.gold,borderRadius:5}]},options:chartOptions('Litres')});
 mk('s1Breakdown',{type:'doughnut',data:{labels:['Transport diesel','DG diesel','Petrol'],datasets:[{data:[cs(d.trDieselEm),cs(d.dgEm),cs(d.petrolEm)],backgroundColor:[colors.gold,colors.orange,colors.teal],borderWidth:2,borderColor:'#fff'}]},options:{responsive:true,maintainAspectRatio:false,cutout:'64%',plugins:{legend:{position:'bottom'}}}});
 mk('s1DG',{type:'bar',data:{labels,datasets:[{type:'bar',label:'DG diesel (L)',data:sl(d.dgL),backgroundColor:'rgba(193,138,46,.4)',borderRadius:5,yAxisID:'y'},{type:'line',label:'DG emissions',data:sl(d.dgEm),borderColor:colors.orange,backgroundColor:colors.orange,tension:.35,yAxisID:'y1',pointRadius:0,borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},scales:{x:{grid:{display:false}},y:{grid:{color:colors.grid},border:{display:false},title:{display:true,text:'Litres',color:'#8a988f'}},y1:{position:'right',grid:{display:false},border:{display:false},title:{display:true,text:'tCO₂e',color:'#8a988f'}}}}});
 mk('s1Diesel',{type:'line',data:{labels,datasets:[{label:'Transport diesel',data:sl(d.trDieselEm),borderColor:colors.gold,backgroundColor:'rgba(193,138,46,.08)',fill:true,tension:.35,pointRadius:0,borderWidth:2},{label:'DG diesel',data:sl(d.dgEm),borderColor:colors.orange,backgroundColor:'rgba(184,98,58,.08)',fill:true,tension:.35,pointRadius:0,borderWidth:2}]},options:chartOptions('tCO₂e')});
 mk('s2Stack',{type:'bar',data:{labels,datasets:[{label:'HT',data:sl(d.htKwh),backgroundColor:colors.cyan,borderRadius:4},{label:'Commercial',data:sl(d.commKwh),backgroundColor:'#6e97c7',borderRadius:4},{label:'Temporary',data:sl(d.tempKwh),backgroundColor:colors.teal,borderRadius:4}]},options:{...chartOptions('kWh'),scales:{x:{stacked:true,grid:{display:false}},y:{stacked:true,grid:{color:colors.grid},border:{display:false},title:{display:true,text:'kWh',color:'#8a988f'}}}}});
 mk('s2Trend',{type:'line',data:{labels,datasets:[{label:'Scope 2 emissions',data:sl(d.elecEm),borderColor:colors.cyan,backgroundColor:'rgba(58,111,168,.1)',fill:true,tension:.35,pointRadius:0,borderWidth:2}]},options:chartOptions('tCO₂e')});
 mk('s2Share',{type:'doughnut',data:{labels:['HT','Commercial','Temporary'],datasets:[{data:[cs(d.htKwh),cs(d.commKwh),cs(d.tempKwh)],backgroundColor:[colors.cyan,'#6e97c7',colors.teal],borderWidth:2,borderColor:'#fff'}]},options:{responsive:true,maintainAspectRatio:false,cutout:'64%',plugins:{legend:{position:'bottom'}}}});
 mk('s2VsRE',{type:'doughnut',data:{labels:['Electricity CO₂ emitted','RE CO₂ avoided'],datasets:[{data:[cs(d.elecEm),chartAvoid],backgroundColor:[colors.cyan,colors.emerald],borderWidth:2,borderColor:'#fff'}]},options:{responsive:true,maintainAspectRatio:false,cutout:'64%',plugins:{legend:{position:'bottom'}}}});
 mk('reMix',{type:'doughnut',data:{labels:['Renewable energy','Grid electricity'],datasets:[{data:[chartRe,periodSum(d.elecKwh,d,month)],backgroundColor:[colors.emerald,colors.blue],borderWidth:2,borderColor:'#fff'}]},options:{responsive:true,maintainAspectRatio:false,cutout:'66%',plugins:{legend:{position:'bottom'}}}});
 mk('reVs',{type:'doughnut',data:{labels:['Scope 2 CO₂ emitted','RE CO₂ avoided'],datasets:[{data:[cs(d.elecEm),chartAvoid],backgroundColor:[colors.cyan,colors.emerald],borderWidth:2,borderColor:'#fff'}]},options:{responsive:true,maintainAspectRatio:false,cutout:'64%',plugins:{legend:{position:'bottom'}}}});
 const chartElectricity=periodSum(d.elecKwh,d,month);const reShareVal=safeRatio(chartRe,chartRe==null||chartElectricity==null?null:chartRe+chartElectricity,100);
 mk('reGauge',{type:'doughnut',data:{labels:['Renewable share','Remaining'],datasets:[{data:reShareVal==null?[null,null]:[reShareVal,100-reShareVal],backgroundColor:[colors.emerald,'rgba(21,32,26,.07)'],borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,cutout:'78%',rotation:-90,circumference:360,plugins:{legend:{display:false},tooltip:{enabled:false}}}});
 mk('reNet',{type:'bar',data:{labels:['Gross inventory','Avoided impact','Illustrative balance'],datasets:[{data:[chartGross,chartAvoid,chartGross==null||chartAvoid==null?null:chartGross-chartAvoid],backgroundColor:[colors.orange,colors.emerald,colors.cyan],borderRadius:6}]},options:{...chartOptions('tCO₂e'),plugins:{legend:{display:false}}}});
 mk('cmpScope',{type:'bar',data:{labels:['Scope 1','Scope 2','Gross inventory'],datasets:scopeDatasets},options:chartOptions('tCO₂e')});
 mk('cmpWaterfall',{type:'bar',data:{labels:['Gross inventory','Avoided impact','Illustrative balance'],datasets:[{label:'Selected',data:[chartGross,chartAvoid,chartGross==null||chartAvoid==null?null:chartGross-chartAvoid],backgroundColor:[colors.orange,colors.emerald,colors.cyan],borderRadius:6}]},options:{...chartOptions('tCO₂e'),plugins:{legend:{display:false}}}});
 mk('cmpFuel',{type:'bar',data:{labels,datasets:[{label:'Petrol',data:sl(d.petrolL),backgroundColor:colors.teal,borderRadius:3},{label:'Transport diesel',data:sl(d.trDieselL),backgroundColor:colors.gold,borderRadius:3},{label:'DG diesel',data:sl(d.dgL),backgroundColor:colors.orange,borderRadius:3}]},options:{...chartOptions('Litres'),scales:{x:{stacked:true,grid:{display:false}},y:{stacked:true,grid:{color:colors.grid},border:{display:false},title:{display:true,text:'Litres',color:'#8a988f'}}}}});
 mk('cmpMonthly',{type:'line',data:{labels,datasets:trendDatasets},options:chartOptions('tCO₂e')});
}

const reduceMotion=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
/* ---- KPI FX: particle engine for the smoke / leaves / lightning cards.
   One _KPar per .kpi-fx-canvas, all driven by a single shared rAF loop
   started in initKpiAnimations. ---- */
let _kfxRAF=null;const _kfxSys=[];
class _KPar{
  constructor(c,t){this.c=c;this.x=c.getContext('2d');this.t=t;this.p=[];this._rs();this._sd();}
  _rs(){const r=this.c.parentElement.getBoundingClientRect(),d=window.devicePixelRatio||1;
    this.w=r.width;this.h=r.height;if(!this.w)return;
    this.c.width=this.w*d;this.c.height=this.h*d;this.x.scale(d,d);}
  _sd(){const n=this.t==='smoke'?25:this.t==='lightning'?2:12;for(let i=0;i<n;i++)this.p.push(this._mk(1));}
  _mk(init){
    if(this.t==='smoke'){const isLeft=Math.random()>.4;const bx=isLeft?this.w-45:this.w-20;const by=isLeft?this.h-72:this.h-56;return{x:bx+(Math.random()-.5)*8,y:init?Math.random()*by:by,sz:8+Math.random()*15,vy:-(0.6+Math.random()*1),vx:(Math.random()-.5)*1.5,o:.05+Math.random()*.08,l:0,ml:150+Math.random()*150};}
    if(this.t==='lightning'){const tx=this.w-45+Math.random()*15;const ty=this.h-80;let cx=Math.random()*this.w,cy=-10;const pts=[{x:cx,y:cy}];while(cy<ty){cy+=10+Math.random()*15;cx+=(tx-cx)*(cy/ty)+(Math.random()-.5)*20;pts.push({x:cx,y:cy});}pts.push({x:tx,y:ty});return{l:0,ml:60+Math.random()*150,pts};}
    return{x:init?Math.random()*this.w:-10,y:10+Math.random()*this.h*.5,
      sz:3+Math.random()*4,vx:.15+Math.random()*.35,vy:.03+Math.random()*.1,
      a:Math.random()*Math.PI*2,ra:(Math.random()-.5)*.04,
      wa:8+Math.random()*18,wf:.01+Math.random()*.01,
      o:.04+Math.random()*.08,l:0,ml:140+Math.random()*130,by:0};
  }
  tick(){for(let i=this.p.length-1;i>=0;i--){const p=this.p[i];p.l++;
    if(this.t==='smoke'){p.x+=p.vx+Math.sin(p.l*.02)*.3;p.y+=p.vy;
      if(p.l>p.ml||p.y<-20||p.x>this.w+20||p.x<-20)this.p[i]=this._mk(0);
    }else if(this.t==='lightning'){
      if(p.l>p.ml)this.p[i]=this._mk(0);
    }else{if(p.l===1)p.by=p.y;p.x+=p.vx;p.y=p.by+Math.sin(p.l*p.wf)*p.wa+p.vy*p.l*.25;
      p.a+=p.ra;if(p.x>this.w+14||p.l>p.ml)this.p[i]=this._mk(0);}}}
  draw(){if(!this.w)return;this.x.clearRect(0,0,this.w,this.h);
    for(const p of this.p){
      const lp=p.l/p.ml,f=lp<.15?lp/.15:lp>.6?(1-lp)/.4:1,a=p.o*f;
      this.x.save();
      if(this.t==='smoke'){
        if(a<=.001){this.x.restore();continue;}
        this.x.globalAlpha=a;this.x.fillStyle='#3a3a3a';
        this.x.beginPath();this.x.arc(p.x,p.y,p.sz,0,Math.PI*2);this.x.fill();
        this.x.globalAlpha=a*.2;this.x.beginPath();this.x.arc(p.x,p.y,p.sz*3,0,Math.PI*2);this.x.fill();
      }else if(this.t==='lightning'){
        if(p.l>15){this.x.restore();continue;}
        this.x.globalAlpha=1-(p.l/15);this.x.strokeStyle='#e0f7fa';this.x.lineWidth=2+Math.random()*2;
        this.x.shadowColor='#00ffff';this.x.shadowBlur=15;this.x.beginPath();this.x.moveTo(p.pts[0].x,p.pts[0].y);
        for(let i=1;i<p.pts.length;i++)this.x.lineTo(p.pts[i].x,p.pts[i].y);this.x.stroke();
        this.x.lineWidth=1;for(let i=1;i<p.pts.length-1;i++){if(Math.random()<0.3){this.x.beginPath();this.x.moveTo(p.pts[i].x,p.pts[i].y);this.x.lineTo(p.pts[i].x+(Math.random()-.5)*40,p.pts[i].y+20+Math.random()*20);this.x.stroke();}}
      }else{
        if(a<=.001){this.x.restore();continue;}
        this.x.globalAlpha=a;this.x.translate(p.x,p.y);this.x.rotate(p.a);
        this.x.fillStyle='#5aa552';this.x.beginPath();
        this.x.ellipse(0,0,p.sz,p.sz*.38,0,0,Math.PI*2);this.x.fill();
        this.x.strokeStyle='#1c7a4b';this.x.globalAlpha=a*.35;this.x.lineWidth=.5;
        this.x.beginPath();this.x.moveTo(-p.sz*.7,0);this.x.lineTo(p.sz*.7,0);this.x.stroke();
      }this.x.restore();}}
}
/* Animate the counter values on the active page and (re)start the
   particle FX loop for the overview cards. Under reduced motion the
   final values render instantly instead. */
function initKpiAnimations(){
  if(_kfxRAF){cancelAnimationFrame(_kfxRAF);_kfxRAF=null;}_kfxSys.length=0;
  
  const activePage=document.querySelector('.page.active');
  if(!activePage)return;
  
  if(!reduceMotion){
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

  if(reduceMotion)return;
  const ct=document.getElementById('overviewKpis');
  if(ct && ct.closest('.page.active')) {
    ct.querySelectorAll('.kpi-fx-canvas').forEach(c=>{_kfxSys.push(new _KPar(c,c.dataset.fx));});
    if(_kfxSys.length){
      (function lp(){if(!ct.closest('.page.active')){_kfxRAF=null;return;}
        _kfxSys.forEach(s=>{s.tick();s.draw();});_kfxRAF=requestAnimationFrame(lp);})();
    }
  }
}

/* ---- Chart FX: 3D interactive tilt ---- */
/* Pointer-tracked 3D tilt on chart cards. */
function initChartAnimations(){
  if(reduceMotion)return;
  const page=document.querySelector('.page.active');
  if(!page)return;
  page.querySelectorAll('.card').forEach(card=>{
    if(!card.querySelector('.chart'))return; // Only tilt cards that contain charts
    card.classList.add('card-3d');
    card.onmousemove=e=>{
      const r=card.getBoundingClientRect(), x=e.clientX-r.left, y=e.clientY-r.top;
      const xPct=(x/r.width-0.5)*2, yPct=(y/r.height-0.5)*2;
      card.style.transform=`perspective(1000px) rotateX(${-yPct*4}deg) rotateY(${xPct*4}deg) scale3d(1.01,1.01,1.01)`;
    };
    card.onmouseleave=()=>card.style.transform='perspective(1000px) rotateX(0) rotateY(0) scale3d(1,1,1)';
  });
}

/* Master re-render for the active page: KPIs, charts, table, then the
   entrance animations. Runs on load, on every filter change, and on
   every page switch. */
function syncMonthAvailability(){
  const d=data[yearFilter.value];
  if(!d)return;
  const allowed=new Set(d.availableMonths||[]);
  Array.from(monthFilter.options).forEach(option=>{
    if(option.value==='all')return;
    option.disabled=!allowed.has(+option.value);
  });
  if(monthFilter.value!=='all'&&!allowed.has(+monthFilter.value))monthFilter.value='all';
}

function refresh() {
  syncMonthAvailability();
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
function go(id){document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.bottom-dock button').forEach(b=>b.classList.toggle('active',b.dataset.page===id));const activeBtn = document.getElementById(id); activeBtn.classList.add('active'); const dockBtn = document.querySelector(`.bottom-dock button[data-page='${id}']`); if(dockBtn) updateIndicator(dockBtn);window.scrollTo({top:0,behavior:'smooth'});refresh();}
document.querySelectorAll('.bottom-dock button').forEach(b=>b.onclick=()=>go(b.dataset.page));
['yearFilter','monthFilter','compareMode'].forEach(id=>document.getElementById(id).addEventListener('change',refresh));

/* Dark mode toggle, persisted across visits in localStorage. */
const themeToggle = document.getElementById('themeToggle');
if(localStorage.getItem('theme') === 'dark') {
  document.body.classList.add('dark-mode');
}
themeToggle.onclick = () => {
  document.body.classList.toggle('dark-mode');
  const isDark = document.body.classList.contains('dark-mode');
  localStorage.setItem('theme', isDark ? 'dark' : 'light');
};

/* ---- data explorer tables ---- */
const tables={};
/* Flatten the master data into the five explorer views (built once at
   startup - filtering and sorting happen in renderTable). */
function buildTables(){const rows=[];for(const [year,d] of Object.entries(data)){months.forEach((m,i)=>{if(d.petrolL[i]!=null)rows.push([year,m,'S1','Petrol',d.petrolL[i],'L',EF.petrol,d.petrolEm[i]]);if(d.trDieselL[i]!=null)rows.push([year,m,'S1','Transport Diesel',d.trDieselL[i],'L',EF.diesel,d.trDieselEm[i]]);if(d.dgL[i]!=null)rows.push([year,m,'S1','DG Diesel',d.dgL[i],'L',EF.diesel,d.dgEm[i]]);if(d.elecKwh[i]!=null)rows.push([year,m,'S2','Grid Electricity',d.elecKwh[i],'kWh',EF.grid,d.elecEm[i]]);})}
 tables.unified={cols:['Year','Month','Scope','Source','Quantity','Unit','EF','Emissions tCO₂e'],rows};
 tables.transport={cols:['Year','Month','Petrol L','Petrol tCO₂e','Diesel L','Diesel tCO₂e'],rows:Object.entries(data).flatMap(([year,d])=>months.map((m,i)=>d.petrolL[i]!=null||d.trDieselL[i]!=null?[year,m,d.petrolL[i],d.petrolEm[i],d.trDieselL[i],d.trDieselEm[i]]:null).filter(Boolean))};
 tables.dg={cols:['Year','Month','DG Diesel L','DG Emissions tCO₂e'],rows:Object.entries(data).flatMap(([year,d])=>months.map((m,i)=>d.dgL[i]!=null?[year,m,d.dgL[i],d.dgEm[i]]:null).filter(Boolean))};
 tables.electricity={cols:['Year','Month','HT kWh','Commercial kWh','Temporary kWh','Emissions tCO₂e'],rows:Object.entries(data).flatMap(([year,d])=>months.map((m,i)=>d.htKwh[i]!=null||d.commKwh[i]!=null||d.tempKwh[i]!=null?[year,m,d.htKwh[i],d.commKwh[i],d.tempKwh[i],d.elecEm[i]]:null).filter(Boolean))};
 tables.re={cols:['Year','Period','RE kWh','Estimated Avoided tCO₂e','Granularity'],rows:Object.entries(data).flatMap(([year,d])=>{
   const rows=[];
   if(d.rePeriodTotal!=null)rows.push([year,`${months[d.rePeriodStartIndex]}–${months[d.rePeriodEndIndex]} period total`,d.rePeriodTotal,d.rePeriodTotal*EF.grid/1000,'period total']);
   d.reKwh.forEach((value,i)=>{if(value!=null)rows.push([year,months[i],value,d.avoidEm[i],'monthly approved'])});
   return rows;
 })};
}
let curTable='unified',sortCol=null,sortDir=1;
function filteredTableRows(t){const year=String(yearFilter.value),month=monthFilter.value==='all'?null:months[+monthFilter.value];return t.rows.filter(r=>String(r[0])===year&&(!month||String(r[1])===month))}
/* Render the current explorer view through the live search box filter
   and any active column sort. */
function renderTable(){if(!tables.unified)return;const t=tables[curTable],q=(document.getElementById('search')?.value||'').toLowerCase();let rows=filteredTableRows(t).filter(r=>r.some(c=>String(c).toLowerCase().includes(q)));if(sortCol!==null){rows=[...rows].sort((a,b)=>{let x=a[sortCol],y=b[sortCol];let nx=parseFloat(String(x).replace(/,/g,'')),ny=parseFloat(String(y).replace(/,/g,''));return (!isNaN(nx)&&!isNaN(ny)?nx-ny:String(x).localeCompare(String(y)))*sortDir})}const head=document.querySelector('#dataTable thead'),body=document.querySelector('#dataTable tbody');if(!head)return;head.innerHTML='<tr>'+t.cols.map((c,i)=>`<th data-c="${i}">${c}${sortCol===i?(sortDir>0?' ▲':' ▼'):''}</th>`).join('')+'</tr>';body.innerHTML=rows.map(r=>'<tr>'+r.map((c,i)=>`<td class="${typeof c==='number'?'num':''}">${t.cols[i]==='Scope'?`<span class="pill ${c==='S1'?'s1':'s2'}">${c}</span>`:c==null?'—':typeof c==='number'?fmt(c,Math.abs(c)<10?3:2):c}</td>`).join('')+'</tr>').join('');head.querySelectorAll('th').forEach(th=>th.onclick=()=>{const c=+th.dataset.c;if(sortCol===c)sortDir*=-1;else{sortCol=c;sortDir=1}renderTable()});}
document.getElementById('search')?.addEventListener('input',renderTable);
document.querySelectorAll('#tableTabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('#tableTabs button').forEach(x=>x.classList.remove('active'));b.classList.add('active');curTable=b.dataset.t;sortCol=null;renderTable();});
/* Download the current explorer view as CSV. */
document.getElementById('exportBtn').onclick=()=>{const t=tables[curTable]||tables.unified;const q=(document.getElementById('search')?.value||'').toLowerCase();const rows=filteredTableRows(t).filter(r=>r.some(c=>String(c).toLowerCase().includes(q)));const csv=[t.cols.join(',')].concat(rows.map(r=>r.map(c=>`"${c??''}"`).join(','))).join('\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));a.download=`kct_${yearFilter.value}_${monthFilter.value}_${curTable}.csv`;a.click();};

/* Boot: build the tables, first render, entrance sweep. */
function start(){buildTables();refresh();if(!reduceMotion){gsap.from('.showcase',{y:14,opacity:0,duration:.55,ease:'power2.out'});gsap.from('.topbar,.toolbar',{y:-16,opacity:0,duration:.5,stagger:.08});}}
/* Fetch + compute the master dataset (data-loader.js) before booting -
   everything below this point in the file only reads `data` from inside
   functions that run after start(), never at parse time. */
(async function boot(){
  const loaded = await loadDashboardData();
  data = loaded.data;
  Object.assign(EF, loaded.EF); // EF stays `const` above - mutate in place, don't reassign
  start();
})();


/* Slide the dock's dark pill under the active nav button. */
function updateIndicator(btn) {
  const ind = document.getElementById('indicator');
  if(ind && btn) {
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
    def: "The sum of reported Scope 1 and location-based Scope 2 emissions within the dashboard boundary.",
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
    impact: "Shows the contribution of reported renewable energy while keeping avoided-impact estimates separate from the formal inventory.",
    trend: "Review measured generation and consumption against the approved reporting period.",
    trendValue: 0
  },
  "Emission avoided": {
    def: "The calculated volume of CO2 emissions prevented from entering the atmosphere due to green initiatives.",
    impact: "A direct measure of the effectiveness and ROI of the institution's sustainability investments.",
    trend: "On track to reach 75% of the 1,000 tCO2e avoided goal by year end.",
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
    trend: "Aiming to drop below 2.0 tCO2e per capita (80% to goal).",
    trendValue: 80
  },
  "Illustrative balance (non-inventory)": {
    def: "An illustrative comparison of gross inventory emissions and separately estimated avoided emissions. It is not a GHG inventory total or verified offset.",
    impact: "Shows the relative scale of renewable impact without claiming that avoided emissions cancel the institutional inventory.",
    trend: "Use gross Scope 1 and Scope 2 values for formal inventory reporting.",
    trendValue: 0
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
        onUpdate: function() {
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
