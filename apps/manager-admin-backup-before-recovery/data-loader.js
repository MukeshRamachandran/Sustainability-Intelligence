/* =====================================================================
   MICROCOSM - DASHBOARD DATA LOADER (data-loader.js)
   Fetches the master CSVs (and the optional dashboard_master.json live
   overlay) from ./data, converts activity data to emissions via the
   emission factors, and returns the exact `data` shape app.js expects
   (per-year monthly arrays + annual/YTD rollups) so app.js no longer
   needs a hardcoded data literal. Ported from the CSV+JSON pipeline
   documented in kct_dynamic_csv_dashboard/DATA_AND_LOGIC.md.
   Must run before app.js (see index.html script order) - app.js awaits
   window.loadDashboardData() before it boots.
   ===================================================================== */
(function(){
  const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const MONTH_INDEX = Object.fromEntries(MONTHS.map((m,i)=>[m.toLowerCase(), i]));
  const DEFAULT_EF = { petrol: 2.388, diesel: 2.701, grid: 0.727 };

  /* Comma/blank/'null'/'-' safe numeric coercion for raw CSV cell text. */
  function num(v){
    if(v === null || v === undefined) return null;
    const s = String(v).trim().replace(/,/g,'');
    if(s === '' || s.toLowerCase() === 'null' || s === '-') return null;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
  }

  /* Hand-rolled CSV parser (quoted cells, "" escapes, \r\n/\n, blank-row skip). */
  function parseCSV(text){
    const rows=[]; let row=[], cell='', q=false;
    for(let i=0;i<text.length;i++){
      const c=text[i], n=text[i+1];
      if(c==='"' && q && n==='"'){ cell+='"'; i++; continue; }
      if(c==='"'){ q=!q; continue; }
      if(c===',' && !q){ row.push(cell); cell=''; continue; }
      if((c==='\n' || c==='\r') && !q){
        if(c==='\r' && n==='\n') i++;
        row.push(cell); cell='';
        if(row.some(x=>String(x).trim()!=='')) rows.push(row);
        row=[]; continue;
      }
      cell+=c;
    }
    row.push(cell); if(row.some(x=>String(x).trim()!=='')) rows.push(row);
    if(!rows.length) return [];
    const headers=rows.shift().map(h=>h.trim());
    return rows.map(r=>Object.fromEntries(headers.map((h,i)=>[h,(r[i]??'').trim()])));
  }

  async function fetchCSV(path){
    const res = await fetch(path + '?v=' + Date.now(), { cache: 'no-store' });
    if(!res.ok) throw new Error(`Cannot load ${path}: ${res.status}`);
    return parseCSV(await res.text());
  }

  function ensureYear(store, year){
    if(!store[year]){
      store[year]={
        label:`${year} Data`, frequency:'annual', population:null,
        totalGHG:null, totalEnergy:null, gridEnergy:0, reEnergy:0, reShare:null, avoided:0, perCapita:null,
        availableMonths:[], completeMonths:[], missingMonths:[], missingDomains:{}, latestMonthIndex:null,
        rePeriodTotal:null, rePeriodStartIndex:null, rePeriodEndIndex:null, reGranularity:'monthly',
        petrolL:Array(12).fill(null), trDieselL:Array(12).fill(null), dgL:Array(12).fill(null),
        lpgEm:Array(12).fill(0), htKwh:Array(12).fill(null), commKwh:Array(12).fill(null), tempKwh:Array(12).fill(null),
        reKwh:Array(12).fill(null), avoidEm:Array(12).fill(null)
      };
    }
    return store[year];
  }

  function monthToIndex(m){ return MONTH_INDEX[String(m||'').trim().slice(0,3).toLowerCase()]; }
  function add(arr, idx, value){ if(idx == null || value == null) return; arr[idx] = (arr[idx] == null ? 0 : arr[idx]) + value; }
  function n(v){ return v==null || Number.isNaN(+v) ? 0 : +v; }
  function sum(arr, s=0, e=12){ return arr.slice(s,e).reduce((a,b)=>a+n(b),0); }

  /* Rolls the per-month raw+emission arrays up into the derived monthly
     series and annual/YTD scalars app.js's rendering code reads directly
     (elecKwh/elecEm/scope1Selected/.../grossSelected, plus totalGHG,
     gridEnergy, reEnergy, avoided, totalEnergy, reShare, perCapita).
     Re-run after the initial CSV load AND after every JSON-overlay edit
     to a year, so downstream totals never go stale. */
  function deriveYear(d){
    const complete=(values)=>values.every(v=>v!=null);
    const addKnown=(values)=>complete(values)?values.reduce((a,v)=>a+n(v),0):null;
    d.elecKwh = MONTHS.map((_,i)=>addKnown([d.htKwh[i],d.commKwh[i],d.tempKwh[i]]));
    d.elecEm = MONTHS.map((_,i)=>addKnown([d.htEm[i],d.commEm[i],d.tempEm[i]]));
    d.scope1Selected = MONTHS.map((_,i)=>addKnown([d.petrolEm[i],d.trDieselEm[i],d.dgEm[i]]));
    d.scope1Full = MONTHS.map((_,i)=>d.scope1Selected[i]==null?null:d.scope1Selected[i]+n(d.lpgEm[i]));
    d.dieselCombo = MONTHS.map((_,i)=>addKnown([d.trDieselEm[i],d.dgEm[i]]));
    d.grossSelected = MONTHS.map((_,i)=>addKnown([d.scope1Selected[i],d.elecEm[i]]));
    d.grossFull = MONTHS.map((_,i)=>addKnown([d.scope1Full[i],d.elecEm[i]]));

    d.gridEnergy = sum(d.htKwh)+sum(d.commKwh)+sum(d.tempKwh);
    const monthlyRe = d.reKwh.reduce((total,value,i)=>{
      if(value==null) return total;
      const covered=d.rePeriodStartIndex!=null&&d.rePeriodEndIndex!=null&&i>=d.rePeriodStartIndex&&i<=d.rePeriodEndIndex;
      return covered?total:total+n(value);
    },0);
    d.reEnergy = n(d.rePeriodTotal) + monthlyRe;
    d.avoided = d.reEnergy * n(d.gridEF) / 1000;
    d.totalEnergy = d.gridEnergy + d.reEnergy;
    d.reShare = d.totalEnergy ? (d.reEnergy/d.totalEnergy*100) : null;

    const activityArrays=[d.petrolL,d.trDieselL,d.dgL,d.htKwh,d.commKwh,d.tempKwh];
    d.availableMonths = MONTHS.map((_,i)=>i).filter(i=>activityArrays.some(a=>a[i]!=null));
    d.completeMonths = MONTHS.map((_,i)=>i).filter(i=>activityArrays.every(a=>a[i]!=null));
    d.latestMonthIndex = d.availableMonths.length ? Math.max(...d.availableMonths) : null;
    d.missingMonths = d.latestMonthIndex==null ? [] : MONTHS.map((_,i)=>i).filter(i=>i<=d.latestMonthIndex && !d.availableMonths.includes(i));
    d.missingDomains = Object.fromEntries(d.availableMonths.map(i=>[i,[
      (d.petrolL[i]==null||d.trDieselL[i]==null)?'transport':null,
      d.dgL[i]==null?'dg':null,
      (d.htKwh[i]==null||d.commKwh[i]==null||d.tempKwh[i]==null)?'electricity':null
    ].filter(Boolean)]).filter(([,domains])=>domains.length));
    d.totalGHG = sum(d.grossSelected);
    d.perCapita = d.population ? d.totalGHG/d.population : null;
  }

  async function loadDashboardData(){
    const [factorRows, transportRows, dgRows, elecRows, reRows, popRows, metaRows] = await Promise.all([
      fetchCSV('data/emission_factors.csv'),
      fetchCSV('data/transport_master.csv'),
      fetchCSV('data/dg_master.csv'),
      fetchCSV('data/electricity_master.csv'),
      fetchCSV('data/renewable_master.csv'),
      fetchCSV('data/population_master.csv').catch(()=>[]),
      fetchCSV('data/dashboard_metadata.csv').catch(()=>[])
    ]);

    const EF = { ...DEFAULT_EF };
    factorRows.forEach(r=>{
      const key = String(r.factor_key||'').toLowerCase();
      const val = num(r.emission_factor);
      if(key && val != null) EF[key] = val;
    });

    const data = {};
    metaRows.forEach(r=>{
      const y=String(r.year||'').trim(); if(!y) return;
      const d=ensureYear(data,y);
      d.label=r.label || d.label;
      d.frequency=(r.frequency || d.frequency).toLowerCase();
    });
    popRows.forEach(r=>{
      const y=String(r.year||'').trim(); const p=num(r.population); if(!y) return;
      ensureYear(data,y).population=p;
    });

    transportRows.forEach(r=>{
      const y=String(r.year||'').trim(), i=monthToIndex(r.month), fuel=String(r.fuel_type||'').toLowerCase(), qty=num(r.consumption_litre);
      const d=ensureYear(data,y);
      if(fuel.includes('petrol')) add(d.petrolL,i,qty);
      else if(fuel.includes('diesel')) add(d.trDieselL,i,qty);
    });

    dgRows.forEach(r=>{
      const y=String(r.year||'').trim(), i=monthToIndex(r.month), qty=num(r.consumption_litre);
      add(ensureYear(data,y).dgL,i,qty);
    });

    elecRows.forEach(r=>{
      const y=String(r.year||'').trim(), i=monthToIndex(r.month), typ=String(r.connection_type||'').toLowerCase(), qty=num(r.consumption_kwh);
      const d=ensureYear(data,y);
      if(typ.includes('ht')) add(d.htKwh,i,qty);
      else if(typ.includes('commercial')) add(d.commKwh,i,qty);
      else if(typ.includes('temporary')) add(d.tempKwh,i,qty);
    });

    reRows.forEach(r=>{
      const y=String(r.year||'').trim(); if(!y) return;
      const d=ensureYear(data,y); const qty=num(r.renewable_kwh); if(qty==null) return;
      const m=String(r.month||'').trim().toLowerCase();
      const i=monthToIndex(m);
      if(i != null){ add(d.reKwh,i,qty); }
      else {
        // A period total is not monthly evidence. Keep it separate so the
        // dashboard never invents equal monthly renewable readings.
        d.rePeriodTotal = n(d.rePeriodTotal) + qty;
        d.rePeriodStartIndex = monthToIndex(r.period_start_month);
        d.rePeriodEndIndex = monthToIndex(r.period_end_month);
        d.reGranularity = 'period_total';
        if(m.includes('ytd')) d.frequency = 'ytd';
      }
    });

    Object.values(data).forEach(d=>{
      d.petrolEm = d.petrolL.map(v=>v==null?null:v*EF.petrol/1000);
      d.trDieselEm = d.trDieselL.map(v=>v==null?null:v*EF.diesel/1000);
      d.dgEm = d.dgL.map(v=>v==null?null:v*EF.diesel/1000);
      d.htEm = d.htKwh.map(v=>v==null?null:v*EF.grid/1000);
      d.commEm = d.commKwh.map(v=>v==null?null:v*EF.grid/1000);
      d.tempEm = d.tempKwh.map(v=>v==null?null:v*EF.grid/1000);
      d.avoidEm = d.reKwh.map(v=>v==null?null:v*EF.grid/1000);
      d.gridEF = EF.grid;

      const knownMonths = Math.max(
        ...[d.petrolL,d.trDieselL,d.dgL,d.htKwh,d.commKwh,d.tempKwh].map(a=>a.filter(v=>v!=null).length), 0
      );
      if(knownMonths>0 && knownMonths<12) d.frequency='ytd';
      d.label = d.label || `${knownMonths<12 ? 'YTD' : 'Full Year'} ${d.year || ''}`;

      deriveYear(d);
    });

    // Dynamic overlay from dashboard_master.json - best-effort, the
    // dashboard still works fine on CSVs alone if this is missing/invalid.
    // Written by the FastAPI pipeline whenever Power Automate posts an
    // approved form submission (see /microcosm-dashboard-backend).
    try {
      const jsonRes = await fetch('data/dashboard_master.json?v=' + Date.now(), { cache: 'no-store' });
      if(jsonRes.ok) {
        const dynamicData = await jsonRes.json();
        const apiData = dynamicData.data || {};

        (apiData.energy || []).forEach(rec => {
          if(String(rec.Status||'').toLowerCase() !== 'approved') return;
          if(!rec.Year || !rec.Month) return;
          const d = ensureYear(data, rec.Year);
          const i = monthToIndex(rec.Month);
          if(i == null) return;

          if(rec.Industrial != null) d.htKwh[i] = num(rec.Industrial);
          if(rec.Commercial != null) d.commKwh[i] = num(rec.Commercial);
          if(rec.Temporary != null) d.tempKwh[i] = num(rec.Temporary);
          if(rec.Total_RE != null) d.reKwh[i] = num(rec.Total_RE);
          if(rec.Total_RE != null && d.rePeriodTotal != null) d.reGranularity = 'mixed';
          // DG_kWh intentionally not mapped to dgL - unit mismatch (kWh vs litres).

          d.htEm[i] = d.htKwh[i] == null ? null : d.htKwh[i]*EF.grid/1000;
          d.commEm[i] = d.commKwh[i] == null ? null : d.commKwh[i]*EF.grid/1000;
          d.tempEm[i] = d.tempKwh[i] == null ? null : d.tempKwh[i]*EF.grid/1000;
          d.avoidEm[i] = d.reKwh[i] == null ? null : d.reKwh[i]*EF.grid/1000;

          deriveYear(d);
        });

        (apiData.transport || []).forEach(rec => {
          if(String(rec.Status||'').toLowerCase() !== 'approved') return;
          if(!rec.Year || !rec.Month) return;
          const d = ensureYear(data, rec.Year);
          const i = monthToIndex(rec.Month);
          if(i == null) return;

          if(rec.Petrol_Litres != null) d.petrolL[i] = num(rec.Petrol_Litres);
          if(rec.Diesel_Litres != null) d.trDieselL[i] = num(rec.Diesel_Litres);

          d.petrolEm[i] = d.petrolL[i] == null ? null : d.petrolL[i]*EF.petrol/1000;
          d.trDieselEm[i] = d.trDieselL[i] == null ? null : d.trDieselL[i]*EF.diesel/1000;

          deriveYear(d);
        });
      }
    } catch(err) {
      console.warn('Could not load dynamic dashboard JSON overlay (might not exist yet):', err);
    }

    return { data, EF };
  }

  window.loadDashboardData = loadDashboardData;
})();
