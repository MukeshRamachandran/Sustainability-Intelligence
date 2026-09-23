(function () {
  const editableStatuses = new Set(['draft', 'correction_requested']);
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[character]);
  const formatSize = bytes => bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

  function attachment(input) {
    return {
      metricCode: input.dataset.evidenceMetric || null,
      category: input.dataset.evidenceCategory || null
    };
  }

  function matches(item, target) {
    return target.metricCode ? item.metric_code === target.metricCode : item.evidence_category === target.category;
  }

  document.addEventListener('DOMContentLoaded', () => {
    const domain = document.body.dataset.authDomain;
    const inputs = Array.from(document.querySelectorAll('[data-evidence-input]'));
    if (!domain || !inputs.length || !window.KCosmosEvidence) return;
    let records = [];
    let loadSequence = 0;
    const busySlots = new Set();

    function context() {
      return window.KCosmosSubmissionContext;
    }

    function containerFor(input) {
      const key = input.dataset.evidenceList;
      return document.querySelector(`[data-evidence-container="${CSS.escape(key)}"]`);
    }

    function slotKey(input) {
      return input.dataset.evidenceList;
    }

    function statusFor(input) {
      const key = slotKey(input);
      let status = document.querySelector(`[data-evidence-status="${CSS.escape(key)}"]`);
      if (status) return status;
      const container = containerFor(input);
      if (!container) return null;
      status = document.createElement('p');
      status.className = 'text-muted mt-1';
      status.dataset.evidenceStatus = key;
      status.style.display = 'none';
      container.parentNode.insertBefore(status, container);
      return status;
    }

    function showStatus(input, message, kind = 'info') {
      const status = statusFor(input);
      if (!status) return;
      status.textContent = message;
      status.style.display = message ? '' : 'none';
      status.style.color = kind === 'error' ? 'var(--danger)' : '';
      status.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    }

    function safeDiagnostic(operation, error) {
      console.warn('[K-COSMOS] Evidence operation failed.', {
        operation,
        status: Number.isInteger(error?.status) ? error.status : null,
        requestId: error?.requestId || null
      });
    }

    function notify(message, type, operation) {
      try {
        window.KCosmosUI?.notify?.(message, type, { operation });
      } catch {
        console.warn('[K-COSMOS] UI notification could not be displayed.', { operation });
      }
    }

    function isEditable() {
      const submission = context()?.getSubmission();
      return !submission || editableStatuses.has(submission.status);
    }

    function isBusy(input) {
      return busySlots.has(slotKey(input));
    }

    function setBusy(input, busy, message = '') {
      const key = slotKey(input);
      if (busy) busySlots.add(key);
      else busySlots.delete(key);
      input.disabled = busy || !isEditable();
      const container = containerFor(input);
      if (container) {
        container.setAttribute('aria-busy', busy ? 'true' : 'false');
        container.querySelectorAll('.evidence-replace, .evidence-remove').forEach(button => {
          button.disabled = busy || !isEditable();
        });
      }
      if (message) showStatus(input, message);
    }

    function resetInput(input) {
      input.value = '';
      delete input.dataset.replacesEvidenceId;
    }

    function mutationErrorMessage(operation, error) {
      /* A bare "Evidence upload failed." hides why, which makes a draft-not-saved
         problem look identical to a rejected file. Surface the actual reason and
         the request id, without leaking internals. */
      const status = error?.status || 0;
      const noun = operation === 'remove' ? 'Evidence could not be removed.' : 'Evidence upload failed.';
      if (status === 409) return 'Evidence cannot be changed after submission.';
      let reason = '';
      if (!status) reason = error?.message || 'The server could not be reached.';
      else if (status === 401) reason = 'Your session has expired. Please sign in again.';
      else if (status === 403) reason = error?.message || 'You are not authorized for this action.';
      else if (status === 404) reason = 'Save the draft before adding evidence, then try again.';
      else if (status === 413) reason = 'The file exceeds the 10 MB maximum.';
      else if (status === 415 || status === 422) reason = error?.message || 'Only PDF, PNG and JPG files are accepted.';
      else if (status >= 500) reason = 'The server could not complete the request.';
      const reference = error?.requestId ? ` Reference: ${error.requestId}` : '';
      return `${noun}${reason ? ` ${reason}` : ''}${reference}`;
    }

    function renderSlot(input) {
      const container = containerFor(input);
      if (!container) return;
      const submission = context()?.getSubmission();
      const target = attachment(input);
      const relevant = records.filter(item => matches(item, target));
      const temporary = relevant.filter(item => (
        item.lifecycle_state ? item.lifecycle_state === 'temporary' : item.committed_at === null
      ));
      const committed = relevant.filter(item => !temporary.includes(item));
      const working = temporary.filter(item => item.is_current && !item.removed_at);
      const editable = isEditable();
      const busy = isBusy(input);
      input.disabled = busy || !editable;
      const disabledAttribute = busy ? ' disabled aria-disabled="true"' : '';
      const workingTitle = submission?.status === 'correction_requested'
        ? '<p class="mt-1"><strong>Current Correction Evidence</strong></p>'
        : '';
      const workingHtml = working.length ? working.map(item => `
        <div class="card mt-1" style="padding:10px;">
          <strong>${escapeHtml(item.original_filename)}</strong><br>
          <span class="text-muted">${escapeHtml(item.mime_type)} • ${formatSize(item.file_size_bytes)} • Working revision ${item.revision_number} • Temporary</span>
          <div class="d-flex gap-2 mt-1">
            <a class="btn btn-outline" target="_blank" rel="noopener" href="${escapeHtml(KCosmosEvidence.contentUrl('manager', domain, item.id))}">View</a>
            <a class="btn btn-outline" href="${escapeHtml(KCosmosEvidence.contentUrl('manager', domain, item.id, true))}">Download</a>
            ${editable ? `<button type="button" class="btn btn-outline evidence-replace" data-evidence-id="${item.id}"${disabledAttribute}>Replace</button><button type="button" class="btn btn-outline evidence-remove" data-evidence-id="${item.id}"${disabledAttribute}>Remove</button>` : ''}
          </div>
        </div>`).join('') : '<p class="text-muted mt-1">No evidence uploaded</p>';
      const currentRevision = submission?.revision_number;
      const currentCommitted = committed.filter(item => item.revision_number === currentRevision);
      const priorCommitted = committed.filter(item => item.revision_number !== currentRevision);
      const committedCards = items => items.map(item => `
        <div class="card mt-1" style="padding:10px;">
          <strong>${escapeHtml(item.original_filename)}</strong><br>
          <span class="text-muted">${escapeHtml(item.mime_type)} • ${formatSize(item.file_size_bytes)} • Revision ${item.revision_number} • Committed</span>
          <div class="d-flex gap-2 mt-1">
            <a class="btn btn-outline" target="_blank" rel="noopener" href="${escapeHtml(KCosmosEvidence.contentUrl('manager', domain, item.id))}">View</a>
            <a class="btn btn-outline" href="${escapeHtml(KCosmosEvidence.contentUrl('manager', domain, item.id, true))}">Download</a>
          </div>
        </div>`).join('');
      if (editable) {
        const priorHtml = committed.length
          ? `<div class="mt-2"><p><strong>Previously Submitted Evidence</strong></p>${committedCards(committed)}</div>`
          : '';
        container.innerHTML = workingTitle + workingHtml + priorHtml;
      } else {
        const submitted = currentCommitted.length ? currentCommitted : committed;
        const history = currentCommitted.length ? priorCommitted : [];
        const historyHtml = history.length
          ? `<details class="mt-1"><summary>Previous submitted revisions (${history.length})</summary>${committedCards(history)}</details>`
          : '';
        container.innerHTML = (submitted.length ? committedCards(submitted) : workingHtml) + historyHtml;
      }
      container.querySelectorAll('.evidence-replace').forEach(button => button.addEventListener('click', event => {
        event.preventDefault();
        if (isBusy(input) || !isEditable()) return;
        input.value = '';
        input.dataset.replacesEvidenceId = button.dataset.evidenceId;
        input.click();
      }));
      container.querySelectorAll('.evidence-remove').forEach(button => button.addEventListener('click', async event => {
        event.preventDefault();
        if (isBusy(input) || !isEditable()) return;
        const submission = context()?.getSubmission();
        if (!submission) return;
        const evidenceId = button.dataset.evidenceId;
        let removed = false;
        setBusy(input, true, 'Removing evidence…');
        try {
          await KCosmosEvidence.removeManager(domain, submission.id, evidenceId);
          removed = true;
          resetInput(input);
          await load();
          showStatus(input, 'Evidence removed. You can upload this file or a different file again.');
          notify('Evidence removed from the current revision.', 'success', 'Remove evidence');
        } catch (error) {
          safeDiagnostic(removed ? 'remove-refresh' : 'remove', error);
          const message = removed
            ? 'Evidence was removed, but the updated evidence list could not be loaded. Refresh this page.'
            : mutationErrorMessage('remove', error);
          showStatus(input, message, 'error');
          notify(message, 'error', 'Remove evidence');
        } finally {
          resetInput(input);
          setBusy(input, false);
        }
      }));
    }

    function render() {
      inputs.forEach(renderSlot);
    }

    async function load() {
      const sequence = ++loadSequence;
      const submission = context()?.getSubmission();
      if (!submission) {
        if (sequence !== loadSequence) return;
        records = [];
        render();
        return;
      }
      let loadedRecords;
      try {
        loadedRecords = await KCosmosEvidence.listManager(domain, submission.id);
      } catch (error) {
        if (sequence !== loadSequence) return;
        throw error;
      }
      // ensureDraft emits submission-loaded while an upload is beginning. An
      // older GET must never overwrite the newer post-mutation refresh.
      if (sequence !== loadSequence) return;
      records = loadedRecords;
      render();
    }

    async function loadSafely() {
      try {
        await load();
      } catch (error) {
        safeDiagnostic('load', error);
        inputs.forEach(input => showStatus(input, 'Evidence could not be loaded. Refresh this page.', 'error'));
        notify('Evidence could not be loaded.', 'error', 'Load evidence');
      }
    }

    inputs.forEach(input => input.addEventListener('change', async () => {
      const file = input.files?.[0];
      if (!file || isBusy(input) || !isEditable()) return;
      const target = attachment(input);
      const replacement = records.find(item => item.id === input.dataset.replacesEvidenceId)
        || records.find(item => item.lifecycle_state === 'temporary' && item.is_current && matches(item, target));
      const operation = replacement ? 'replace' : 'upload';
      let uploaded = false;
      setBusy(input, true, replacement ? 'Replacing evidence…' : 'Uploading evidence…');
      try {
        const submission = await context()?.ensureDraft();
        if (!submission) throw new Error('Save the draft before adding evidence.');
        // ensureDraft can run the page-wide editability routine. Reassert the
        // evidence lock so a double click cannot start a second mutation.
        setBusy(input, true);
        await KCosmosEvidence.uploadManager(domain, submission.id, file, target, replacement?.id);
        uploaded = true;
        resetInput(input);
        await load();
        const message = replacement ? 'Evidence replaced successfully.' : 'Evidence uploaded successfully.';
        showStatus(input, message);
        notify(message, 'success', operation);
      } catch (error) {
        safeDiagnostic(uploaded ? `${operation}-refresh` : operation, error);
        const message = uploaded
          ? 'Evidence was saved, but the updated evidence list could not be loaded. Refresh this page.'
          : mutationErrorMessage(operation, error);
        showStatus(input, message, 'error');
        notify(message, 'error', operation);
      } finally {
        resetInput(input);
        setBusy(input, false);
      }
    }));

    document.addEventListener('kcosmos:submission-loaded', () => { void loadSafely(); });
    void loadSafely();
  });
})();
