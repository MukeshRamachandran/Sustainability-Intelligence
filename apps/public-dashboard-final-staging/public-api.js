/* Single public sustainability API adapter. The dashboard consumes only the
   active immutable release returned here; missing values remain missing. */
(function () {
  'use strict';

  const ROUTE = '/api/public/dashboard';
  const HISTORY_ROUTE = '/api/public/dashboard/history';
  const TIMELINE_ROUTE = '/api/public/dashboard/timeline';

  function apiBase() {
    if (typeof window.KCOSMOS_API_BASE === 'string' && window.KCOSMOS_API_BASE.trim()) {
      return window.KCOSMOS_API_BASE.trim().replace(/\/$/, '');
    }
    return '';
  }

  function numberOrNull(value) {
    if (value === null || value === undefined || value === '') return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function metric(domain, code) {
    const item = domain?.metrics?.[code];
    const value = numberOrNull(item?.value);
    return {
      code,
      status: value === null ? 'unavailable' : 'available',
      value,
      unit: item?.unit || null
    };
  }

  function calculation(domain, code) {
    const candidates = Array.isArray(domain?.calculations) ? domain.calculations : [];
    const item = candidates.find(entry => entry?.calculation_code === code)
      || (code === 'lpg_emissions' ? domain?.emissions : null);
    const value = item?.status === 'available' ? numberOrNull(item.value ?? item.result_value) : null;
    return {
      code,
      status: value === null ? 'unavailable' : 'available',
      value,
      unit: item?.unit || item?.result_unit || null,
      reason: item?.reason || (value === null ? 'not_published' : null),
      activityValue: numberOrNull(item?.activity_value),
      activityUnit: item?.activity_unit || null,
      factorCode: item?.factor_code || null,
      factorValue: numberOrNull(item?.factor_value),
      factorUnit: item?.factor_unit || null,
      factorSetVersion: item?.factor_set_version || null,
      resultKgco2e: numberOrNull(item?.result_kgco2e),
      formulaVersion: item?.formula_version || null
    };
  }

  function indicator(payload, code) {
    const item = payload?.indicators?.[code];
    const value = item?.status === 'available' ? numberOrNull(item.value) : null;
    return {
      code,
      status: value === null ? 'unavailable' : 'available',
      value,
      unit: item?.unit || null,
      reason: item?.reason || (value === null ? 'not_published' : null)
    };
  }

  function normalize(payload) {
    const hasRelease = Boolean(payload?.release && payload?.period);
    return {
      state: hasRelease ? 'published' : 'no_publication',
      release: hasRelease ? {
        version: payload.release.version || null,
        publishedAt: payload.release.published_at || null,
        checksum: payload.release.checksum_sha256 || null,
        schemaVersion: payload.schema_version || null
      } : null,
      period: hasRelease ? {
        id: payload.period.id || null,
        year: numberOrNull(payload.period.year),
        month: numberOrNull(payload.period.month)
      } : null,
      publicationStatus: payload?.publication_status || {},
      indicators: payload?.indicators || {},
      population: payload?.population || null,
      domains: {
        transport: payload?.transport || null,
        energy: payload?.energy || null,
        lpg: payload?.lpg || null,
        water: payload?.water || null,
        outreach: payload?.outreach || null,
        // Present from schema 1.2 onward; null on older published releases,
        // which is reported as unavailable rather than fabricated.
        waste: payload?.waste || null
      },
      raw: payload
    };
  }

  async function load() {
    const url = apiBase() + ROUTE;
    try {
      const response = await fetch(url, { cache: 'no-store', credentials: 'omit' });
      if (!response.ok) throw new Error(`Public dashboard request failed (${response.status})`);
      return { ...normalize(await response.json()), url };
    } catch (error) {
      return {
        state: 'error', release: null, period: null, publicationStatus: {}, population: null,
        domains: { transport: null, energy: null, lpg: null, water: null, outreach: null, waste: null },
        raw: null, url, error: error instanceof Error ? error.message : String(error)
      };
    }
  }

  async function loadHistory() {
    const url = apiBase() + HISTORY_ROUTE;
    try {
      const response = await fetch(url, { cache: 'no-store', credentials: 'omit' });
      if (!response.ok) throw new Error(`Public dashboard history request failed (${response.status})`);
      const payload = await response.json();
      if (!Array.isArray(payload)) throw new Error('Public dashboard history response is invalid');
      return { state: 'published', releases: payload.map(normalize).filter(item => item.state === 'published'), url };
    } catch (error) {
      return {
        state: 'error', releases: [], url,
        error: error instanceof Error ? error.message : String(error)
      };
    }
  }

  /* The public timeline: official published releases merged by the backend
     with verified historical records. Granularity, coverage and provenance
     come from the API; the browser never recomputes them. */
  async function loadTimeline() {
    const url = apiBase() + TIMELINE_ROUTE;
    try {
      const response = await fetch(url, { cache: 'no-store', credentials: 'omit' });
      if (!response.ok) throw new Error(`Public timeline request failed (${response.status})`);
      const payload = await response.json();
      if (!payload || typeof payload.periods !== 'object' || !Array.isArray(payload.selector)) {
        throw new Error('Public timeline response is invalid');
      }
      return { state: 'loaded', ...payload, url };
    } catch (error) {
      return {
        state: 'error', default_key: null, selector: [], periods: {}, labels: {}, static_references: {}, url,
        error: error instanceof Error ? error.message : String(error)
      };
    }
  }

  window.KCOSMOSPublicAPI = Object.freeze({
    load, loadHistory, loadTimeline, metric, calculation, indicator, numberOrNull,
    route: ROUTE, historyRoute: HISTORY_ROUTE, timelineRoute: TIMELINE_ROUTE
  });
})();
