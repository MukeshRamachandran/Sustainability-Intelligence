document.addEventListener('DOMContentLoaded', async () => {
  const form = document.getElementById('outreach-entry-form');
  if (!form) return;

  let currentProgrammeId = null;
  let currentSubmissionId = null;
  let currentRowVersion = null;
  let currentStatus = 'draft';
  let operationInProgress = false;
  const field = id => document.getElementById(id);
  const nullableInteger = id => field(id).value.trim() === '' ? null : field(id).value.trim();
  const nullableDecimal = id => field(id).value.trim() === '' ? null : field(id).value.trim();
  const themeMap = {
    'Climate Smart Agriculture': 'climate_smart_agriculture',
    'Climate Change': 'climate_change',
    'Afforestation': 'afforestation',
    'Water Conservation': 'water_conservation',
    'Waste Management': 'waste_management',
    'Biodiversity Conservation': 'biodiversity_conservation',
    'HWCC': 'hwcc',
    'Livelihood Development': 'livelihood_development',
    'Campus Sustainability': 'campus_sustainability',
    'Other': 'other'
  };
  const reverseTheme = Object.fromEntries(Object.entries(themeMap).map(([label, code]) => [code, label]));
  const monthNames = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  function periodLabel(value) {
    const [year, month] = String(value || '').split('-').map(Number);
    return year && monthNames[month] ? `${monthNames[month]} ${year}` : String(value || '');
  }

  function notify(message, type, operation) {
    try {
      window.KCosmosUI?.notify?.(message, type, { operation });
    } catch {
      console.warn('[K-COSMOS] UI notification could not be displayed.', { operation });
    }
  }

  function workflowMessage() {
    let message = field('outreach-workflow-message');
    if (!message) {
      message = document.createElement('p');
      message.id = 'outreach-workflow-message';
      message.className = 'text-muted';
      message.style.margin = '8px 0 0';
      field('save-draft-btn').parentElement.appendChild(message);
    }
    return message;
  }

  function showOperationMessage(text, kind = 'status') {
    const message = workflowMessage();
    message.textContent = text;
    message.style.color = kind === 'error' ? 'var(--danger)' : kind === 'success' ? 'var(--success)' : '';
  }

  function operationError(error, operation) {
    const status = error.status || 0;
    const requestReference = error.requestId ? ` Reference: ${error.requestId}` : '';
    const text = `${operation} failed${status ? ` (${status})` : ''}. ${error.message || 'Please try again.'}${requestReference}`;
    showOperationMessage(text, 'error');
    if (error.code === 'stale_submission' && currentProgrammeId) {
      const reload = document.createElement('button');
      reload.type = 'button';
      reload.className = 'btn btn-outline';
      reload.style.marginLeft = '8px';
      reload.textContent = 'Refresh submission';
      reload.addEventListener('click', async () => {
        reload.disabled = true;
        try {
          populate(await KCosmos.api(`/api/manager/outreach/programmes/${currentProgrammeId}`));
        } catch (refreshError) {
          operationError(refreshError, 'Refresh Outreach submission');
        }
      });
      workflowMessage().appendChild(reload);
    }
    console.warn(`[K-COSMOS] ${operation} failed`, { status, requestId: error.requestId || null });
    notify(text, 'error', operation);
  }

  function rememberProgramme(programmeId) {
    const url = new URL(window.location.href);
    if (programmeId) url.searchParams.set('programme', programmeId);
    else url.searchParams.delete('programme');
    window.history.replaceState(null, '', url);
  }

  function payload(includePeriod) {
    const result = {
      programme_name: field('programme-name').value.trim(),
      programme_date: field('programme-date').value,
      theme: themeMap[field('programme-theme').value],
      other_theme: field('programme-theme').value === 'Other' ? field('other-theme').value.trim() || null : null,
      partner_organisation: field('partner-organisation').value.trim() || null,
      programme_location: field('programme-location').value.trim() || null,
      programme_description: field('programme-description').value.trim() || null,
      school_students: nullableInteger('participant-school'),
      college_students: nullableInteger('participant-college'),
      farmers_agriculture: nullableInteger('participant-farmers'),
      industrial_experts: nullableInteger('participant-industrial'),
      researchers_experts: nullableInteger('participant-researchers'),
      government_participants: nullableInteger('participant-government'),
      saplings_planted: nullableInteger('saplings-planted'),
      waste_collected_kg: nullableDecimal('waste-collected-kg'),
      species_identified_count: nullableInteger('species-identified-count'),
      species_details: Array.from(document.querySelectorAll('.species-row')).map(row => {
        const name = row.querySelector('.species-name')?.value.trim() || '';
        const count = row.querySelector('.species-count')?.value.trim() || '0';
        return name ? { species_name: name, count: count } : null;
      }).filter(Boolean),
      species_verification_notes: field('species-verification-notes')?.value.trim() || null,
      experts_involved: nullableInteger('experts-involved'),
      volunteers_engaged: nullableInteger('volunteers-engaged'),
      volunteer_hours: nullableDecimal('volunteer-hours'),
      remarks: field('remarks').value.trim() || null
    };
    if (includePeriod) result.reporting_period_id = field('reporting-month').value;
    if (!includePeriod && currentRowVersion) result.expected_row_version = currentRowVersion;
    return result;
  }

  function setStatus(status) {
    currentStatus = status;
    const badge = field('topbar-status-badge');
    badge.textContent = status.replaceAll('_', ' ');
    badge.className = `badge ${status === 'approved' ? 'badge-approved' : status === 'correction_requested' ? 'badge-correction' : status === 'draft' ? 'badge-draft' : 'badge-submitted'}`;
    const locked = !['draft', 'correction_requested'].includes(status);
    form.querySelectorAll('input,select,textarea').forEach(element => {
      if (element.id !== 'participant-total') element.disabled = locked;
    });
    field('save-draft-btn').disabled = locked;
    field('submit-review-btn').disabled = locked;
    field('modal-confirm-btn').disabled = locked;
    if (operationInProgress) {
      field('save-draft-btn').disabled = true;
      field('submit-review-btn').disabled = true;
      field('modal-confirm-btn').disabled = true;
    }
    document.dispatchEvent(new CustomEvent('kcosmos:submission-loaded', {
      detail: { submission: currentSubmissionId ? { id: currentSubmissionId, status: currentStatus } : null }
    }));
  }

  function populate(programme) {
    currentProgrammeId = programme.id;
    currentSubmissionId = programme.submission_id;
    currentRowVersion = programme.row_version;
    field('reporting-month').value = programme.reporting_period_id;
    field('reporting-year').value = String(Number(programme.reporting_period_label.slice(0, 4)));
    field('reporting-period-label').value = periodLabel(programme.reporting_period_label);
    field('programme-date').value = programme.programme_date;
    field('programme-name').value = programme.programme_name;
    field('programme-theme').value = reverseTheme[programme.theme] || 'Other';
    field('other-theme').value = programme.other_theme || '';
    field('other-theme-container').classList.toggle('d-none', programme.theme !== 'other');
    const values = {
      'partner-organisation': programme.partner_organisation,
      'programme-location': programme.programme_location,
      'programme-description': programme.programme_description,
      'participant-school': programme.school_students,
      'participant-college': programme.college_students,
      'participant-farmers': programme.farmers_agriculture,
      'participant-industrial': programme.industrial_experts,
      'participant-researchers': programme.researchers_experts,
      'participant-government': programme.government_participants,
      'saplings-planted': programme.saplings_planted,
      'waste-collected-kg': programme.waste_collected_kg,
      'species-identified-count': programme.species_identified_count,
      'species-verification-notes': programme.species_verification_notes,
      'experts-involved': programme.experts_involved,
      'volunteers-engaged': programme.volunteers_engaged,
      'volunteer-hours': programme.volunteer_hours,
      'remarks': programme.remarks
    };
    Object.entries(values).forEach(([id, value]) => { if (field(id)) field(id).value = value ?? ''; });
    if (Array.isArray(programme.species_details) && programme.species_details.length > 0) {
      const container = field('species-list-container');
      if (container) {
        container.innerHTML = '';
        programme.species_details.forEach(item => {
          const row = document.createElement('div');
          row.className = 'species-row';
          row.innerHTML = `
            <div class="form-group mb-0 flex-1">
              <label class="form-label font-xs text-muted">Species Name</label>
              <input type="text" class="form-control species-name" placeholder="Enter species name (e.g., Neem)">
            </div>
            <div class="form-group mb-0" style="flex: 0 0 160px;">
              <label class="form-label font-xs text-muted">Number Identified</label>
              <input type="number" class="form-control species-count" placeholder="0" min="0" step="1">
            </div>
            <div class="species-remove-wrap">
              <label class="form-label font-xs" style="visibility: hidden;">Action</label>
              <button type="button" class="btn btn-outline-danger species-remove-btn" title="Remove Species">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                <span>Remove</span>
              </button>
            </div>
          `;
          row.querySelector('.species-name').value = item.species_name || '';
          row.querySelector('.species-count').value = item.count ?? 0;
          container.appendChild(row);
        });
      }
    }
    /* The page's own calculators (participant total, species
       total, summary preview) listen for `input` on each individual field.
       An event dispatched on the form bubbles UP and never reaches those
       children, which left the read-only totals showing 0 after a reload even
       though the fields were populated. Dispatch per field instead, as the
       generic manager module does. */
    form.querySelectorAll('input, select, textarea').forEach(element => {
      element.dispatchEvent(new Event('input', { bubbles: true }));
      element.dispatchEvent(new Event('change', { bubbles: true }));
    });
    setStatus(programme.status);
    if (programme.correction_reason) notify(`Correction requested: ${programme.correction_reason}`, 'warning', 'Load Outreach');
  }

  async function saveDraft(announce = true) {
    const body = payload(!currentProgrammeId);
    if (!body.programme_name || !body.programme_date || !body.theme || (!currentProgrammeId && !body.reporting_period_id)) {
      throw new Error('Select a reporting period and complete programme name, date and theme.');
    }
    const path = currentProgrammeId
      ? `/api/manager/outreach/programmes/${currentProgrammeId}`
      : '/api/manager/outreach/programmes';
    const saved = await KCosmos.api(path, { method: currentProgrammeId ? 'PUT' : 'POST', body: JSON.stringify(body) });
    currentProgrammeId = saved.id;
    currentSubmissionId = saved.submission_id;
    currentRowVersion = saved.row_version;
    setStatus(saved.status);
    rememberProgramme(saved.id);
    if (announce) {
      showOperationMessage('Draft saved. Status: Draft.', 'success');
      notify('Draft saved.', 'success', 'Save Draft');
    }
    return saved;
  }

  /* Shared-context contract: `id` is always the SUBMISSION id, because that is
     what evidence-manager.js posts to /api/manager/{domain}/submissions/{id}/evidence.

     Outreach is the only domain where saveDraft() returns a different entity -
     the programme - whose `id` is the programme id and which carries the
     submission id separately as `submission_id`. Returning the programme from
     ensureDraft() made evidence upload post the programme id and fail with
     404 "Submission not found". Both accessors now build the same shape so
     they cannot drift apart again. */
  const submissionRef = () =>
    currentSubmissionId ? { id: currentSubmissionId, status: currentStatus } : null;

  window.KCosmosSubmissionContext = {
    domain: 'outreach',
    getSubmission: submissionRef,
    getStatus: () => currentStatus,
    ensureDraft: async () => {
      await saveDraft(false);
      return submissionRef();
    }
  };

  try {
    const user = await KCosmos.requireRole('manager', 'outreach');
    document.querySelectorAll('#user-role-badge').forEach(item => { item.textContent = user.display_name; });
    const currentPeriod = await KCosmos.api('/api/manager/outreach/current-period');
    field('reporting-year').value = String(currentPeriod.year);
    field('reporting-month').value = currentPeriod.id;
    field('reporting-period-label').value = currentPeriod.label;
    const requested = new URLSearchParams(window.location.search).get('programme');
    if (requested) {
      const programme = await KCosmos.api(`/api/manager/outreach/programmes/${requested}`);
      populate(programme);
    } else {
      const programmes = await KCosmos.api('/api/manager/outreach/programmes');
      const currentProgramme = programmes.find(item => item.reporting_period_id === currentPeriod.id);
      if (currentProgramme) populate(currentProgramme);
    }
  } catch (error) {
    operationError(error, 'Initialize Outreach form');
    return;
  }

  document.addEventListener('click', async event => {
    const target = event.target.closest('button');
    if (!target) return;
    if (target.id === 'save-draft-btn') {
      event.preventDefault(); event.stopImmediatePropagation();
      if (operationInProgress) return;
      operationInProgress = true;
      setStatus(currentStatus);
      showOperationMessage(`Status: ${currentStatus.replaceAll('_', ' ')}.`);
      try { await saveDraft(); }
      catch (error) { operationError(error, 'Save Draft'); }
      finally { operationInProgress = false; setStatus(currentStatus); }
    }
    if (target.id === 'modal-confirm-btn') {
      event.preventDefault(); event.stopImmediatePropagation();
      if (operationInProgress) return;
      operationInProgress = true;
      setStatus(currentStatus);
      field('confirm-submit-modal').classList.remove('active');
      try {
        await saveDraft(false);
        await KCosmos.api(`/api/manager/outreach/submissions/${currentSubmissionId}/submit`, { method: 'POST' });
        setStatus('submitted');
        try {
          const authoritative = await KCosmos.api(`/api/manager/outreach/programmes/${currentProgrammeId}`);
          populate(authoritative);
        } catch (error) {
          console.warn('[K-COSMOS] Outreach submitted state refresh failed', {
            status: error.status || 0,
            requestId: error.requestId || null
          });
          showOperationMessage('Submitted for review. Refresh this page to reload the latest server state.', 'success');
          notify('Submitted for review. Status refresh is pending.', 'warning', 'Submit refresh');
          return;
        }
        if (currentStatus !== 'submitted') {
          setStatus('submitted');
          showOperationMessage('Submitted for review. Refresh this page to reload the latest server state.', 'success');
          notify('Submitted for review. Status refresh is pending.', 'warning', 'Submit refresh');
          return;
        }
        showOperationMessage('Submitted for review. Status: Submitted.', 'success');
        notify('Submitted for review.', 'success', 'Submit for Review');
      } catch (error) { operationError(error, 'Submit for Review'); }
      finally { operationInProgress = false; setStatus(currentStatus); }
    }
  }, true);

  field('clear-form-btn').addEventListener('click', () => {
    currentProgrammeId = null; currentSubmissionId = null; currentRowVersion = null; currentStatus = 'draft';
    rememberProgramme(null);
    document.dispatchEvent(new CustomEvent('kcosmos:submission-loaded', { detail: { submission: null } }));
    notify('Unsaved form fields cleared. Server records were not deleted.', 'info', 'Clear form');
  });
  field('header-reset-btn').addEventListener('click', () => {
    currentProgrammeId = null; currentSubmissionId = null; currentRowVersion = null; currentStatus = 'draft';
    rememberProgramme(null);
    document.dispatchEvent(new CustomEvent('kcosmos:submission-loaded', { detail: { submission: null } }));
  });
});
