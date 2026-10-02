(function () {
  'use strict';
  const definitions = [
    { code: 'PETROL', label: 'Petrol', unit: 'L' },
    { code: 'DIESEL', label: 'Diesel', unit: 'L' },
    { code: 'GRID_ELECTRICITY', label: 'Grid Electricity', unit: 'kWh' },
    // Optional mirrors the backend: CORE_FACTORS requires only petrol, diesel
    // and grid, so a set still activates without LPG. LPG is governed on weight
    // as LPG_KG (kgCO2e/kg, 0013_lpg_kg_governance_v2); the retired litre code
    // LPG is rejected by the backend for any new or edited set.
    { code: 'LPG_KG', label: 'LPG (optional)', unit: 'kg', optional: true }
  ];
  let sets = [];
  let selected = null;

  const byId = id => document.getElementById(id);
  const text = value => String(value ?? '—');
  const notify = (message, type = 'success') => window.showToast?.(message, type);

  function editorRows(factors = []) {
    const indexed = new Map(factors.map(item => [item.code, item]));
    byId('factor-editor-body').replaceChildren(...definitions.map(definition => {
      const factor = indexed.get(definition.code) || {};
      const row = document.createElement('tr');
      const name = document.createElement('td'); name.textContent = definition.label;
      const valueCell = document.createElement('td');
      const value = document.createElement('input'); value.type = 'number'; value.min = '0'; value.step = '0.0000000001'; value.required = !definition.optional; value.className = 'form-control'; value.dataset.field = 'value'; value.dataset.code = definition.code; value.value = factor.factor_value ?? '';
      valueCell.append(value);
      const unit = document.createElement('td'); unit.textContent = `kgCO2e/${definition.unit}`;
      const sourceCell = document.createElement('td');
      const source = document.createElement('input'); source.className = 'form-control'; source.required = !definition.optional; source.maxLength = 2000; source.dataset.field = 'source'; source.dataset.code = definition.code; source.value = factor.source_reference ?? '';
      sourceCell.append(source);
      const urlCell = document.createElement('td');
      const url = document.createElement('input'); url.type = 'url'; url.className = 'form-control'; url.dataset.field = 'url'; url.dataset.code = definition.code; url.value = factor.source_url ?? '';
      urlCell.append(url);
      row.append(name, valueCell, unit, sourceCell, urlCell);
      return row;
    }), ...legacyRows(factors));
  }

  /* A retired set may still hold a legacy factor (e.g. the litre LPG code).
     It is shown read-only for audit and is never part of a write payload. */
  function legacyRows(factors) {
    const governed = new Set(definitions.map(definition => definition.code));
    return factors.filter(factor => !governed.has(factor.code)).map(factor => {
      const row = document.createElement('tr');
      for (const value of [`${factor.code} (legacy, read-only)`, factor.factor_value, `${factor.result_unit}/${factor.activity_unit}`, factor.source_reference, factor.source_url]) {
        const cell = document.createElement('td'); cell.textContent = text(value); row.append(cell);
      }
      return row;
    });
  }

  function payload() {
    const factors = definitions.flatMap(definition => {
      const factorValue = byId('factor-editor-body').querySelector(`[data-field="value"][data-code="${definition.code}"]`).value;
      const sourceReference = byId('factor-editor-body').querySelector(`[data-field="source"][data-code="${definition.code}"]`).value.trim();
      const sourceUrl = byId('factor-editor-body').querySelector(`[data-field="url"][data-code="${definition.code}"]`).value.trim();
      if (definition.optional && !factorValue && !sourceReference && !sourceUrl) return [];
      if (!factorValue || !sourceReference) throw new Error(`${definition.label} requires both a value and source/reference.`);
      return [{
        code: definition.code,
        factor_value: factorValue,
        activity_unit: definition.unit,
        result_unit: 'kgCO2e',
        source_reference: sourceReference,
        source_url: sourceUrl || null,
        notes: null
      }];
    });
    return {
      version: byId('factor-version').value.trim(),
      effective_from: byId('factor-effective-from').value,
      source_note: byId('factor-source-note').value.trim(),
      factors
    };
  }

  function openEditor(item = null) {
    selected = item;
    const editable = !item || item.status === 'draft';
    byId('factor-modal-title').textContent = item ? `${text(item.version)} — ${text(item.status)}` : 'Create Draft Factor Set';
    byId('factor-set-id').value = item?.id || '';
    byId('factor-row-version').value = item?.row_version || '';
    byId('factor-version').value = item?.version || '';
    byId('factor-effective-from').value = item?.effective_from || '';
    byId('factor-source-note').value = item?.source_note || '';
    editorRows(item?.factors || []);
    byId('factor-set-form').querySelectorAll('input, textarea').forEach(control => { if (control.type !== 'hidden') control.disabled = !editable; });
    byId('save-factor-set').hidden = !editable;
    byId('activate-factor-set').hidden = !item || !editable;
    byId('factor-modal').classList.add('active');
  }

  function render() {
    const body = byId('factor-sets-body');
    if (!sets.length) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 7;
      cell.textContent = 'No factor sets configured.';
      row.append(cell);
      body.replaceChildren(row);
      return;
    }
    body.replaceChildren(...sets.map(item => {
      const row = document.createElement('tr');
      for (const value of [item.version, item.status, item.effective_from, `${item.factors.length} factor(s)`, `${item.created_by_name || 'System'} · ${new Date(item.created_at).toLocaleString()}`, item.activated_at ? `${item.activated_by_name || 'Admin'} · ${new Date(item.activated_at).toLocaleString()}` : '—']) {
        const cell = document.createElement('td'); cell.textContent = text(value); row.append(cell);
      }
      const action = document.createElement('td');
      const button = document.createElement('button'); button.type = 'button'; button.className = 'btn btn-outline'; button.textContent = item.status === 'draft' ? 'Edit' : 'View'; button.addEventListener('click', () => openEditor(item)); action.append(button); row.append(action);
      return row;
    }));
  }

  async function load() { sets = await KCosmos.api('/api/admin/emission-factor-sets'); render(); }

  /* A failed initialization must never leave the page sitting on its static
     "Loading…" placeholder with no explanation. Redirects raised by
     requireRole are the one exception: the browser is already navigating. */
  function renderLoadFailure(error) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 7;
    cell.textContent = 'Unable to load emission factors. Please verify session/API connection.';
    row.append(cell);
    byId('factor-sets-body').replaceChildren(row);
    notify('Unable to load emission factors. Please verify session/API connection.', 'error');
    // Diagnostic only: status, error code and request id. Never session or factor data.
    console.error('[K-COSMOS] Emission factor initialization failed.', {
      status: error?.status ?? null,
      code: error?.code ?? null,
      requestId: error?.requestId ?? null,
      message: error?.message || String(error)
    });
  }

  document.addEventListener('DOMContentLoaded', async () => {
    try {
      await KCosmos.requireRole('microcosm_admin');
    } catch (error) {
      // requireRole navigates away before throwing in these three cases, so
      // the page is already unloading and an error banner would just flicker.
      const redirecting = error?.status === 401
        || error?.message === 'Access denied'
        || error?.message === 'Password change required';
      if (!redirecting) renderLoadFailure(error);
      return;
    }
    try {
      await load();
    } catch (error) {
      renderLoadFailure(error);
      // Authorization succeeded, so the admin controls stay wired and usable.
    }
    byId('btn-new-factor').addEventListener('click', () => openEditor());
    for (const id of ['close-factor-modal', 'close-factor-message']) byId(id).addEventListener('click', () => byId('factor-modal').classList.remove('active'));
    byId('factor-set-form').addEventListener('submit', async event => {
      event.preventDefault();
      try {
        const body = payload();
        if (selected) body.expected_row_version = selected.row_version;
        selected = await KCosmos.api(selected ? `/api/admin/emission-factor-sets/${selected.id}` : '/api/admin/emission-factor-sets', { method: selected ? 'PUT' : 'POST', body: JSON.stringify(body), csrf: true });
        notify('Draft factor set saved.'); await load(); openEditor(selected);
      } catch (error) { notify(error.message, 'error'); }
    });
    byId('activate-factor-set').addEventListener('click', async () => {
      if (!selected || !window.confirm(`Activate ${selected.version}? Active factor sets are immutable.`)) return;
      try { selected = await KCosmos.api(`/api/admin/emission-factor-sets/${selected.id}/activate`, { method: 'POST', csrf: true }); notify('Factor set activated.'); await load(); openEditor(selected); } catch (error) { notify(error.message, 'error'); }
    });
  });
})();
