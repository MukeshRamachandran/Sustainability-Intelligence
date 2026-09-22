(function () {
  const body = document.getElementById('audit-table-body');
  let page = 1;
  let pages = 0;
  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);
  }
  function parameters() {
    const query = new URLSearchParams({ page: String(page), page_size: '25' });
    const action = document.getElementById('audit-action').value.trim();
    const actor = document.getElementById('audit-actor').value.trim();
    const domain = document.getElementById('audit-domain').value;
    const from = document.getElementById('audit-from').value;
    const to = document.getElementById('audit-to').value;
    if (action) query.set('action', action);
    if (actor) query.set('user', actor);
    if (domain) query.set('domain', domain);
    if (from) query.set('date_from', `${from}T00:00:00+05:30`);
    if (to) query.set('date_to', `${to}T23:59:59+05:30`);
    return query;
  }
  async function loadAudit() {
    body.innerHTML = '<tr><td colspan="8">Loading…</td></tr>';
    try {
      const result = await apiRequest(`/api/admin/audit-logs?${parameters()}`);
      pages = result.pages;
      body.innerHTML = result.items.length ? result.items.map(item => `<tr><td>${new Date(item.timestamp).toLocaleString()}</td><td>${escapeHtml(item.actor_display_name || item.actor_username || item.actor_type)}</td><td>${escapeHtml(item.action)}</td><td>${escapeHtml(item.domain || '—')}</td><td>${escapeHtml(item.resource_type)}<br><span class="text-muted">${escapeHtml(item.resource_id || '—')}</span></td><td>${escapeHtml(item.outcome)}</td><td><details><summary>View</summary><code>${escapeHtml(JSON.stringify(item.metadata))}</code></details></td><td>${escapeHtml(item.request_id || '—')}</td></tr>`).join('') : '<tr><td colspan="8" class="text-center text-muted">No audit records match these filters.</td></tr>';
      document.getElementById('audit-page-status').textContent = `${result.total} record(s) · Page ${result.page} of ${result.pages || 1}`;
      document.getElementById('audit-prev-btn').disabled = page <= 1;
      document.getElementById('audit-next-btn').disabled = !pages || page >= pages;
    } catch (error) { body.innerHTML = `<tr><td colspan="8" class="text-danger">${escapeHtml(error.message)}</td></tr>`; }
  }
  document.getElementById('audit-filter-form').addEventListener('submit', event => { event.preventDefault(); page = 1; loadAudit(); });
  document.getElementById('audit-clear-btn').addEventListener('click', () => { document.getElementById('audit-filter-form').reset(); page = 1; loadAudit(); });
  document.getElementById('audit-prev-btn').addEventListener('click', () => { if (page > 1) { page -= 1; loadAudit(); } });
  document.getElementById('audit-next-btn').addEventListener('click', () => { if (page < pages) { page += 1; loadAudit(); } });
  document.addEventListener('DOMContentLoaded', loadAudit);
})();
