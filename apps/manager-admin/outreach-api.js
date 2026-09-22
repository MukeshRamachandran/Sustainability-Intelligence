(function () {
  async function api(path, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    return apiRequest(path, {
      ...options,
      method,
      csrf: !['GET', 'HEAD', 'OPTIONS'].includes(method)
    });
  }

  async function session() {
    return (await getSession()).user;
  }

  async function requireRole(role, domain) {
    try {
      const user = await session();
      if (user.role !== role || (domain && user.manager_domain !== domain)) {
        window.location.replace('index.html?denied=1');
        throw new Error('Access denied');
      }
      if (user.must_change_password) {
        window.location.replace('change-password.html');
        throw new Error('Password change required');
      }
      return user;
    } catch (error) {
      if (error.status === 401) window.location.replace('index.html');
      throw error;
    }
  }

  window.KCosmos = { api, session, requireRole };
  if (typeof window.KCosmosUI?.notify !== 'function') {
    window.KCosmosUI = {
      ...(window.KCosmosUI || {}),
      notify(message, type = 'info', diagnostic = {}) {
        try {
          let container = document.getElementById('toast-container');
          if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container';
            document.body.appendChild(container);
          }
          const toast = document.createElement('div');
          toast.className = `toast ${type}`;
          toast.textContent = message;
          container.appendChild(toast);
          window.setTimeout(() => toast.remove(), 4000);
        } catch {
          console.warn('[K-COSMOS] UI notification could not be displayed.', {
            operation: diagnostic.operation || 'notification'
          });
        }
      }
    };
  }
  try {
    Object.defineProperty(window, 'showToast', {
      configurable: true,
      writable: true,
      value: window.KCosmosUI.notify
    });
  } catch {
    // Outreach workflow code uses the namespaced safe notifier directly.
  }
})();
