/* =====================================================================
   THE CARBON STORY — cinematic KPI walkthrough (pure addon)
   ---------------------------------------------------------------------
   Self-contained. Reads its numbers off the rendered .kpi cards, so it
   always reflects the current year / month filters and needs
   nothing from app.js. Builds its own DOM, scrolls in its own container,
   and leaves no trace on the dashboard when it closes.
   ===================================================================== */

(function () {
  'use strict';

  var gsap = window.gsap;
  var ST = window.ScrollTrigger;
  if (!gsap || !ST) {
    console.warn('[carbon-story] GSAP + ScrollTrigger required; walkthrough disabled.');
    return;
  }
  gsap.registerPlugin(ST);

  var REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var FINE_POINTER = window.matchMedia('(pointer: fine)').matches;

  /* ------------------------------------------------------------------
     Equivalency factors — every "in other words" line is computed live
     from these. Correct a factor here and every act updates.
     ------------------------------------------------------------------ */
  var WT_EQUIV = {
    homeKwhYr: 1200,   // kWh consumed per Indian household per year
    carKgKm: 0.17,     // kg CO₂e per km, average petrol car
    indiaPerCap: 2.0   // tCO₂e per person per year, India average
  };

  // n = act number 1..8, v = the live card value. Returns {sign, html} or null.
  function equivFor(n, v) {
    if (v == null || isNaN(v)) return null;
    var f = WT_EQUIV;
    function b(x, dec) { return '<b>' + fmtNum(x, dec || 0) + '</b>'; }
    switch (n) {
      case 1: return null;
      case 2: return 'enough to run ' + b(v / f.homeKwhYr) + ' Indian homes for a year';
      case 3: return 'a full year of clean power for ' + b(v / f.homeKwhYr) + ' homes';
      case 4: return b(v * 1000 / f.carKgKm) + ' km of petrol driving that never happened';
      case 5: return 'equal to driving a petrol car ' + b(v * 1000 / f.carKgKm) + ' km';
      case 6: return null;
      case 7: return 'about ' + b(v / f.indiaPerCap * 100) + '% of the average Indian’s annual footprint';
      case 8: return null;
    }
    return null;
  }

  // mix two hex colours; used to tint the letterbox bars toward each accent
  function hexMix(a, b, t) {
    var pa = /^#([0-9a-f]{6})$/i.exec(a), pb = /^#([0-9a-f]{6})$/i.exec(b);
    if (!pa || !pb) return b;
    var out = '#';
    for (var i = 0; i < 3; i++) {
      var ca = parseInt(pa[1].substr(i * 2, 2), 16), cb = parseInt(pb[1].substr(i * 2, 2), 16);
      out += ('0' + Math.round(ca * t + cb * (1 - t)).toString(16)).slice(-2);
    }
    return out;
  }

  /* ------------------------------------------------------------------
     Narrative. Keyed by the exact .label text rendered by kpi() in app.js.
     `video` is a fallback: the cards omit their <video> under reduced
     motion, so we cannot always read the source off the DOM.
     `storyVideo` is the opposite — an override that WINS over the card's
     own footage, so an act can be cast with cinema the dashboard doesn't
     use. The KPI cards keep playing their own videos, untouched.
     ------------------------------------------------------------------ */

  var WT_STORY = [
    {
      title: 'Total carbon footprint (gross)',
      video: 'media/industrynew.mp4',
      head: ['The Weight of', 'What We Make'],
      def: 'Every litre of fuel burned and every unit of electricity drawn, converted into a single number — the total greenhouse gas this campus released before a single offset is counted.',
      chips: ['Scope 1 + Scope 2', 'Before offsets']
    },
    {
      title: 'Total electricity consumption',
      video: 'media/elecmeter.mp4',
      head: ['The Current', 'Beneath Everything'],
      def: 'The aggregate electrical energy drawn by every building, laboratory, hostel and streetlight on campus. It is the quiet constant standing behind almost everything else measured here.',
      chips: ['Grid + on-site solar', 'Metered at source']
    },
    {
      title: 'Renewable energy used',
      video: 'media/solar-kpi.mp4',
      storyVideo: 'media/solarbuild.mp4',
      head: ['Light, Borrowed', 'and Returned'],
      def: 'Energy generated from sources that replenish themselves — here, overwhelmingly the sun. Every unit produced on campus is a unit the grid never had to burn coal to supply.',
      chips: ['Solar generation', 'Displaces grid power']
    },
    {
      title: 'Emission avoided',
      video: 'media/leavesfall.mp4',
      storyVideo: 'media/natureview.mp4',
      head: ['The Carbon', 'That Never Was'],
      def: 'The greenhouse gas that would have entered the atmosphere had the campus drawn this same energy from the grid instead of generating it cleanly. It is measured in absence — emissions that never happened.',
      chips: ['Governed GRID factor', 'Separate from operational inventory']
    },
    {
      title: 'Scope 1 emissions',
      video: 'media/fuelpour.mp4',
      storyVideo: 'media/busdepot.mp4',
      head: ['What We', 'Burn Ourselves'],
      def: 'Direct emissions from sources the institution owns and controls: the diesel in its buses, the petrol in its vehicles, the fuel feeding its generators. These cannot be purchased away, only designed away.',
      chips: ['Petrol · Diesel · DG sets', 'Direct combustion']
    },
    {
      title: 'Scope 2 emissions',
      video: 'media/electricspark.mp4',
      storyVideo: 'media/electri.mp4',
      head: ['The Grid', 'We Inherit'],
      def: 'Indirect emissions embedded in the electricity the campus buys. The carbon was released somewhere else, at a power station, on this campus’s behalf — which makes the grid’s fuel mix part of our footprint.',
      chips: ['Purchased electricity', 'Governed result · published API only']
    },
    {
      title: 'Per capita emissions',
      video: 'media/queper.mp4',
      head: ['One Campus, Divided', 'by Its People'],
      def: 'The total footprint shared across every student and staff member. It normalises the picture: an institution can grow in size and still, by this measure, grow lighter on the world.',
      chips: ['Footprint ÷ population', 'Growth-adjusted']
    },
    {
      title: 'Where We Stand',
      video: 'media/earth.mp4',
      head: ['Where', 'We Stand'],
      def: 'Operational greenhouse gas emissions and estimated avoided grid emissions are reported separately. Avoided emissions are not subtracted from the operational inventory.',
      chips: ['Two distinct indicators', 'No net subtraction']
    }
  ];

  var INTRO = {
    kind: 'intro',
    accent: '#1c7a4b',
    video: 'media/entrykct.mp4',  // the campus gate opens the story
    still: 'media/background.png', // shown instantly as a poster while it loads
    eyebrow: 'Kumaraguru Institution Microcosm · Carbon Observatory',
    head: ['The Carbon', 'Story'],
    def: 'Eight measures of what a campus takes from the world, and what it gives back.'
  };

  var OUTRO = {
    kind: 'outro',
    accent: '#1c7a4b',
    video: 'media/micronew.mp4',
    eyebrow: 'The story continues',
    head: ['A Clearer', 'Picture'],
    lead: 'The published operational inventory and estimated avoided grid emissions remain separate measures.'
  };

  /* ------------------------------------------------------------------ */

  var fab, overlay, scroller, track, frame, chrome, rail, grainCanvas, hint, progressFill;
  var motesCanvas, barEls = [];
  var washes = [], washTop = 0;
  var acts = [], cues = [], tls = [], fxTweens = [];
  var open = false, building = false;
  var activeIdx = -1, atmoRaf = 0, atmoFrames = 0, scrollRaf = 0, savedScrollY = 0;
  var lastScrollTop = 0, moteImpulse = 0;
  var dashEls = [];
  var px = { qs: null };            // parallax quickTo set for the active act

  function fmtNum(v, dec) {
    return Number(v).toLocaleString('en-IN', { minimumFractionDigits: dec, maximumFractionDigits: dec });
  }

  function el(tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  }

  // gsap.set() accepts an element or a NodeList, but not an array containing
  // NodeLists — it hands each entry straight to getComputedStyle. Flatten first.
  function nodes() {
    var out = [];
    for (var i = 0; i < arguments.length; i++) {
      var v = arguments[i];
      if (!v) continue;
      if (v.nodeType) out.push(v);
      else Array.prototype.push.apply(out, Array.prototype.slice.call(v));
    }
    return out;
  }

  /* ------------------------------------------------------------------
     Read the live KPI cards. Everything the story needs is already in
     the markup that kpi() produces.
     ------------------------------------------------------------------ */

  function readCards() {
    var map = {};
    document.querySelectorAll('.page .kpi').forEach(function (card) {
      var labelEl = card.querySelector('.label');
      if (!labelEl) return;
      var title = labelEl.textContent.trim();
      var counter = card.querySelector('.counter-val');
      var unitEl = card.querySelector('.value small');
      var src = card.querySelector('video source');
      var b = card.querySelector('.trend b');
      var s = card.querySelector('.trend span');

      var unit = unitEl ? unitEl.textContent.trim() : '';
      var statusText = s ? s.textContent.trim() : '';
      var trend = null;
      if (b && !b.classList.contains('neutral')) {
        trend = {
          text: (b.textContent.trim() + ' ' + (s ? s.textContent.trim() : '')).trim(),
          cls: b.classList.contains('good') ? 'is-good' : 'is-bad'
        };
      }

      var unavailable = !counter;
      var source = card.querySelector('.kpi-source');
      map[title] = {
        provenance: source ? source.textContent.trim() : '',
        value: unavailable ? null : parseFloat(counter.getAttribute('data-val')),
        dec: counter ? parseInt(counter.getAttribute('data-dec'), 10) || 0 : 0,
        unit: unit,
        na: unavailable,
        statusText: statusText,
        accent: (card.style.getPropertyValue('--a') || '#1c7a4b').trim(),
        video: src ? src.getAttribute('src') : null,
        trend: trend
      };
    });

    // Scope totals are published in the GHG page's split summary rather
    // than in a `.kpi` card in the current staging layout.
    document.querySelectorAll('#ghgKpis .ghg-split').forEach(function (split) {
      var heading = split.querySelector('.ghg-split-head');
      if (!heading) return;
      var title = heading.textContent.trim().replace(/\s+/g, ' ').toLowerCase();
      if (title !== 'scope 1 emissions' && title !== 'scope 2 emissions') return;
      var counter = split.querySelector('.counter-val');
      var unavailable = !counter;
      var value = counter ? parseFloat(counter.getAttribute('data-val')) : NaN;
      var splitSource = split.querySelector('.kpi-source');
      map[title === 'scope 1 emissions' ? 'Scope 1 emissions' : 'Scope 2 emissions'] = {
        provenance: splitSource ? splitSource.textContent.trim() : '',
        value: unavailable || !isFinite(value) ? null : value,
        dec: counter ? parseInt(counter.getAttribute('data-dec'), 10) || 2 : 2,
        unit: 'tCO₂e',
        na: unavailable || !isFinite(value),
        statusText: '',
        accent: '#1c7a4b',
        video: null,
        trend: null
      };
    });

    // The original story predates the current GHG page labels. Read these
    // aliases from the dashboard's already-rendered, API-backed KPI cards.
    function alias(title, source) {
      if (map[source]) map[title] = Object.assign({}, map[source]);
    }
    // Same governed metric (estimated_avoided_grid_emissions_tco2e): the GHG
    // page card, or an 'Estimated avoided grid emissions' card where one exists.
    alias('Emission avoided', 'Reduction through renewables');
    alias('Emission avoided', 'Estimated avoided grid emissions');
    alias('Per capita emissions', 'Operational GHG per capita');

    // The former gross-footprint KPI now lives in the governed hero card.
    // It is the API-published Operational GHG value, not a browser sum.
    var grossEl = document.querySelector('#ghgKpis .ghg-top .counter-val');
    var grossValue = grossEl ? parseFloat(grossEl.getAttribute('data-val')) : NaN;
    var grossSource = document.querySelector('#ghgKpis .ghg-top .kpi-source');
    map['Total carbon footprint (gross)'] = {
      provenance: grossSource ? grossSource.textContent.trim() : '',
      value: isFinite(grossValue) ? grossValue : null,
      dec: grossEl ? parseInt(grossEl.getAttribute('data-dec'), 10) || 2 : 2,
      unit: 'tCO₂e',
      na: !isFinite(grossValue),
      statusText: '',
      accent: '#b8623a',
      video: null,
      trend: null
    };
    return map;
  }

  function periodText() {
    var p = document.getElementById('periodText');
    if (!p) return '';
    return p.textContent.replace(/^Viewing\s+/i, '').split('·')[0].trim();
  }

  /* ------------------------------------------------------------------
     Build one act
     ------------------------------------------------------------------ */

  function buildStage(cfg, i, total) {
    var centered = cfg.kind === 'intro' || cfg.kind === 'outro';
    var stage = el('section', 'wt-stage wt-act-' + i + (centered ? ' wt-centered' : '') + (i === total - 1 ? ' wt-act-last' : ''));
    stage.style.setProperty('--a', cfg.accent);
    stage.style.zIndex = String(i + 1);

    /* plate --------------------------------------------------------- */
    var plate = el('div', 'wt-plate');
    var media;
    if (cfg.video) {
      // a still, if provided, is laid underneath as an instant poster so a
      // large clip never opens on an empty plate — it fades to video on load
      if (cfg.still) {
        var poster = el('div', 'wt-media wt-poster');
        poster.style.backgroundImage = 'url("' + cfg.still + '")';
        requestAnimationFrame(function () { poster.classList.add('is-ready'); });
        plate.appendChild(poster);
      }
      media = document.createElement('video');
      media.className = 'wt-media';
      media.muted = true;
      media.loop = true;
      media.playsInline = true;
      media.preload = 'none';
      media.setAttribute('muted', '');
      media.setAttribute('playsinline', '');
      media.setAttribute('aria-hidden', 'true');
      media.dataset.src = cfg.video;
      media.addEventListener('loadeddata', function () { media.classList.add('is-ready'); }, { once: true });
    } else {
      media = el('div', 'wt-media');
      media.style.backgroundImage = 'url("' + cfg.still + '")';
    }
    // videos sit inside a wrapper so the pointer parallax can move the
    // pair (original + loop twin) as one — a dissolve mid-parallax must
    // not jump sideways
    var mediaWrap = null;
    if (media.tagName === 'VIDEO') {
      mediaWrap = el('div', 'wt-mwrap');
      mediaWrap.appendChild(media);
      plate.appendChild(mediaWrap);
      makeSeamless(media);
    } else {
      plate.appendChild(media);
    }
    plate.appendChild(el('div', 'wt-grade'));
    var haze = el('div', 'wt-haze');
    plate.appendChild(haze);
    var shafts = [];
    if (cfg.kind === 'kpi' && (cfg.n === 2 || cfg.n === 3)) {   // the two energy acts
      for (var si = 0; si < 2; si++) {
        var sh = el('div', 'wt-shaft');
        sh.style.left = (18 + si * 34) + '%';
        plate.appendChild(sh);
        shafts.push(sh);
      }
    }
    plate.appendChild(el('div', 'wt-vignette'));
    plate.appendChild(el('div', 'wt-scrim'));
    var edge = el('div', 'wt-edge');
    plate.appendChild(edge);
    stage.appendChild(plate);

    /* copy ---------------------------------------------------------- */
    var copy = el('div', 'wt-copy');
    copy.appendChild(el('div', 'wt-rule'));

    var eyebrow = el('div', 'wt-eyebrow');
    if (cfg.kind === 'kpi') {
      eyebrow.appendChild(el('span', 'wt-idx', String(cfg.n).padStart(2, '0')));
      eyebrow.appendChild(el('span', 'wt-sep', '/'));
      eyebrow.appendChild(el('span', null, '08'));
      eyebrow.appendChild(el('span', 'wt-sep', '·'));
      eyebrow.appendChild(el('span', 'wt-name', cfg.title));
    } else {
      eyebrow.appendChild(el('span', 'wt-name', cfg.eyebrow));
    }
    copy.appendChild(eyebrow);
    copy.appendChild(el('div', 'wt-hair'));

    var head = el('h2', 'wt-head');
    cfg.head.forEach(function (line) {
      var wrap = el('span', 'wt-line');
      wrap.appendChild(el('i', null, line));
      head.appendChild(wrap);
    });
    copy.appendChild(head);

    var valEl = null, valLine = null, ledger = null;
    if (cfg.ledger) {
      // Two independent published measures; never an arithmetic ledger.
      var lg = el('div', 'wt-ledger');
      var rows = cfg.ledger.rows;
      ledger = { nums: [], vals: rows.map(function (r) { return r.v; }), rows: [] };
      rows.forEach(function (r) {
        var row = el('div', 'wt-ledger-row');
        var key = el('span', 'k', r.k);
        if (r.provenance) key.appendChild(el('small', 'wt-source', ' · ' + r.provenance));
        row.appendChild(key);
        var num = el('span', 'n', fmtNum(0, cfg.dec));
        num.appendChild(el('small', null, ' tCO₂e'));
        row.appendChild(num);
        lg.appendChild(row);
        ledger.rows.push(row);
        ledger.nums.push(num);
      });
      copy.appendChild(lg);
      ledger.root = lg;
    } else if (cfg.value != null || cfg.na) {
      var metric = el('div', 'wt-metric');
      valEl = el('span', 'wt-val', cfg.na ? '—' : fmtNum(0, cfg.dec));
      metric.appendChild(valEl);
      if (!cfg.na) metric.appendChild(el('span', 'wt-unit', cfg.unit));
      valLine = el('div', 'wt-val-line');
      metric.appendChild(valLine);
      copy.appendChild(metric);
      if (cfg.provenance) copy.appendChild(el('div', 'wt-source', cfg.provenance));
    }

    var def = el('p', 'wt-def');
    cfg.def.split(/\s+/).forEach(function (w, wi) {
      if (wi) def.appendChild(document.createTextNode(' '));
      def.appendChild(el('span', 'wt-w', w));
    });
    copy.appendChild(def);

    var equiv = null;
    if (cfg.equiv) {
      equiv = el('div', 'wt-equiv');
      equiv.appendChild(el('span', 'wt-equiv-sign', '≈'));
      var eqText = el('span');
      eqText.innerHTML = cfg.equiv;      // built by equivFor(); only <b> tags inside
      equiv.appendChild(eqText);
      copy.appendChild(equiv);
    }

    var chipList = (cfg.chips || []).slice();
    if (cfg.trend) chipList.push(cfg.trend);
    if (chipList.length) {
      var chips = el('div', 'wt-chips');
      chipList.forEach(function (c) {
        var isObj = typeof c === 'object';
        chips.appendChild(el('span', 'wt-chip' + (isObj ? ' ' + c.cls : ''), isObj ? c.text : c));
      });
      copy.appendChild(chips);
    }

    if (cfg.kind === 'intro') {
      var sub = el('div', 'wt-sub');
      sub.appendChild(el('span', 'wt-chip', periodText() || 'Current period'));
      copy.appendChild(sub);
    }

    if (cfg.kind === 'outro') {
      var cta = el('button', 'wt-cta', 'Return to dashboard');
      cta.type = 'button';
      cta.addEventListener('click', closeStory);
      copy.appendChild(cta);
    }

    stage.appendChild(copy);

    return {
      cfg: cfg, stage: stage, plate: plate, media: media, mediaWrap: mediaWrap, copy: copy,
      haze: haze, edge: edge, shafts: shafts, equiv: equiv,
      valEl: valEl, valLine: valLine, ledger: ledger,
      value: (cfg.ledger || cfg.na) ? null : (cfg.value != null ? cfg.value : null),
      dec: cfg.dec || 0, centered: centered,
      eyebrow: eyebrow, head: head, def: def,
      rule: copy.querySelector('.wt-rule'),
      hair: copy.querySelector('.wt-hair'),
      metric: copy.querySelector('.wt-metric'),
      chipsEl: copy.querySelector('.wt-chips')
    };
  }

  /* ------------------------------------------------------------------
     Assemble the acts from live data
     ------------------------------------------------------------------ */

  function composeConfigs() {
    var cards = readCards();
    var list = [];

    var intro = Object.assign({}, INTRO);
    list.push(intro);

    // An act whose figure has no trustworthy number for this selection is
    // skipped - the story never shows "Unavailable" or a placeholder.
    var shown = 0;
    WT_STORY.forEach(function (s, i) {
      var c = cards[s.title];
      if (s.title === 'Where We Stand') {
        var ledgerRows = [
          { k: 'Operational GHG', card: cards['Total carbon footprint (gross)'] },
          { k: 'Estimated avoided grid emissions', card: cards['Emission avoided'] }
        ].filter(function (row) { return row.card && !row.card.na && row.card.value != null; })
          .map(function (row) { return { k: row.k, v: row.card.value, provenance: row.card.provenance }; });
        if (!ledgerRows.length) return;
        shown += 1;
        list.push({
          kind: 'kpi', n: shown, title: s.title, head: s.head, def: s.def,
          chips: s.chips, video: s.video, accent: '#1c7a4b', na: false,
          dec: 3, unit: 'tCO₂e', ledger: { rows: ledgerRows }
        });
        return;
      }
      if (!c || c.na || c.value == null) return;
      var na = false;
      shown += 1;
      list.push({
        kind: 'kpi',
        n: shown,
        provenance: c.provenance,
        title: s.title,
        head: s.head,
        def: s.def,
        chips: s.chips,
        video: s.storyVideo || (c && c.video) || s.video,
        accent: (c && c.accent) || '#1c7a4b',
        value: c ? c.value : null,
        dec: c ? c.dec : 2,
        unit: c ? c.unit : '',
        na: na,
        equiv: (c && !na) ? equivFor(i + 1, c.value) : null,
        trend: c ? c.trend : null
      });
    });

    var outro = Object.assign({}, OUTRO, {
      na: false,
      def: OUTRO.lead
    });
    list.push(outro);

    return list;
  }

  /* ------------------------------------------------------------------
     Animation
     ------------------------------------------------------------------ */

  function textParts(a) {
    return {
      lines: a.head.querySelectorAll('.wt-line > i'),
      words: a.def.querySelectorAll('.wt-w'),
      chips: a.copy.querySelectorAll('.wt-chip'),   // .wt-chips and the intro's .wt-sub
      metric: a.metric,
      equiv: a.equiv,
      ledger: a.ledger,
      eyebrow: a.eyebrow,
      hair: a.hair,
      rule: a.rule,
      cta: a.copy.querySelector('.wt-cta')
    };
  }

  function primeText(a) {
    var p = textParts(a);
    gsap.set(p.lines, { yPercent: 112, rotate: 3, opacity: 0, transformOrigin: '0% 100%' });
    gsap.set(p.words, { y: 16, opacity: 0, filter: 'blur(6px)' });
    if (p.chips.length) gsap.set(p.chips, { y: 14, opacity: 0 });
    if (p.metric) gsap.set(p.metric, { y: 26, opacity: 0 });
    if (p.ledger) gsap.set(p.ledger.rows, { y: 18, opacity: 0 });
    if (p.cta) gsap.set(p.cta, { y: 18, opacity: 0 });
    gsap.set(p.eyebrow, { clipPath: 'inset(0 100% 0 0)' });
    gsap.set(p.hair, { width: 0 });
    gsap.set(p.rule, { scaleY: 0 });
  }

  // one number counting inside a reveal timeline (not scroll-scrubbed)
  function countTween(numEl, target, dec, duration, opts) {
    var o = { v: 0 };
    return gsap.to(o, {
      v: target, duration: duration, ease: 'power2.out',
      onUpdate: function () { numEl.childNodes[0].nodeValue = fmtNum(o.v, dec); },
      onComplete: opts && opts.onComplete,
      onReverseComplete: opts && opts.onReverseComplete
    });
  }

  function revealText(a) {
    var p = textParts(a);
    var hairTo = a.centered ? 260 : '100%';

    if (REDUCED) {
      var tl0 = gsap.timeline();
      tl0.set(nodes(p.lines, p.words, p.chips, p.metric, p.cta, p.ledger && p.ledger.rows),
        { yPercent: 0, y: 0, rotate: 0, opacity: 1, filter: 'blur(0px)' });
      tl0.set(p.eyebrow, { clipPath: 'inset(0 0% 0 0)' });
      tl0.set(p.hair, { width: hairTo });
      tl0.set(p.rule, { scaleY: 1 });
      if (p.ledger) {
        p.ledger.nums.forEach(function (numEl, k) {
          numEl.childNodes[0].nodeValue = fmtNum(p.ledger.vals[k], a.dec);
        });
      } else if (a.value != null && a.valEl) {
        a.valEl.childNodes[0].nodeValue = fmtNum(a.value, a.dec);
      }
      return tl0;
    }

    var tl = gsap.timeline({ defaults: { ease: 'expo.out' } });
    tl.to(p.eyebrow, { clipPath: 'inset(0 0% 0 0)', duration: .95 }, 0)
      .to(p.rule, { scaleY: 1, duration: 1.15 }, .04)
      .to(p.hair, { width: hairTo, duration: 1.25 }, .12)
      .to(p.lines, { yPercent: 0, rotate: 0, opacity: 1, duration: 1.15, stagger: .09 }, .10);
    if (p.metric) tl.to(p.metric, { y: 0, opacity: 1, duration: .95, ease: 'power3.out' }, .40);
    if (!p.ledger && a.value != null && a.valEl) {
      // Counts up once, on the discrete section-enter reveal - not tied to
      // scroll position, so the number never shows an intermediate/"wrong"
      // value while scrolling around inside the act. Settles and stays put
      // until the act is left/re-entered.
      tl.add(countTween(a.valEl, a.value, a.dec, .9, {
        onComplete: function () { lockIn(a); },
        onReverseComplete: function () { if (a.valLine) gsap.set(a.valLine, { width: 0 }); }
      }), .40);
    }
    tl.to(p.words, { y: 0, opacity: 1, filter: 'blur(0px)', duration: .8, stagger: .012, ease: 'power2.out' }, .48);
    if (p.equiv) tl.to(p.equiv, { clipPath: 'inset(0 0% 0 0)', duration: .9, ease: 'power2.inOut' }, .78);
    if (p.chips.length) tl.to(p.chips, { y: 0, opacity: 1, duration: .7, stagger: .06, ease: 'power2.out' }, .74);
    if (p.cta) tl.to(p.cta, { y: 0, opacity: 1, duration: .8, ease: 'power3.out' }, .86);

    if (p.ledger) {
      // Reveal each independent published figure without combining them.
      var lg = p.ledger;
      tl.to(lg.rows, { y: 0, opacity: 1, duration: .7, stagger: .14, ease: 'power3.out' }, .35);
      lg.nums.forEach(function (num, index) {
        tl.add(countTween(num, lg.vals[index], a.dec, .8), .55 + index * .5);
      });
    }
    return tl;
  }

  // one-shot pulse when the scrubbed number settles on its final value
  function lockIn(a) {
    if (REDUCED || !a.valLine || !a.metric || !a.valEl) return;
    gsap.timeline()
      .to(a.metric, { scale: 1.045, duration: .16, ease: 'power2.out' }, 0)
      .to(a.metric, { scale: 1, duration: .5, ease: 'power2.inOut' }, .16);
    gsap.fromTo(a.valLine, { width: 0 },
      { width: (a.valEl.offsetWidth || 120) + 'px', duration: .7, ease: 'expo.out' });
  }

  function buildScrub(a, i, last) {
    var isFirst = i === 0;
    var isLast = i === last;
    var cue = cues[i];

    var tl = gsap.timeline({
      scrollTrigger: { scroller: scroller, trigger: cue, start: 'top bottom', end: 'bottom top', scrub: REDUCED ? true : 1 },
      defaults: { ease: 'none' }
    });

    // Every position below is written as a fraction of the act's scroll range,
    // which only holds if the timeline is exactly 1 unit long. The closing act
    // has no exit tweens, so without this spacer its duration would collapse to
    // the end of its last tween and GSAP would stretch every position to fit.
    tl.to({}, { duration: 1 }, 0);

    if (isFirst) {
      gsap.set(a.copy, { opacity: 1 });
      if (!REDUCED) tl.fromTo(a.mediaWrap || a.media, { scale: 1.06 }, { scale: 1.14, duration: .58, ease: 'sine.out' }, 0);
    } else if (!REDUCED) {
      // Pure cross-dissolve on compositor-only properties (opacity/transform):
      // seamless by construction, and cheap enough to stay fluid on ordinary
      // GPUs. The incoming stage reaches near-solid quickly (sine.out) while
      // the outgoing one below fades late (power1.in), so the blend never
      // visibly dips to black.
      tl.fromTo(a.stage, { opacity: 0 }, { opacity: 1, duration: .45, ease: 'sine.out' }, 0)
        // one continuous deceleration ending exactly where the exit push (.58)
        // takes over — the frame is never still and no two tweens share `scale`
        .fromTo(a.mediaWrap || a.media, { scale: 1.16, yPercent: 5 },
          { scale: 1.02, yPercent: 0, duration: .58, ease: 'sine.out' }, 0)
        // the glow band sweeps with the dissolve — transform only, static blur
        .fromTo(a.edge, { yPercent: 0 }, { yPercent: -525, duration: .55, ease: 'sine.inOut' }, 0)
        .fromTo(a.edge, { opacity: 0 }, { opacity: .45, duration: .22, ease: 'sine.in' }, .05)
        .to(a.edge, { opacity: 0, duration: .26, ease: 'sine.out', immediateRender: false }, .29)
        .fromTo(a.copy, { opacity: 0, y: 60 },
          { opacity: 1, y: 0, duration: .40, ease: 'power2.out' }, .08);
    } else {
      // reduced motion: opacity-only crossfade, scrubbed both ways
      tl.fromTo(a.stage, { opacity: 0 }, { opacity: 1, duration: .45 }, 0)
        .fromTo(a.copy, { opacity: 0 }, { opacity: 1, duration: .40 }, .05);
    }

    // The metric number itself is no longer driven by this scroll-scrubbed
    // timeline (that made it show partial/intermediate values while
    // scrolling). It's set once, statically, by the discrete section-enter
    // reveal in revealText() instead - see buildTriggers()'s onEnter/
    // onLeaveBack wiring.

    if (!isLast && !REDUCED) {
      // The outgoing act recedes by pushing INTO the frame and fading —
      // starting at .58 so it is always cross-blended with the incoming
      // dissolve; no static moment, no cut. No filter tweens: blurring a
      // playing video repaints it every scroll frame. The copy leaves in
      // depth-ordered layers rather than as one slab.
      var exitLayers = [
        [a.eyebrow, -104], [a.head, -92],
        [a.ledger ? a.ledger.root : a.metric, -74],
        [a.def, -56], [a.equiv, -48], [a.chipsEl, -40]
      ];
      tl.to(a.mediaWrap || a.media, { scale: 1.12, duration: .42, immediateRender: false }, .58)
        .to(a.stage, { opacity: 0, duration: .42, ease: 'power1.in', immediateRender: false }, .58)
        .to(a.copy, { opacity: 0, duration: .34, ease: 'power1.in', immediateRender: false }, .60);
      exitLayers.forEach(function (L) {
        if (L[0]) tl.to(L[0], { y: L[1], duration: .40, ease: 'power1.in', immediateRender: false }, .58);
      });
    } else if (!isLast && REDUCED) {
      tl.to(a.stage, { opacity: 0, duration: .35, immediateRender: false }, .58);
    }

    return tl;
  }

  /* ------------------------------------------------------------------
     Media + chapter state
     ------------------------------------------------------------------ */

  /* ------------------------------------------------------------------
     Seamless looping. A bare `loop` attribute stutters at the wrap
     point (decoder seek back to 0 + first/last frames that don't
     match). Each looping video gets a hidden twin of the same file;
     just before the end the twin starts from 0 and dissolves in over
     the still-playing original, then they swap roles — an unbroken
     infinite loop with no gap and no jump cut. `loop` stays on both as
     a safety net: if the twin isn't ready in time, the native wrap
     happens invisibly underneath and we try again next cycle.
     ------------------------------------------------------------------ */
  var LOOP_FADE = 0.45;               // dissolve duration — matches .wt-loop-twin's transition
  var LOOP_COVER = LOOP_FADE + 0.45;  // twin rises this early so it is opaque before the wrap

  function makeSeamless(v) {
    if (!v || v._wtLoop) return;

    var twin = document.createElement('video');
    twin.className = v.className.replace(/\bis-ready\b/, '').trim() + ' wt-loop-twin';
    twin.muted = true; twin.loop = true; twin.playsInline = true;
    twin.preload = 'none';
    twin.setAttribute('muted', ''); twin.setAttribute('playsinline', '');
    twin.setAttribute('aria-hidden', 'true');
    v.parentNode.insertBefore(twin, v.nextSibling);   // paints just above v, below the grade layers

    // The original v stays the master the dashboard/story talks to — it
    // is ALWAYS the playing element, so external play()/pause()/seeks
    // behave exactly as without the twin. Around each wrap:
    //   phase 1 — twin starts at 0 and dissolves up, hiding v's native
    //             loop stutter beneath it;
    //   phase 2 — the hidden v is re-aligned to the twin's clock, the
    //             twin dissolves away, and v carries on. If the server
    //             can't seek (no Range support), the handback still
    //             happens — just as a soft dissolve instead of an exact
    //             frame match.
    var st = { phase: 0, timer: 0 };
    v._wtLoop = st;

    function srcOf(x) {
      var s = x.currentSrc || x.getAttribute('src');
      if (!s) { var so = x.querySelector('source'); s = so && so.getAttribute('src'); }
      return s || '';
    }
    st.syncSrc = function () {
      var s = srcOf(v);
      if (s && !twin.getAttribute('src')) { twin.preload = 'auto'; twin.setAttribute('src', s); twin.load(); }
    };
    v.addEventListener('loadeddata', st.syncSrc);
    st.syncSrc();

    function stop() {                       // idle: twin dark, paused
      if (st.timer) { clearTimeout(st.timer); st.timer = 0; }
      st.phase = 0;
      twin.classList.remove('wt-loop-in');
      if (!twin.paused) twin.pause();
    }
    // v pausing or (re)starting is always the outside world's doing —
    // the controller itself never calls play/pause on v
    v.addEventListener('pause', stop);
    v.addEventListener('play', function () {
      stop();
      try { twin.currentTime = 0; } catch (e) {}
    });

    function tick() {
      if (v.paused || !isFinite(v.duration) || v.duration < LOOP_COVER * 3) return;

      if (st.phase === 0) {
        var left = v.duration - v.currentTime;
        if (left > LOOP_COVER + 0.35) return;           // slack for timeupdate granularity
        if (twin.readyState < 2) { st.syncSrc(); return; }  // not ready: native wrap this lap
        st.phase = 1;
        try { twin.currentTime = 0; } catch (e) {}
        var p = twin.play(); if (p && p.catch) p.catch(function () {});
        twin.classList.add('wt-loop-in');

      } else if (st.phase === 1) {
        // once v is younger than the twin it has wrapped (invisibly)
        if (v.currentTime < twin.currentTime && twin.currentTime > LOOP_FADE + 0.15) {
          st.phase = 2;
          var target = Math.min(twin.currentTime + 0.05, v.duration - 1);
          var done = function () {
            v.removeEventListener('seeked', done);
            if (st.phase !== 2) return;
            // hold the opaque cover a beat so the master's restart is
            // fully settled before it starts showing through
            st.timer = setTimeout(function () {
              if (st.phase !== 2) return;
              twin.classList.remove('wt-loop-in');      // dissolve back to the master
              st.timer = setTimeout(function () {
                st.timer = 0;
                if (st.phase !== 2) return;
                st.phase = 0;
                if (!twin.paused) twin.pause();
                try { twin.currentTime = 0; } catch (e) {}
              }, LOOP_FADE * 1000 + 80);
            }, 120);
          };
          v.addEventListener('seeked', done);
          try { v.currentTime = target; } catch (e) { done(); }
        }
      }
    }
    v.addEventListener('timeupdate', tick);
    twin.addEventListener('timeupdate', tick);
  }

  function ensureSrc(i) {
    var a = acts[i];
    if (!a) return;
    var m = a.media;
    if (m && m.tagName === 'VIDEO' && !m.getAttribute('src') && m.dataset.src) {
      m.setAttribute('src', m.dataset.src);
      m.load();
      if (m._wtLoop) m._wtLoop.syncSrc();
    }
  }

  function setActive(i) {
    if (i === activeIdx) return;
    var prev = activeIdx;
    activeIdx = i;

    for (var j = i - 1; j <= i + 1; j++) if (j >= 0 && j < acts.length) ensureSrc(j);

    // Only the active act and its neighbours exist for the compositor.
    // Ten stacked full-screen stages (video + gradient layers each) being
    // kept as live GPU layers was a major stutter source.
    acts.forEach(function (a, k) {
      a.stage.style.visibility = Math.abs(k - i) <= 1 ? '' : 'hidden';
    });

    // A video plays ONLY while its act is the current one, and it starts
    // from the top each time you scroll onto the page — never left running
    // or resuming mid-clip in the background. setActive only fires on an
    // index change, so dwelling on an act never restarts it.
    acts.forEach(function (a, k) {
      if (a.media.tagName !== 'VIDEO') return;
      if (k === i && !REDUCED) {
        try { a.media.currentTime = 0; } catch (e) {}
        var p = a.media.play();
        if (p && p.catch) p.catch(function () {});
      } else if (!a.media.paused) {
        a.media.pause();
      }
    });

    var accent = acts[i].cfg.accent;
    rail.querySelectorAll('.wt-tick').forEach(function (t, k) { t.classList.toggle('is-on', k === i); });
    if (!REDUCED) {
      setWash(accent);
      // the atmosphere and chrome follow the new act's colour
      moteTarget = hexToRgb(accent);
      moteBiasTarget = moteBiasFor(i);
      gsap.to(barEls, { backgroundColor: hexMix(accent, '#070c09', .12), duration: 1.2, ease: 'power2.inOut' });
    }
    if (prev >= 0) relaxParallax(prev);
    buildParallax(i);

    hint.classList.toggle('is-on', i === 0 && scroller.scrollTop < 60);
  }

  function setWash(color) {
    var inEl = washes[washTop ^ 1], outEl = washes[washTop];
    inEl.style.setProperty('--c', color);
    gsap.to(inEl, { opacity: .07, duration: 1.2, ease: 'power2.inOut', overwrite: true });
    gsap.to(outEl, { opacity: 0, duration: 1.2, ease: 'power2.inOut', overwrite: true });
    washTop ^= 1;
  }

  function onScroll() {
    if (scrollRaf) return;
    scrollRaf = requestAnimationFrame(function () {
      scrollRaf = 0;
      var top = scroller.scrollTop;
      // scrolling lends the motes a small impulse (capped — a breath, not a gust)
      moteImpulse = Math.max(-26, Math.min(26, moteImpulse + (top - lastScrollTop) * .22));
      lastScrollTop = top;

      var vh = scroller.clientHeight || 1;
      var cueH = vh * 1.6;
      var i = Math.floor((top + vh * 0.5) / cueH);
      i = Math.max(0, Math.min(acts.length - 1, i));
      setActive(i);
      if (activeIdx === 0) hint.classList.toggle('is-on', top < 60);
    });
  }

  /* ------------------------------------------------------------------
     Atmosphere — ONE rAF loop drives both the film grain (~12fps) and
     the sparse accent motes (every frame). The motes are deliberately
     minimal: ~26 slow, near-invisible blobs, felt as air rather than
     noticed as an effect. All raster; no SVG. The browser suspends rAF
     entirely for hidden tabs, which is our background pause.
     ------------------------------------------------------------------ */

  var grainPatterns = null, grainLast = 0, grainFrame = 0, atmoLast = 0;
  var motes = [], moteTile = null;
  var moteTint = { r: 28, g: 122, b: 75 }, moteTarget = { r: 28, g: 122, b: 75 };
  var moteBias = 0, moteBiasTarget = 0;

  function sizeAtmo() {
    [grainCanvas, motesCanvas].forEach(function (cv) {
      if (!cv) return;
      cv.width = Math.max(1, cv.clientWidth);
      cv.height = Math.max(1, cv.clientHeight);
    });
    grainPatterns = null;
  }

  function hexToRgb(hex) {
    var m = /^#([0-9a-f]{6})$/i.exec((hex || '').trim());
    if (!m) return { r: 28, g: 122, b: 75 };
    return {
      r: parseInt(m[1].substr(0, 2), 16),
      g: parseInt(m[1].substr(2, 2), 16),
      b: parseInt(m[1].substr(4, 2), 16)
    };
  }

  function initMotes() {
    var n = window.innerWidth < 900 ? 16 : 30;
    motes = [];
    for (var i = 0; i < n; i++) {
      motes.push({
        x: Math.random(), y: Math.random(),           // normalized; scaled at draw
        size: 3 + Math.pow(Math.random(), 1.5) * 27,  // small ones dominate
        alpha: .07 + Math.random() * .11,
        vx: (Math.random() - .5) * 7,                 // px/s — a crossing takes minutes
        vy: (Math.random() - .5) * 6,
        phase: Math.random() * Math.PI * 2,
        wobble: .4 + Math.random() * .8
      });
    }
  }

  function moteTileFor(tint) {
    // pre-rendered soft blob; the accent is lifted ~40% toward white so the
    // motes actually read against dark footage while staying quiet
    var t = document.createElement('canvas');
    t.width = t.height = 64;
    var c = t.getContext('2d');
    var lift = function (v) { return Math.round(v + (255 - v) * .4); };
    var rgb = lift(tint.r) + ',' + lift(tint.g) + ',' + lift(tint.b);
    var g = c.createRadialGradient(32, 32, 0, 32, 32, 32);
    g.addColorStop(0, 'rgba(' + rgb + ',1)');
    g.addColorStop(.45, 'rgba(' + rgb + ',.55)');
    g.addColorStop(1, 'rgba(' + rgb + ',0)');
    c.fillStyle = g;
    c.fillRect(0, 0, 64, 64);
    return t;
  }

  function atmoTick(t) {
    if (!open || REDUCED) { atmoRaf = 0; return; }
    atmoRaf = requestAnimationFrame(atmoTick);
    atmoFrames++;
    var dt = Math.min(.06, (t - atmoLast) / 1000 || .016);
    atmoLast = t;

    /* ---- grain, ~12fps ---- */
    if (t - grainLast >= 83) {
      grainLast = t;
      var ctx = grainCanvas.getContext('2d');
      if (!grainPatterns) {
        grainPatterns = [];
        for (var i = 0; i < 4; i++) {
          var tile = document.createElement('canvas');
          tile.width = tile.height = 128;
          var tc = tile.getContext('2d');
          var img = tc.createImageData(128, 128);
          for (var p = 0; p < img.data.length; p += 4) {
            var v = 96 + Math.random() * 64;
            img.data[p] = img.data[p + 1] = img.data[p + 2] = v;
            img.data[p + 3] = 255;
          }
          tc.putImageData(img, 0, 0);
          grainPatterns.push(ctx.createPattern(tile, 'repeat'));
        }
      }
      grainFrame = (grainFrame + 1) % 4;
      ctx.setTransform(1, 0, 0, 1, -(Math.random() * 128 | 0), -(Math.random() * 128 | 0));
      ctx.fillStyle = grainPatterns[grainFrame];
      ctx.fillRect(0, 0, grainCanvas.width + 128, grainCanvas.height + 128);
    }

    /* ---- motes, every frame ---- */
    var k = Math.min(1, dt * 1.6);                    // tint drifts over ~1.5s
    moteTint.r += (moteTarget.r - moteTint.r) * k;
    moteTint.g += (moteTarget.g - moteTint.g) * k;
    moteTint.b += (moteTarget.b - moteTint.b) * k;
    var tintDelta = Math.abs(moteTint.r - moteTarget.r) + Math.abs(moteTint.g - moteTarget.g) + Math.abs(moteTint.b - moteTarget.b);
    if (!moteTile || (tintDelta > 4 && atmoFrames % 4 === 0)) moteTile = moteTileFor(moteTint);

    moteBias += (moteBiasTarget - moteBias) * Math.min(1, dt * 1.2);
    moteImpulse *= Math.exp(-dt / .8);                // a breath, ~2s to fade

    var mc = motesCanvas.getContext('2d');
    var W = motesCanvas.width, H = motesCanvas.height;
    mc.clearRect(0, 0, W, H);
    mc.globalCompositeOperation = 'lighter';
    for (var j = 0; j < motes.length; j++) {
      var m = motes[j];
      m.phase += dt * m.wobble;
      m.x += (m.vx * dt) / W;
      m.y += ((m.vy + moteBias - moteImpulse) * dt) / H;
      if (m.x < -.06) m.x += 1.12; else if (m.x > 1.06) m.x -= 1.12;
      if (m.y < -.06) m.y += 1.12; else if (m.y > 1.06) m.y -= 1.12;
      mc.globalAlpha = m.alpha;
      var s = m.size;
      mc.drawImage(moteTile, m.x * W + Math.sin(m.phase) * 6 - s / 2, m.y * H - s / 2, s, s);
    }
    mc.globalAlpha = 1;
    mc.globalCompositeOperation = 'source-over';
  }

  // gentle per-act vertical drift bias (px/s): emissions rise, green settles
  function moteBiasFor(i) {
    if (i === 1 || i === 5 || i === 6) return -4;     // gross, scope 1, scope 2
    if (i === 3 || i === 4) return 2;                 // renewable, avoided
    return 0;
  }

  /* ------------------------------------------------------------------
     Pointer parallax + tilt — the active act's layers follow the cursor
     at different rates; retargeted on every act change. Desktop only.
     ------------------------------------------------------------------ */

  function buildParallax(i) {
    px.qs = null;
    if (!FINE_POINTER || REDUCED) return;
    var a = acts[i];
    if (!a) return;
    var opts = { duration: .9, ease: 'power3' };
    var mediaT = a.mediaWrap || a.media;
    px.qs = {
      mx: gsap.quickTo(mediaT, 'x', opts), my: gsap.quickTo(mediaT, 'y', opts),
      hx: gsap.quickTo(a.haze, 'x', opts), hy: gsap.quickTo(a.haze, 'y', opts),
      cx: gsap.quickTo(a.copy, 'x', opts),
      crx: gsap.quickTo(a.copy, 'rotationX', opts),
      cry: gsap.quickTo(a.copy, 'rotationY', opts)
    };
  }

  function relaxParallax(i) {                          // outgoing act back to rest
    var a = acts[i];
    if (!a) return;
    gsap.to([a.mediaWrap || a.media, a.haze], { x: 0, y: 0, duration: .8, ease: 'power2.out' });
    gsap.to(a.copy, { x: 0, rotationX: 0, rotationY: 0, skewY: 0, duration: .8, ease: 'power2.out' });
  }

  function onPointerMove(e) {
    if (!open || !px.qs) return;
    var nx = (e.clientX / window.innerWidth) * 2 - 1;
    var ny = (e.clientY / window.innerHeight) * 2 - 1;
    px.qs.mx(nx * -14); px.qs.my(ny * -10);            // background: least, inverse
    px.qs.hx(nx * -26); px.qs.hy(ny * -18);            // haze: most — depth between
    px.qs.cx(nx * 10);                                 // copy: with the cursor
    px.qs.cry(nx * 1.2); px.qs.crx(ny * -0.9);         // ~1° cinematic tilt
  }

  /* ------------------------------------------------------------------
     Shell
     ------------------------------------------------------------------ */

  function buildShell() {
    overlay = el('div', null);
    overlay.id = 'wt-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'The Carbon Story — walkthrough of the eight overview metrics');
    if (REDUCED) overlay.classList.add('wt-reduced');

    scroller = el('div', null); scroller.id = 'wt-scroller';
    track = el('div', null); track.id = 'wt-track';
    frame = el('div', null); frame.id = 'wt-frame';
    track.appendChild(frame);
    scroller.appendChild(track);
    overlay.appendChild(scroller);

    motesCanvas = el('canvas', null); motesCanvas.id = 'wt-motes';
    motesCanvas.setAttribute('aria-hidden', 'true');
    overlay.appendChild(motesCanvas);

    washes = [el('div', 'wt-wash'), el('div', 'wt-wash')];
    washes.forEach(function (w) { overlay.appendChild(w); });

    grainCanvas = el('canvas', null); grainCanvas.id = 'wt-grain';
    grainCanvas.setAttribute('aria-hidden', 'true');
    overlay.appendChild(grainCanvas);

    chrome = el('div', null); chrome.id = 'wt-chrome';
    barEls = [el('div', 'wt-bar wt-bar-top'), el('div', 'wt-bar wt-bar-bot')];
    barEls.forEach(function (b) { chrome.appendChild(b); });

    var prog = el('div', null); prog.id = 'wt-progress';
    progressFill = el('i');
    prog.appendChild(progressFill);
    chrome.appendChild(prog);

    rail = el('div', null); rail.id = 'wt-rail';
    chrome.appendChild(rail);

    hint = el('div', null); hint.id = 'wt-hint';
    hint.appendChild(el('i'));
    hint.appendChild(el('span', null, 'Scroll'));
    chrome.appendChild(hint);

    var close = el('button', null); close.id = 'wt-close';
    close.type = 'button';
    close.setAttribute('aria-label', 'Close the walkthrough');
    close.addEventListener('click', closeStory);
    chrome.appendChild(close);

    overlay.appendChild(chrome);
    document.body.appendChild(overlay);

    // the rail and close button sit outside the scroller; forward the wheel
    [rail, close].forEach(function (n) {
      n.addEventListener('wheel', function (e) {
        scroller.scrollTop += e.deltaY;
        e.preventDefault();
      }, { passive: false });
    });

    scroller.addEventListener('scroll', onScroll, { passive: true });
  }

  function buildActs() {
    var cfgs = composeConfigs();
    frame.innerHTML = '';
    Array.prototype.slice.call(track.querySelectorAll('.wt-cue, .wt-tail')).forEach(function (n) { n.remove(); });
    rail.innerHTML = '';
    acts = []; cues = [];

    cfgs.forEach(function (cfg, i) {
      var a = buildStage(cfg, i, cfgs.length);
      frame.appendChild(a.stage);
      acts.push(a);

      var cue = el('div', 'wt-cue');
      cue.dataset.i = String(i);
      track.appendChild(cue);
      cues.push(cue);

      var tick = el('button', 'wt-tick');
      tick.type = 'button';
      tick.style.setProperty('--a', cfg.accent);
      tick.setAttribute('aria-label', 'Go to ' + (cfg.kind === 'kpi' ? cfg.title : cfg.head.join(' ')));
      tick.appendChild(el('i'));
      tick.addEventListener('click', function () {
        scroller.scrollTo({ top: i * scroller.clientHeight * 1.6 + 1, behavior: REDUCED ? 'auto' : 'smooth' });
      });
      rail.appendChild(tick);
    });

    track.appendChild(el('div', 'wt-tail'));

    progressFill.style.backgroundImage =
      'linear-gradient(90deg,' + cfgs.map(function (c) { return c.accent; }).join(',') + ')';

    acts.forEach(function (a, k) {
      primeText(a);
      a.stage.style.visibility = k <= 1 ? '' : 'hidden';   // culled until near
      if (a.media.tagName === 'DIV') requestAnimationFrame(function () { a.media.classList.add('is-ready'); });
    });
  }

  function buildTriggers() {
    var last = acts.length - 1;

    acts.forEach(function (a, i) { tls.push(buildScrub(a, i, last)); });

    // discrete copy reveals — deliberate, not smeared across the scrub
    acts.forEach(function (a, i) {
      if (i === 0) return;                                  // the title card reveals on open
      var tl = revealText(a);
      tl.pause(0);
      ST.create({
        scroller: scroller, trigger: cues[i],
        start: 'top top', end: 'bottom top',
        onEnter: function () { tl.play(); },
        onLeaveBack: function () { tl.reverse(); }
      });
      tls.push(tl);
    });

    var skewProxy = { v: 0 };
    tls.push(ST.create({
      scroller: scroller, trigger: track,
      start: 'top top', end: 'bottom bottom',
      onUpdate: function (self) {
        progressFill.style.width = (self.progress * 100).toFixed(2) + '%';
        if (REDUCED) return;
        // the type leans into the scroll, springing back on settle
        var s = gsap.utils.clamp(-2.2, 2.2, self.getVelocity() / -320);
        if (Math.abs(s) > Math.abs(skewProxy.v)) {
          skewProxy.v = s;
          gsap.to(skewProxy, {
            v: 0, duration: .9, ease: 'power3', overwrite: true,
            onUpdate: function () {
              var a = acts[activeIdx];
              if (a) gsap.set(a.copy, { skewY: skewProxy.v });
            }
          });
        }
      }
    }));
  }

  function killTriggers() {
    tls.forEach(function (t) {
      if (t && t.scrollTrigger) t.scrollTrigger.kill();
      if (t && t.kill) t.kill();
    });
    tls = [];
    fxTweens.forEach(function (t) { t.kill(); });
    fxTweens = [];
    px.qs = null;
    // parallax quickTos / lock-in pulses may still target act elements
    gsap.killTweensOf(frame.querySelectorAll('*'));
    ST.getAll().forEach(function (st) { if (st.scroller === scroller) st.kill(); });
  }

  /* ------------------------------------------------------------------
     Open / close
     ------------------------------------------------------------------ */

  function syncVh() {
    if (!overlay) return;
    overlay.style.setProperty('--wt-vh', scroller.clientHeight + 'px');
  }

  function dashboardEls() {
    return Array.prototype.slice.call(
      document.querySelectorAll('.topbar, .toolbar, .page.active, .bottom-dock-wrapper')
    );
  }

  /* ------------------------------------------------------------------
     Mobile landscape gate. On a small touch device the story only plays
     in landscape: opening it in portrait shows a "rotate your phone"
     prompt instead, and rotating to landscape starts it. Rotating back
     to portrait mid-story exits to the dashboard. On browsers that
     allow it (Android, fullscreen) the orientation is locked.
     ------------------------------------------------------------------ */
  var PORTRAIT_MQ = window.matchMedia ? window.matchMedia('(orientation: portrait)') : null;
  var gate = null, gateOn = false, ownFullscreen = false;

  function isSmallTouch() {
    return window.matchMedia && window.matchMedia('(pointer: coarse)').matches &&
      Math.min(window.screen.width, window.screen.height) < 900;
  }

  function gateKey(e) { if (e.key === 'Escape') { e.preventDefault(); hideGate(); } }

  function buildGate() {
    gate = el('div', 'wt-rotate-gate');
    gate.setAttribute('role', 'dialog');
    gate.setAttribute('aria-label', 'Rotate your phone to play the Carbon Story');
    gate.innerHTML =
      '<button class="wt-gate-x" aria-label="Not now">&times;</button>' +
      '<div class="wt-gate-phone" aria-hidden="true"><i></i></div>' +
      '<div class="wt-gate-title">Turn your phone sideways</div>' +
      '<div class="wt-gate-sub">The Carbon Story plays in landscape</div>';
    gate.querySelector('.wt-gate-x').addEventListener('click', hideGate);
    document.body.appendChild(gate);
  }
  function showGate() {
    if (!gate) buildGate();
    gateOn = true;
    gate.classList.add('is-on');
    document.addEventListener('keydown', gateKey, true);
  }
  function hideGate() {
    gateOn = false;
    if (gate) gate.classList.remove('is-on');
    document.removeEventListener('keydown', gateKey, true);
  }

  function onOrientation() {
    var portrait = PORTRAIT_MQ && PORTRAIT_MQ.matches;
    if (gateOn && !portrait) { hideGate(); startStory(); }
    else if (open && portrait && isSmallTouch()) closeStory();
  }
  if (PORTRAIT_MQ) {
    if (PORTRAIT_MQ.addEventListener) PORTRAIT_MQ.addEventListener('change', onOrientation);
    else if (PORTRAIT_MQ.addListener) PORTRAIT_MQ.addListener(onOrientation);
  }

  // Fullscreen + orientation lock: best effort, phone-only. Fails quietly
  // where unsupported (iOS Safari has no lock; lock needs fullscreen).
  function enterImmersive() {
    if (!isSmallTouch()) return;
    var lock = function () {
      try {
        if (screen.orientation && screen.orientation.lock) {
          var lp = screen.orientation.lock('landscape');
          if (lp && lp.catch) lp.catch(function () {});
        }
      } catch (e) {}
    };
    try {
      var root = document.documentElement;
      if (root.requestFullscreen) {
        var fp = root.requestFullscreen({ navigationUI: 'hide' });
        ownFullscreen = true;
        if (fp && fp.then) fp.then(lock, function () { lock(); });
        else lock();
      } else lock();
    } catch (e) {}
  }
  function exitImmersive() {
    try { if (screen.orientation && screen.orientation.unlock) screen.orientation.unlock(); } catch (e) {}
    if (ownFullscreen) {
      ownFullscreen = false;
      if (document.fullscreenElement && document.exitFullscreen) {
        var xp = document.exitFullscreen();
        if (xp && xp.catch) xp.catch(function () {});
      }
    }
  }

  function openStory() {
    if (open || building) return;
    // phone in portrait: ask for landscape first — the rotation itself
    // starts the story (onOrientation)
    if (isSmallTouch() && PORTRAIT_MQ && PORTRAIT_MQ.matches) { showGate(); return; }
    startStory();
  }

  function startStory() {
    if (open || building) return;
    building = true;
    if (!overlay) buildShell();
    enterImmersive();

    savedScrollY = window.scrollY;
    overlay.classList.add('is-active');
    syncVh();
    sizeAtmo();
    initMotes();
    lastScrollTop = 0;
    moteImpulse = 0;
    atmoFrames = 0;

    buildActs();
    scroller.scrollTop = 0;
    activeIdx = -1;
    buildTriggers();
    ST.refresh();

    open = true;
    building = false;

    // pause the dashboard's own card videos while we take over
    document.querySelectorAll('#overviewKpis video').forEach(function (v) { v.pause(); });

    var r = fab.getBoundingClientRect();
    var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    var vw = window.innerWidth, vh = window.innerHeight;
    var radius = Math.hypot(Math.max(cx, vw - cx), Math.max(cy, vh - cy)) * 1.03;
    overlay.style.setProperty('--wt-x', cx + 'px');
    overlay.style.setProperty('--wt-y', cy + 'px');

    fab.classList.remove('is-visible');
    stopTree();

    dashEls = dashboardEls();
    if (!REDUCED && dashEls.length) {
      gsap.fromTo(dashEls, { filter: 'blur(0px)' }, { filter: 'blur(6px)', duration: .8, ease: 'power2.out' });
      gsap.to('.page.active', { scale: .985, duration: 1, ease: 'power2.out', transformOrigin: '50% 40%' });
    }

    setActive(0);

    // Bind the exits before anything that animates, so a failure in the
    // reveal can never strand the user inside an overlay they cannot close.
    document.addEventListener('keydown', onKeydown, true);
    window.addEventListener('resize', onResize);
    setTimeout(function () { var c = document.getElementById('wt-close'); if (c) c.focus(); }, 60);

    // Once the reveal has finished, the circle mask and the (invisible,
    // blurred) dashboard behind the opaque overlay would otherwise keep
    // costing composite work on every frame — release both.
    var settleOpen = function () {
      if (!open) return;
      overlay.style.clipPath = 'none';
      if (dashEls.length) gsap.set(dashEls, { visibility: 'hidden' });
    };

    if (REDUCED) {
      gsap.set(overlay, { '--wt-r': radius + 'px' });
      settleOpen();
      revealText(acts[0]);
    } else {
      gsap.fromTo(overlay, { '--wt-r': '0px' },
        { '--wt-r': radius + 'px', duration: .95, ease: 'expo.inOut', onComplete: settleOpen });
      gsap.fromTo(['.wt-bar-top', '.wt-bar-bot'], { height: 0 },
        { height: '5.6vh', duration: 1.1, ease: 'expo.out', delay: .18 });
      gsap.delayedCall(.55, function () { if (open && acts[0]) revealText(acts[0]); });

      grainLast = 0;
      atmoLast = 0;
      if (!atmoRaf) atmoRaf = requestAnimationFrame(atmoTick);

      if (FINE_POINTER) overlay.addEventListener('pointermove', onPointerMove, { passive: true });

      // light shafts sweep slowly across the energy acts
      acts.forEach(function (a) {
        (a.shafts || []).forEach(function (sh, k) {
          fxTweens.push(gsap.fromTo(sh, { xPercent: -45 },
            { xPercent: 45, duration: 13 + k * 4, yoyo: true, repeat: -1, ease: 'sine.inOut' }));
        });
      });
    }
  }

  function closeStory() {
    if (!open) return;
    open = false;
    exitImmersive();

    document.removeEventListener('keydown', onKeydown, true);
    window.removeEventListener('resize', onResize);
    overlay.removeEventListener('pointermove', onPointerMove);
    if (atmoRaf) { cancelAnimationFrame(atmoRaf); atmoRaf = 0; }

    acts.forEach(function (a) { if (a.media.tagName === 'VIDEO') a.media.pause(); });

    // undo the post-open optimizations before animating the collapse
    overlay.style.clipPath = '';                       // back to circle(var(--wt-r))
    if (dashEls.length) gsap.set(dashEls, { clearProps: 'visibility' });

    if (!REDUCED && dashEls.length) {
      gsap.to(dashEls, { filter: 'blur(0px)', duration: .6, ease: 'power2.out' });
      gsap.to('.page.active', { scale: 1, duration: .7, ease: 'power2.out' });
    }
    gsap.to(['.wt-bar-top', '.wt-bar-bot'], { height: 0, duration: .5, ease: 'power2.in' });

    var finish = function () {
      killTriggers();
      overlay.classList.remove('is-active');
      frame.innerHTML = '';
      Array.prototype.slice.call(track.querySelectorAll('.wt-cue, .wt-tail')).forEach(function (n) { n.remove(); });
      rail.innerHTML = '';
      acts = []; cues = []; activeIdx = -1;
      washes.forEach(function (w) { gsap.set(w, { opacity: 0, clearProps: 'transform' }); });
      washTop = 0;
      gsap.set(barEls, { clearProps: 'backgroundColor' });
      if (motesCanvas) motesCanvas.getContext('2d').clearRect(0, 0, motesCanvas.width, motesCanvas.height);

      // leave the dashboard exactly as we found it
      if (dashEls.length) gsap.set(dashEls, { clearProps: 'all' });
      dashEls = [];
      document.querySelectorAll('#overviewKpis video').forEach(function (v) {
        var p = v.play(); if (p && p.catch) p.catch(function () {});
      });
      if (window.scrollY !== savedScrollY) window.scrollTo(0, savedScrollY);

      updateFab();
      // is-visible is added on the next frame by updateFab; the tile being
      // back in the grid is the reliable signal that focus should return
      if (fab && fab.parentNode) fab.focus();
    };

    if (REDUCED) {
      gsap.set(overlay, { '--wt-r': '0px' });
      finish();
    } else {
      gsap.to(overlay, { '--wt-r': '0px', duration: .72, ease: 'expo.inOut', onComplete: finish });
    }
  }

  function onKeydown(e) {
    if (!open) return;
    if (e.key === 'Escape') { e.preventDefault(); closeStory(); return; }

    // glide between acts — additive to free scroll, never snapping
    var NEXT = e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === 'PageDown';
    var PREV = e.key === 'ArrowLeft' || e.key === 'ArrowUp' || e.key === 'PageUp';
    if (NEXT || PREV || e.key === 'Home' || e.key === 'End') {
      e.preventDefault();
      var t = e.key === 'Home' ? 0
        : e.key === 'End' ? acts.length - 1
        : Math.max(0, Math.min(acts.length - 1, activeIdx + (NEXT ? 1 : -1)));
      scroller.scrollTo({ top: t * scroller.clientHeight * 1.6 + 1, behavior: REDUCED ? 'auto' : 'smooth' });
      return;
    }

    if (e.key !== 'Tab') return;

    var f = overlay.querySelectorAll('button:not([disabled])');
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    else if (!overlay.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
  }

  var resizeTimer = 0;
  function onResize() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      if (!open) return;
      syncVh();
      sizeAtmo();
      ST.refresh();
    }, 140);
  }

  /* ------------------------------------------------------------------
     The button + its tree.
     A living terrarium in a glass globe: a generative tree grown on a
     92×92 canvas (raster — no SVG) that sits inside the button's circular
     clip, so the whole scene — tree, ground mound, falling leaves, rising
     spores — is contained in the one clickable globe. A seeded fractal
     grows branch by branch when the button appears, then lives: a soft
     continuous breeze bends every branch by its own flexibility, leaves
     detach and flutter down to the globe floor (with stronger gusts every
     so often), and hover blooms the foliage fuller. The loop runs only
     while the button is visible; a calm tree draws at half rate.
     ------------------------------------------------------------------ */

  var treeCanvas, treeRoot = null, treeTips = [];
  var treeRaf = 0, treeRun = false, treeFrame = 0, treeDraws = 0;
  var gustTimer = null, leafTimer = null;
  var growP = 0, windAmp = 0, breezeUntil = 0, bloomP = 0, bloomTarget = 0;
  var fallers = [], treeInk = '#23372c';
  var TREE_MAXD = 5, TREE_DPR = 2;
  var TREE_W = 92, TREE_H = 92;        // canvas logical size = the globe
  var TREE_BX = 46, TREE_BY = 79;      // trunk base, standing on the mound
  // rising canopy spores: fixed phases so they never bunch up
  var spores = [
    { ph: .05, spd: .10, off: .90 }, { ph: .31, spd: .13, off: .40 },
    { ph: .52, spd: .09, off: 1.0 }, { ph: .68, spd: .12, off: .60 },
    { ph: .86, spd: .11, off: .25 }
  ];

  function mulberry(seed) {
    return function () {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  // seeded, so the tree is designed once and identical on every visit
  function buildTreeSpec() {
    var rnd = mulberry(20260709);
    function node(ang, len, depth) {
      var n = {
        ang: ang, len: len, depth: depth,
        flex: (depth + 1) / (TREE_MAXD + 1),        // tips bend, trunk doesn't
        phase: rnd() * 6.283, kids: []
      };
      if (depth < TREE_MAXD) {
        var k = depth < 2 ? 2 : (rnd() < .3 ? 3 : 2);
        for (var i = 0; i < k; i++) {
          var side = i === 0 ? -1 : i === 1 ? 1 : (rnd() < .5 ? -1 : 1);
          n.kids.push(node(side * (.30 + rnd() * .34), len * (.68 + rnd() * .14), depth + 1));
        }
      }
      return n;
    }
    treeRoot = node(0, 16, 0);   // same seed as ever — composed for the globe
  }

  function refreshTreeColors() {
    var ink = getComputedStyle(document.body).getPropertyValue('--ink').trim();
    treeInk = ink || '#23372c';
  }

  var TREE_LEAF_COLS = ['#5aa552', '#1c7a4b', '#8fc97e'];
  var TREE_OFFS = [
    [0, 0, 2.5], [-2.2, -1.3, 1.8], [1.9, -1.9, 1.6], [.5, 1.8, 1.4], [-1.0, 1.2, 1.1]
  ];

  function drawTree(tSec) {
    if (!treeCanvas || !treeRoot) return;
    treeDraws++;
    var ctx = treeCanvas.getContext('2d');
    ctx.setTransform(TREE_DPR, 0, 0, TREE_DPR, 0, 0);
    ctx.clearRect(0, 0, TREE_W, TREE_H);
    ctx.lineCap = 'round';
    ctx.strokeStyle = treeInk;

    // the globe floor: a soft green mound the tree stands on, cut off by
    // the circular clip so it reads as earth curving inside the glass
    if (growP > .02) {
      ctx.globalAlpha = .16;
      ctx.fillStyle = treeInk;
      ctx.beginPath(); ctx.ellipse(TREE_BX, 88, 38, 10, 0, 0, 6.29); ctx.fill();
      ctx.globalAlpha = .13;
      ctx.fillStyle = '#5aa552';
      ctx.beginPath(); ctx.ellipse(TREE_BX, 87, 33, 8, 0, 0, 6.29); ctx.fill();
    }

    // grounding shadow under the trunk
    if (growP > .05) {
      ctx.globalAlpha = .13 * Math.min(1, growP * 2);
      ctx.fillStyle = treeInk;
      ctx.beginPath();
      ctx.ellipse(TREE_BX, TREE_BY + 1.5, 10 * growP, 1.9, 0, 0, 6.29);
      ctx.fill();
    }

    var leaves = [];
    (function walk(n, x, y, absAng) {
      var start = n.depth / (TREE_MAXD + 1);
      var p = Math.min(1, Math.max(0, (growP - start) * (TREE_MAXD + 1)));
      if (p <= 0) return;
      var pe = 1 - Math.pow(1 - p, 3);   // each branch eases out as it extends
      var a = absAng + n.ang + windAmp * Math.sin(tSec * 1.7 + n.phase) * n.flex;
      var ex = x + Math.cos(a) * n.len * pe;
      var ey = y + Math.sin(a) * n.len * pe;
      ctx.globalAlpha = .92;
      ctx.lineWidth = .55 + (TREE_MAXD - n.depth) * .6;   // tapers to fine twigs
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(ex, ey); ctx.stroke();
      // .999, not 1: at the deepest tips (1 - d/(D+1))*(D+1) lands a float
      // ulp below 1, and a strict >= 1 would suppress the entire canopy
      if (p >= .999) {
        if (!n.kids.length) leaves.push([ex, ey, n.phase]);
        for (var i = 0; i < n.kids.length; i++) walk(n.kids[i], ex, ey, a);
      }
    })(treeRoot, TREE_BX, TREE_BY, -Math.PI / 2);
    treeTips = leaves;

    // a lush canopy: every tip carries a cluster of foliage dots that
    // shimmer very slightly out of phase — alive rather than wintry
    var lp = Math.min(1, Math.max(0, (growP - .8) / .2));
    var cx = 0, cy = 0;
    for (var i = 0; i < leaves.length; i++) {
      cx += leaves[i][0]; cy += leaves[i][1];
      for (var j = 0; j < TREE_OFFS.length; j++) {
        ctx.globalAlpha = (.40 + ((i + j) % 3) * .17) * lp;
        ctx.fillStyle = TREE_LEAF_COLS[(i + j) % 3];
        var tw = 1 + Math.sin(tSec * .9 + i * 1.7 + j) * .07;
        var r = TREE_OFFS[j][2] * lp * (1 + bloomP * .5) * tw;
        ctx.beginPath();
        ctx.arc(leaves[i][0] + TREE_OFFS[j][0], leaves[i][1] + TREE_OFFS[j][1], r, 0, 6.29);
        ctx.fill();
      }
    }

    // glow-spores drifting up through the globe — the terrarium breathing
    if (!REDUCED && lp > 0 && leaves.length) {
      cx /= leaves.length; cy /= leaves.length;
      for (var s = 0; s < spores.length; s++) {
        var S = spores[s];
        var sp = (tSec * S.spd + S.ph) % 1;
        var sx = cx + Math.sin(sp * 9 + S.ph * 20) * (5 + 9 * S.off);
        var sy = (cy + 12) - sp * 34;
        var al = Math.sin(Math.PI * sp) * .42 * lp;
        ctx.fillStyle = '#9fd694';
        ctx.globalAlpha = al * .3;
        ctx.beginPath(); ctx.arc(sx, sy, 2.2, 0, 6.29); ctx.fill();
        ctx.globalAlpha = al;
        ctx.beginPath(); ctx.arc(sx, sy, .95, 0, 6.29); ctx.fill();
      }
    }

    // detached leaves flutter down as rotating slivers, not dots
    for (var f = fallers.length - 1; f >= 0; f--) {
      var L = fallers[f];
      ctx.globalAlpha = L.a;
      ctx.fillStyle = TREE_LEAF_COLS[L.c];
      ctx.beginPath();
      ctx.ellipse(L.x, L.y, L.r * 1.6, L.r * .9, L.rot, 0, 6.29);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  function treeTick(t) {
    treeRaf = 0;
    treeFrame++;
    var tSec = t / 1000;
    if (growP < 1) growP = Math.min(1, growP + .011);

    // wind: a living idle drift, plus a gust envelope when one is blowing
    var idle = .05 * (.55 + .45 * Math.sin(tSec * .35));
    var gust = 0;
    if (breezeUntil > t) {
      var bp = 1 - (breezeUntil - t) / 1800;
      gust = Math.sin(Math.PI * Math.min(1, Math.max(0, bp))) * .21;
    }
    windAmp = idle + gust;

    if (Math.abs(bloomTarget - bloomP) > .01) bloomP += (bloomTarget - bloomP) * .14;
    else bloomP = bloomTarget;

    for (var i = fallers.length - 1; i >= 0; i--) {
      var L = fallers[i];
      L.y += L.vy;
      L.x += L.vx + Math.sin(t / 300 + L.p) * .38;
      L.rot += L.vr + Math.sin(t / 260 + L.p) * .05;
      // leaves fade quickly once they reach the mound — they land, not exit
      L.a -= L.y > 76 ? .028 : .004;
      if (L.a <= 0 || L.y > 84) fallers.splice(i, 1);
    }

    // draw every frame while things change fast; a calm tree (idle sway
    // and spores only) reads identically at half rate, so skip alternates
    var calm = growP >= 1 && breezeUntil <= t && !fallers.length && bloomP === bloomTarget;
    if (!calm || (treeFrame & 1)) drawTree(tSec);
    // Only stopTree() ends the chain — gating on a live class check here
    // let transient visibility flaps (dashboard mutations) kill the loop
    // mid-growth and freeze the tree half-grown.
    if (treeRun) treeRaf = requestAnimationFrame(treeTick);
  }

  function startTree() {
    treeRun = true;
    if (!treeRaf) treeRaf = requestAnimationFrame(treeTick);
  }

  function shedLeaves(n) {
    for (var i = 0; i < n && treeTips.length; i++) {
      var tip = treeTips[(Math.random() * treeTips.length) | 0];
      fallers.push({
        x: tip[0], y: tip[1],
        vx: .1 + Math.random() * .22, vy: .22 + Math.random() * .2,
        rot: Math.random() * 3.14, vr: (Math.random() - .5) * .09,
        r: 1.1 + Math.random() * .8, a: .85,
        c: (Math.random() * 3) | 0, p: Math.random() * 6.28
      });
    }
  }

  // a single leaf lets go every few seconds — constant, quiet autumn
  function scheduleLeaf() {
    if (leafTimer) leafTimer.kill();
    leafTimer = gsap.delayedCall(2.5 + Math.random() * 2.5, function () {
      leafTimer = null;
      if (!treeRun || open || REDUCED) return;
      shedLeaves(1);
      scheduleLeaf();
    });
  }

  // and every so often a real gust bends the whole tree and takes a few
  function scheduleGust() {
    if (gustTimer) gustTimer.kill();
    gustTimer = gsap.delayedCall(7 + Math.random() * 5, function () {
      gustTimer = null;
      if (!treeRun || open || REDUCED) return;
      breezeUntil = performance.now() + 1800;
      shedLeaves(3 + ((Math.random() * 2) | 0));
      scheduleGust();
    });
  }

  function stopTree() {
    treeRun = false;
    if (gustTimer) { gustTimer.kill(); gustTimer = null; }
    if (leafTimer) { leafTimer.kill(); leafTimer = null; }
    if (treeRaf) { cancelAnimationFrame(treeRaf); treeRaf = 0; }
    windAmp = 0; bloomTarget = 0; bloomP = 0; fallers = []; breezeUntil = 0;
  }

  /* ------------------------------------------------------------------
     Entry point — a special "Carbon Story" tile placed inside the
     Overview KPI grid, right after the gross-footprint card. It borrows
     the dashboard's own `.kpi` class for grid fit, then styles itself
     apart (campus-building photo, glow border, light sweep, CTA). The
     element is kept in the `fab` variable so the overlay's open/close
     reveal still emanates from it. app.js / styles.css stay untouched.
     ------------------------------------------------------------------ */

  function buildFab() {
    fab = el('article', 'wt-cta-kpi');
    fab.id = 'wt-fab';
    fab.setAttribute('role', 'button');
    fab.setAttribute('tabindex', '0');
    fab.setAttribute('aria-label', 'Open The Carbon Story — a guided walkthrough of the eight metrics');
    fab.innerHTML =
      '<video class="wt-cta-video" autoplay loop muted playsinline preload="auto">' +
        '<source src="media/entrykct.mp4" type="video/mp4"></video>' +
      '<div class="wt-cta-tint"></div>' +
      '<div class="wt-cta-shine"></div>' +
      '<div class="wt-cta-glow"></div>' +
      '<div class="wt-cta-content">' +
        '<span class="wt-cta-badge">Guided tour</span>' +
        '<div class="wt-cta-copy">' +
          '<span class="wt-cta-title">The Carbon Story</span>' +
          '<span class="wt-cta-go">Explore the 8 metrics <i class="wt-cta-arrow">→</i></span>' +
        '</div>' +
      '</div>';
    var v = fab.querySelector('video');
    if (v) { v.muted = true; makeSeamless(v); }   // muted: belt-and-braces for autoplay
    fab.addEventListener('click', openStory);
    fab.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openStory(); }
    });
    // NOT appended here — updateFab() slots it into the hero row.
  }

  // Slot the card into the hero row, right after the gross-emissions
  // balance card, filling the empty right half. heroGHG() only rewrites
  // that card's *values*, never the row itself, so this placement is
  // stable; the observers + heartbeat still re-run it defensively.
  function placeTile(heroRow) {
    var balance = heroRow.querySelector('.balance');
    heroRow.classList.add('wt-hero-host');
    var placed = fab.parentNode === heroRow &&
      (balance ? fab.previousElementSibling === balance : fab === heroRow.firstElementChild);
    if (placed) return;
    if (balance && balance.nextSibling) heroRow.insertBefore(fab, balance.nextSibling);
    else heroRow.appendChild(fab);
    var v = fab.querySelector('video');
    if (v && v.paused) { var p = v.play(); if (p && p.catch) p.catch(function () {}); }
  }

  function introGone() {
    var i = document.getElementById('intro-screen');
    if (!i) return true;
    return i.style.display === 'none' || i.classList.contains('hidden');
  }

  function updateFab() {
    if (!fab) return;
    var overview = document.getElementById('overview');
    var heroRow = overview ? overview.querySelector('.hero-row') : null;
    var grid = document.getElementById('overviewKpis');
    var show = !open
      && !!overview && overview.classList.contains('active')
      && !document.body.classList.contains('sidebar-active')
      && introGone()
      && !!heroRow
      && !!grid && grid.querySelectorAll('.kpi').length > 0;

    if (show) {
      placeTile(heroRow);
      if (!fab.classList.contains('is-visible')) {
        // add on the next frame so the entrance transition actually plays
        requestAnimationFrame(function () {
          if (fab.parentNode) fab.classList.add('is-visible');
        });
      }
    } else {
      fab.classList.remove('is-visible');
      if (fab.parentNode) {
        var host = fab.parentNode;
        host.removeChild(fab);
        // revert the hero row to exactly how the dashboard left it
        if (host.classList) host.classList.remove('wt-hero-host');
      }
    }
  }

  function watch() {
    var mo = new MutationObserver(updateFab);
    var overview = document.getElementById('overview');
    if (overview) mo.observe(overview, { attributes: true, attributeFilter: ['class'] });
    mo.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    var intro = document.getElementById('intro-screen');
    if (intro) mo.observe(intro, { attributes: true, attributeFilter: ['class', 'style'] });

    var kpis = document.getElementById('overviewKpis');
    if (kpis) new MutationObserver(updateFab).observe(kpis, { childList: true });
  }

  function init() {
    buildFab();
    watch();
    updateFab();
    // Heartbeat: the observers cover most state changes, but transient flaps
    // (e.g. the KPI grid re-rendering mid-frame) can leave the button or the
    // tree in a stale state with no further mutation to correct it. A cheap
    // periodic reconcile makes the whole thing self-healing.
    setInterval(updateFab, 1500);

    // Auto-open the Carbon Story if directed from external link
    if (window.location.search.indexOf('story=true') !== -1 || window.location.hash === '#story') {
      var checkReady = setInterval(function() {
        // Also wait for the overview KPI grid to actually have rendered
        // cards - data now loads asynchronously (data-loader.js fetches
        // the CSVs), so introGone()/page-active can both be true before
        // makeKpis() has run even once, which would otherwise open the
        // story onto an empty readCards() map (every act showing 0).
        var kpisReady = document.querySelectorAll('#overviewKpis .kpi').length > 0;
        if (introGone() && document.getElementById('overview').classList.contains('active') && kpisReady) {
          clearInterval(checkReady);
          setTimeout(openStory, 100);
        } else {
          // If the intro screen is visible, try to click its "Enter" button to clear it
          var introBtn = document.querySelector('#intro-screen button, .intro-cta, .enter-btn');
          if (introBtn) introBtn.click();
        }
      }, 200);
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window.KPIWalkthrough = {
    open: openStory, close: closeStory,
    isOpen: function () { return open; },
    _debug: {
      get frames() { return atmoFrames; },
      get treeDraws() { return treeDraws; },
      get treeTips() { return treeTips.length; },
      get treeRun() { return treeRun; },
      get fallers() { return fallers.length; },
      get growP() { return growP; }
    }
  };
})();
