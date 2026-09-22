/* API-authoritative staging loader. Governed operational domains come only
   from public-api.js. Waste, green cover, population and labels remain
   clearly separated static institutional presentation data. */
(function () {
  'use strict';
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

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

  function parseCSV(text) {
    const rows = tokenizeCSV(text);
    if (!rows.length) return [];
    const headers = rows.shift().map(value => value.trim());
    return rows.map(row => Object.fromEntries(headers.map((header, index) => [header, (row[index] || '').trim()])));
  }

  async function optionalText(path) {
    try {
      const response = await fetch(`${path}?v=${Date.now()}`, { cache: 'no-store' });
      return response.ok ? response.text() : '';
    } catch (_) { return ''; }
  }

  function emptyYear(year) {
    const empty = () => Array(12).fill(null);
    return {
      year: Number(year), label: `${year} Published snapshot`, frequency: 'ytd', population: null,
      publicationState: 'unavailable', totalGHG: null, totalEnergy: null, gridEnergy: null,
      reEnergy: null, reShare: null, avoided: null, perCapita: null,
      petrolL: empty(), trDieselL: empty(), dgL: empty(), lpgKg: empty(),
      petrolEm: empty(), trDieselEm: empty(), dgEm: empty(), lpgEm: empty(),
      dieselCombo: empty(), scope1Selected: empty(), scope1Full: empty(),
      htKwh: empty(), commKwh: empty(), tempKwh: empty(), elecKwh: empty(),
      htEm: empty(), commEm: empty(), tempEm: empty(), elecEm: empty(),
      reKwh: empty(), reOnCampusKwh: empty(), reProcuredKwh: empty(), avoidEm: empty(),
      solarWaterHeaterKwh: null, wetWaste: null, dryWaste: null, totalWaste: null, wasteBreakdown: [],
      waterKL: empty(), waterTWAD: empty(), waterBorewell: empty(), waterProcured: empty(),
      waterRecycledKL: null, waterTWADAnnual: null, waterBorewellAnnual: null, waterTotalAnnual: null,
      grossSelected: empty(), grossFull: empty(), petrolVehicleCount: null, dieselVehicleCount: null,
      evConsumptionKwh: null, dgCount: null
    };
  }

  function ensureYear(store, year) {
    const key = String(year);
    if (!store[key]) store[key] = emptyYear(key);
    return store[key];
  }

  function setMetric(target, index, domain, code) {
    const metric = window.KCOSMOSPublicAPI.metric(domain, code);
    target[index] = metric.status === 'available' ? metric.value : null;
    return metric.value;
  }

  function setCalculation(target, index, domain, code) {
    const calculation = window.KCOSMOSPublicAPI.calculation(domain, code);
    target[index] = calculation.status === 'available' ? calculation.value : null;
    return calculation;
  }

  function applyPublication(publication, data) {
    if (publication.state !== 'published') return;
    const item = ensureYear(data, publication.period.year);
    const month = Math.max(0, Math.min(11, publication.period.month - 1));
    item.publicationState = 'published';
    item.label = `${MONTHS[month]} ${publication.period.year} · Published ${publication.release.version || 'release'}`;
    const { transport, energy, lpg, water } = publication.domains;
    setMetric(item.petrolL, month, transport, 'transport_petrol_litres');
    setMetric(item.trDieselL, month, transport, 'transport_diesel_litres');
    setMetric(item.dgL, month, transport, 'dg_diesel_litres');
    setCalculation(item.petrolEm, month, transport, 'transport_petrol_emissions');
    setCalculation(item.trDieselEm, month, transport, 'transport_diesel_emissions');
    setCalculation(item.dgEm, month, transport, 'dg_diesel_emissions');
    item.petrolVehicleCount = window.KCOSMOSPublicAPI.metric(transport, 'petrol_vehicle_count').value;
    item.dieselVehicleCount = window.KCOSMOSPublicAPI.metric(transport, 'diesel_vehicle_count').value;
    item.evConsumptionKwh = window.KCOSMOSPublicAPI.metric(transport, 'ev_consumption_kwh').value;
    item.dgCount = window.KCOSMOSPublicAPI.metric(transport, 'dg_count').value;
    setMetric(item.htKwh, month, energy, 'grid_ht_kwh');
    setMetric(item.commKwh, month, energy, 'grid_commercial_kwh');
    setMetric(item.tempKwh, month, energy, 'grid_temporary_kwh');
    setMetric(item.elecKwh, month, energy, 'grid_total_kwh');
    item.gridEnergy = item.elecKwh[month];
    setCalculation(item.elecEm, month, energy, 'grid_electricity_emissions');
    setMetric(item.reOnCampusKwh, month, energy, 'renewable_on_campus_kwh');
    setMetric(item.reProcuredKwh, month, energy, 'renewable_procured_kwh');
    setMetric(item.reKwh, month, energy, 'renewable_total_kwh');
    item.reEnergy = item.reKwh[month];
    setMetric(item.lpgKg, month, lpg, 'lpg_weight_kg');
    setCalculation(item.lpgEm, month, lpg, 'lpg_emissions');
    setMetric(item.waterKL, month, water, 'water_consumed_kl');
    item.waterRecycledKL = window.KCOSMOSPublicAPI.metric(water, 'water_recycled_kl').value;
    item.totalGHG = window.KCOSMOSPublicAPI.indicator(publication.raw, 'total_ghg_tco2e').value;
    item.avoided = window.KCOSMOSPublicAPI.indicator(publication.raw, 'avoided_emissions_tco2e').value;
    item.reShare = window.KCOSMOSPublicAPI.indicator(publication.raw, 'renewable_share_percent').value;
  }

  function staticWaste(text, data) {
    const rows = tokenizeCSV(text);
    const years = rows.find(row => String(row[0]).trim().toLowerCase() === 'year');
    if (!years) return;
    for (let column = 1; column < years.length; column++) {
      const year = String(years[column]).trim();
      if (!year) continue;
      const item = ensureYear(data, year);
      rows.forEach(row => {
        const key = String(row[0]).trim().toLowerCase();
        const value = num(row[column]);
        if (value === null) return;
        if (key.includes('wet waste')) item.wetWaste = (item.wetWaste || 0) + value;
        else if (key.includes('dry waste')) item.dryWaste = (item.dryWaste || 0) + value;
        else if (key.includes('total waste approximate')) item.totalWaste = (item.totalWaste || 0) + value;
        else if (!['', 'total', 'item', 'year', 'waste inventory'].includes(key)) {
          item.wasteBreakdown.push({ name: String(row[0]).trim(), value });
        }
      });
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

  function outreachFrom(domain, publication) {
    if (!domain || publication.state !== 'published') return {
      programsDelivered: null, participantsServed: null, partnerOrganizations: null,
      saplingsPlanted: null, expertsInvolved: null, volunteersEngaged: null, volunteerHours: null,
      audienceReach: [], thematicAreas: [], gender: { available: false }, published: false
    };
    return {
      programsDelivered: num(domain.total_programs), participantsServed: num(domain.total_participants),
      partnerOrganizations: num(domain.partner_organizations), saplingsPlanted: num(domain.saplings_planted),
      expertsInvolved: num(domain.experts_involved), volunteersEngaged: num(domain.volunteers_engaged),
      volunteerHours: num(domain.volunteer_hours),
      audienceReach: Object.entries(domain.participants_by_category || {}).map(([category, reach]) => ({ category, reach: num(reach) })),
      thematicAreas: Object.entries(domain.themes || {}).map(([category, programs]) => ({ category, programs: num(programs) })),
      gender: domain.gender || { available: false }, year: publication.period.year, month: publication.period.month,
      published: true
    };
  }

  async function loadDashboardData() {
    const [publication, history, populationText, metadataText, wasteText, greenText] = await Promise.all([
      window.KCOSMOSPublicAPI.load(), window.KCOSMOSPublicAPI.loadHistory(), optionalText('data/population_master.csv'),
      optionalText('data/dashboard_metadata.csv'), optionalText('data/waste_master.csv'), optionalText('data/green_master.csv')
    ]);
    const data = {};
    parseCSV(metadataText).forEach(row => {
      if (!row.year) return;
      const item = ensureYear(data, row.year);
      item.label = row.label || item.label;
    });
    parseCSV(populationText).forEach(row => { if (row.year) ensureYear(data, row.year).population = num(row.population); });
    staticWaste(wasteText, data);

    const fallbackYear = publication.period?.year || new Date().getFullYear();
    const item = ensureYear(data, fallbackYear);
    item.publicationState = publication.state;
    const releases = history.releases.length ? history.releases : (publication.state === 'published' ? [publication] : []);
    releases.forEach(release => applyPublication(release, data));
    if (publication.state === 'published') applyPublication(publication, data);

    const petrol = window.KCOSMOSPublicAPI.calculation(publication.domains.transport, 'transport_petrol_emissions');
    const diesel = window.KCOSMOSPublicAPI.calculation(publication.domains.transport, 'transport_diesel_emissions');
    const grid = window.KCOSMOSPublicAPI.calculation(publication.domains.energy, 'grid_electricity_emissions');
    const lpg = window.KCOSMOSPublicAPI.calculation(publication.domains.lpg, 'lpg_emissions');

    return {
      data, EF: {
        petrol: petrol.factorValue, diesel: diesel.factorValue,
        grid: grid.factorValue, lpg: lpg.factorValue
      },
      green: staticGreen(greenText), outreach: outreachFrom(publication.domains.outreach, publication),
      publication, history
    };
  }

  window.loadDashboardData = loadDashboardData;
})();
