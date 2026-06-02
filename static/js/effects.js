/* ── EFFECTS ──────────────────────────────────── */
/* Lightweight CSS-driven effects for the Control Panel */

(function() {
  'use strict';

  /* IntersectionObserver to trigger counter animation when stats visible */
  function initStatsObserver() {
    var statsSection = document.querySelector('.stats-section');
    if (!statsSection) return;

    var hasAnimated = false;

    var observer = new IntersectionObserver(function(entries) {
      entries.forEach(function(entry) {
        if (entry.isIntersecting && !hasAnimated) {
          hasAnimated = true;
          statsSection.classList.add('stats-visible');
        }
      });
    }, { threshold: 0.3 });

    observer.observe(statsSection);
  }

  /* Record load time so we can calculate counter elapsed */
  window.__effectsLoadTime = Date.now();

  /* Initialize on DOM ready */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      initStatsObserver();
    });
  } else {
    initStatsObserver();
  }
})();

/* ── INTERACTIVE ORBS ─────────────────────────── */
(function() {
  'use strict';

  // Respect reduced-motion preference
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  var MAX_ORBS = 8;
  var orbContainer = document.getElementById('orbContainer');
  if (!orbContainer) return;

  var activeOrbs = [];
  var lastTouchMove = 0;

  function createOrb(x, y, isSmall) {
    var orb = document.createElement('div');
    orb.className = 'touch-orb' + (isSmall ? ' orb-small' : '');
    var size = isSmall ? 40 : 80;
    orb.style.left = (x - size / 2) + 'px';
    orb.style.top = (y - size / 2) + 'px';
    orbContainer.appendChild(orb);
    activeOrbs.push(orb);

    if (activeOrbs.length > MAX_ORBS) {
      var oldest = activeOrbs.shift();
      if (oldest.parentNode) {
        oldest.parentNode.removeChild(oldest);
      }
    }

    var duration = 600 + Math.floor(Math.random() * 300);
    setTimeout(function() {
      if (orb.parentNode) {
        orb.parentNode.removeChild(orb);
      }
      var idx = activeOrbs.indexOf(orb);
      if (idx > -1) {
        activeOrbs.splice(idx, 1);
      }
    }, duration);
  }

  document.addEventListener('click', function(e) {
    if (e.target.closest('button, a, .modal, .desktop-sidebar, .mobile-drawer, .drawer-backdrop, .dl-btn, .q-btn, .clear-btn, input')) return;
    createOrb(e.clientX, e.clientY, false);
  });

  document.addEventListener('touchstart', function(e) {
    if (e.target.closest('button, a, .modal, .desktop-sidebar, .mobile-drawer, .drawer-backdrop, .dl-btn, .q-btn, .clear-btn, input')) return;
    if (e.touches && e.touches.length > 0) {
      createOrb(e.touches[0].clientX, e.touches[0].clientY, false);
    }
  }, { passive: true });

  document.addEventListener('touchmove', function(e) {
    var now = Date.now();
    if (now - lastTouchMove < 80) return;
    lastTouchMove = now;
    if (e.target.closest('button, a, .modal, .desktop-sidebar, .mobile-drawer, .drawer-backdrop, .dl-btn, .q-btn, .clear-btn, input')) return;
    if (e.touches && e.touches.length > 0) {
      createOrb(e.touches[0].clientX, e.touches[0].clientY, true);
    }
  }, { passive: true });
})();

/* ── ANIME SILHOUETTE AWAKE INTERACTION ───────── */
(function() {
  'use strict';

  var silhouette = document.querySelector('.anime-body-silhouette');
  if (!silhouette) return;

  var awakeTimer = null;

  function awakeSilhouette() {
    if (awakeTimer) {
      clearTimeout(awakeTimer);
    }
    silhouette.classList.add('is-awake');
    awakeTimer = setTimeout(function() {
      silhouette.classList.remove('is-awake');
      awakeTimer = null;
    }, 700);
  }

  document.addEventListener('click', function(e) {
    if (e.target.closest('button, a, input, .modal, .desktop-sidebar, .mobile-drawer, .drawer-backdrop')) return;
    awakeSilhouette();
  });

  document.addEventListener('touchstart', function(e) {
    if (e.target.closest('button, a, input, .modal, .desktop-sidebar, .mobile-drawer, .drawer-backdrop')) return;
    awakeSilhouette();
  }, { passive: true });
})();
