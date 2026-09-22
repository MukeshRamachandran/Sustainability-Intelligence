(function () {
  const domains = ['transport', 'energy', 'lpg', 'water', 'outreach'];
  const labels = {
    transport: 'Transport + DG',
    energy: 'Energy + Renewable',
    lpg: 'LPG',
    water: 'Water',
    outreach: 'Outreach'
  };

  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[character]);

  document.addEventListener('DOMContentLoaded', async () => {
    const body = document.getElementById('overview-table-body');
    try {
      const queues = await Promise.all(domains.map(async domain => {
        const items = await apiRequest(`/api/admin/review-queue?domain=${domain}`);
        return items.map(item => ({ ...item, domain }));
      }));
      const submissions = queues.flat();
      document.getElementById('stat-pending').textContent = submissions.length;
      document.getElementById('stat-approved').textContent = '—';
      document.getElementById('stat-correction').textContent = '—';
      document.getElementById('stat-missing').textContent = '—';

      body.innerHTML = domains.map(domain => {
        const item = submissions.find(entry => entry.domain === domain);
        if (!item) {
          return `<tr><td><strong>${labels[domain]}</strong></td><td colspan="3" class="text-muted">No submission awaiting review</td><td>—</td><td><a href="admin-queue.html" class="btn btn-outline" style="padding:4px 8px;font-size:12px;">Open queue</a></td></tr>`;
        }
        const status = escapeHtml(item.status.replaceAll('_', ' '));
        const submitted = item.submitted_at ? new Date(item.submitted_at).toLocaleString() : '—';
        return `<tr><td><strong>${labels[domain]}</strong></td><td>${escapeHtml(item.reporting_period_label)}</td><td>${escapeHtml(item.manager_display_name)}</td><td>${escapeHtml(submitted)}</td><td><span class="badge badge-review">${status}</span></td><td><a href="admin-queue.html?submission=${encodeURIComponent(item.id)}" class="btn btn-outline" style="padding:4px 8px;font-size:12px;">Review</a></td></tr>`;
      }).join('');
    } catch (error) {
      body.innerHTML = '<tr><td colspan="6" class="text-center text-muted">Unable to load the review queue.</td></tr>';
      showToast(error.message, 'error');
    }
  });
})();
