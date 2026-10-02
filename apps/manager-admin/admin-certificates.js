/* Admin certificate management. Everything shown comes from /api/admin/certificates;
   nothing about a particular certificate is written into this file. */
(function () {
  'use strict';
  const BASE = '/api/admin/certificates';
  const FIELDS = {
    domain: 'cert-domain', certificate_type: 'cert-type', reporting_year: 'cert-year', title: 'cert-title',
    issuer: 'cert-issuer', registration_id: 'cert-registration', authorization_no: 'cert-authorization',
    serial_no: 'cert-serial', certificate_date: 'cert-date', received_date: 'cert-received',
    invoice_no: 'cert-invoice', manifest_doc_no: 'cert-manifest', quantity_value: 'cert-quantity',
    quantity_unit: 'cert-unit', display_order: 'cert-order', notes: 'cert-notes'
  };
  const NUMERIC = new Set(['reporting_year', 'quantity_value', 'display_order']);
  const REQUIRED = new Set(['domain', 'certificate_type', 'reporting_year', 'title', 'display_order']);
  const STATUS_BADGE = { DRAFT: 'badge-draft', PUBLISHED: 'badge-approved', ARCHIVED: 'badge-correction' };
  let certificates = [];

  const byId = id => document.getElementById(id);
  const notify = (message, type = 'success') => window.showToast?.(message, type);
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[character]);
  const request = (path, options = {}) => apiRequest(path, {
    ...options, csrf: !['GET', 'HEAD'].includes((options.method || 'GET').toUpperCase())
  });
  const fileUrl = id => window.KCOSMOS_API_URL(`${BASE}/${encodeURIComponent(id)}/file`);
  const dateText = value => (value ? new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' }) : '—');
  const quantityText = item => (item.quantity_value == null ? '—' : `${Number(item.quantity_value).toLocaleString()} ${item.quantity_unit || ''}`.trim());

  function filters() {
    return { domain: byId('filter-domain').value, year: byId('filter-year').value, status: byId('filter-status').value };
  }

  /* Filter choices are whatever the registry holds - no fixed year list. */
  function fillFilterOptions() {
    const keep = filters();
    const fill = (select, values, label) => {
      select.replaceChildren(new Option(label, ''), ...values.map(value => new Option(value, value)));
    };
    fill(byId('filter-domain'), [...new Set(certificates.map(item => item.domain))].sort(), 'All domains');
    fill(byId('filter-year'), [...new Set(certificates.map(item => String(item.reporting_year)))].sort().reverse(), 'All years');
    byId('filter-domain').value = keep.domain;
    byId('filter-year').value = keep.year;
  }

  function render() {
    const active = filters();
    const rows = certificates.filter(item =>
      (!active.domain || item.domain === active.domain)
      && (!active.year || String(item.reporting_year) === active.year)
      && (!active.status || item.status === active.status));
    const body = byId('certificates-body');
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="8">No certificates match.</td></tr>';
      return;
    }
    body.innerHTML = rows.map(item => `<tr>
      <td><strong>${escapeHtml(item.title)}</strong><br><span class="text-muted">${escapeHtml(item.certificate_type)}${item.serial_no ? ` · Serial ${escapeHtml(item.serial_no)}` : ''}</span></td>
      <td>${escapeHtml(item.domain)}</td>
      <td>${escapeHtml(item.reporting_year)}</td>
      <td>${escapeHtml(dateText(item.received_date))}</td>
      <td>${escapeHtml(dateText(item.certificate_date))}</td>
      <td>${escapeHtml(quantityText(item))}</td>
      <td><span class="badge ${STATUS_BADGE[item.status] || 'badge-draft'}">${escapeHtml(item.status)}</span></td>
      <td style="white-space:nowrap;">
        <button class="btn btn-outline btn-sm" data-action="preview" data-id="${escapeHtml(item.id)}">Preview</button>
        <button class="btn btn-outline btn-sm" data-action="edit" data-id="${escapeHtml(item.id)}">Edit</button>
        ${item.status !== 'PUBLISHED' ? `<button class="btn btn-primary btn-sm" data-action="publish" data-id="${escapeHtml(item.id)}">Publish</button>` : ''}
        ${item.status !== 'ARCHIVED' ? `<button class="btn btn-outline btn-sm" data-action="archive" data-id="${escapeHtml(item.id)}">Archive</button>` : ''}
      </td></tr>`).join('');
  }

  async function load() {
    try {
      certificates = await request(BASE);
      fillFilterOptions();
      render();
    } catch (error) {
      byId('certificates-body').innerHTML = `<tr><td colspan="8">${escapeHtml(error.message)}</td></tr>`;
    }
  }

  function openForm(item) {
    byId('certificate-form').reset();
    byId('certificate-id').value = item ? item.id : '';
    byId('certificate-modal-title').textContent = item ? 'Edit Certificate Metadata' : 'Upload Certificate';
    byId('save-certificate').textContent = item ? 'Save Changes' : 'Save Draft';
    byId('cert-file-group').style.display = item ? 'none' : '';
    byId('cert-file-note').style.display = item ? '' : 'none';
    byId('cert-file').required = !item;
    byId('certificate-form-status').textContent = '';
    if (item) {
      Object.entries(FIELDS).forEach(([field, id]) => {
        const control = byId(id);
        // A domain the form does not list yet is still shown, not silently changed.
        if (field === 'domain' && ![...control.options].some(option => option.value === item.domain)) {
          control.add(new Option(item.domain, item.domain));
        }
        control.value = item[field] ?? '';
      });
    }
    byId('certificate-modal').classList.add('active');
  }

  function formValues() {
    const values = {};
    Object.entries(FIELDS).forEach(([field, id]) => {
      const raw = byId(id).value.trim();
      values[field] = raw === '' ? null : (NUMERIC.has(field) ? Number(raw) : raw);
    });
    return values;
  }

  async function submitForm(event) {
    event.preventDefault();
    const id = byId('certificate-id').value;
    const values = formValues();
    const status = byId('certificate-form-status');
    byId('save-certificate').disabled = true;
    status.textContent = 'Saving…';
    try {
      if (id) {
        await request(`${BASE}/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(values) });
        notify('Certificate metadata updated.');
      } else {
        const file = byId('cert-file').files[0];
        if (!file) throw new Error('Choose the certificate file.');
        const body = new FormData();
        body.append('file', file);
        // Empty optional fields are simply not sent; nothing is defaulted on their behalf.
        Object.entries(values).forEach(([field, value]) => {
          if (value !== null || REQUIRED.has(field)) body.append(field, value ?? '');
        });
        await request(BASE, { method: 'POST', body });
        notify('Draft saved. Publish it to show it on the public dashboard.');
      }
      byId('certificate-modal').classList.remove('active');
      await load();
    } catch (error) {
      status.textContent = error.message;
      notify(error.message, 'error');
    } finally {
      byId('save-certificate').disabled = false;
    }
  }

  function preview(item) {
    const url = fileUrl(item.id);
    byId('preview-title').textContent = item.title;
    byId('preview-open').href = url;
    const body = byId('preview-body');
    body.replaceChildren();
    if (item.mime_type === 'application/pdf') {
      const frame = document.createElement('iframe');
      frame.src = url; frame.title = item.title; frame.style.cssText = 'width:100%;height:70vh;border:1px solid #ddd;';
      body.append(frame);
    } else {
      const image = document.createElement('img');
      image.src = url; image.alt = item.title; image.style.cssText = 'max-width:100%;height:auto;';
      body.append(image);
    }
    byId('preview-modal').classList.add('active');
  }

  async function act(action, item) {
    if (action === 'preview') return preview(item);
    if (action === 'edit') return openForm(item);
    const question = action === 'publish'
      ? `Publish "${item.title}"? It becomes visible on the public dashboard.`
      : `Archive "${item.title}"? It is removed from the public dashboard but kept in the registry.`;
    if (!window.confirm(question)) return;
    try {
      await request(`${BASE}/${encodeURIComponent(item.id)}/${action}`, { method: 'POST' });
      notify(action === 'publish' ? 'Certificate published.' : 'Certificate archived.');
      await load();
    } catch (error) {
      notify(error.message, 'error');
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    byId('btn-new-certificate').addEventListener('click', () => openForm(null));
    byId('certificate-form').addEventListener('submit', submitForm);
    ['close-certificate-modal', 'cancel-certificate'].forEach(id => byId(id).addEventListener('click', () => byId('certificate-modal').classList.remove('active')));
    byId('close-preview-modal').addEventListener('click', () => { byId('preview-modal').classList.remove('active'); byId('preview-body').replaceChildren(); });
    ['filter-domain', 'filter-year', 'filter-status'].forEach(id => byId(id).addEventListener('change', render));
    byId('certificates-body').addEventListener('click', event => {
      const button = event.target.closest('button[data-action]');
      const item = button && certificates.find(entry => entry.id === button.dataset.id);
      if (item) act(button.dataset.action, item);
    });
    load();
  });
})();
