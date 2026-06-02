/* ── UI HELPERS ────────────────────────────────── */

function setStatus(msg, type) {
  var el = document.getElementById('status');
  if (!el) return;
  el.textContent = msg;
  el.className = 'status' + (type ? ' ' + type : '');
}

function hidePreview() {
  previewData = null;
  var card = document.getElementById('previewCard');
  if (card) card.classList.remove('show');
}


function closeAllDrawers() {
  document.body.classList.remove("menu-open", "drawer-open", "sidebar-open");
  document.querySelectorAll(".sidebar, .mobile-menu, .dashboard-drawer, .drawer, .nav-drawer")
    .forEach(el => el.classList.remove("open", "active", "show"));
  document.querySelectorAll(".drawer-backdrop, .menu-backdrop, .overlay")
    .forEach(el => el.remove());

  document.querySelectorAll(".drawer-overlay, .menu-overlay")
    .forEach(el => {
      el.classList.remove("active", "open", "show");
      el.setAttribute("aria-hidden", "true");
    });

  var sideDrawer = document.getElementById("sideDrawer");
  if (sideDrawer) sideDrawer.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
}

window.closeAllDrawers = closeAllDrawers;

function setAppMode(mode) {
  var isMakima = mode === "makima";
  document.body.classList.toggle("makima-mode", isMakima);
  document.body.classList.toggle("dashboard-mode", !isMakima);
  if (!isMakima) document.body.classList.remove("makima-ai-body");
}

window.setAppMode = setAppMode;

/* ── SIDE DRAWER ──────────────────────────────── */
(function() {
  console.log('[MAKIMA] app init');
  console.log('[MAKIMA] page:', location.pathname);
  try {
    window.localStorage.setItem('__makima_storage_probe', '1');
    window.localStorage.removeItem('__makima_storage_probe');
    console.log('[MAKIMA] localStorage ready');
  } catch (e) {
    console.warn('[MAKIMA] localStorage unavailable:', e);
  }

  closeAllDrawers();
  setAppMode(currentView === 'makima-ai' ? 'makima' : 'dashboard');

  var btn = document.getElementById('hamburgerBtn');
  var drawer = document.getElementById('sideDrawer');
  var overlay = document.getElementById('drawerOverlay');
  var closeBtn = document.getElementById('drawerClose');

  if (!btn || !drawer || !overlay) return;

  function openDrawer() {
    if (document.body.classList.contains('makima-mode')) return;
    closeAllDrawers();
    document.body.classList.add('drawer-open');
    drawer.classList.add('active');
    overlay.classList.add('active');
    drawer.setAttribute('aria-hidden', 'false');
    overlay.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  function closeDrawer() {
    closeAllDrawers();
  }

  // Expose closeDrawer for use by navigation logic
  window._closeDrawer = closeDrawer;

  btn.addEventListener('click', function(e) {
    e.stopPropagation();
    openDrawer();
  });

  overlay.addEventListener('click', function() {
    closeDrawer();
  });

  if (closeBtn) {
    closeBtn.addEventListener('click', function() {
      closeAllDrawers();
    });
  }

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && drawer.classList.contains('active')) {
      closeDrawer();
    }
  });

  // Update downloads counter in drawer if statDownloads exists
  var statDl = document.getElementById('statDownloads');
  var drawerDl = document.getElementById('drawerDownloads');
  if (statDl && drawerDl) {
    var observer = new MutationObserver(function() {
      drawerDl.textContent = 'DOWNLOADS: ' + (statDl.textContent || '0');
    });
    observer.observe(statDl, { childList: true, characterData: true, subtree: true });
  }
})();

/* -- VIEW NAVIGATION SYSTEM -- */
(function() {
  'use strict';

  // View configuration
  var viewConfig = {
    'downloader': { type: 'main' },
    'makima-ai': { type: 'makima-ai' },
    'hinter-mt': { type: 'coming-soon', title: 'HINTER MT', badge: 'SOON', description: 'HINTER MT belum tersedia.' },
    'wa-status': { type: 'coming-soon', title: 'WA STATUS CONVERTER', badge: 'COMING SOON', description: 'Convert video to WhatsApp Status ready format.' },
    'status-splitter': { type: 'coming-soon', title: 'STATUS SPLITTER', badge: 'COMING SOON', description: 'Split long videos into WhatsApp Status parts.' },
    'caption': { type: 'coming-soon', title: 'CAPTION COPIER', badge: 'COMING SOON', description: 'Caption copy tool is under development.' },
    'store': { type: 'store' },
    'control': { type: 'control' },
    'server': { type: 'coming-soon', title: 'SERVER STATUS', badge: 'COMING SOON', description: 'SERVER MONITORING DASHBOARD IS UNDER DEVELOPMENT.' },
    'howto': { type: 'coming-soon', title: 'HOW TO USE', badge: 'COMING SOON', description: 'USAGE GUIDE IS UNDER DEVELOPMENT.' },
    'report': { type: 'coming-soon', title: 'REPORT BUG', badge: 'COMING SOON', description: 'BUG REPORTING SYSTEM IS UNDER DEVELOPMENT.' }
  };

  function navigateTo(view, skipPush) {
    if (!viewConfig[view]) return;
    closeAllDrawers();
    var previousView = currentView;
    currentView = view;

    // Hide all views
    var viewDownloader = document.getElementById('viewDownloader');
    var viewComingSoon = document.getElementById('viewComingSoon');
    var viewStore = document.getElementById('viewStore');
    var viewControl = document.getElementById('viewControl');
    var viewMakimaAI = document.getElementById('viewMakimaAI');
    var headerEl = document.querySelector('.page > .header');

    if (viewDownloader) viewDownloader.style.display = 'none';
    if (viewComingSoon) viewComingSoon.style.display = 'none';
    if (viewStore) viewStore.style.display = 'none';
    if (viewControl) viewControl.style.display = 'none';
    if (viewMakimaAI) viewMakimaAI.style.display = 'none';

    // Disconnect control panel observer when leaving control view
    if (previousView === 'control' && view !== 'control') {
      disconnectControlObservers();
    }

    // Remove makima-ai-body class when navigating away from makima-ai
    if (previousView === 'makima-ai') {
      document.body.classList.remove('makima-ai-body');
    }

    var config = viewConfig[view];
    setAppMode(config.type === 'makima-ai' ? 'makima' : 'dashboard');

    if (config.type === 'main') {
      if (viewDownloader) viewDownloader.style.display = '';
      if (headerEl) headerEl.style.display = '';
    } else if (config.type === 'coming-soon') {
      renderComingSoon(config.title, config.badge, config.description);
      if (viewComingSoon) viewComingSoon.style.display = '';
      if (headerEl) headerEl.style.display = '';
    } else if (config.type === 'store') {
      renderStore();
      if (viewStore) viewStore.style.display = '';
      if (headerEl) headerEl.style.display = '';
    } else if (config.type === 'control') {
      renderControl();
      if (viewControl) viewControl.style.display = '';
      if (headerEl) headerEl.style.display = '';
    } else if (config.type === 'makima-ai') {
      if (viewMakimaAI) viewMakimaAI.style.display = '';
      if (headerEl) headerEl.style.display = 'none';
      document.body.classList.add('makima-ai-body');
      renderMakimaAI();
    }

    // Push history state (stay on same URL, no /ai route)
    if (!skipPush) {
      history.pushState({ view: view }, '', '/');
    }

    // Update active state in drawer
    updateDrawerActive(view);

    // Close drawer
    closeAllDrawers();

    // Scroll to top
    window.scrollTo(0, 0);
  }

  function renderComingSoon(title, badge, description) {
    var container = document.getElementById('viewComingSoon');
    if (!container) return;
    container.innerHTML = '<div class="coming-soon-card">' +
      '<div class="coming-soon-scanline"></div>' +
      '<div class="coming-soon-corner tl"></div>' +
      '<div class="coming-soon-corner tr"></div>' +
      '<div class="coming-soon-corner bl"></div>' +
      '<div class="coming-soon-corner br"></div>' +
      '<h2 class="coming-soon-title"></h2>' +
      '<span class="coming-soon-badge"></span>' +
      '<p class="coming-soon-subtitle"></p>' +
      '<button class="coming-soon-btn" onclick="showMainView()">BACK TO DOWNLOADER</button>' +
      '</div>';
    // Use textContent to avoid XSS from any future dynamic values
    var titleEl = container.querySelector('.coming-soon-title');
    var badgeEl = container.querySelector('.coming-soon-badge');
    var subtitleEl = container.querySelector('.coming-soon-subtitle');
    if (titleEl) titleEl.textContent = title;
    if (badgeEl) badgeEl.textContent = badge;
    if (subtitleEl) subtitleEl.textContent = description;
  }

  function renderStore() {
    var container = document.getElementById('viewStore');
    if (!container) return;
    container.innerHTML = '<div class="store-page">' +
      '<div class="store-header">' +
        '<h2 class="store-title">PREMIUM APPS STORE</h2>' +
        '<p class="store-subtitle">MII NETWORK DIGITAL PRODUCTS</p>' +
      '</div>' +
      '<div class="store-grid">' +
        '<a href="https://www.instagram.com/miistore.99?igsh=ZmFqanZuOXo4cG92" target="_blank" rel="noopener noreferrer" class="store-card">' +
          '<div class="store-card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="28" height="28"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"/><circle cx="12" cy="12" r="4.5"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none"/></svg></div>' +
          '<div class="store-card-title">INSTAGRAM</div>' +
          '<div class="store-card-desc">FOLLOW FOR UPDATES</div>' +
        '</a>' +
        '<a href="https://t.me/asami_am0" target="_blank" rel="noopener noreferrer" class="store-card">' +
          '<div class="store-card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="28" height="28"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg></div>' +
          '<div class="store-card-title">TELEGRAM</div>' +
          '<div class="store-card-desc">JOIN OUR CHANNEL</div>' +
        '</a>' +
        '<a href="https://wa.me/6282191223912" target="_blank" rel="noopener noreferrer" class="store-card">' +
          '<div class="store-card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="28" height="28"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg></div>' +
          '<div class="store-card-title">WHATSAPP</div>' +
          '<div class="store-card-desc">CHAT WITH US</div>' +
        '</a>' +
        '<a href="https://lynk.id/miistore99" target="_blank" rel="noopener noreferrer" class="store-card">' +
          '<div class="store-card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="28" height="28"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg></div>' +
          '<div class="store-card-title">LYNK.ID STORE</div>' +
          '<div class="store-card-desc">BROWSE ALL PRODUCTS</div>' +
        '</a>' +
      '</div>' +
      '<button class="coming-soon-btn" onclick="showMainView()" style="margin-top:24px;">BACK TO DOWNLOADER</button>' +
    '</div>';
  }

  // Track control panel MutationObservers for cleanup
  var controlObservers = [];

  function disconnectControlObservers() {
    controlObservers.forEach(function(obs) { obs.disconnect(); });
    controlObservers = [];
  }

  function renderControl() {
    var container = document.getElementById('viewControl');
    if (!container) return;
    container.innerHTML = '<div class="control-page">' +
      '<div class="control-header">' +
        '<h2 class="control-title">CONTROL PANEL</h2>' +
        '<p class="control-subtitle">MII NETWORK SYSTEM</p>' +
      '</div>' +
      '<div class="control-grid">' +
        '<div class="control-status-card"><span class="control-dot green"></span><span>SERVER ONLINE</span></div>' +
        '<div class="control-status-card"><span class="control-dot green"></span><span>VIDEO READY</span></div>' +
        '<div class="control-status-card"><span class="control-dot yellow"></span><span>STATUS TOOLS SOON</span></div>' +
        '<div class="control-status-card"><span class="control-dot green"></span><span>DOWNLOADS ACTIVE</span></div>' +
      '</div>' +
      '<div class="control-stats">' +
        '<div class="control-stat-box"><div class="control-stat-value" id="ctrlViews">0</div><div class="control-stat-label">VIEWS</div></div>' +
        '<div class="control-stat-box"><div class="control-stat-value" id="ctrlDownloads">0</div><div class="control-stat-label">DOWNLOADS</div></div>' +
        '<div class="control-stat-box"><div class="control-stat-value" id="ctrlVisitors">0</div><div class="control-stat-label">VISITORS</div></div>' +
      '</div>' +
      '<button class="coming-soon-btn" onclick="showMainView()" style="margin-top:24px;">BACK TO DOWNLOADER</button>' +
    '</div>';

    // Copy stats from main page if available
    var sv = document.getElementById('statViews');
    var sd = document.getElementById('statDownloads');
    var svi = document.getElementById('statVisitors');
    var cv = document.getElementById('ctrlViews');
    var cd = document.getElementById('ctrlDownloads');
    var cvi = document.getElementById('ctrlVisitors');
    if (sv && cv) cv.textContent = sv.textContent;
    if (sd && cd) cd.textContent = sd.textContent;
    if (svi && cvi) cvi.textContent = svi.textContent;

    // Observe source stats for live updates while control view is open
    disconnectControlObservers();
    var observerOpts = { childList: true, characterData: true, subtree: true };

    if (sv && cv) {
      var obsViews = new MutationObserver(function() { cv.textContent = sv.textContent; });
      obsViews.observe(sv, observerOpts);
      controlObservers.push(obsViews);
    }
    if (sd && cd) {
      var obsDownloads = new MutationObserver(function() { cd.textContent = sd.textContent; });
      obsDownloads.observe(sd, observerOpts);
      controlObservers.push(obsDownloads);
    }
    if (svi && cvi) {
      var obsVisitors = new MutationObserver(function() { cvi.textContent = svi.textContent; });
      obsVisitors.observe(svi, observerOpts);
      controlObservers.push(obsVisitors);
    }
  }

  function updateDrawerActive(view) {
    var items = document.querySelectorAll('.side-drawer .drawer-item[data-view]');
    items.forEach(function(item) {
      if (item.getAttribute('data-view') === view) {
        item.classList.add('active');
      } else {
        item.classList.remove('active');
      }
    });
  }

  function showMainView() {
    closeAllDrawers();
    navigateTo('downloader');
  }

  // Expose globally
  window.showMainView = showMainView;
  window.navigateTo = navigateTo;

  // Handle browser back/forward button
  window.addEventListener('popstate', function(e) {
    if (e.state && e.state.view && viewConfig[e.state.view]) {
      navigateTo(e.state.view, true);
    } else {
      navigateTo('downloader', true);
    }
  });

  // Feature mapping for Coming Soon items
  var featureMap = {
    'wa-status': { title: 'WA STATUS CONVERTER', description: 'Convert video to WhatsApp Status ready format.' },
    'status-splitter': { title: 'STATUS SPLITTER', description: 'Split long videos into WhatsApp Status parts.' },
    'caption-copier': { title: 'CAPTION COPIER', description: 'Caption copy tool is under development.' },
    'hinter-mt': { title: 'HINTER MT', description: 'HINTER MT belum tersedia.' }
  };

  // Wire up drawer items using event delegation on the drawer (robust on mobile)
  var sideDrawer = document.getElementById('sideDrawer');
  document.addEventListener('DOMContentLoaded', function() {
    closeAllDrawers();
    setAppMode(currentView === 'makima-ai' ? 'makima' : 'dashboard');
  });

  if (sideDrawer) {
    sideDrawer.addEventListener('click', function(e) {
      var item = e.target.closest('.drawer-item[data-view]');
      if (!item) return;

      var feature = item.getAttribute('data-feature');
      var view = item.getAttribute('data-view');

      // If item has data-feature, use featureMap for Coming Soon
      if (feature && featureMap[feature]) {
        e.preventDefault();
        closeAllDrawers();

        var viewDownloader = document.getElementById('viewDownloader');
        var viewComingSoon = document.getElementById('viewComingSoon');
        var viewStore = document.getElementById('viewStore');
        var viewControl = document.getElementById('viewControl');
        var viewMakimaAI = document.getElementById('viewMakimaAI');

        if (viewDownloader) viewDownloader.style.display = 'none';
        if (viewComingSoon) viewComingSoon.style.display = 'none';
        if (viewStore) viewStore.style.display = 'none';
        if (viewControl) viewControl.style.display = 'none';
        if (viewMakimaAI) viewMakimaAI.style.display = 'none';
        setAppMode('dashboard');
        document.body.classList.remove('makima-ai-body');

        // Show header again when leaving AI view
        var headerEl = document.querySelector('.page > .header');
        if (headerEl) headerEl.style.display = '';

        var fm = featureMap[feature];
        renderComingSoon(fm.title, 'COMING SOON', fm.description);
        if (viewComingSoon) viewComingSoon.style.display = '';

        currentView = view;
        updateDrawerActive(view);
        history.pushState({ view: view }, '', '');
        window.scrollTo(0, 0);
        return;
      }

      // Default: use navigateTo for non-feature items
      if (view) {
        e.preventDefault();
        navigateTo(view);
      }
    });
  }

})();
