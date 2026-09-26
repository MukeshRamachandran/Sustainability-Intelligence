/* =====================================================================
   MICROCOSM - LIVE WEATHER MONITORING (weather.js)
   Self-contained addon (same pattern as walkthrough.js/mobile.js): reads
   shared helpers already on the page (ic, colors, chartOptions, fmt,
   reduceMotion - all defined in app.js, which loads before this file)
   but app.js does not depend on anything in here.

   Talks to the separate Aeron Environment Dashboard backend through the
   same-origin /api/environment reverse-proxy path.
   If it isn't reachable, every widget here degrades to '--' and the
   status pill/dock dot switch to OFFLINE rather than erroring.
   ===================================================================== */
(function () {
  const API_BASE = '/api/environment';
  const POLL_MS = 20000;      // latest reading + status (drives the dock dot)
  const HISTORY_POLL_MS = 60000; // trend charts, only while the page is open

  let shellBuilt = false;
  let charts = {};
  let lastRecordedAt = null;
  let latestInFlight = false;
  let historyInFlight = false;

  const wnum = (v, d = 1) => (v == null || v === '' || isNaN(v)) ? '--' : Number(v).toFixed(d);

  /* ---- AQI severity band: color, label, and 0-100% position on the
     six-segment severity bar (segments are equal width, like the source
     station's own speedometer, so the mapping is piecewise not linear). */
  function aqiSeverity(aqi) {
    if (aqi == null || isNaN(aqi)) return { label: 'No data yet', color: 'var(--faint)', pct: 0 };
    const v = +aqi, seg = 100 / 6;
    if (v <= 50) return { label: 'Good', color: '#10b981', pct: (v / 50) * seg };
    if (v <= 100) return { label: 'Moderate', color: '#facc15', pct: seg + ((v - 50) / 50) * seg };
    if (v <= 150) return { label: 'Unhealthy for Sensitive Groups', color: '#f97316', pct: seg * 2 + ((v - 100) / 50) * seg };
    if (v <= 200) return { label: 'Unhealthy', color: '#ef4444', pct: seg * 3 + ((v - 150) / 50) * seg };
    if (v <= 300) return { label: 'Very Unhealthy', color: '#a855f7', pct: seg * 4 + ((v - 200) / 100) * seg };
    return { label: 'Hazardous', color: '#9f1239', pct: seg * 5 + (Math.min(v - 300, 200) / 200) * seg };
  }

  /* LIVE < 10 min old, STALE 10-30 min, OFFLINE beyond that or no reading at all.
     The server classifies against its own clock; the local fallback only
     applies if an older API response lacks `freshness`. */
  function computeStatus(data) {
    if (!data || !data.recorded_at) return 'offline';
    if (data.freshness) return String(data.freshness).toLowerCase();
    const ageSec = (Date.now() - new Date(data.recorded_at).getTime()) / 1000;
    if (ageSec > 30 * 60) return 'offline';
    if (ageSec >= 10 * 60) return 'stale';
    return 'live';
  }

  function relativeAge(recordedAtISO) {
    if (!recordedAtISO) return null;
    const secs = Math.floor((Date.now() - new Date(recordedAtISO).getTime()) / 1000);
    if (secs < 0) return 'just now';
    if (secs < 60) return `${secs}s ago`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
    return `${Math.floor(secs / 3600)}h ago`;
  }

  async function fetchJson(path) {
    try {
      const res = await fetch(`${API_BASE}${path}`, { cache: 'no-store', credentials: 'omit' });
      if (!res.ok) {
        console.warn(`[weather] ${path} responded ${res.status}`);
        return null;
      }
      return await res.json();
    } catch (error) {
      console.warn(`[weather] could not reach ${API_BASE}${path}`, error);
      return null;
    }
  }
  const fetchLatest = () => fetchJson('/latest');
  const fetchHistory = (limit) => fetchJson(`/history?limit=${limit}`);

  /* ---- nav dock dot: reflects connectivity regardless of which page is open ---- */
  function updateNavDot(status) {
    const dot = document.getElementById('weatherNavDot');
    if (!dot) return;
    dot.classList.remove('live', 'stale', 'offline');
    dot.classList.add(status);
  }

  function updateStatusPill(status, recordedAtISO) {
    const pill = document.getElementById('weatherStatusPill');
    const text = document.getElementById('weatherStatusText');
    const foot = document.getElementById('weatherUpdatedText');
    if (pill) pill.className = 'weather-status-pill ' + status;
    if (text) text.textContent = status === 'live' ? 'LIVE' : status === 'stale' ? 'STALE' : 'OFFLINE';
    if (foot) {
      if (status === 'offline' && !recordedAtISO) {
        foot.textContent = 'Environmental readings are temporarily unavailable.';
      } else {
        const age = relativeAge(recordedAtISO);
        foot.textContent = age ? `Reading captured ${age}${status === 'stale' ? ' — station may be offline' : ''}` : '—';
      }
    }
  }

  function animateNumber(id, target, dec) {
    const el = document.getElementById(id);
    if (!el) return;
    if (target == null || isNaN(target)) { el.textContent = '--'; return; }
    if (typeof gsap === 'undefined' || (typeof reduceMotion !== 'undefined' && reduceMotion)) {
      el.textContent = Number(target).toFixed(dec);
      return;
    }
    const start = parseFloat(el.textContent);
    const obj = { val: isNaN(start) ? 0 : start };
    gsap.to(obj, {
      val: target, duration: 1, ease: 'power2.out',
      onUpdate: () => { el.textContent = obj.val.toFixed(dec); },
      onComplete: () => { el.textContent = Number(target).toFixed(dec); }
    });
  }

  /* ---- static shell: built once, values updated in place afterwards
     so a poll never interrupts an in-flight number animation or a hover
     state. Reuses the site's own .kpi / .highlight / .strip components. */
  function statCard(title, id, unit, accent, icon) {
    return `<article class="kpi" style="--a:${accent}">
      <div class="icon">${ic(icon)}</div>
      <div class="label">${title}</div>
      <div class="value"><span id="${id}">--</span><small>${unit}</small></div>
    </article>`;
  }
  function pollutantTile(label, id, unit) {
    return `<div class="highlight"><b><span id="${id}">--</span> <span style="font-size:12px;font-weight:600;color:var(--muted);">${unit}</span></b><span>${label}</span></div>`;
  }
  function statusRow(label, id) {
    return `<div style="display:flex;justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:8px;font-size:13px;">
      <span style="color:var(--muted);">${label}</span><span style="font-weight:600;color:var(--ink);" id="${id}">--</span></div>`;
  }

  function buildShell() {
    if (shellBuilt) return;
    const hero = document.getElementById('weatherHero');
    const kpis = document.getElementById('weatherKpis');
    const kpis2 = document.getElementById('weatherKpis2');
    const pollutants = document.getElementById('weatherPollutants');
    const station = document.getElementById('weatherStation');
    const noise = document.getElementById('weatherNoise');
    if (!hero || !kpis || !kpis2 || !pollutants || !station || !noise) return;

    hero.innerHTML = `
      <style>
        .weather-hero{background:var(--surface);border:1px solid var(--line);border-radius:20px;padding:22px 26px;margin:14px 0 20px;box-shadow:var(--shadow);}
        .weather-hero-top{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:14px;}
        .weather-hero-title{display:flex;align-items:center;gap:8px;font-weight:700;font-size:14px;color:var(--ink);opacity:.8;margin-bottom:8px;}
        .weather-hero-title .icon{width:18px;height:18px;}
        .weather-aqi-row{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;}
        .weather-aqi-value{font-family:'IBM Plex Mono';font-size:clamp(36px,5vw,52px);font-weight:700;color:var(--weather-aqi-color,var(--ink));line-height:1;}
        .weather-aqi-label{font-size:15px;font-weight:700;color:var(--weather-aqi-color,var(--muted));}
        .weather-status-pill{display:inline-flex;align-items:center;gap:7px;padding:6px 12px;border-radius:99px;background:var(--surface2);border:1px solid var(--line);font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);white-space:nowrap;}
        .weather-status-dot{width:8px;height:8px;border-radius:50%;background:var(--faint);flex:none;}
        .weather-status-pill.live .weather-status-dot{background:#10b981;animation:navDotPulseLive 1.8s ease-in-out infinite;}
        .weather-status-pill.stale .weather-status-dot{background:#f59e0b;animation:navDotPulseStale 2.6s ease-in-out infinite;}
        .weather-status-pill.offline .weather-status-dot{background:#ef4444;}
        .weather-severity-bar{position:relative;height:10px;border-radius:99px;margin-top:20px;background:linear-gradient(90deg,#10b981 0%,#10b981 16.6%,#facc15 16.6%,#facc15 33.3%,#f97316 33.3%,#f97316 50%,#ef4444 50%,#ef4444 66.6%,#a855f7 66.6%,#a855f7 83.3%,#9f1239 83.3%,#9f1239 100%);}
        .weather-severity-marker{position:absolute;top:-4px;width:4px;height:18px;border-radius:2px;background:var(--ink);box-shadow:0 0 0 2px var(--surface);transform:translateX(-50%);transition:left 1s cubic-bezier(.25,1,.5,1);left:0%;}
        .weather-severity-labels{display:flex;justify-content:space-between;font-size:9.5px;color:var(--faint);margin-top:6px;font-weight:600;text-transform:uppercase;letter-spacing:.02em;}
        .weather-hero-foot{font-size:12px;color:var(--faint);margin-top:14px;}
      </style>
      <div class="weather-hero">
        <div class="weather-hero-top">
          <div>
            <div class="weather-hero-title">${ic('gauge')} Air Quality Index</div>
            <div class="weather-aqi-row">
              <span class="weather-aqi-value" id="weatherAqiVal">--</span>
              <span class="weather-aqi-label" id="weatherAqiLabel">Gathering data…</span>
            </div>
          </div>
          <div class="weather-status-pill" id="weatherStatusPill"><span class="weather-status-dot"></span><span id="weatherStatusText">CONNECTING</span></div>
        </div>
        <div class="weather-severity-bar"><div class="weather-severity-marker" id="weatherAqiMarker"></div></div>
        <div class="weather-severity-labels"><span>Good</span><span>Moderate</span><span>USG</span><span>Unhealthy</span><span>V. Unhealthy</span><span>Hazardous</span></div>
        <div class="weather-hero-foot" id="weatherUpdatedText">Waiting for first reading…</div>
      </div>`;

    kpis.innerHTML = [
      statCard('Temperature', 'wx-temp', '°C', colors.gold, 'sun'),
      statCard('Humidity', 'wx-humidity', '%', colors.cyan, 'droplet'),
      statCard('PM2.5', 'wx-pm25', 'µg/m³', colors.violet, 'cloud'),
      statCard('PM10', 'wx-pm10', 'µg/m³', colors.teal, 'cloud')
    ].join('');

    kpis2.innerHTML = [
      statCard('Wind Speed', 'wx-wind', 'km/h', colors.emerald, 'wind'),
      statCard('Rain', 'wx-rain', 'mm', colors.cyan, 'rain'),
      statCard('UV Index', 'wx-uv', '', colors.gold, 'shield'),
      statCard('Barometric Pressure', 'wx-pressure', 'mba', '#7b8794', 'gauge')
    ].join('');

    pollutants.innerHTML = [
      pollutantTile('CO', 'wx-co', 'mg/m³'),
      pollutantTile('NO₂', 'wx-no2', 'µg/m³'),
      pollutantTile('SO₂', 'wx-so2', 'µg/m³'),
      pollutantTile('O₃', 'wx-o3', 'µg/m³'),
      pollutantTile('NO', 'wx-no', 'µg/m³'),
      pollutantTile('CO₂', 'wx-co2', 'ppm')
    ].join('');

    station.innerHTML = [
      statusRow('Network', 'wx-network'),
      statusRow('Battery', 'wx-battery'),
      statusRow('Charging', 'wx-charging'),
      statusRow('Device Temp', 'wx-device-temp'),
      statusRow('Last Sync', 'wx-last-sync')
    ].join('');

    noise.innerHTML = [
      statusRow('Average', 'wx-noise-avg'),
      statusRow('Minimum', 'wx-noise-min'),
      statusRow('Maximum', 'wx-noise-max')
    ].join('');

    shellBuilt = true;
  }

  function ensureCharts() {
    if (charts.aqi) return;
    const aqiEl = document.getElementById('weatherAqiChart');
    const pmEl = document.getElementById('weatherPmChart');
    const tempEl = document.getElementById('weatherTempChart');
    if (!aqiEl || !pmEl || !tempEl || typeof Chart === 'undefined') return;

    charts.aqi = new Chart(aqiEl, {
      type: 'line',
      data: { labels: [], datasets: [{ label: 'AQI', data: [], borderColor: colors.blue, backgroundColor: 'rgba(58,111,168,.1)', fill: true, tension: .35, pointRadius: 0, borderWidth: 2 }] },
      options: chartOptions('AQI')
    });
    charts.pm = new Chart(pmEl, {
      type: 'line',
      data: {
        labels: [], datasets: [
          { label: 'PM2.5', data: [], borderColor: colors.orange, tension: .35, pointRadius: 0, borderWidth: 2 },
          { label: 'PM10', data: [], borderColor: colors.gold, tension: .35, pointRadius: 0, borderWidth: 2 }
        ]
      },
      options: chartOptions('µg/m³')
    });
    charts.temp = new Chart(tempEl, {
      type: 'line',
      data: {
        labels: [], datasets: [
          { label: 'Temp (°C)', data: [], borderColor: colors.teal, tension: .35, pointRadius: 0, borderWidth: 2, yAxisID: 'y' },
          { label: 'Humidity (%)', data: [], borderColor: colors.violet, tension: .35, pointRadius: 0, borderWidth: 2, yAxisID: 'y1' }
        ]
      },
      options: {
        ...chartOptions(),
        scales: {
          x: { grid: { display: false }, border: { color: colors.grid } },
          y: { type: 'linear', position: 'left', grid: { color: colors.grid }, border: { display: false } },
          y1: { type: 'linear', position: 'right', grid: { drawOnChartArea: false }, border: { display: false } }
        }
      }
    });
  }

  function renderLatest(data, status) {
    updateStatusPill(status, data ? data.recorded_at : lastRecordedAt);
    if (!data) return;
    lastRecordedAt = data.recorded_at;

    const sev = aqiSeverity(data.air_quality_index);
    const heroEl = document.querySelector('.weather-hero');
    if (heroEl) heroEl.style.setProperty('--weather-aqi-color', sev.color);
    animateNumber('weatherAqiVal', data.air_quality_index, 0);
    const aqiLabelEl = document.getElementById('weatherAqiLabel');
    if (aqiLabelEl) aqiLabelEl.textContent = sev.label;
    const marker = document.getElementById('weatherAqiMarker');
    if (marker) marker.style.left = Math.max(0, Math.min(100, sev.pct)) + '%';

    animateNumber('wx-temp', data.temperature_c, 1);
    animateNumber('wx-humidity', data.relative_humidity_percent, 1);
    animateNumber('wx-pm25', data.pm25_ug_m3, 1);
    animateNumber('wx-pm10', data.pm10_ug_m3, 1);
    animateNumber('wx-wind', data.wind_speed_kmph, 1);
    animateNumber('wx-rain', data.rain_mm, 1);
    animateNumber('wx-uv', data.uv_index, 1);
    animateNumber('wx-pressure', data.barometric_pressure_mba, 0);

    animateNumber('wx-co', data.co_mg_m3, 2);
    animateNumber('wx-no2', data.no2_ug_m3, 1);
    animateNumber('wx-so2', data.so2_ug_m3, 1);
    animateNumber('wx-o3', data.o3_ug_m3, 1);
    animateNumber('wx-no', data.no_ug_m3, 1);
    animateNumber('wx-co2', data.co2_ppm, 0);

    const net = document.getElementById('wx-network');
    if (net) net.textContent = data.network != null ? `${data.network}/4` : '--';
    const bat = document.getElementById('wx-battery');
    if (bat) bat.textContent = data.battery != null ? `${data.battery}%` : '--';
    const chg = document.getElementById('wx-charging');
    if (chg) chg.textContent = data.charging === 1 ? 'Yes' : data.charging === 0 ? 'No' : '--';
    const devt = document.getElementById('wx-device-temp');
    if (devt) devt.textContent = data.device_temp != null ? `${data.device_temp}°C` : '--';
    const lastSync = document.getElementById('wx-last-sync');
    if (lastSync) lastSync.textContent = relativeAge(data.recorded_at) || '--';

    animateNumber('wx-noise-avg', data.noise_average_db, 1);
    animateNumber('wx-noise-min', data.noise_min_db, 1);
    animateNumber('wx-noise-max', data.noise_max_db, 1);
  }

  function renderCharts(history) {
    if (!history || !history.length || !charts.aqi) return;
    let rows = [...history].sort((a, b) => new Date(a.recorded_at) - new Date(b.recorded_at));
    const cutoff = Date.now() - 24 * 60 * 60 * 1000;
    rows = rows.filter(d => new Date(d.recorded_at).getTime() >= cutoff);
    if (!rows.length) rows = [...history].sort((a, b) => new Date(a.recorded_at) - new Date(b.recorded_at));

    const labels = rows.map(d => new Date(d.recorded_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));

    charts.aqi.data.labels = labels;
    charts.aqi.data.datasets[0].data = rows.map(d => d.air_quality_index);
    charts.aqi.update();

    charts.pm.data.labels = labels;
    charts.pm.data.datasets[0].data = rows.map(d => d.pm25_ug_m3);
    charts.pm.data.datasets[1].data = rows.map(d => d.pm10_ug_m3);
    charts.pm.update();

    charts.temp.data.labels = labels;
    charts.temp.data.datasets[0].data = rows.map(d => d.temperature_c);
    charts.temp.data.datasets[1].data = rows.map(d => d.relative_humidity_percent);
    charts.temp.update();
  }

  /* ---- polling ---- */
  async function tickLatest() {
    if (latestInFlight) return;
    latestInFlight = true;
    try {
      const data = await fetchLatest();
      const status = computeStatus(data);
      updateNavDot(status);
      if (document.body.dataset.page === 'weather') renderLatest(data, status);
    } finally {
      latestInFlight = false;
    }
  }
  async function tickHistory() {
    if (document.body.dataset.page !== 'weather' || historyInFlight) return;
    historyInFlight = true;
    try {
      const history = await fetchHistory(500);
      renderCharts(history);
    } finally {
      historyInFlight = false;
    }
  }

  function activate() {
    buildShell();
    ensureCharts();
    tickLatest();
    tickHistory();
  }

  const navBtn = document.querySelector('.bottom-dock button[data-page="weather"]');
  if (navBtn) navBtn.addEventListener('click', activate);

  // Ambient status polling starts immediately so the dock dot is live even
  // before anyone opens the tab; the heavier history poll only runs while
  // the Weather page itself is the active one.
  tickLatest();
  setInterval(tickLatest, POLL_MS);
  setInterval(tickHistory, HISTORY_POLL_MS);
})();
