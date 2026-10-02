(function () {
  const domain = document.body.dataset.authDomain;
  // Waste uses this same shared workflow (fieldMaps.waste, the waste_items
  // payload branch below, and the backend's GENERIC_DOMAINS all already
  // assumed it). Omitting it here made the whole module return before
  // initialize() ever ran: no current-period fetch, no Save/Submit wiring,
  // and no KCosmosSubmissionContext - which is also why evidence upload
  // failed with "Save the draft before adding evidence.": context() resolved
  // to undefined instead of a real submission accessor.
  if (!['transport', 'energy', 'lpg', 'water', 'waste'].includes(domain)) return;

  const fieldMaps = {
    transport: {
      petrol: 'transport_petrol_litres',
      'diesel-transport': 'transport_diesel_litres',
      'active-vehicles-petrol': 'petrol_vehicle_count',
      'active-vehicles-diesel': 'diesel_vehicle_count',
      'ev-consumption': 'ev_consumption_kwh',
      // DG is entered as electricity generated (kWh) (0015_dg_kwh_methodology).
      // Diesel litres are derived by the backend and are never sent.
      'dg-generation': 'dg_generation_kwh',
      'active-dg': 'dg_count'
    },
    energy: {
      'grid-ht': 'grid_ht_kwh',
      'grid-comm': 'grid_commercial_kwh',
      'grid-temp': 'grid_temporary_kwh',
      'ren-campus': 'renewable_on_campus_kwh',
      'ren-procured': 'renewable_procured_kwh',
      'ren-solar': 'solar_water_heater_kwh'
    },
    lpg: {
      // lpg_weight_kg (kg) is the governed emissions activity
      // (0013_lpg_kg_governance_v2). The cylinder count is optional reference
      // metadata and drives no calculation; litres are no longer collected.
      'lpg-kg': 'lpg_weight_kg',
      'lpg-cylinders': 'lpg_cylinder_count'
    },
    waste: {
      // Only wet waste is manager-entered. dry_waste_generated_kg and
      // total_waste_generated_kg are derived by the backend and are never sent.
      'wet-waste': 'wet_waste_generated_kg'
    },
    water: {
      'water-twad': 'water_twad_kl',
      'water-borewell': 'water_borewell_kl',
      'water-priv': 'water_private_kl',
      'water-waste': 'wastewater_generated_kl',
      'water-recycled': 'water_recycled_kl',
      'inlet-ph': 'inlet_ph',
      'inlet-tss': 'inlet_tss',
      'inlet-tds': 'inlet_tds',
      'inlet-nh3n': 'inlet_nh3n',
      'inlet-p': 'inlet_phosphorus',
      'inlet-cl': 'inlet_chloride',
      'inlet-so4': 'inlet_sulphate',
      'inlet-og': 'inlet_oil_grease',
      'inlet-cod': 'inlet_cod',
      'inlet-bod': 'inlet_bod',
      'outlet-ph': 'outlet_ph',
      'outlet-tss': 'outlet_tss',
      'outlet-tds': 'outlet_tds',
      'outlet-nh3n': 'outlet_nh3n',
      'outlet-p': 'outlet_phosphorus',
      'outlet-cl': 'outlet_chloride',
      'outlet-so4': 'outlet_sulphate',
      'outlet-og': 'outlet_oil_grease',
      'outlet-cod': 'outlet_cod',
      'outlet-bod': 'outlet_bod',
      'stp-inlet-cod': 'stp_inlet_cod',
      'stp-outlet-cod': 'stp_outlet_cod'
    }
  };

  const calculatedFields = {
    energy: ['grid-total', 'ren-total'],
    water: ['water-consumed']
  };
  const calculatedSwitches = {
    energy: ['grid-auto-calc', 'auto-calc'],
    water: ['auto-calc-consumed']
  };
  const editableStatuses = new Set(['draft', 'correction_requested']);
  const map = fieldMaps[domain];
  let currentPeriod = null;
  let definitions = new Map();
  let currentSubmission = null;
  let operationInProgress = false;
  let currentLoadSequence = 0;

  function request(path, options = {}) {
    const write = options.method && !['GET', 'HEAD'].includes(options.method.toUpperCase());
    return apiRequest(`/api/manager/${domain}${path}`, { ...options, csrf: write });
  }

  function valueFor(input) {
    return input.value.trim() === '' ? null : input.value;
  }

  function notify(message, type, operation) {
    try {
      window.KCosmosUI?.notify?.(message, type, { operation });
    } catch {
      console.warn('[K-COSMOS] UI notification could not be displayed.', { operation });
    }
  }

  function workflowMessage() {
    let message = document.getElementById('submission-status-message');
    if (!message) {
      message = document.createElement('p');
      message.id = 'submission-status-message';
      message.className = 'text-muted';
      message.style.margin = '8px 0 0';
      document.getElementById('save-draft-btn').parentElement.appendChild(message);
    }
    return message;
  }

  function operationError(error, operation) {
    const status = error.status || 0;
    const prefix = status ? `${operation} failed (${status}).` : `${operation} failed.`;
    let guidance = error.message || 'Please try again.';
    if (status === 401) guidance = 'Your session has expired. Please sign in again.';
    if (status === 403) guidance = error.message || 'This account is not authorized for this action.';
    if (status === 409) guidance = error.message || 'The submission state changed. Refresh and try again.';
    if (status === 422) guidance = error.message || 'One or more submitted values are invalid.';
    if (status >= 500) guidance = 'The server could not complete the request. Please try again.';
    const requestReference = error.requestId ? ` Reference: ${error.requestId}` : '';
    const text = `${prefix} ${guidance}${requestReference}`;
    const message = workflowMessage();
    message.textContent = text;
    message.style.color = 'var(--danger)';
    if (error.code === 'stale_submission') {
      const reload = document.createElement('button');
      reload.type = 'button';
      reload.className = 'btn btn-outline';
      reload.style.marginLeft = '8px';
      reload.textContent = 'Refresh submission';
      reload.addEventListener('click', async () => {
        reload.disabled = true;
        try { await loadCurrent(); }
        catch (refreshError) { operationError(refreshError, 'Refresh submission'); }
      });
      message.appendChild(reload);
    }
    console.warn(`[K-COSMOS] ${operation} failed`, { status, requestId: error.requestId || null });
    notify(text, 'error', operation);
  }

  function validateRequiredMetrics() {
    const missing = Object.entries(map).filter(([id, metricCode]) => {
      const definition = definitions.get(metricCode);
      return definition?.required_for_complete && definition.manager_editable
        && valueFor(document.getElementById(id)) === null;
    }).map(([, metricCode]) => definitions.get(metricCode).display_name || metricCode);
    if (missing.length) {
      const error = new Error(`Complete the required metrics: ${missing.join(', ')}.`);
      error.status = 422;
      throw error;
    }
  }

  function payload(includePeriod) {
    const values = Object.entries(map).map(([id, metricCode]) => ({
      metric_code: metricCode,
      value: valueFor(document.getElementById(id)),
      quality_note: null
    }));
    const body = { remarks: document.getElementById('remarks')?.value.trim() || null, values };
    // Waste sends its dry-material inventory alongside the metric values so
    // the backend saves both in one transaction. The derived dry and total
    // quantities are never sent: the server owns them.
    if (domain === 'waste' && window.KCosmosWasteInventory) {
      body.waste_items = window.KCosmosWasteInventory.items();
    }
    if (includePeriod) body.reporting_period_id = document.getElementById('month').value;
    if (currentSubmission) body.expected_row_version = currentSubmission.row_version;
    return body;
  }

  function statusLabel(status) {
    return status ? status.replaceAll('_', ' ').replace(/\b\w/g, char => char.toUpperCase()) : 'No draft';
  }

  function showStatus(submission) {
    const message = workflowMessage();
    if (!submission) {
      message.textContent = 'Status: No saved submission for this reporting period.';
      message.style.color = '';
      return;
    }
    const correction = submission.status === 'correction_requested' && submission.correction_reason
      ? ` — ${submission.correction_reason}` : '';
    message.textContent = `Status: ${statusLabel(submission.status)} · Revision ${submission.revision_number}${correction}`;
    message.style.color = submission.status === 'correction_requested' ? 'var(--danger)' : '';
    const lpgStatus = document.getElementById('prev-status');
    if (lpgStatus) lpgStatus.textContent = statusLabel(submission.status);
  }

  function showSuccess(text, submission) {
    const message = workflowMessage();
    message.textContent = `${text} Status: ${statusLabel(submission.status)} · Revision ${submission.revision_number}`;
    message.style.color = 'var(--success)';
  }

  function setEditable(editable) {
    const enabled = editable && !operationInProgress;
    document.querySelectorAll('#entry-form input, #entry-form textarea, #entry-form button').forEach(control => {
      if (['reporting-period-label', 'year', 'month'].includes(control.id)) return;
      control.disabled = !enabled;
    });
    document.getElementById('save-draft-btn').disabled = !enabled;
    document.getElementById('submit-btn').disabled = !enabled;
    document.getElementById('reset-btn').disabled = !enabled;
    ['autofill-inlet-btn', 'autofill-outlet-btn', 'autofill-stp-btn'].forEach(id => {
      const button = document.getElementById(id);
      if (button) button.disabled = !enabled;
    });
    (calculatedFields[domain] || []).forEach(id => {
      const input = document.getElementById(id);
      if (input) input.readOnly = true;
    });
    (calculatedSwitches[domain] || []).forEach(id => {
      const checkbox = document.getElementById(id);
      if (checkbox) checkbox.disabled = true;
    });
  }

  function populate(submission) {
    const byCode = new Map((submission?.values || []).map(item => [item.metric_code, item.value]));
    Object.entries(map).forEach(([id, metricCode]) => {
      document.getElementById(id).value = byCode.get(metricCode) ?? '';
    });
    const remarks = document.getElementById('remarks');
    if (remarks) remarks.value = submission?.remarks || '';
    document.querySelectorAll('#entry-form input').forEach(input => input.dispatchEvent(new Event('input')));
    showStatus(submission);
    setEditable(!submission || editableStatuses.has(submission.status));
    document.dispatchEvent(new CustomEvent('kcosmos:submission-loaded', { detail: { submission } }));
  }

  async function loadCurrent() {
    const sequence = ++currentLoadSequence;
    const periodId = document.getElementById('month').value;
    if (!periodId) return;
    let loaded;
    try {
      loaded = await request(`/submissions/current?reporting_period_id=${encodeURIComponent(periodId)}`);
    } catch (error) {
      if (sequence !== currentLoadSequence) return;
      throw error;
    }
    if (sequence !== currentLoadSequence) return;
    currentSubmission = loaded;
    populate(currentSubmission);
  }

  async function saveDraft(announce = true) {
    const isUpdate = currentSubmission && editableStatuses.has(currentSubmission.status);
    const path = isUpdate ? `/submissions/${currentSubmission.id}` : '/submissions';
    const method = isUpdate ? 'PUT' : 'POST';
    currentSubmission = await request(path, {
      method,
      body: JSON.stringify(payload(!isUpdate))
    });
    populate(currentSubmission);
    if (announce) {
      showSuccess('Draft saved.', currentSubmission);
      notify('Draft saved.', 'success', 'Save Draft');
    }
    return currentSubmission;
  }

  async function submitForReview() {
    validateRequiredMetrics();
    const submission = await saveDraft(false);
    await request(`/submissions/${submission.id}/submit`, { method: 'POST' });
    try {
      await loadCurrent();
    } catch (error) {
      currentSubmission = { ...submission, status: 'submitted' };
      populate(currentSubmission);
      console.warn('[K-COSMOS] Submitted state refresh failed', {
        status: error.status || 0,
        requestId: error.requestId || null
      });
      showSuccess('Submitted for review. Refresh this page to reload the latest server state.', currentSubmission);
      notify('Submitted for review. Status refresh is pending.', 'warning', 'Submit refresh');
      return;
    }
    if (!currentSubmission || currentSubmission.id !== submission.id || currentSubmission.status !== 'submitted') {
      currentSubmission = { ...submission, status: 'submitted' };
      populate(currentSubmission);
      showSuccess('Submitted for review. Refresh this page to reload the latest server state.', currentSubmission);
      notify('Submitted for review. Status refresh is pending.', 'warning', 'Submit refresh');
      return;
    }
    showSuccess('Submitted for review.', currentSubmission);
    notify('Submitted for review.', 'success', 'Submit for Review');
  }

  window.KCosmosSubmissionContext = {
    domain,
    getSubmission: () => currentSubmission,
    getStatus: () => currentSubmission?.status || 'draft',
    ensureDraft: () => saveDraft(false)
  };

  function replaceButton(id, operation, handler) {
    const oldButton = document.getElementById(id);
    const button = oldButton.cloneNode(true);
    oldButton.replaceWith(button);
    button.addEventListener('click', async event => {
      event.preventDefault();
      if (operationInProgress) return;
      operationInProgress = true;
      showStatus(currentSubmission);
      setEditable(Boolean(!currentSubmission || editableStatuses.has(currentSubmission.status)));
      try { await handler(); }
      catch (error) { operationError(error, operation); }
      finally {
        operationInProgress = false;
        setEditable(Boolean(!currentSubmission || editableStatuses.has(currentSubmission.status)));
      }
    });
  }

  async function initialize() {
    try {
      const session = await getSession();
      if (session.user.role !== 'manager' || session.user.manager_domain !== domain) {
        window.location.replace(`${domain}-login.html`);
        return;
      }
      [currentPeriod, definitions] = await Promise.all([
        request('/current-period'),
        request('/metrics').then(items => new Map(items.map(item => [item.code, item])))
      ]);
      for (const metricCode of Object.values(map)) {
        if (!definitions.has(metricCode)) throw new Error(`Backend metric definition is missing: ${metricCode}`);
        if (!definitions.get(metricCode).manager_editable) throw new Error(`Calculated metric cannot be edited: ${metricCode}`);
      }
      document.getElementById('year').value = String(currentPeriod.year);
      document.getElementById('month').value = currentPeriod.id;
      document.getElementById('reporting-period-label').value = currentPeriod.label;
      document.getElementById('ay').innerHTML = `<option>${currentPeriod.year}-${currentPeriod.year + 1}</option>`;
      replaceButton('save-draft-btn', 'Save Draft', saveDraft);
      replaceButton('submit-btn', 'Submit for Review', submitForReview);
      (calculatedFields[domain] || []).forEach(id => { document.getElementById(id).readOnly = true; });
      (calculatedSwitches[domain] || []).forEach(id => {
        const checkbox = document.getElementById(id);
        if (checkbox) {
          checkbox.checked = true;
          checkbox.disabled = true;
        }
      });
      await loadCurrent();
    } catch (error) {
      operationError(error, 'Initialize manager form');
      setEditable(false);
    }
  }

  document.addEventListener('DOMContentLoaded', initialize);
})();
