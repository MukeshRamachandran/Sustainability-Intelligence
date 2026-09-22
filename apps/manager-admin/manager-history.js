(function () {
  const entryPages = {
    transport: 'transport-entry.html',
    energy: 'energy-entry.html',
    lpg: 'lpg-entry.html',
    water: 'water-entry.html',
    outreach: 'community-outreach-entry.html'
  };
  const badgeClasses = {
    draft: 'badge-draft',
    submitted: 'badge-submitted',
    under_review: 'badge-review',
    correction_requested: 'badge-correction',
    approved: 'badge-approved'
  };

  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));

  function label(value) {
    return value.replaceAll('_', ' ').replace(/\b\w/g, char => char.toUpperCase());
  }

  async function initialize() {
    const tbody = document.getElementById('history-table-body');
    try {
      const session = await getSession();
      const user = session.user;
      if (user.role !== 'manager' || !entryPages[user.manager_domain]) {
        window.location.replace('index.html');
        return;
      }
      const domain = user.manager_domain;
      const entryPage = entryPages[domain];
      document.getElementById('monthly-entry-link').href = entryPage;
      document.getElementById('user-role-badge').textContent = `${label(domain)} Manager`;
      document.getElementById('logout-btn').addEventListener('click', event => {
        event.preventDefault();
        KCosmosAuth.logoutTo(`${domain}-login.html`);
      });
      const submissions = await apiRequest(`/api/manager/${domain}/submissions`);
      if (!submissions.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted" style="padding:24px">No submissions found.</td></tr>';
        return;
      }
      tbody.innerHTML = submissions.map(submission => {
        const editable = ['draft', 'correction_requested'].includes(submission.status);
        const actionText = submission.status === 'draft' ? 'Edit Draft'
          : submission.status === 'correction_requested' ? 'Resubmit' : 'View';
        const actionClass = submission.status === 'correction_requested' ? 'btn btn-warning' :
          editable ? 'btn btn-primary' : 'btn btn-outline';
        const href = domain === 'outreach' ? entryPage :
          `${entryPage}?reporting_period_id=${encodeURIComponent(submission.reporting_period_id)}`;
        const submittedAt = submission.submitted_at
          ? new Date(submission.submitted_at).toLocaleString() : '—';
        return `<tr>
          <td><strong>${escapeHtml(submission.id)}</strong></td>
          <td>${escapeHtml(submission.reporting_period_label)}</td>
          <td>${escapeHtml(label(domain))}</td>
          <td>${escapeHtml(submittedAt)}</td>
          <td><span class="badge ${badgeClasses[submission.status] || 'badge-draft'}">${escapeHtml(label(submission.status))}</span></td>
          <td style="max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--danger);font-size:13px">${escapeHtml(submission.correction_reason || '—')}</td>
          <td><a href="${href}" class="${actionClass}" style="padding:4px 8px;font-size:12px">${actionText}</a></td>
        </tr>`;
      }).join('');
    } catch (error) {
      if (error.status === 401) {
        window.location.replace('index.html');
        return;
      }
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger" style="padding:24px">${escapeHtml(error.message)}</td></tr>`;
    }
  }

  document.addEventListener('DOMContentLoaded', initialize);
})();
