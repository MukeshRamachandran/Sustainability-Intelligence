/* Shared presentation helpers for the original Manager/Admin portal. */
(function () {
  function renderToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const label = document.createElement('span');
    label.textContent = message;
    toast.appendChild(label);
    container.appendChild(toast);

    window.setTimeout(() => {
      toast.style.animation = 'fadeOut 0.3s ease forwards';
      window.setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  function notify(message, type = 'info', diagnostic = {}) {
    try {
      renderToast(message, type);
    } catch {
      // Presentation must never turn a successful API operation into a failure.
      console.warn('[K-COSMOS] UI notification could not be displayed.', {
        operation: diagnostic.operation || 'notification'
      });
    }
  }

  window.KCosmosUI = { ...(window.KCosmosUI || {}), notify };
  try {
    // Replace any browser/host-injected function with the portal-owned helper.
    Object.defineProperty(window, 'showToast', {
      configurable: true,
      writable: true,
      value: notify
    });
  } catch {
    // Core workflows call KCosmosUI.notify directly and remain safe even when
    // an embedded browser exposes a non-configurable showToast property.
  }

  document.addEventListener('DOMContentLoaded', () => {
    const path = window.location.pathname.split('/').pop();
    document.querySelectorAll('.sidebar-nav .nav-item').forEach(link => {
      link.classList.toggle('active', link.getAttribute('href') === path);
    });
  });
})();
