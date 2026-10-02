/* API-authoritative staging loader.

   Every sustainability value comes from GET /api/public/dashboard/timeline:
   official published releases merged by the backend with verified historical
   records from PostgreSQL. The browser never reads operational CSVs and never
   recomputes an official figure.

   Granularity is preserved: a month's arrays hold only that month's genuine
   values; Full Year / YTD figures are the backend's aggregates (with their
   coverage), attached to each array as `.aggregate`; annual-only or YTD-only
   records are never placed into a month. Green cover remains static
   institutional presentation data (green_master.csv). */
(function () {
  'use strict';
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  /* Dashboard array name -> timeline value code. */
  const SERIES = {
    petrolL: 'transport_petrol_litres', trDieselL: 'transport_diesel_litres', dgL: 'dg_diesel_litres',
    // DG generation (kWh) is the source activity from the governed SFC's effective
    // date; dg_diesel_litres is then the backend-derived quantity (0015).
    dgKwh: 'dg_generation_kwh',
    // Governed LPG activity is weight in kg (0013_lpg_kg_governance_v2).
    lpgKg: 'lpg_weight_kg',
    petrolEm: 'transport_petrol_emissions', trDieselEm: 'transport_diesel_emissions', dgEm: 'dg_diesel_emissions',
    lpgEm: 'lpg_emissions',
    htKwh: 'grid_ht_kwh', commKwh: 'grid_commercial_kwh', tempKwh: 'grid_temporary_kwh', elecKwh: 'grid_total_kwh',
    elecEm: 'scope2_tco2e',
    reOnCampusKwh: 'renewable_on_campus_kwh', reProcuredKwh: 'renewable_procured_kwh',
    solarWaterHeaterKwh: 'solar_water_heater_kwh',
    reKwh: 'renewable_electricity_kwh', totalElectricityKwh: 'total_electricity_consumption_kwh',
    renewableSharePct: 'renewable_share_pct', avoidEm: 'estimated_avoided_grid_emissions_tco2e',
    scope1Full: 'scope1_tco2e', scope1Selected: 'scope1_tco2e', operationalGHG: 'operational_ghg_tco2e',
    perCapita: 'operational_ghg_per_capita_kgco2e',
    waterKL: 'water_consumed_kl', waterTWAD: 'water_twad_kl', waterBorewell: 'water_borewell_kl',
    waterProcured: 'water_private_kl', wastewaterKL: 'wastewater_generated_kl', waterRecycledKL: 'water_recycled_kl',
    waterPerCapitaL: 'water_per_capita_l',
    wetWaste: 'wet_waste_generated_kg', dryWaste: 'dry_waste_generated_kg', totalWaste: 'total_waste_generated_kg',
    wastePerCapita: 'waste_per_capita_kg'
  };
  const FACTOR_SERIES = {
    petrolEF: 'transport_petrol_emissions', trDieselEF: 'transport_diesel_emissions', dgEF: 'dg_diesel_emissions',
    gridEF: 'grid_electricity_emissions', lpgEF: 'lpg_emissions'
  };
  const OUTREACH_FIELDS = {
    programsDelivered: 'total_programs', participantsServed: 'total_participants',
    partnerOrganizations: 'partner_organizations', saplingsPlanted: 'saplings_planted',
    expertsInvolved: 'experts_involved', volunteersEngaged: 'volunteers_engaged', volunteerHours: 'volunteer_hours'
  };

  function num(value) {
    if (value === null || value === undefined) return null;
    const normalized = String(value).trim().replace(/,/g, '');
    if (!normalized || normalized.toLowerCase() === 'null' || normalized === '-') return null;
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function tokenizeCSV(text) {
    const rows = []; let row = [], cell = '', quoted = false;
    for (let i = 0; i < text.length; i++) {
      const char = text[i], next = text[i + 1];
      if (char === '"' && quoted && next === '"') { cell += '"'; i++; continue; }
      if (char === '"') { quoted = !quoted; continue; }
      if (char === ',' && !quoted) { row.push(cell); cell = ''; continue; }
      if ((char === '\n' || char === '\r') && !quoted) {
        if (char === '\r' && next === '\n') i++;
        row.push(cell); cell = '';
        if (row.some(item => String(item).trim())) rows.push(row);
        row = []; continue;
      }
      cell += char;
    }
    row.push(cell);
    if (row.some(item => String(item).trim())) rows.push(row);
    return rows;
  }

  async function optionalText(path) {
    try {
      const response = await fetch(`${path}?v=${Date.now()}`, { cache: 'no-store' });
      return response.ok ? response.text() : '';
    } catch (_) { return ''; }
  }

  function emptyYear(year) {
    const item = {
      year: Number(year), label: String(year), frequency: 'ytd', population: null,
      aggregateKey: null, aggregateEndMonth: null, aggregateGranularity: null,
      monthKeys: Array(12).fill(null), periodMeta: { all: null }, domainStatus: { all: {} }, secondary: {},
      // What each period's KPI cards SHOW (backend display items, incl. labelled
      // annual/YTD/static context). Never used for charts, exports or sums.
      display: { all: {} },
      publishedMonths: Array(12).fill(false), wastePublishedMonths: Array(12).fill(false),
      wasteBreakdownByMonth: Array(12).fill(null), wasteBreakdownAggregate: [],
      // Waste is a year-aggregate domain: every selection inside a year
      // resolves to that year's current Full Year / YTD waste (see wasteYearFrom).
      wasteYear: { all: null },
      landfillDiversionPct: null, waterTWADAnnual: null, waterBorewellAnnual: null, waterTotalAnnual: null,
      totalGHG: null, avoided: null, reShare: null,
      petrolVehicleCount: null, dieselVehicleCount: null, evConsumptionKwh: null, dgCount: null
    };
    // Arrays the charts no longer draw from are kept empty rather than faked.
    ['htEm', 'commEm', 'tempEm', 'grossSelected', 'grossFull']
      .concat(Object.keys(SERIES), Object.keys(FACTOR_SERIES))
      .forEach(name => {
        const series = Array(12).fill(null);
        series.aggregate = null;
        series.aggregateCoverage = null;
        series.aggregateMonths = [];
        item[name] = series;
      });
    return item;
  }

  function valueOf(period, code) {
    const item = period?.values?.[code];
    return item && item.status === 'available' ? num(item.value) : null;
  }

  function factorOf(period, code) {
    return num(period?.values?.[code]?.provenance?.factor_value);
  }

  function materials(period, labels) {
    return Object.entries(period?.values || {})
      .filter(([code, item]) => code.startsWith('material:') && item.status === 'available')
      .map(([code, item]) => ({ name: labels[code] || code.slice('material:'.length), value: num(item.value) }))
      .filter(row => row.value !== null);
  }

  /* The year's current Waste aggregate as the backend resolved it for this
     selection (its display items): a month does not filter waste, so a month
     and the year's Full Year / YTD view carry the same figures. Wet, dry and
     every material:* value are read as published - nothing is summed here, and
     a material the backend does not report is simply absent. */
  function wasteYearFrom(period, labels) {
    const display = period?.display || {};
    const shown = code => (display[code] && display[code].value != null ? display[code] : null);
    const context = ['total_waste_generated_kg', 'dry_waste_generated_kg', 'wet_waste_generated_kg'].map(shown).find(Boolean);
    return {
      label: context ? context.display_label : null,
      wet: shown('wet_waste_generated_kg') ? num(display.wet_waste_generated_kg.value) : null,
      dry: shown('dry_waste_generated_kg') ? num(display.dry_waste_generated_kg.value) : null,
      materials: Object.keys(display)
        .filter(code => code.startsWith('material:') && shown(code))
        .map(code => ({ code, name: labels[code] || code.slice('material:'.length), value: num(display[code].value) }))
        .filter(row => row.value !== null)
        .sort((a, b) => b.value - a.value || a.name.localeCompare(b.name))
    };
  }

  function outreachFrom(period, year, month) {
    const empty = {
      programsDelivered: null, participantsServed: null, partnerOrganizations: null, saplingsPlanted: null,
      expertsInvolved: null, volunteersEngaged: null, volunteerHours: null, audienceReach: [], thematicAreas: [],
      qualifiers: {}, published: false, year, month
    };
    if (!period || period.domains?.outreach?.state !== 'available') return empty;
    const result = { ...empty, published: true };
    Object.entries(OUTREACH_FIELDS).forEach(([field, code]) => {
      result[field] = valueOf(period, code);
      result.qualifiers[field] = period.values?.[code]?.qualifier || 'EXACT';
    });
    Object.entries(period.values || {}).forEach(([code, item]) => {
      if (item.status !== 'available') return;
      // Each slice keeps the unit the backend reports: theme counts are
      // programmes; audience values are people for Manager programme data but a
      // plain source count for a historical table that is not participant reach.
      if (code.startsWith('theme:')) result.thematicAreas.push({ category: code.slice(6), programs: num(item.value), unit: item.unit });
      if (code.startsWith('audience:')) result.audienceReach.push({ category: code.slice(9), reach: num(item.value), unit: item.unit });
    });
    const unitOf = rows => { const units = [...new Set(rows.map(row => row.unit))]; return units.length === 1 ? units[0] : null; };
    result.audienceUnit = unitOf(result.audienceReach);
    result.thematicUnit = unitOf(result.thematicAreas);
    // The coverage the backend states for this outreach record ("2026 YTD · through 17 Aug 2026").
    result.coverageLabel = period.display?.total_participants?.display_label
      || period.values?.total_participants?.coverage_label || period.label || null;
    return result;
  }

  /* "LPG 2.332744 tCO2e; Grid electricity 32.944005 tCO2e" - the backend's own
     contributor list for a calculated GHG value (a contributor that covers only
     some months of a Full Year / YTD window says so). */
  function contributorsText(parts) {
    return (parts || []).map(part => {
      const missing = (part.months_missing || []).length, covered = (part.months_covered || []).length;
      const coverage = missing ? ` (${covered} of ${covered + missing} months)` : '';
      return `${part.label} ${part.value} ${part.unit}${coverage}`;
    }).join('; ');
  }
  function missingText(parts) {
    return (parts || []).map(part => part.label).join('; ');
  }

  /* One flat, semantics-preserving row per published value for the Data Explorer. */
  function explorerRows(timeline) {
    const rows = [];
    Object.values(timeline.periods || {}).forEach(period => {
      Object.values(period.values || {}).forEach(item => {
        if (item.status !== 'available') return;
        // A confirmed "<year> / to date" figure has no stated end month: it
        // carries its own label and never borrows the period's date range.
        // ...unless it is a cumulative baseline, whose exact coverage dates are
        // stated here (the audit view) even though cards just say "2026 YTD".
        const baselineEnd = item.provenance?.baseline_coverage_end;
        const added = item.provenance?.months_added || [];
        // A year aggregate built only from published months states its window.
        const window = !baselineEnd && item.provenance?.coverage_end
          ? `${item.coverage_label} · ${item.provenance.coverage_start} – ${item.provenance.coverage_end}` : null;
        const coverage = window || (item.coverage_label
          ? (baselineEnd
            ? `${item.coverage_label} · baseline ${item.provenance.baseline_coverage_start} – ${baselineEnd}${added.length ? ` + ${added.join(', ')}` : ''}`
            : `${item.coverage_label}, end month not stated`)
          : (item.months_covered && item.months_covered.length
            ? `${item.months_covered.length} month(s): ${item.months_covered[0]}…${item.months_covered[item.months_covered.length - 1]}`
            : `${period.coverage_start} – ${period.coverage_end}`));
        // A value the backend derived from another source value (DG litres from
        // kWh) is DERIVED, and the governed parameter it used gets its own row.
        const derivation = item.provenance?.derivation;
        const derived = derivation && derivation.derived_metric_code === item.code;
        if (derived) {
          rows.push([
            String(period.year), period.label, item.granularity || period.granularity, item.domain,
            derivation.parameter_code, num(derivation.parameter_value), derivation.parameter_unit,
            'governed_parameter', `effective from ${derivation.parameter_effective_from}`, 'GOVERNED_PARAMETER',
            '', '', '', ''
          ]);
        }
        rows.push([
          String(period.year), period.label, item.granularity || period.granularity, item.domain,
          (timeline.labels || {})[item.code] || item.code, num(item.value), item.unit,
          item.source_kind, item.coverage_label ? coverage : `${coverage} (${item.coverage_status})`,
          derived ? 'DERIVED'
            : item.provenance?.verification_status || (item.kind === 'calculation' ? 'CALCULATED' : 'PUBLISHED'),
          item.qualifier === 'AT_LEAST' ? 'at least' : (item.qualifier === 'APPROXIMATE' ? 'approximate' : ''),
          // Calculated GHG values: COMPLETE / PARTIAL, what produced them and what is missing.
          item.calculation_status || '', contributorsText(item.contributors), missingText(item.missing_contributors)
        ]);
      });
    });
    return rows.sort((a, b) => a[0].localeCompare(b[0]) || String(a[1]).localeCompare(String(b[1])));
  }

  function buildData(timeline) {
    const data = {};
    const labels = timeline.labels || {};
    const landfill = num(timeline.static_references?.landfill_diversion_pct?.value);
    const outreachByKey = {};
    const outreachAlias = {};
    (timeline.selector || []).forEach(({ year, options }) => {
      const item = emptyYear(year);
      item.landfillDiversionPct = landfill;
      data[String(year)] = item;
      options.forEach(option => {
        const period = timeline.periods[option.key];
        if (!period) return;
        if (option.granularity === 'MONTHLY') {
          const index = period.month - 1;
          item.monthKeys[index] = option.key;
          item.periodMeta[index] = period;
          item.domainStatus[index] = period.domains || {};
          item.display[index] = period.display || {};
          item.publishedMonths[index] = true;
          item.wastePublishedMonths[index] = period.domains?.waste?.state === 'available';
          Object.entries(SERIES).forEach(([name, code]) => { item[name][index] = valueOf(period, code); });
          Object.entries(FACTOR_SERIES).forEach(([name, code]) => { item[name][index] = factorOf(period, code); });
          item.wasteBreakdownByMonth[index] = materials(period, labels);
          item.wasteYear[index] = wasteYearFrom(period, labels);
          outreachByKey[option.key] = outreachFrom(period, year, period.month);
          // A year whose outreach is one running year-to-date dataset: the
          // backend points every month at the year's YTD record, so selecting
          // a month does not filter outreach. Other domains are unaffected.
          if (period.domains?.outreach?.state === 'year_to_date' && period.domains.outreach.alternative_key) {
            outreachAlias[option.key] = period.domains.outreach.alternative_key;
          }
        } else {
          // The first aggregate option is the year's primary Full Year / YTD view;
          // any further one (e.g. an annual-only source record in a year that has
          // a partial-year YTD) gets its own dataset, reachable as 'agg:<key>'.
          const target = item.aggregateKey ? emptyYear(year) : item;
          if (target !== item) {
            target.landfillDiversionPct = landfill;
            item.secondary[option.key] = target;
          }
          applyAggregate(target, option, period);
          outreachByKey[option.key] = outreachFrom(period, year, null);
        }
      });
    });
    return { data, outreachByKey, outreachAlias };

    function applyAggregate(item, option, period) {
      item.aggregateKey = option.key;
      item.aggregateGranularity = period.granularity;
      item.aggregateEndMonth = Number(String(period.coverage_end).slice(5, 7));
      item.frequency = period.granularity === 'ANNUAL' ? 'annual' : 'ytd';
      item.label = period.label;
      item.periodMeta.all = period;
      item.domainStatus.all = period.domains || {};
      item.display.all = period.display || {};
      item.population = num(period.population?.value);
      Object.entries(SERIES).forEach(([name, code]) => {
        const value = period.values?.[code];
        item[name].aggregate = valueOf(period, code);
        item[name].aggregateCoverage = value?.status === 'available' ? value.coverage_status : null;
        item[name].aggregateMonths = value?.months_covered || [];
      });
      Object.entries(FACTOR_SERIES).forEach(([name, code]) => { item[name].aggregate = factorOf(period, code); });
      const annual = code => (period.values?.[code]?.granularity === 'ANNUAL' ? valueOf(period, code) : null);
      item.waterTWADAnnual = annual('water_twad_kl');
      item.waterBorewellAnnual = annual('water_borewell_kl');
      item.wasteBreakdownAggregate = materials(period, labels);
      item.wasteYear.all = wasteYearFrom(period, labels);
    }
  }

  function staticGreen(text) {
    const green = {
      totalTrees: null, totalSpecies: null, campusAreaAcres: null, totalGreenCoverPct: null,
      maintainedVegetationAcres: null, naturalVegetationAcres: null, zones: [], speciesList: [], phenology: []
    };
    let section = null;
    tokenizeCSV(text).forEach(row => {
      const first = String(row[0] || '').trim();
      if (first === 'Green Cover Summary') { section = 'summary'; return; }
      if (first === 'Zone-wise Tree and Species Distribution') { section = 'zones'; return; }
      if (first === 'Species List') { section = 'species'; return; }
      if (first.startsWith('Species Phenology')) { section = 'phenology'; return; }
      if (!first || ['Metric', 'Zone', 'Species'].includes(first) || (first === 'Scientific Name' && section === 'species')) return;
      const value = num(row[1]);
      if (section === 'summary') {
        if (first === 'Total trees') green.totalTrees = value;
        else if (first === 'Total tree species identified') green.totalSpecies = value;
        else if (first === 'Campus area') green.campusAreaAcres = value;
        else if (first === 'Total green cover') green.totalGreenCoverPct = value;
        else if (first === 'Maintained vegetation') green.maintainedVegetationAcres = value;
        else if (first === 'Natural vegetation') green.naturalVegetationAcres = value;
      } else if (section === 'zones') green.zones.push({ zone: first, trees: value || 0, species: num(row[2]) || 0 });
      else if (section === 'species') green.speciesList.push({ scientific: first, common: String(row[1] || '').trim() });
      else if (section === 'phenology') green.phenology.push({ species: first, period: String(row[1] || '').trim() });
    });
    return green;
  }

  async function loadDashboardData() {
    const [timeline, greenText] = await Promise.all([
      window.KCOSMOSPublicAPI.loadTimeline(), optionalText('data/green_master.csv')
    ]);
    const { data, outreachByKey, outreachAlias } = buildData(timeline);
    // No timeline (API unreachable): one empty year so every card reads "unavailable".
    const selector = timeline.selector && timeline.selector.length
      ? timeline.selector : [{ year: new Date().getFullYear(), options: [] }];
    selector.forEach(({ year }) => { if (!data[String(year)]) data[String(year)] = emptyYear(year); });
    const emptyOutreach = outreachFrom(null, null, null);
    return {
      data,
      timeline,
      selector,
      defaultKey: timeline.default_key,
      green: staticGreen(greenText),
      outreachFor(year, month) {
        const item = data[String(year)];
        if (!item) return emptyOutreach;
        const key = String(month).startsWith('agg:') ? String(month).slice(4)
          : (month === 'all' ? item.aggregateKey : item.monthKeys[+month]);
        const resolved = (key && outreachAlias[key]) || key;
        return (resolved && outreachByKey[resolved]) || { ...emptyOutreach, year: Number(year) };
      },
      explorerRows: explorerRows(timeline),
      // Kept for callers that still read the publication state line.
      publication: { state: timeline.state === 'loaded' ? 'published' : 'error', release: null, period: null }
    };
  }

  window.loadDashboardData = loadDashboardData;
  window.KCOSMOSMonths = MONTHS;
})();
