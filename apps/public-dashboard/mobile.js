/* =====================================================================
   MICROCOSM — MOBILE ADDON (mobile.js)
   The few behaviours mobile.css can't do alone. Pure addon: it builds
   its own elements and toggles its own classes; app.js, styles.css and
   the dashboard's DOM contract are never modified. Everything is a
   no-op on desktop (the elements it adds are display:none there and
   the listeners are passive observers).
   ===================================================================== */
(function () {
  'use strict';

  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  ready(function () {

    /* ---------------- filter accordion bar ---------------- */
    // A compact summary bar prepended to the .toolbar. mobile.css shows
    // it only on phones and hides the real controls until it's tapped.
    var toolbar = document.querySelector('.toolbar');
    if (toolbar && !toolbar.querySelector('.mob-filter-toggle')) {
      var bar = document.createElement('button');
      bar.type = 'button';
      bar.className = 'mob-filter-toggle';
      bar.setAttribute('aria-expanded', 'false');
      bar.innerHTML =
        '<span class="mob-ft-chev" aria-hidden="true">▸</span>' +
        '<span class="mob-ft-text">Filters</span>' +
        '<span class="mob-ft-hint">Filters</span>';
      toolbar.insertBefore(bar, toolbar.firstChild);

      var txt = bar.querySelector('.mob-ft-text');
      var periodText = document.getElementById('periodText');

      function syncSummary() {
        var t = periodText ? periodText.textContent.replace(/^Viewing\s+/i, '') : '';
        txt.textContent = t || 'Filters';
      }
      syncSummary();
      // app.js rewrites #periodText on every filter change — mirror it
      if (periodText && window.MutationObserver) {
        new MutationObserver(syncSummary)
          .observe(periodText, { childList: true, characterData: true, subtree: true });
      }

      bar.addEventListener('click', function () {
        var open = document.body.classList.toggle('mob-filters-open');
        bar.setAttribute('aria-expanded', open ? 'true' : 'false');
      });

      // picking a filter is usually the end of the visit to the panel —
      // fold it away so the data gets the screen back (phones only)
      toolbar.addEventListener('change', function (e) {
        if (e.target && e.target.tagName === 'SELECT' &&
            window.matchMedia('(max-width: 820px)').matches) {
          setTimeout(function () {
            document.body.classList.remove('mob-filters-open');
            bar.setAttribute('aria-expanded', 'false');
          }, 350);
        }
      });
    }

    /* ---------------- swipeable dock hints ---------------- */
    var dock = document.querySelector('.bottom-dock');
    var wrap = document.querySelector('.bottom-dock-wrapper');
    if (dock && wrap) {
      function edges() {
        var max = dock.scrollWidth - dock.clientWidth;
        wrap.classList.toggle('mob-can-l', max > 4 && dock.scrollLeft > 4);
        wrap.classList.toggle('mob-can-r', max > 4 && dock.scrollLeft < max - 4);
      }
      dock.addEventListener('scroll', edges, { passive: true });
      window.addEventListener('resize', edges, { passive: true });
      edges();

      // keep the active page's button in view (also on load)
      function revealActive() {
        var btn = dock.querySelector('button.active');
        if (!btn || dock.scrollWidth <= dock.clientWidth + 4) return;
        var target = btn.offsetLeft - (dock.clientWidth - btn.offsetWidth) / 2;
        if (dock.scrollTo) dock.scrollTo({ left: target, behavior: 'smooth' });
        else dock.scrollLeft = target;
      }
      dock.addEventListener('click', function (e) {
        if (e.target && e.target.tagName === 'BUTTON') {
          // app.js flips .active in this same click — let it land first
          setTimeout(revealActive, 60);
        }
      });
      setTimeout(revealActive, 300);
      setTimeout(edges, 600);   // fonts settling can change scrollWidth
    }
  });
})();
