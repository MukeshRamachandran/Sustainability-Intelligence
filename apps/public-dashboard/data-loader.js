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
(function () {
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const MONTH_INDEX = Object.fromEntries(MONTHS.map((m, i) => [m.toLowerCase(), i]));
  const DEFAULT_EF = { petrol: 2.388, diesel: 2.701, grid: 0.727, lpg: 1.5571 };

  /* Comma/blank/'null'/'-' safe numeric coercion for raw CSV cell text. */
  function num(v) {
    if (v === null || v === undefined) return null;
    const s = String(v).trim().replace(/,/g, '');
    if (s === '' || s.toLowerCase() === 'null' || s === '-') return null;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
  }

  /* Pulls the first number out of a free-text reported figure - the
     outreach sheet writes cells like "20+", "9025+ hours" and "30,278
     seedlings raised and planted in 2025.", never a bare number. Returns
     null for genuinely non-numeric cells (e.g. "Not quantified"). */
  function extractNumber(v) {
    if (v === null || v === undefined) return null;
    const m = String(v).replace(/,/g, '').match(/\d+(\.\d+)?/);
    return m ? parseFloat(m[0]) : null;
  }

  /* Hand-rolled CSV tokenizer (quoted cells, "" escapes, \r\n/\n, blank-row
     skip). Returns raw row arrays - shared by parseCSV (plain, one header
     row) and parseGroupedCSV (side-by-side blocks, see below). */
  function tokenizeCSV(text) {
    const rows = []; let row = [], cell = '', q = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i], n = text[i + 1];
      if (c === '"' && q && n === '"') { cell += '"'; i++; continue; }
      if (c === '"') { q = !q; continue; }
      if (c === ',' && !q) { row.push(cell); cell = ''; continue; }
      if ((c === '\n' || c === '\r') && !q) {
        if (c === '\r' && n === '\n') i++;
        row.push(cell); cell = '';
        if (row.some(x => String(x).trim() !== '')) rows.push(row);
        row = []; continue;
      }
      cell += c;
    }
    row.push(cell); if (row.some(x => String(x).trim() !== '')) rows.push(row);
    return rows;
  }

  function parseCSV(text) {
    const rows = tokenizeCSV(text);
    if (!rows.length) return [];
    const headers = rows.shift().map(h => h.trim());
    return rows.map(r => Object.fromEntries(headers.map((h, i) => [h, (r[i] ?? '').trim()])));
  }

  /* Parses a "grouped" master sheet: several blocks laid out side by side
     on one sheet (e.g. HT | Commercial | Temporary, or Diesel | Petrol),
     each with its own year/month/quantity columns and a blank spacer
     column between blocks - a purely visual rearrangement some master
     CSVs now use instead of one stacked table. Row 0 names each block
     (label sits only in the block's first cell), row 1 repeats the real
     sub-headers per block. Flattens back into the same row-object shape
     parseCSV produces, with `keyField` set to the block's label, so
     downstream code (which expects a single fuel_type/connection_type
     column) doesn't need to know the sheet is laid out side by side. */
  function parseGroupedCSV(text, keyField) {
    const rows = tokenizeCSV(text);
    if (rows.length < 2) return [];
    const groupRow = rows[0].map(c => c.trim());
    const headerRow = rows[1].map(c => c.trim());
    const starts = [];
    groupRow.forEach((c, i) => { if (c !== '') starts.push(i); });
    const blocks = starts.map((start, bi) => {
      const limit = bi + 1 < starts.length ? starts[bi + 1] : headerRow.length;
      let width = limit - start;
      while (width > 0 && headerRow[start + width - 1] === '') width--;
      return { label: groupRow[start], start, headers: headerRow.slice(start, start + width) };
    });
    const out = [];
    for (let r = 2; r < rows.length; r++) {
      const raw = rows[r];
      blocks.forEach(b => {
        let hasData = false;
        const rec = { [keyField]: b.label };
        b.headers.forEach((h, i) => { const v = (raw[b.start + i] ?? '').trim(); rec[h] = v; if (v !== '') hasData = true; });
        if (hasData) out.push(rec);
      });
    }
    return out;
  }

  async function fetchCSV(path) {
    const res = await fetch(path + '?v=' + Date.now(), { cache: 'no-store' });
    if (!res.ok) throw new Error(`Cannot load ${path}: ${res.status}`);
    return parseCSV(await res.text());
  }

  async function fetchGroupedCSV(path, keyField) {
    const res = await fetch(path + '?v=' + Date.now(), { cache: 'no-store' });
    if (!res.ok) throw new Error(`Cannot load ${path}: ${res.status}`);
    return parseGroupedCSV(await res.text(), keyField);
  }

  function ensureYear(store, year) {
    if (!store[year]) {
      store[year] = {
        label: `${year} Data`, frequency: 'annual', population: null,
        totalGHG: null, totalEnergy: null, gridEnergy: 0, reEnergy: 0, reShare: null, avoided: 0, perCapita: null,
        petrolL: Array(12).fill(null), trDieselL: Array(12).fill(null), dgL: Array(12).fill(null), lpgL: Array(12).fill(null),
        htKwh: Array(12).fill(null), commKwh: Array(12).fill(null), tempKwh: Array(12).fill(null),
        reKwh: Array(12).fill(null), avoidEm: Array(12).fill(null),
        /* On-campus generation vs procured green energy - the two real
           components of reKwh (see energy_master.csv), replacing the old
           60/30 estimated split the Energy page charts used to draw. */
        reOnCampusKwh: Array(12).fill(null), reProcuredKwh: Array(12).fill(null),
        solarWaterHeaterKwh: null,
        wetWaste: 0, dryWaste: 0, totalWaste: 0, wasteBreakdown: [],
        waterKL: Array(12).fill(null), waterTWAD: Array(12).fill(null),
        waterBorewell: Array(12).fill(null), waterProcured: Array(12).fill(null),
        waterRecycledKL: null,
        /* Some years (2025 so far) only report TWAD/Borewell as one annual
           split rather than a monthly breakdown - kept separate from the
           monthly arrays above rather than spread across months, since we
           don't know the real monthly shape. */
        waterTWADAnnual: null, waterBorewellAnnual: null, waterTotalAnnual: null
      };
    }
    return store[year];
  }

  function monthToIndex(m) { return MONTH_INDEX[String(m || '').trim().slice(0, 3).toLowerCase()]; }
  function add(arr, idx, value) { if (idx == null || value == null) return; arr[idx] = (arr[idx] == null ? 0 : arr[idx]) + value; }
  function n(v) { return v == null || Number.isNaN(+v) ? 0 : +v; }
  function sum(arr, s = 0, e = 12) { return arr.slice(s, e).reduce((a, b) => a + n(b), 0); }

  /* Rolls the per-month raw+emission arrays up into the derived monthly
     series and annual/YTD scalars app.js's rendering code reads directly
     (elecKwh/elecEm/scope1Selected/.../grossSelected, plus totalGHG,
     gridEnergy, reEnergy, avoided, totalEnergy, reShare, perCapita).
     Re-run after the initial CSV load AND after every JSON-overlay edit
     to a year, so downstream totals never go stale. */
  function deriveYear(d) {
    d.elecKwh = MONTHS.map((_, i) => Calculations.totalGridElectricity(d.htKwh[i], d.commKwh[i], d.tempKwh[i]));
    d.elecEm = MONTHS.map((_, i) => Calculations.scope2Total(d.htEm[i], d.commEm[i], d.tempEm[i]));
    d.scope1Selected = MONTHS.map((_, i) => Calculations.scope1Total(d.petrolEm[i], d.trDieselEm[i], d.dgEm[i], d.lpgEm[i]));
    d.scope1Full = d.scope1Selected;
    d.dieselCombo = MONTHS.map((_, i) => n(d.trDieselEm[i]) + n(d.dgEm[i]));
    d.grossSelected = MONTHS.map((_, i) => Calculations.grossEmissions(d.scope1Selected[i], d.elecEm[i]));
    d.grossFull = MONTHS.map((_, i) => Calculations.grossEmissions(d.scope1Full[i], d.elecEm[i]));

    d.gridEnergy = Calculations.totalGridElectricity(sum(d.htKwh), sum(d.commKwh), sum(d.tempKwh));
    d.reEnergy = sum(d.reKwh);
    d.avoided = sum(d.avoidEm);
    // Electricity demand boundary (grid + RE) used as the renewable-share
    // denominator below. NOT the doc's §13 Total Energy (which also folds
    // in fuel litres via an energy-content factor - see calculations.js).
    d.totalEnergy = d.gridEnergy + d.reEnergy;
    d.reShare = Calculations.renewableShare(d.reEnergy, d.gridEnergy);

    const end = d.frequency === 'ytd' ? 4 : 12;
    d.totalGHG = Calculations.ytdSum(d.grossFull, end - 1);
    d.perCapita = Calculations.perPersonFootprint(d.totalGHG, d.population);
  }

  async function loadDashboardData() {
    const [factorRows, transportRows, dgRows, lpgRows, popRows, metaRows, wasteText, waterText, greenText, outreachText, energyText] = await Promise.all([
      fetchCSV('data/emission_factors.csv'),
      fetchGroupedCSV('data/transport_master.csv', 'fuel_type'),
      fetchCSV('data/dg_master.csv'),
      fetchCSV('data/lpg_master.csv'),
      fetchCSV('data/population_master.csv').catch(() => []),
      fetchCSV('data/dashboard_metadata.csv').catch(() => []),
      fetch('data/waste_master.csv?v=' + Date.now()).then(r => r.text()).catch(() => ''),
      fetch('data/water_master.csv?v=' + Date.now()).then(r => r.text()).catch(() => ''),
      fetch('data/green_master.csv?v=' + Date.now()).then(r => r.text()).catch(() => ''),
      fetch('data/outreach_master.csv?v=' + Date.now()).then(r => r.text()).catch(() => ''),
      /* Replaces electricity_master.csv + renewable_master.csv - both grid
         (HT/Commercial/Temporary) and renewable (on-campus + procured) now
         come from this one sheet. See the block parser below. */
      fetch('data/energy_master.csv?v=' + Date.now()).then(r => r.text()).catch(() => '')
    ]);

    const EF = { ...DEFAULT_EF };
    factorRows.forEach(r => {
      const key = String(r.factor_key || '').toLowerCase();
      const val = num(r.emission_factor);
      if (key && val != null) EF[key] = val;
    });

    const data = {};
    metaRows.forEach(r => {
      const y = String(r.year || '').trim(); if (!y) return;
      const d = ensureYear(data, y);
      d.label = r.label || d.label;
      d.frequency = (r.frequency || d.frequency).toLowerCase();
    });
    popRows.forEach(r => {
      const y = String(r.year || '').trim(); const p = num(r.population); if (!y) return;
      ensureYear(data, y).population = p;
    });

    if (wasteText) {
      const wRows = tokenizeCSV(wasteText);
      const yRow = wRows.find(r => String(r[0]).toLowerCase().trim() === 'year');
      if (yRow) {
        for (let col = 1; col < yRow.length; col++) {
          const y = String(yRow[col]).trim();
          if (!y) continue;
          const d = ensureYear(data, y);
          wRows.forEach(r => {
            const key = String(r[0]).toLowerCase().trim();
            const val = num(r[col]);
            if (val != null) {
              if (key.includes('wet waste')) d.wetWaste = (d.wetWaste || 0) + val;
              else if (key.includes('dry waste')) d.dryWaste = (d.dryWaste || 0) + val;
              else if (key.includes('total waste approximate')) d.totalWaste = (d.totalWaste || 0) + val;
              else if (key !== 'total' && key !== 'item' && key !== 'year' && key !== 'waste inventory' && key !== '') {
                d.wasteBreakdown.push({ name: String(r[0]).trim(), value: val });
              }
            }
          });
        }
      }
    }

    if (waterText) {
      /* Line-by-line dispatcher rather than a fixed row layout, since the
         sheet doesn't put the same rows in the same order every year: a
         "Water Consumption <year>" label starts a year's section; inside
         it, in whatever order they appear, there can be a "Total water
         recycled" scalar, a "Month" header (naming that year's monthly
         columns - TWAD/Borewell/Procured/Total for 2026, a single KL
         total for 2025) followed by month rows, and/or a standalone
         "TWAD Consumption KL / Borewell.../ Total Consumption" header
         with one annual-total data row beneath it for years (2025) that
         only report the TWAD/Borewell split annually, not per month.
         Unrecognized rows ("Total", blanks) are just skipped. */
      const rows = tokenizeCSV(waterText);
      let wd = null;
      let colTotal = -1, colTWAD = -1, colBore = -1, colProc = -1, colSimple = -1;
      let ri = 0;
      while (ri < rows.length) {
        const r = rows[ri];
        const label = String(r[0] || '').trim();

        const yearMatch = label.match(/^water consumption (\d{4})/i);
        if (yearMatch) {
          wd = ensureYear(data, yearMatch[1]);
          colTotal = colTWAD = colBore = colProc = colSimple = -1;
          ri++; continue;
        }
        if (!wd) { ri++; continue; }

        if (/^total water recy/i.test(label)) {
          const val = num(r[1]);
          if (val != null) wd.waterRecycledKL = val;
          ri++; continue;
        }

        if (label.toLowerCase() === 'month') {
          const header = r.map(h => String(h || '').trim().toLowerCase());
          colTotal = header.findIndex(h => h.startsWith('total consumption'));
          colTWAD = header.findIndex(h => h.includes('twad'));
          colBore = header.findIndex(h => h.includes('borewell'));
          colProc = header.findIndex(h => h.includes('procured'));
          colSimple = header.findIndex(h => h.includes('water consumption'));
          ri++; continue;
        }

        if (label.toLowerCase().startsWith('twad consumption')) {
          ri++; // the annual split's one data row sits right under this header
          if (ri < rows.length) {
            const dr = rows[ri];
            wd.waterTWADAnnual = num(dr[0]);
            wd.waterBorewellAnnual = num(dr[1]);
            wd.waterTotalAnnual = num(dr[2]);
            ri++;
          }
          continue;
        }

        const mi = monthToIndex(label);
        if (mi != null) {
          if (colTWAD >= 0) add(wd.waterTWAD, mi, num(r[colTWAD]));
          if (colBore >= 0) add(wd.waterBorewell, mi, num(r[colBore]));
          if (colProc >= 0) add(wd.waterProcured, mi, num(r[colProc]));
          if (colTotal >= 0) add(wd.waterKL, mi, num(r[colTotal]));
          else if (colSimple >= 0) add(wd.waterKL, mi, num(r[colSimple]));
        }
        ri++;
      }
    }

    /* Green cover is a one-time campus survey (Trees of Kumaraguru Institution), not a monthly
       series, so it lives outside the year-keyed `data` object entirely -
       see the block-section parser below and the green_master.csv comment
       at the top of that file for the four sections it walks. */
    const green = {
      totalTrees: null, totalSpecies: null, campusAreaAcres: null,
      /* Maintained/natural vegetation are recorded in acres in the source
         sheet (not %) - only "Total green cover" is itself a percentage. */
      totalGreenCoverPct: null, maintainedVegetationAcres: null, naturalVegetationAcres: null,
      zones: [], speciesList: [], phenology: []
    };
    if (greenText) {
      const gRows = tokenizeCSV(greenText);
      let section = null;
      gRows.forEach(r => {
        const c0 = String(r[0] || '').trim();
        if (c0 === 'Green Cover Summary') { section = 'summary'; return; }
        if (c0 === 'Zone-wise Tree and Species Distribution') { section = 'zones'; return; }
        if (c0 === 'Species List') { section = 'species'; return; }
        if (c0.startsWith('Species Phenology')) { section = 'phenology'; return; }
        if (c0 === 'Metric' || c0 === 'Zone' || (c0 === 'Scientific Name' && section === 'species') || c0 === 'Species') return;
        if (!c0) return;

        if (section === 'summary') {
          const val = num(r[1]);
          if (c0 === 'Total trees') green.totalTrees = val;
          else if (c0 === 'Total tree species identified') green.totalSpecies = val;
          else if (c0 === 'Campus area') green.campusAreaAcres = val;
          else if (c0 === 'Total green cover') green.totalGreenCoverPct = val;
          else if (c0 === 'Maintained vegetation') green.maintainedVegetationAcres = val;
          else if (c0 === 'Natural vegetation') green.naturalVegetationAcres = val;
        } else if (section === 'zones') {
          green.zones.push({ zone: c0, trees: num(r[1]) || 0, species: num(r[2]) || 0 });
        } else if (section === 'species') {
          green.speciesList.push({ scientific: c0, common: String(r[1] || '').trim() });
        } else if (section === 'phenology') {
          green.phenology.push({ species: c0, common: String(r[1] || '').trim(), event: String(r[2] || '').trim(), months: r.slice(3, 15).map(v => String(v || '').trim() === '1') });
        }
      });
    }

    /* Outreach, like green cover, is a one-time reported set of figures
       (currently 2025 only - no year column in the sheet at all), not a
       monthly series. app.js gates display on the YEAR filter itself
       (there's nothing to compute for 2026 - see outreachKpisEl there). */
    const outreach = {
      programsDelivered: null, volunteersEngaged: null, volunteerHours: null,
      expertsInvolved: null, participantsServed: null, partnerOrganizations: null,
      saplingsPlanted: null, thematicAreas: [], audienceReach: []
    };
    if (outreachText) {
      const oRows = tokenizeCSV(outreachText);
      let section = null;
      oRows.forEach(r => {
        const c0 = String(r[0] || '').trim();
        if (c0 === 'Overall Metrix') { section = 'summary'; return; }
        if (c0 === 'Thematic Areas') { section = 'thematic'; return; }
        if (c0 === 'Category wise mapping') { section = 'audience'; return; }
        if (c0 === 'Metric' || c0 === 'Category' || c0 === 'Audience category') return;
        if (!c0) return;

        if (section === 'summary') {
          const val = extractNumber(r[1]);
          if (c0.startsWith('Number of Outreach Programs')) outreach.programsDelivered = val;
          else if (c0 === 'Volunteers engaged') outreach.volunteersEngaged = val;
          else if (c0 === 'Volunteering hours') outreach.volunteerHours = val;
          else if (c0 === 'Experts involved') outreach.expertsInvolved = val;
          else if (c0.startsWith('Total participants')) outreach.participantsServed = val;
          else if (c0.startsWith('Partner organizations')) outreach.partnerOrganizations = val;
          else if (c0.startsWith('Saplings')) outreach.saplingsPlanted = val;
        } else if (section === 'thematic') {
          outreach.thematicAreas.push({ category: c0, programs: extractNumber(r[1]) || 0 });
        } else if (section === 'audience') {
          outreach.audienceReach.push({ category: c0, reach: extractNumber(r[1]) });
        }
      });
    }

    transportRows.forEach(r => {
      const y = String(r.year || '').trim(), i = monthToIndex(r.month), fuel = String(r.fuel_type || '').toLowerCase(), qty = num(r.consumption_litre);
      const d = ensureYear(data, y);
      if (fuel.includes('petrol')) add(d.petrolL, i, qty);
      else if (fuel.includes('diesel')) add(d.trDieselL, i, qty);
    });

    dgRows.forEach(r => {
      const y = String(r.year || '').trim(), i = monthToIndex(r.month), qty = num(r.consumption_litre);
      add(ensureYear(data, y).dgL, i, qty);
    });

    lpgRows.forEach(r => {
      const y = String(r.year || '').trim(), i = monthToIndex(r.month), qty = num(r.consumption_litre);
      add(ensureYear(data, y).lpgL, i, qty);
    });

    /* Grid (HT/Commercial/Temporary) + renewable (on-campus/procured) in one
       sheet - a "year" label row (with that year's Solar Water Heater
       constant, only given for 2025 so far) followed by one row per month
       until the next year label. Replaces electricity_master.csv and
       renewable_master.csv entirely; reKwh (total renewable) is computed
       here as on-campus + procured, not read from a column. */
    if (energyText) {
      const enRows = tokenizeCSV(energyText);
      enRows.forEach((r, idx) => {
        if (idx === 0) return; // header row
        const enYear = String(r[0] || '').trim();
        if (!/^\d{4}$/.test(enYear)) return;
        const mi = monthToIndex(String(r[1] || '').trim());
        if (mi == null) return;
        const d = ensureYear(data, enYear);
        
        const swh = num(r[7]);
        if (swh != null) d.solarWaterHeaterKwh = swh;
        
        add(d.htKwh, mi, num(r[2]));
        add(d.commKwh, mi, num(r[3]));
        add(d.tempKwh, mi, num(r[4]));
        const onCampus = num(r[5]), procured = num(r[6]);
        add(d.reOnCampusKwh, mi, onCampus);
        add(d.reProcuredKwh, mi, procured);
        if (onCampus != null || procured != null) add(d.reKwh, mi, (onCampus || 0) + (procured || 0));
      });
    }

    Object.values(data).forEach(d => {
      d.petrolEm = d.petrolL.map(v => Calculations.co2e(v, EF.petrol));
      d.trDieselEm = d.trDieselL.map(v => Calculations.co2e(v, EF.diesel));
      d.dgEm = d.dgL.map(v => Calculations.co2e(v, EF.diesel));
      d.lpgEm = d.lpgL.map(v => Calculations.co2e(v, EF.lpg));
      d.htEm = d.htKwh.map(v => Calculations.co2e(v, EF.grid));
      d.commEm = d.commKwh.map(v => Calculations.co2e(v, EF.grid));
      d.tempEm = d.tempKwh.map(v => Calculations.co2e(v, EF.grid));
      d.avoidEm = d.reKwh.map(v => Calculations.renewableAvoidedEmissions(v, EF.grid));

      const knownMonths = Math.max(
        ...[d.petrolL, d.trDieselL, d.dgL, d.lpgL, d.htKwh, d.commKwh, d.tempKwh].map(a => a.filter(v => v != null).length), 0
      );
      if (knownMonths > 0 && knownMonths < 12) d.frequency = 'ytd';
      d.label = d.label || (knownMonths > 0 && knownMonths < 12
        ? `${d.year || ''} YTD (${MONTHS[0]}–${MONTHS[knownMonths - 1]})`
        : `${d.year || ''} Full Year`);

      deriveYear(d);
    });

    // Dynamic overlay from dashboard_master.json - best-effort, the
    // dashboard still works fine on CSVs alone if this is missing/invalid.
    // Written by the FastAPI pipeline whenever Power Automate posts an
    // approved form submission (see /microcosm-dashboard-backend).
    try {
      const jsonRes = await fetch('data/dashboard_master.json?v=' + Date.now(), { cache: 'no-store' });
      if (jsonRes.ok) {
        const dynamicData = await jsonRes.json();
        const apiData = dynamicData.data || {};

        (apiData.energy || []).forEach(rec => {
          if (!rec.Year || !rec.Month) return;
          const d = ensureYear(data, rec.Year);
          const i = monthToIndex(rec.Month);
          if (i == null) return;

          if (rec.Industrial != null) d.htKwh[i] = rec.Industrial;
          if (rec.Commercial != null) d.commKwh[i] = rec.Commercial;
          if (rec.Temporary != null) d.tempKwh[i] = rec.Temporary;
          if (rec.Total_RE != null) d.reKwh[i] = rec.Total_RE;
          // DG_kWh intentionally not mapped to dgL - unit mismatch (kWh vs litres).

          d.htEm[i] = Calculations.co2e(d.htKwh[i], EF.grid);
          d.commEm[i] = Calculations.co2e(d.commKwh[i], EF.grid);
          d.tempEm[i] = Calculations.co2e(d.tempKwh[i], EF.grid);
          d.avoidEm[i] = Calculations.renewableAvoidedEmissions(d.reKwh[i], EF.grid);

          deriveYear(d);
        });

        (apiData.transport || []).forEach(rec => {
          if (!rec.Year || !rec.Month) return;
          const d = ensureYear(data, rec.Year);
          const i = monthToIndex(rec.Month);
          if (i == null) return;

          if (rec.Petrol_Litres != null) d.petrolL[i] = rec.Petrol_Litres;
          if (rec.Diesel_Litres != null) d.trDieselL[i] = rec.Diesel_Litres;

          d.petrolEm[i] = Calculations.co2e(d.petrolL[i], EF.petrol);
          d.trDieselEm[i] = Calculations.co2e(d.trDieselL[i], EF.diesel);

          deriveYear(d);
        });
      }
    } catch (err) {
      console.warn('Could not load dynamic dashboard JSON overlay (might not exist yet):', err);
    }

    return { data, EF, green, outreach };
  }

  window.loadDashboardData = loadDashboardData;
})();
