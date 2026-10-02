/* =====================================================================
   K-COSMOS - PUBLIC CERTIFICATES (certificates.js)
   A read-only document section inside a dashboard page:

     <page> -> Certificates -> year -> certificate gallery -> viewer

   Everything shown - the years, the document list, every title, date,
   quantity and number - comes from the public certificate API. This file
   holds only the API routes and the rendering rules, so a new certificate
   or a new year appears without any change here.

   Certificates are supporting documents. A certificate quantity is
   document metadata; it is not read by any KPI card or chart.
   ===================================================================== */
(function () {
  'use strict';

  const YEARS_ROUTE = '/api/public/certificates/years';
  const LIST_ROUTE = '/api/public/certificates';
  const fileRoute = id => `${LIST_ROUTE}/${encodeURIComponent(id)}/file`;

  function apiBase() {
    if (typeof window.KCOSMOS_API_BASE === 'string' && window.KCOSMOS_API_BASE.trim()) {
      return window.KCOSMOS_API_BASE.trim().replace(/\/$/, '');
    }
    return '';
  }
  async function getJson(path) {
    const response = await fetch(apiBase() + path, { cache: 'no-store', credentials: 'omit' });
    if (!response.ok) throw new Error(`Certificate request failed (${response.status})`);
    return response.json();
  }
  const loadYears = domain => getJson(`${YEARS_ROUTE}?domain=${encodeURIComponent(domain)}`);
  const loadCertificates = (domain, year) => getJson(`${LIST_ROUTE}?domain=${encodeURIComponent(domain)}&year=${encodeURIComponent(year)}`);
  const fileUrl = (id, download) => apiBase() + fileRoute(id) + (download ? '?download=1' : '');

  /* ---- presentation helpers (formatting only) ---- */
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;   // API text is never parsed as HTML
    return node;
  }
  function dateText(value) {
    if (!value) return null;
    const parsed = new Date(`${value}T00:00:00`);
    return Number.isNaN(parsed.getTime()) ? String(value)
      : parsed.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  }
  function quantityText(item) {
    if (item.quantity_value == null) return null;
    return `${Number(item.quantity_value).toLocaleString('en-IN', { maximumFractionDigits: 3 })} ${item.quantity_unit || ''}`.trim();
  }
  const countText = count => `${count} ${count === 1 ? 'document' : 'documents'}`;
  const isImage = item => String(item.mime_type || '').startsWith('image/');
  /* Label / value rows; a value the backend does not have is simply not listed. */
  function facts(item, rows) {
    const list = el('dl', 'cert-facts');
    rows.forEach(([label, value]) => {
      if (value == null || value === '') return;
      list.append(el('dt', null, label), el('dd', null, String(value)));
    });
    return list;
  }

  /* ---- viewer (one shared dialog) ---- */
  const viewer = { root: null, items: [], index: 0, rotation: 0, opener: null };

  function buildViewer() {
    if (viewer.root) return;
    const root = el('div', 'cert-viewer');
    root.id = 'certViewer';
    root.hidden = true;
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-labelledby', 'certViewerTitle');
    const panel = el('div', 'cert-viewer-panel');
    const bar = el('div', 'cert-viewer-bar');
    const title = el('h2', 'cert-viewer-title');
    title.id = 'certViewerTitle';
    const controls = el('div', 'cert-viewer-controls');
    const button = (id, label, handler) => {
      const node = el('button', 'cert-btn cert-btn-ghost', label);
      node.type = 'button'; node.id = id; node.addEventListener('click', handler);
      return node;
    };
    const link = (id, label) => {
      const node = el('a', 'cert-btn cert-btn-ghost', label);
      node.id = id; node.target = '_blank'; node.rel = 'noopener';
      return node;
    };
    controls.append(
      button('certViewerPrev', 'Previous', () => showInViewer(viewer.index - 1)),
      button('certViewerNext', 'Next', () => showInViewer(viewer.index + 1)),
      button('certViewerRotate', 'Rotate', rotateDocument),
      link('certViewerOpen', 'Open original'),
      link('certViewerDownload', 'Download'),
      button('certViewerClose', 'Close', closeViewer)
    );
    bar.append(title, controls);
    const body = el('div', 'cert-viewer-body');
    const stage = el('div', 'cert-viewer-stage');
    stage.id = 'certViewerStage';
    const side = el('aside', 'cert-viewer-side');
    side.id = 'certViewerSide';
    body.append(stage, side);
    panel.append(bar, body);
    root.append(panel);
    root.addEventListener('click', event => { if (event.target === root) closeViewer(); });
    root.addEventListener('keydown', onViewerKey);
    document.body.append(root);
    viewer.root = root;
  }

  function focusable() {
    return [...viewer.root.querySelectorAll('button, a[href]')].filter(node => !node.hidden && !node.disabled);
  }
  function onViewerKey(event) {
    if (event.key === 'Escape') { event.preventDefault(); closeViewer(); return; }
    if (event.key === 'ArrowLeft') { showInViewer(viewer.index - 1); return; }
    if (event.key === 'ArrowRight') { showInViewer(viewer.index + 1); return; }
    if (event.key !== 'Tab') return;
    // Keep keyboard focus inside the dialog while it is open.
    const nodes = focusable();
    if (!nodes.length) return;
    const first = nodes[0], last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  function fitRotation() {
    const stage = document.getElementById('certViewerStage');
    const image = stage && stage.querySelector('img');
    if (!image) return;
    const sideways = viewer.rotation % 180 !== 0;
    // A sideways image is sized against the stage's other dimension so it still fits.
    image.style.maxWidth = `${sideways ? stage.clientHeight : stage.clientWidth}px`;
    image.style.maxHeight = `${sideways ? stage.clientWidth : stage.clientHeight}px`;
    image.style.transform = `rotate(${viewer.rotation}deg)`;
  }
  function rotateDocument() {
    // Quarter turns anticlockwise: a scan photographed sideways is upright after one press.
    viewer.rotation = (viewer.rotation + 270) % 360;
    fitRotation();
  }

  function showInViewer(index) {
    if (index < 0 || index >= viewer.items.length) return;
    viewer.index = index;
    viewer.rotation = 0;
    const item = viewer.items[index];
    const stage = document.getElementById('certViewerStage');
    const side = document.getElementById('certViewerSide');
    document.getElementById('certViewerTitle').textContent = item.title;
    stage.replaceChildren();
    if (isImage(item)) {
      const image = el('img', 'cert-viewer-image');
      image.alt = item.title;
      image.addEventListener('load', fitRotation);
      image.src = fileUrl(item.id);
      stage.append(image);
    } else {
      const frame = el('iframe', 'cert-viewer-frame');
      frame.title = item.title;
      frame.src = fileUrl(item.id);
      const fallback = el('a', 'cert-btn', 'Open document');
      fallback.href = fileUrl(item.id); fallback.target = '_blank'; fallback.rel = 'noopener';
      stage.append(frame, fallback);
    }
    side.replaceChildren(
      el('p', 'cert-type', item.certificate_type),
      facts(item, [
        ['Reporting year', item.reporting_year],
        ['Disposal received', dateText(item.received_date)],
        ['Certificate issued', dateText(item.certificate_date)],
        ['Quantity', quantityText(item)],
        ['Issuer', item.issuer],
        ['Serial no.', item.serial_no],
        ['Manifest doc. no.', item.manifest_doc_no],
        ['Invoice no.', item.invoice_no],
        ['Registration ID', item.registration_id],
        ['Authorization no.', item.authorization_no]
      ]),
      el('p', 'cert-note', 'Supporting document. Its quantity is not used in any dashboard figure.')
    );
    document.getElementById('certViewerOpen').href = fileUrl(item.id);
    document.getElementById('certViewerDownload').href = fileUrl(item.id, true);
    document.getElementById('certViewerRotate').hidden = !isImage(item);
    document.getElementById('certViewerPrev').disabled = index === 0;
    document.getElementById('certViewerNext').disabled = index === viewer.items.length - 1;
    const single = viewer.items.length < 2;
    document.getElementById('certViewerPrev').hidden = single;
    document.getElementById('certViewerNext').hidden = single;
  }

  function openViewer(items, index, opener) {
    buildViewer();
    viewer.items = items;
    viewer.opener = opener || document.activeElement;
    viewer.root.hidden = false;
    document.body.classList.add('cert-viewer-open');
    showInViewer(index);
    document.getElementById('certViewerClose').focus();
  }
  function closeViewer() {
    if (!viewer.root || viewer.root.hidden) return;
    viewer.root.hidden = true;
    document.body.classList.remove('cert-viewer-open');
    document.getElementById('certViewerStage').replaceChildren();
    if (viewer.opener && typeof viewer.opener.focus === 'function') viewer.opener.focus();
  }
  window.addEventListener('resize', fitRotation);

  /* ---- one certificate section per page ---- */
  function section(config) {
    const page = document.getElementById(config.pageId);
    const host = document.getElementById(config.hostId);
    const entry = document.getElementById(config.entryButtonId);
    if (!page || !host || !entry) return null;
    const hashRoot = `#${config.hashKey}`;
    let token = 0;

    const stateFromHash = () => {
      const hash = window.location.hash || '';
      if (hash !== hashRoot && !hash.startsWith(`${hashRoot}/`)) return null;
      const year = Number(hash.slice(hashRoot.length + 1));
      return { year: Number.isInteger(year) && year > 0 ? year : null };
    };

    function crumbs(parts) {
      const nav = el('nav', 'cert-crumbs');
      nav.setAttribute('aria-label', 'Breadcrumb');
      parts.forEach(([label, href], position) => {
        if (position) nav.append(el('span', 'cert-crumb-sep', '→'));
        if (href == null) { nav.append(el('span', 'cert-crumb-current', label)); return; }
        const link = el('a', null, label);
        link.href = href;
        nav.append(link);
      });
      return nav;
    }
    function message(text) { return el('p', 'cert-message hint', text); }

    async function renderYears() {
      const mine = ++token;
      host.replaceChildren(
        crumbs([[config.pageTitle, '#'], ['Certificates', null]]),
        el('h1', 'cert-heading', 'Certificates'),
        el('p', 'hint', config.description),
        el('h2', 'cert-subheading', 'Available years'),
        message('Loading…')
      );
      let years;
      try { years = (await loadYears(config.domain)).years || []; }
      catch (_) { if (mine === token) host.lastChild.replaceWith(message('Certificates are unavailable right now.')); return; }
      if (mine !== token) return;
      if (!years.length) { host.lastChild.replaceWith(message('No certificates have been published yet.')); return; }
      const grid = el('div', 'cert-year-grid');
      years.forEach(item => {
        const card = el('a', 'cert-year-card');
        card.href = `${hashRoot}/${item.year}`;
        card.append(
          el('span', 'cert-year', String(item.year)),
          el('span', 'cert-year-types', (item.certificate_types || []).join(', ')),
          el('span', 'cert-year-count', countText(item.certificate_count))
        );
        grid.append(card);
      });
      host.lastChild.replaceWith(grid);
    }

    async function renderGallery(year) {
      const mine = ++token;
      host.replaceChildren(
        crumbs([[config.pageTitle, '#'], ['Certificates', hashRoot], [String(year), null]]),
        el('h1', 'cert-heading', `Certificates — ${year}`),
        el('p', 'hint', `Reporting year ${year}. A certificate belongs to the year of the activity it covers, which can differ from the date it was issued.`),
        message('Loading…')
      );
      let items;
      try { items = (await loadCertificates(config.domain, year)).certificates || []; }
      catch (_) { if (mine === token) host.lastChild.replaceWith(message('Certificates are unavailable right now.')); return; }
      if (mine !== token) return;
      if (!items.length) { host.lastChild.replaceWith(message(`No certificates are published for ${year}.`)); return; }
      const grid = el('div', 'cert-grid');
      items.forEach((item, index) => {
        const card = el('article', 'cert-card');
        const thumb = el('div', 'cert-thumb');
        if (isImage(item)) {
          const image = el('img');
          image.loading = 'lazy'; image.alt = ''; image.src = fileUrl(item.id);
          thumb.append(image);
        } else {
          thumb.append(el('span', 'cert-thumb-doc', 'PDF'));
        }
        const view = el('button', 'cert-btn', 'View Certificate');
        view.type = 'button';
        view.addEventListener('click', () => openViewer(items, index, view));
        thumb.addEventListener('click', () => openViewer(items, index, view));
        const body = el('div', 'cert-card-body');
        body.append(
          el('h3', 'cert-title', item.title),
          el('p', 'cert-type', item.certificate_type),
          el('p', 'cert-quantity', quantityText(item) || ''),
          facts(item, [
            ['Issuer', item.issuer],
            ['Reporting year', item.reporting_year],
            ['Disposal received', dateText(item.received_date)],
            ['Certificate issued', dateText(item.certificate_date)],
            ['Serial no.', item.serial_no],
            ['Manifest doc. no.', item.manifest_doc_no]
          ]),
          view
        );
        card.append(thumb, body);
        grid.append(card);
      });
      host.lastChild.replaceWith(grid);
    }

    function apply() {
      const state = stateFromHash();
      const active = Boolean(state);
      page.classList.toggle('cert-view', active);
      host.hidden = !active;
      if (!active) { token++; closeViewer(); return; }
      // A shared link opens the right page first; the page itself is otherwise untouched.
      if (document.body.getAttribute('data-page') !== config.pageId && typeof window.go === 'function') {
        try { window.go(config.pageId); } catch (_) { /* dashboard still starting */ }
      }
      if (state.year) renderGallery(state.year); else renderYears();
      window.scrollTo({ top: 0 });
    }

    entry.addEventListener('click', () => { window.location.hash = hashRoot; });
    window.addEventListener('hashchange', apply);
    // Leaving through the navigation dock closes the certificate view.
    document.querySelectorAll('.bottom-dock button').forEach(button => button.addEventListener('click', () => {
      if (stateFromHash()) {
        window.history.replaceState(null, '', window.location.pathname + window.location.search);
        apply();
      }
    }));
    host.addEventListener('click', event => {
      const link = event.target.closest('a[href="#"]');
      if (!link) return;
      event.preventDefault();
      window.history.pushState(null, '', window.location.pathname + window.location.search);
      apply();
    });
    window.addEventListener('popstate', apply);
    return { apply };
  }

  function start() {
    const waste = section({
      domain: 'waste', pageId: 'waste', hostId: 'wasteCertificates', entryButtonId: 'wasteCertOpen',
      hashKey: 'waste-certificates', pageTitle: 'Waste Management',
      description: 'Official environmental disposal and compliance documents related to Waste Management.'
    });
    if (!waste) return;
    if (!window.location.hash.startsWith('#waste-certificates')) return;
    // A deep link waits until the dashboard has loaded its periods before switching page.
    let tries = 0;
    const ready = () => document.getElementById('yearFilter')?.options.length > 0;
    const open = () => { if (ready() || ++tries > 100) waste.apply(); else setTimeout(open, 100); };
    open();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();

  window.KCOSMOSCertificates = Object.freeze({ yearsRoute: YEARS_ROUTE, listRoute: LIST_ROUTE, fileRoute, section, openViewer, closeViewer });
})();
