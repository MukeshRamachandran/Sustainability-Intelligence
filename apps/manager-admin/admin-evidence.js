(function () {
  const monthNames = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];
  const domainLabels = {
    transport: 'Transport', energy: 'Energy', lpg: 'LPG', water: 'Water', outreach: 'Outreach'
  };
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[character]);
  const formatSize = bytes => bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  const formatDate = value => value ? new Date(value).toLocaleString() : '—';
  let currentPage = 1;
  let totalPages = 0;
  let loading = false;

  function controls() {
    return document.getElementById('evidence-filters');
  }

  function applyUrlState() {
    const parameters = new URLSearchParams(window.location.search);
    controls().querySelectorAll('[name]').forEach(control => {
      if (parameters.has(control.name)) control.value = parameters.get(control.name);
    });
    currentPage = Math.max(1, Number.parseInt(parameters.get('page') || '1', 10) || 1);
  }

  function requestParameters(page) {
    const parameters = new URLSearchParams();
    new FormData(controls()).forEach((value, key) => {
      const normalized = String(value).trim();
      if (normalized && !(key === 'latest_revision' && normalized === 'true') && !(key === 'page_size' && normalized === '25')) {
        parameters.set(key, normalized);
      }
    });
    parameters.set('latest_revision', document.getElementById('filter-scope').value);
    parameters.set('page', String(page));
    parameters.set('page_size', document.getElementById('filter-page-size').value);
    return parameters;
  }

  function setLoading(value) {
    loading = value;
    document.getElementById('search-evidence').disabled = value;
    document.getElementById('previous-evidence-page').disabled = value || currentPage <= 1;
    document.getElementById('next-evidence-page').disabled = value || currentPage >= totalPages;
    if (value) document.getElementById('evidence-repository-status').textContent = 'Loading evidence...';
  }

  function itemRow(item) {
    const label = item.metric_display_name || item.evidence_category || 'General evidence';
    const revisionLabel = item.is_latest_revision ? 'Current submitted revision' : 'Previous submitted revision';
    return `<tr>
      <td><strong>${escapeHtml(label)}</strong><br><span class="text-muted">${escapeHtml(item.metric_code || item.evidence_category || 'general')}</span></td>
      <td><strong>${escapeHtml(item.original_filename)}</strong><br><span class="text-muted">${escapeHtml(item.mime_type)} • ${formatSize(item.file_size_bytes)}</span></td>
      <td>Revision ${escapeHtml(item.revision_number)}<br><span class="text-muted">${revisionLabel}</span></td>
      <td>${escapeHtml(item.uploaded_by.display_name)}<br><span class="text-muted">Committed ${escapeHtml(formatDate(item.committed_at))}</span></td>
      <td><a class="btn btn-outline" target="_blank" rel="noopener" href="${escapeHtml(KCosmosEvidence.contentUrl('admin', null, item.evidence_id))}">View</a> <a class="btn btn-outline" href="${escapeHtml(KCosmosEvidence.contentUrl('admin', null, item.evidence_id, true))}">Download</a></td>
    </tr><tr><td colspan="5"><details><summary>Audit details</summary><div class="grid-2 mt-1"><div><span class="text-muted">Submission status</span><br>${escapeHtml(item.submission_status.replaceAll('_', ' '))}</div><div><span class="text-muted">Uploaded</span><br>${escapeHtml(formatDate(item.uploaded_at))}</div><div><span class="text-muted">Submission ID</span><br>${escapeHtml(item.submission_id)}</div><div><span class="text-muted">Evidence ID</span><br>${escapeHtml(item.evidence_id)}</div><div style="grid-column:1/-1;overflow-wrap:anywhere;"><span class="text-muted">SHA-256</span><br>${escapeHtml(item.sha256)}</div></div></details></td></tr>`;
  }

  function render(data) {
    const target = document.getElementById('evidence-repository-results');
    if (!data.items.length) {
      target.innerHTML = '<div class="glass-card text-center text-muted" style="padding:32px;">No committed evidence found for the selected filters.</div>';
      document.getElementById('evidence-repository-status').textContent = '0 committed evidence records';
      document.getElementById('evidence-pagination').hidden = true;
      return;
    }
    const groups = new Map();
    data.items.forEach(item => {
      const key = `${item.reporting_period.year}-${item.reporting_period.month}-${item.domain}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(item);
    });
    target.innerHTML = Array.from(groups.values()).map(items => {
      const first = items[0];
      const period = `${monthNames[first.reporting_period.month]} ${first.reporting_period.year}`;
      return `<section class="glass-card mb-3"><div class="d-flex justify-between align-center mb-2"><div><h2>${escapeHtml(period)}</h2><p class="text-muted">${escapeHtml(domainLabels[first.domain] || first.domain)}</p></div><span class="badge badge-review">${escapeHtml(first.submission_status.replaceAll('_', ' '))}</span></div><div class="table-responsive"><table class="table"><thead><tr><th>Metric / Category</th><th>Evidence</th><th>Revision</th><th>Submitted by</th><th>Action</th></tr></thead><tbody>${items.map(itemRow).join('')}</tbody></table></div></section>`;
    }).join('');
    document.getElementById('evidence-repository-status').textContent = `${data.total_items} committed evidence record${data.total_items === 1 ? '' : 's'}`;
    document.getElementById('evidence-pagination').hidden = false;
    document.getElementById('evidence-page-summary').textContent = `Page ${data.page} of ${data.total_pages}`;
  }

  function safeErrorMessage(error) {
    if (error?.status === 401) return 'Your session has expired. Please sign in again.';
    if (error?.status === 403) return 'Access denied.';
    if (error?.status === 422) return 'One or more evidence filters are invalid.';
    return 'Evidence repository could not be loaded.';
  }

  async function load(page = 1) {
    if (loading) return;
    currentPage = page;
    const parameters = requestParameters(page);
    window.history.replaceState(null, '', `${window.location.pathname}?${parameters.toString()}`);
    setLoading(true);
    try {
      const data = await KCosmos.api(`/api/admin/evidence?${parameters.toString()}`);
      currentPage = data.page;
      totalPages = data.total_pages;
      render(data);
    } catch (error) {
      document.getElementById('evidence-repository-results').innerHTML = '';
      document.getElementById('evidence-repository-status').textContent = safeErrorMessage(error);
      document.getElementById('evidence-pagination').hidden = true;
      if (error?.status === 401) window.location.replace('admin-login.html');
    } finally {
      setLoading(false);
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    try {
      await KCosmos.requireRole('microcosm_admin');
    } catch (error) {
      // requireRole navigates away before throwing in these three cases; any
      // other failure must be visible rather than leaving a blank repository.
      const redirecting = error?.status === 401
        || error?.message === 'Access denied'
        || error?.message === 'Password change required';
      if (!redirecting) {
        document.getElementById('evidence-repository-status').textContent =
          'Unable to load the evidence repository. Please verify session/API connection.';
        // Diagnostic only: no session, filename or evidence content.
        console.error('[K-COSMOS] Evidence repository initialization failed.', {
          status: error?.status ?? null,
          code: error?.code ?? null,
          requestId: error?.requestId ?? null,
          message: error?.message || String(error)
        });
      }
      return;
    }
    applyUrlState();
    controls().addEventListener('submit', event => { event.preventDefault(); void load(1); });
    document.getElementById('clear-evidence-filters').addEventListener('click', () => {
      controls().reset();
      void load(1);
    });
    document.getElementById('previous-evidence-page').addEventListener('click', () => { if (currentPage > 1) void load(currentPage - 1); });
    document.getElementById('next-evidence-page').addEventListener('click', () => { if (currentPage < totalPages) void load(currentPage + 1); });
    await load(currentPage);
  });
})();
