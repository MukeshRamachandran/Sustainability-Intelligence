/* =====================================================================
   MICROCOSM - LIVE WEATHER MONITORING (weather.js)
   Self-contained addon (same pattern as walkthrough.js/mobile.js): reads
   shared helpers already on the page (ic, colors, chartOptions, fmt,
   reduceMotion - all defined in app.js, which loads before this file)
   but app.js does not depend on anything in here.

   This page is framed as a climate observatory first: ambient temperature,
   humidity, rainfall, wind and pressure are the primary KPI rows. Air
   quality (AQI/PM/gas pollutants) is real data from the same station, but
   deliberately laid out as secondary, lower-priority context underneath.

   Talks to the separate Aeron Environment Dashboard backend (FastAPI +
   Postgres, see aeron-environment-dashboard/) over HTTP - that backend
   must be running locally (uvicorn, port 8000) for live data to show.
   If it isn't reachable, every widget here degrades to '--' and the
   status pill/dock dot switch to OFFLINE rather than erroring.
   ===================================================================== */
(function () {
  // Candidate hosts for the Aeron backend, tried in order and cached once one
  // works. "localhost" can resolve to the IPv6 loopback (::1) on Windows while
  // uvicorn only listens on IPv4 127.0.0.1 - that alone is enough to make every
  // request silently fail to connect even though the backend is up, so we don't
  // rely on window.location.hostname alone.
  const API_HOST_CANDIDATES = [...new Set([window.location.hostname, '127.0.0.1', 'localhost'].filter(Boolean))];
  let resolvedApiBase = null;
  const POLL_MS = 20000;      // latest reading + status (drives the dock dot)
  const HISTORY_POLL_MS = 60000; // trend charts, only while the page is open

  let shellBuilt = false;
  let charts = {};
  let lastRecordedAt = null;
  let lastHistory = null;
  let lastData = null; // most recent full reading, so activate() can pick the right condition immediately instead of guessing

  /* ---- condition -> background video ----
     "sunny" is an intro+loop pair (sunny1.mp4 plays once, then hands off to
     sunny2.mp4 looping - see playConditionVideo()). "rainy" has only one clip
     (rain.mp4), so it's registered as its own intro *and* loop - it still
     goes through the same intro->loop handoff machinery, which just means
     the clip crossfades into itself at the loop point instead of a hard cut,
     which is a fine outcome, not a bug. Any other condition falls back to
     the page's static background image (#bg-weather/#bg-main). Add more
     entries here as more clips become available - everything below this
     table is generic and doesn't assume "sunny" specifically. */
  const CONDITION_VIDEOS = {
    sunny: { intro: 'media/sunny1.mp4', loop: 'media/sunny2.mp4' },
    rainy: { intro: 'media/rain.mp4', loop: 'media/rain.mp4' }
  };
  /* Best-effort read of "what's it like outside" from the fields this
     station actually has (no cloud-cover sensor, so this is a coarse proxy,
     not a real forecast): any detected rain means rainy, otherwise sunny -
     the only two conditions with clips today. */
  function classifyCondition(data) {
    if (!data) return null;
    if (data.rain_mm != null && data.rain_mm > 0) return 'rainy';
    return 'sunny';
  }

  let bgCondition = null;   // condition the video layer is currently showing, or null if hidden
  let bgSwapHandlers = null; // {ended, timeupdate} listeners on the intro clip, so a re-trigger can clean up an in-flight one

  /* Starts (or restarts, from the top) the intro->loop video for `condition`.
     The intro (sunny1) plays once; ~0.5s before it ends, the loop clip
     (sunny2) is already primed and starts playing underneath, then the two
     cross-fade via the .video-visible opacity transition in CSS - so the
     handoff reads as one continuous clip rather than a hard cut. */
  function playConditionVideo(condition, opts) {
    // Respect prefers-reduced-motion like the rest of the site's animations -
    // fall back to the static page background instead of an ambient video.
    if (typeof reduceMotion !== 'undefined' && reduceMotion) { hideConditionVideo(); return; }
    const cfg = CONDITION_VIDEOS[condition];
    const wrap = document.getElementById('weatherBgVideoWrap');
    const vIntro = document.getElementById('weatherBgVideoA');
    const vLoop = document.getElementById('weatherBgVideoB');
    if (!cfg || !wrap || !vIntro || !vLoop) { hideConditionVideo(); return; }

    const restart = !opts || opts.restart !== false;
    if (bgCondition === condition && !restart) { wrap.classList.add('active'); return; }

    if (bgSwapHandlers) {
      vIntro.removeEventListener('ended', bgSwapHandlers.handoff);
      vIntro.removeEventListener('timeupdate', bgSwapHandlers.nearEnd);
      bgSwapHandlers = null;
    }

    bgCondition = condition;
    wrap.classList.add('active');

    vLoop.loop = true;
    vLoop.classList.remove('video-visible');
    vLoop.src = cfg.loop;
    vLoop.load();

    vIntro.loop = false;
    vIntro.classList.add('video-visible');
    vIntro.src = cfg.intro;
    vIntro.currentTime = 0;
    vIntro.play().catch(() => {});

    const handoff = () => {
      vLoop.currentTime = 0;
      vLoop.play().catch(() => {});
      vLoop.classList.add('video-visible');
      vIntro.classList.remove('video-visible');
      vIntro.removeEventListener('ended', handoff);
      vIntro.removeEventListener('timeupdate', nearEnd);
      bgSwapHandlers = null;
    };
    const nearEnd = () => {
      if (vIntro.duration && vIntro.currentTime >= vIntro.duration - 0.5) handoff();
    };
    vIntro.addEventListener('ended', handoff);
    vIntro.addEventListener('timeupdate', nearEnd);
    bgSwapHandlers = { handoff, nearEnd };
  }

  function hideConditionVideo() {
    const wrap = document.getElementById('weatherBgVideoWrap');
    if (wrap) wrap.classList.remove('active');
    // Paused, not just hidden - the next activate() always restarts the
    // condition's intro clip fresh anyway, and there's no reason to keep
    // decoding video while the user is looking at a different page.
    const vIntro = document.getElementById('weatherBgVideoA');
    const vLoop = document.getElementById('weatherBgVideoB');
    if (vIntro) vIntro.pause();
    if (vLoop) vLoop.pause();
    bgCondition = null;
  }

  /* Called on every fresh reading: keeps the background truthful to live
     data without replaying the intro animation every 20s - only a genuine
     condition change (or the initial tab-open below) restarts sunny1. */
  function syncConditionVideo(data) {
    const condition = classifyCondition(data);
    if (!condition || !CONDITION_VIDEOS[condition]) { hideConditionVideo(); return; }
    if (condition === bgCondition) return; // already showing the right thing, don't restart it
    playConditionVideo(condition, { restart: true });
  }

  /* ---- AQI severity band: color + public-facing label (kept for the small
     secondary AQI card - this page no longer has a dedicated AQI hero). */
  function aqiSeverity(aqi) {
    if (aqi == null || isNaN(aqi)) return { label: 'No data yet', color: 'var(--faint)' };
    const v = +aqi;
    if (v <= 50) return { label: 'Good', color: '#10b981' };
    if (v <= 100) return { label: 'Moderate', color: '#facc15' };
    if (v <= 150) return { label: 'Unhealthy for Sensitive Groups', color: '#f97316' };
    if (v <= 200) return { label: 'Unhealthy', color: '#ef4444' };
    if (v <= 300) return { label: 'Very Unhealthy', color: '#a855f7' };
    return { label: 'Hazardous', color: '#9f1239' };
  }

  /* 16-point compass label from a wind direction in degrees. */
  function windCompass(deg) {
    if (deg == null || isNaN(deg)) return '';
    const dirs = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
    return dirs[Math.round((+deg % 360) / 22.5) % 16];
  }

  /* LIVE < 10 min old, STALE 10-30 min, OFFLINE beyond that or no reading at all. */
  function computeStatus(recordedAtISO) {
    if (!recordedAtISO) return 'offline';
    const ageSec = (Date.now() - new Date(recordedAtISO).getTime()) / 1000;
    if (ageSec > 30 * 60) return 'offline';
    if (ageSec > 10 * 60) return 'stale';
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

  /* Absolute "28 Aug 2026 · 14:32:07" for the always-visible fetched-at
     timestamp - relative age alone ("2m ago") doesn't tell you *when*. */
  function absoluteStamp(recordedAtISO) {
    if (!recordedAtISO) return null;
    const dt = new Date(recordedAtISO);
    const datePart = dt.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
    const timePart = dt.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    return `${datePart} · ${timePart}`;
  }

  /* Tries the already-known-good host first, then walks the full candidate
     list. A thrown fetch error OR a non-2xx response both move on to the next
     candidate - some other, unrelated server (e.g. a stray static file server
     also squatting on :8000 via a different loopback address) can easily
     answer with its own 404 instead of a real network failure, so a bad
     response is not proof the real backend is unreachable, only that *this*
     host wasn't it. Only a genuinely-OK response gets cached. */
  async function request(path, method) {
    const hosts = resolvedApiBase ? [resolvedApiBase, ...API_HOST_CANDIDATES.filter(h => h !== resolvedApiBase)] : API_HOST_CANDIDATES;
    let lastErr = null, lastBad = null;
    for (const host of hosts) {
      const url = `http://${host}:8000/api${path}`;
      try {
        const res = await fetch(url, { cache: 'no-store', method: method || 'GET' });
        if (!res.ok) {
          lastBad = `${url} responded ${res.status} ${res.statusText}`;
          continue;
        }
        resolvedApiBase = host;
        return await res.json();
      } catch (e) {
        lastErr = e;
      }
    }
    resolvedApiBase = null;
    if (lastBad) console.warn(`[weather] ${lastBad}`);
    // Most common causes: the Aeron backend (uvicorn, port 8000) isn't running,
    // this page was opened via file:// (browsers block cross-origin fetch from
    // a file:// origin), or none of the tried hostnames reach it on this machine.
    console.warn(`[weather] could not reach the Aeron backend on any of [${hosts.join(', ')}]:8000`, lastErr);
    return null;
  }
  const fetchLatest = () => request('/environment/latest');
  const fetchHistory = (limit) => request(`/environment/history?limit=${limit}`);
  const postSync = () => request('/sync/aeron', 'POST');

  /* ---- nav dock dot: reflects connectivity regardless of which page is open ---- */
  function updateNavDot(status) {
    const dot = document.getElementById('weatherNavDot');
    if (!dot) return;
    dot.classList.remove('live', 'stale', 'offline');
    dot.classList.add(status);
  }

  function updateStatusBar(status, recordedAtISO) {
    const pill = document.getElementById('weatherStatusPill');
    const text = document.getElementById('weatherStatusText');
    const updated = document.getElementById('weatherUpdatedText');
    if (pill) pill.className = 'weather-status-pill ' + status;
    if (text) text.textContent = status === 'live' ? 'LIVE' : status === 'stale' ? 'STALE' : 'OFFLINE';
    if (updated) {
      if (!recordedAtISO) {
        const hosts = resolvedApiBase ? [resolvedApiBase] : API_HOST_CANDIDATES;
        updated.textContent = status === 'offline'
          ? `Can't reach the Aeron backend (tried ${hosts.map(h => `${h}:8000`).join(', ')})`
          : 'Waiting for first reading…';
      } else {
        const stamp = absoluteStamp(recordedAtISO), age = relativeAge(recordedAtISO);
        updated.textContent = `Data fetched: ${stamp} (${age})${status === 'stale' ? ' — station may be offline' : ''}`;
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
  function statCard(title, id, unit, accent, icon, opts) {
    opts = opts || {};
    return `<article class="kpi" style="--a:${accent}"${opts.cardId ? ` id="${opts.cardId}"` : ''}>
      <div class="icon">${ic(icon)}</div>
      <div class="label">${title}</div>
      <div class="value"><span id="${id}">--</span><small>${unit}</small></div>
      ${opts.subId ? `<div class="wx-sub" id="${opts.subId}">—</div>` : ''}
      ${opts.note ? `<div class="wx-sub wx-note">${opts.note}</div>` : ''}
    </article>`;
  }
  function pollutantTile(label, id, unit) {
    return `<div class="highlight"><b><span id="${id}">--</span> <span style="font-size:12px;font-weight:600;color:var(--muted);">${unit}</span></b><span>${label}</span></div>`;
  }
  function statusRow(label, id) {
    return `<div style="display:flex;justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:8px;font-size:13px;">
      <span style="color:var(--muted);">${label}</span><span style="font-weight:600;color:var(--ink);" id="${id}">--</span></div>`;
  }

  function injectStyles() {
    if (document.getElementById('weatherStyles')) return;
    const style = document.createElement('style');
    style.id = 'weatherStyles';
    style.textContent = `
      .weather-statusbar{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;
        background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:12px 18px;margin:14px 0 20px;}
      .weather-statusbar-left{display:flex;align-items:center;flex-wrap:wrap;gap:12px;min-width:0;}
      .weather-status-pill{display:inline-flex;align-items:center;gap:7px;padding:6px 12px;border-radius:99px;
        background:var(--surface2);border:1px solid var(--line);font-size:11px;font-weight:700;letter-spacing:.06em;
        text-transform:uppercase;color:var(--muted);white-space:nowrap;flex:none;}
      .weather-status-dot{width:8px;height:8px;border-radius:50%;background:var(--faint);flex:none;}
      .weather-status-pill.live .weather-status-dot{background:#10b981;animation:navDotPulseLive 1.8s ease-in-out infinite;}
      .weather-status-pill.stale .weather-status-dot{background:#f59e0b;animation:navDotPulseStale 2.6s ease-in-out infinite;}
      .weather-status-pill.offline .weather-status-dot{background:#ef4444;}
      .weather-updated-text{font-size:12.5px;color:var(--muted);font-weight:500;}
      .weather-network-badge{font-size:11px;font-weight:700;color:var(--faint);background:var(--surface2);
        border:1px solid var(--line);border-radius:99px;padding:4px 10px;white-space:nowrap;}
      .wx-sub{font-size:11.5px;color:var(--faint);font-weight:600;margin-top:6px;}
      .wx-note{color:#b8862e;}
    `;
    document.head.appendChild(style);
  }

  function buildShell() {
    if (shellBuilt) return;
    const statusBar = document.getElementById('weatherStatusBar');
    const kpis = document.getElementById('weatherKpis');
    const kpis2 = document.getElementById('weatherKpis2');
    const aqiKpis = document.getElementById('weatherAqiKpis');
    const pollutants = document.getElementById('weatherPollutants');
    const noise = document.getElementById('weatherNoise');
    if (!statusBar || !kpis || !kpis2 || !aqiKpis || !pollutants || !noise) return;

    injectStyles();

    statusBar.innerHTML = `
      <div class="weather-statusbar">
        <div class="weather-statusbar-left">
          <span class="weather-status-pill" id="weatherStatusPill"><span class="weather-status-dot"></span><span id="weatherStatusText">CONNECTING</span></span>
          <span class="weather-updated-text" id="weatherUpdatedText">Waiting for first reading…</span>
          <span class="weather-network-badge" id="weatherNetworkBadge" style="display:none;"></span>
        </div>
        <button class="btn" id="weatherSyncBtn">Sync Now</button>
      </div>`;

    // ---- Primary: climate parameters (Ambient Temperature, Humidity, Rainfall, Wind Speed)
    kpis.innerHTML = [
      statCard('Ambient Temperature', 'wx-temp', '°C', colors.gold, 'sun', { subId: 'wx-temp-range' }),
      statCard('Relative Humidity', 'wx-humidity', '%', colors.cyan, 'droplet'),
      statCard('Rainfall', 'wx-rain', 'mm', colors.blue, 'rain', { subId: 'wx-rain-total' }),
      statCard('Wind Speed', 'wx-wind', 'km/h', colors.emerald, 'wind', { subId: 'wx-wind-peak' })
    ].join('');

    // ---- Primary continued: Wind Direction, UV Index, Barometric Pressure, CO2
    kpis2.innerHTML = [
      statCard('Wind Direction', 'wx-wind-dir', '°', colors.emerald, 'gauge', { subId: 'wx-wind-compass' }),
      statCard('UV Index', 'wx-uv', '', colors.gold, 'shield'),
      statCard('Barometric Pressure', 'wx-pressure', 'mba', '#7b8794', 'gauge', { note: '⚠ Verify sensor calibration' }),
      statCard('CO₂', 'wx-co2', 'ppm', colors.teal, 'cloud', { note: 'Context reading — verify calibration' })
    ].join('');

    // ---- Secondary: Air Quality & Pollutants (below climate metrics)
    aqiKpis.innerHTML = [
      statCard('Air Quality Index', 'wx-aqi', '', 'var(--faint)', 'gauge', { cardId: 'wx-aqi-card', subId: 'wx-aqi-label' }),
      statCard('PM2.5', 'wx-pm25', 'µg/m³', colors.violet, 'cloud'),
      statCard('PM10', 'wx-pm10', 'µg/m³', colors.teal, 'cloud'),
      statCard('O₃', 'wx-o3', 'µg/m³', colors.cyan, 'sprout')
    ].join('');

    pollutants.innerHTML = [
      pollutantTile('NO₂', 'wx-no2', 'µg/m³'),
      pollutantTile('SO₂', 'wx-so2', 'µg/m³'),
      pollutantTile('CO', 'wx-co', 'mg/m³'),
      pollutantTile('NO', 'wx-no', 'µg/m³')
    ].join('');

    noise.innerHTML = [
      statusRow('Average', 'wx-noise-avg'),
      statusRow('Minimum', 'wx-noise-min'),
      statusRow('Maximum', 'wx-noise-max')
    ].join('');

    document.getElementById('weatherSyncBtn').addEventListener('click', triggerSync);

    shellBuilt = true;
  }

  function ensureCharts() {
    if (charts.temp) return;
    const tempEl = document.getElementById('weatherTempChart');
    const rainWindEl = document.getElementById('weatherRainWindChart');
    const aqiEl = document.getElementById('weatherAqiChart');
    const pmEl = document.getElementById('weatherPmChart');
    if (!tempEl || !rainWindEl || !aqiEl || !pmEl || typeof Chart === 'undefined') return;

    charts.temp = new Chart(tempEl, {
      type: 'line',
      data: {
        labels: [], datasets: [
          { label: 'Temp (°C)', data: [], borderColor: colors.gold, backgroundColor: 'rgba(193,138,46,.08)', fill: true, tension: .35, pointRadius: 0, borderWidth: 2, yAxisID: 'y' },
          { label: 'Humidity (%)', data: [], borderColor: colors.cyan, tension: .35, pointRadius: 0, borderWidth: 2, yAxisID: 'y1' }
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

    charts.rainWind = new Chart(rainWindEl, {
      type: 'bar',
      data: {
        labels: [], datasets: [
          { type: 'bar', label: 'Rainfall (mm)', data: [], backgroundColor: 'rgba(58,111,168,.45)', borderRadius: 4, yAxisID: 'y' },
          { type: 'line', label: 'Wind speed (km/h)', data: [], borderColor: colors.emerald, tension: .35, pointRadius: 0, borderWidth: 2, yAxisID: 'y1' }
        ]
      },
      options: {
        ...chartOptions(),
        scales: {
          x: { grid: { display: false }, border: { color: colors.grid } },
          y: { type: 'linear', position: 'left', grid: { color: colors.grid }, border: { display: false }, beginAtZero: true },
          y1: { type: 'linear', position: 'right', grid: { drawOnChartArea: false }, border: { display: false }, beginAtZero: true }
        }
      }
    });

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
  }

  function renderLatest(data, status) {
    updateStatusBar(status, data ? data.recorded_at : lastRecordedAt);
    syncConditionVideo(data);
    if (!data) return;
    lastRecordedAt = data.recorded_at;
    lastData = data;

    // ---- Climate parameters
    animateNumber('wx-temp', data.temperature_c, 1);
    animateNumber('wx-humidity', data.relative_humidity_percent, 1);
    animateNumber('wx-rain', data.rain_mm, 1);
    animateNumber('wx-wind', data.wind_speed_kmph, 1);
    animateNumber('wx-wind-dir', data.wind_direction_deg, 0);
    const compassEl = document.getElementById('wx-wind-compass');
    if (compassEl) compassEl.textContent = data.wind_direction_deg != null ? windCompass(data.wind_direction_deg) + ' prevailing' : '—';
    animateNumber('wx-uv', data.uv_index, 1);
    animateNumber('wx-pressure', data.barometric_pressure_mba, 0);
    animateNumber('wx-co2', data.co2_ppm, 0);

    // ---- Secondary: air quality
    const sev = aqiSeverity(data.air_quality_index);
    const aqiCard = document.getElementById('wx-aqi-card');
    if (aqiCard) aqiCard.style.setProperty('--a', sev.color);
    animateNumber('wx-aqi', data.air_quality_index, 0);
    const aqiLabelEl = document.getElementById('wx-aqi-label');
    if (aqiLabelEl) aqiLabelEl.textContent = sev.label;
    animateNumber('wx-pm25', data.pm25_ug_m3, 1);
    animateNumber('wx-pm10', data.pm10_ug_m3, 1);
    animateNumber('wx-o3', data.o3_ug_m3, 1);
    animateNumber('wx-no2', data.no2_ug_m3, 1);
    animateNumber('wx-so2', data.so2_ug_m3, 1);
    animateNumber('wx-co', data.co_mg_m3, 2);
    animateNumber('wx-no', data.no_ug_m3, 1);

    // ---- Network badge (kept as a small ambient indicator; battery/charging/device-temp dropped)
    const netBadge = document.getElementById('weatherNetworkBadge');
    if (netBadge) {
      if (data.network != null) { netBadge.style.display = ''; netBadge.textContent = `Signal ${data.network}/4`; }
      else netBadge.style.display = 'none';
    }

    animateNumber('wx-noise-avg', data.noise_average_db, 1);
    animateNumber('wx-noise-min', data.noise_min_db, 1);
    animateNumber('wx-noise-max', data.noise_max_db, 1);
  }

  function renderCharts(history) {
    if (!history || !history.length || !charts.temp) return;
    lastHistory = history;
    let rows = [...history].sort((a, b) => new Date(a.recorded_at) - new Date(b.recorded_at));
    const cutoff = Date.now() - 24 * 60 * 60 * 1000;
    let last24h = rows.filter(d => new Date(d.recorded_at).getTime() >= cutoff);
    if (!last24h.length) last24h = rows;

    const labels = last24h.map(d => new Date(d.recorded_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));

    charts.temp.data.labels = labels;
    charts.temp.data.datasets[0].data = last24h.map(d => d.temperature_c);
    charts.temp.data.datasets[1].data = last24h.map(d => d.relative_humidity_percent);
    charts.temp.update();

    charts.rainWind.data.labels = labels;
    charts.rainWind.data.datasets[0].data = last24h.map(d => d.rain_mm);
    charts.rainWind.data.datasets[1].data = last24h.map(d => d.wind_speed_kmph);
    charts.rainWind.update();

    charts.aqi.data.labels = labels;
    charts.aqi.data.datasets[0].data = last24h.map(d => d.air_quality_index);
    charts.aqi.update();

    charts.pm.data.labels = labels;
    charts.pm.data.datasets[0].data = last24h.map(d => d.pm25_ug_m3);
    charts.pm.data.datasets[1].data = last24h.map(d => d.pm10_ug_m3);
    charts.pm.update();

    // ---- Derived stats for the KPI subtitles: today's range/total/peak
    const now = new Date();
    const todayRows = rows.filter(d => { const dt = new Date(d.recorded_at); return dt.toDateString() === now.toDateString(); });
    const sample = todayRows.length ? todayRows : last24h;

    const temps = sample.map(d => d.temperature_c).filter(v => v != null);
    const tempRangeEl = document.getElementById('wx-temp-range');
    if (tempRangeEl) tempRangeEl.textContent = temps.length ? `Today: ${Math.min(...temps).toFixed(1)}° – ${Math.max(...temps).toFixed(1)}°` : '—';

    const rainTotal = sample.reduce((sum, d) => sum + (d.rain_mm || 0), 0);
    const rainTotalEl = document.getElementById('wx-rain-total');
    if (rainTotalEl) rainTotalEl.textContent = `Today's total: ${rainTotal.toFixed(1)} mm`;

    const winds = sample.map(d => d.wind_speed_kmph).filter(v => v != null);
    const windPeakEl = document.getElementById('wx-wind-peak');
    if (windPeakEl) windPeakEl.textContent = winds.length ? `Peak: ${Math.max(...winds).toFixed(1)} km/h` : '—';
  }

  /* ---- polling ---- */
  async function tickLatest() {
    const data = await fetchLatest();
    const status = data ? computeStatus(data.recorded_at) : 'offline';
    updateNavDot(status);
    if (document.body.dataset.page === 'weather') renderLatest(data, status);
  }
  async function tickHistory() {
    if (document.body.dataset.page !== 'weather') return;
    const history = await fetchHistory(500);
    renderCharts(history);
  }

  async function triggerSync() {
    const btn = document.getElementById('weatherSyncBtn');
    if (!btn) return;
    const original = btn.textContent;
    btn.textContent = 'Syncing…';
    btn.disabled = true;
    try {
      await postSync();
    } finally {
      await tickLatest();
      await tickHistory();
      btn.textContent = original;
      btn.disabled = false;
    }
  }

  function activate() {
    buildShell();
    ensureCharts();
    // Restart the condition's intro/loop fresh on every tab-open, as the
    // "startup animation". Uses the last reading we already have (if any) so
    // a rainy visit opens on rain.mp4 immediately instead of flashing sunny
    // first and correcting a tick later; only falls back to 'sunny' when
    // there's truly no data yet (first open this session). Either way,
    // syncConditionVideo() still corrects it once the next reading lands.
    playConditionVideo(classifyCondition(lastData) || 'sunny', { restart: true });
    tickLatest();
    tickHistory();
  }

  const navBtn = document.querySelector('.bottom-dock button[data-page="weather"]');
  if (navBtn) navBtn.addEventListener('click', activate);

  // The video layer's own .active class is independent of body[data-page] -
  // without this, it would keep covering every other page too once shown,
  // since nothing else ever clears it. Catches every way navigation can
  // happen (dock click, the logo's onclick="go('overview')", walkthrough.js,
  // ...), not just clicks on this one button.
  new MutationObserver(() => {
    if (document.body.dataset.page !== 'weather') hideConditionVideo();
  }).observe(document.body, { attributes: true, attributeFilter: ['data-page'] });

  // Ambient status polling starts immediately so the dock dot is live even
  // before anyone opens the tab; the heavier history poll only runs while
  // the Weather page itself is the active one.
  tickLatest();
  setInterval(tickLatest, POLL_MS);
  setInterval(tickHistory, HISTORY_POLL_MS);
})();
