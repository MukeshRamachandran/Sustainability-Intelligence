(function () {
  const body = document.getElementById('users-table-body');
  const message = document.getElementById('users-message');
  const dialog = document.getElementById('reset-password-dialog');

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, character => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    })[character]);
  }
  function showMessage(text, error = false) {
    message.textContent = text;
    message.style.color = error ? 'var(--danger)' : 'var(--success)';
  }
  function request(path, options = {}) {
    const write = options.method && options.method !== 'GET';
    return apiRequest(`/api/admin/users${path}`, { ...options, csrf: write });
  }
  function userRow(user) {
    const role = user.role === 'manager' ? `Manager · ${user.manager_domain}` : 'Microcosm Admin';
    const accountAction = user.is_active
      ? `<button class="btn btn-outline" data-action="deactivate" data-id="${user.id}">Deactivate</button>`
      : `<button class="btn btn-outline" data-action="activate" data-id="${user.id}">Activate</button>`;
    return `<tr><td><strong>${escapeHtml(user.display_name)}</strong><br><span class="text-muted">${escapeHtml(user.username)}</span></td><td>${escapeHtml(role)}</td><td>${user.is_active ? '<span class="badge badge-success">Active</span>' : '<span class="badge badge-danger">Inactive</span>'}</td><td>${user.must_change_password ? 'Change required' : 'Current'}</td><td>${user.active_session_count}</td><td>${user.last_login_at ? new Date(user.last_login_at).toLocaleString() : 'Never'}</td><td><div class="d-flex gap-2"><button class="btn btn-outline" data-action="reset" data-id="${user.id}">Reset password</button><button class="btn btn-outline" data-action="revoke-sessions" data-id="${user.id}">Revoke sessions</button>${accountAction}</div></td></tr>`;
  }
  async function loadUsers() {
    body.innerHTML = '<tr><td colspan="7">Loading…</td></tr>';
    try {
      const users = await request('');
      body.innerHTML = users.length ? users.map(userRow).join('') : '<tr><td colspan="7" class="text-center text-muted">No users found.</td></tr>';
    } catch (error) {
      body.innerHTML = `<tr><td colspan="7" class="text-danger">${escapeHtml(error.message)}</td></tr>`;
    }
  }
  document.getElementById('create-manager-form').addEventListener('submit', async event => {
    event.preventDefault();
    try {
      await request('', { method: 'POST', body: JSON.stringify({ username: document.getElementById('new-username').value, display_name: document.getElementById('new-display-name').value, manager_domain: document.getElementById('new-domain').value, temporary_password: document.getElementById('new-password').value }) });
      event.currentTarget.reset();
      showMessage('Manager created. Password change is required at first sign-in.');
      await loadUsers();
    } catch (error) { showMessage(error.message, true); }
  });
  body.addEventListener('click', async event => {
    const button = event.target.closest('button[data-action]');
    if (!button) return;
    const { action, id } = button.dataset;
    if (action === 'reset') {
      document.getElementById('reset-user-id').value = id;
      document.getElementById('reset-password').value = '';
      dialog.showModal();
      return;
    }
    if (!window.confirm(`Confirm ${action.replace('-', ' ')} for this user?`)) return;
    button.disabled = true;
    try {
      const result = await request(`/${id}/${action}`, { method: 'POST' });
      showMessage(result.message);
      await loadUsers();
    } catch (error) { showMessage(error.message, true); button.disabled = false; }
  });
  document.getElementById('reset-password-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (!window.confirm('Reset this user password and revoke all active sessions?')) return;
    try {
      const result = await request(`/${document.getElementById('reset-user-id').value}/reset-password`, { method: 'POST', body: JSON.stringify({ temporary_password: document.getElementById('reset-password').value }) });
      dialog.close();
      showMessage(result.message);
      await loadUsers();
    } catch (error) { showMessage(error.message, true); }
  });
  document.getElementById('cancel-reset-btn').addEventListener('click', () => dialog.close());
  document.getElementById('refresh-users-btn').addEventListener('click', loadUsers);
  document.addEventListener('DOMContentLoaded', loadUsers);
})();
