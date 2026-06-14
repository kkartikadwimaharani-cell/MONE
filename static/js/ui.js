function uiText(key, vars) {
  return (window.t && window.t(key, vars)) || key;
}

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

function setAppMode(mode) {
  var isMakima = mode === 'makima';
  document.body.classList.toggle('makima-mode', isMakima);
  document.body.classList.toggle('dashboard-mode', !isMakima);
  if (!isMakima) document.body.classList.remove('makima-ai-body');
}

window.setAppMode = setAppMode;

/* ── APP DRAWER ───────────────────────────────── */
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

  var hamburger = document.querySelector('.hamburger-btn');
  var drawer = document.querySelector('.app-drawer');

  setAppMode('dashboard');

  if (!hamburger || !drawer) return;

  function removeBackdrops() {
    document.querySelectorAll('.drawer-backdrop').forEach(function(el) {
      el.remove();
    });
  }

  function openDrawer() {
    if (!drawer) return;
    drawer.classList.add('open');
    drawer.classList.remove('active', 'show');
    drawer.setAttribute('aria-hidden', 'false');
    hamburger.setAttribute('aria-expanded', 'true');
    document.body.classList.add('drawer-open');
    document.body.classList.remove('menu-open', 'sidebar-open', 'desktop-menu-open');
    document.body.style.overflow = 'hidden';

    if (!document.querySelector('.drawer-backdrop')) {
      var backdrop = document.createElement('div');
      backdrop.className = 'drawer-backdrop';
      backdrop.setAttribute('aria-hidden', 'true');
      backdrop.addEventListener('click', closeDrawer);
      document.body.appendChild(backdrop);
    }
  }

  function closeDrawer() {
    if (drawer) {
      drawer.classList.remove('open', 'active', 'show');
      drawer.setAttribute('aria-hidden', 'true');
    }
    removeBackdrops();
    hamburger.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('drawer-open', 'menu-open', 'sidebar-open', 'desktop-menu-open');
    document.body.style.overflow = '';
  }

  window._openDrawer = openDrawer;
  window._closeDrawer = closeDrawer;

  hamburger.addEventListener('click', function(e) {
    e.preventDefault();
    e.stopPropagation();
    if (drawer && drawer.classList.contains('open')) closeDrawer();
    else openDrawer();
  });

  document.querySelectorAll('.drawer-close').forEach(function(btn) {
    btn.addEventListener('click', closeDrawer);
  });

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && drawer.classList.contains('open')) {
      closeDrawer();
    }
  });

  // Update downloads counter in drawer if statDownloads exists
  var statDl = document.getElementById('statDownloads');
  var drawerDl = document.getElementById('drawerDownloads');
  if (statDl && drawerDl) {
    var observer = new MutationObserver(function() {
      var count = statDl.textContent || '0';
      drawerDl.setAttribute('data-download-count', count);
      drawerDl.textContent = uiText('drawer_downloads', { count: count });
    });
    observer.observe(statDl, { childList: true, characterData: true, subtree: true });
  }
})();

/* -- VIEW NAVIGATION SYSTEM -- */
(function() {
  'use strict';

  // Private Vault gate and scoped audio state
  var vaultSessionKey = 'mii_private_vault_human_confirmed';
  var vaultAudio = null;

  function isPrivateVaultVerified() {
    try {
      return window.sessionStorage.getItem(vaultSessionKey) === 'true';
    } catch (e) {
      return false;
    }
  }

  function setPrivateVaultVerified() {
    try {
      window.sessionStorage.setItem(vaultSessionKey, 'true');
    } catch (e) {
      // Session storage can be unavailable in strict privacy modes; keep the gate locked for safety.
    }
  }

  function getVaultAudio() {
    if (!vaultAudio) {
      vaultAudio = new Audio('/static/audio/vault-theme.mp3');
      vaultAudio.volume = 0.25;
      vaultAudio.loop = true;
      vaultAudio.preload = 'none';
    }
    vaultAudio.volume = 0.25;
    vaultAudio.loop = true;
    return vaultAudio;
  }

  function startVaultMusic() {
    var audio = getVaultAudio();
    if (!audio.paused) return;
    var playAttempt = audio.play();
    if (playAttempt && typeof playAttempt.catch === 'function') {
      playAttempt.catch(function() {
        // Browser autoplay policy may block resume without a fresh gesture; verification click still unlocks normally.
      });
    }
  }

  function pauseVaultMusic() {
    if (!vaultAudio) return;
    vaultAudio.pause();
  }

  // View configuration
  var viewConfig = {
    'downloader': { type: 'main' },
    'makima-ai': { type: 'makima-ai' },
    'hinter-mt': { type: 'private-vault', titleKey: 'private_vault', badgeKey: 'active', descriptionKey: 'classified_showcase' },
    'wa-status': { type: 'coming-soon', titleKey: 'wa_status_converter', badgeKey: 'coming_soon', descriptionKey: 'wa_status_desc' },
    'status-splitter': { type: 'coming-soon', titleKey: 'status_splitter', badgeKey: 'coming_soon', descriptionKey: 'status_splitter_desc' },
    'caption': { type: 'coming-soon', titleKey: 'caption_copier', badgeKey: 'coming_soon', descriptionKey: 'caption_desc' },
    'store': { type: 'store' },
    'control': { type: 'control' },
    'server': { type: 'coming-soon', titleKey: 'server_status', badgeKey: 'coming_soon', descriptionKey: 'server_desc' },
    'howto': { type: 'coming-soon', titleKey: 'how_to_use', badgeKey: 'coming_soon', descriptionKey: 'howto_desc' },
    'report': { type: 'coming-soon', titleKey: 'report_bug', badgeKey: 'coming_soon', descriptionKey: 'report_desc' }
  };

  function navigateTo(view, skipPush) {
    if (!viewConfig[view]) return;
    var previousView = currentView;
    currentView = view;

    // Hide all views
    var viewDownloader = document.getElementById('viewDownloader');
    var viewComingSoon = document.getElementById('viewComingSoon');
    var viewPrivateVault = document.getElementById('viewPrivateVault');
    var viewStore = document.getElementById('viewStore');
    var viewControl = document.getElementById('viewControl');
    var viewMakimaAI = document.getElementById('viewMakimaAI');
    var headerEl = document.querySelector('.page > .header');

    if (viewDownloader) viewDownloader.style.display = 'none';
    if (viewComingSoon) viewComingSoon.style.display = 'none';
    if (viewPrivateVault) viewPrivateVault.style.display = 'none';
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

    if (previousView === 'hinter-mt' && view !== 'hinter-mt') {
      pauseVaultMusic();
    }

    var config = viewConfig[view];

    if (config.type === 'main') {
      setAppMode('dashboard');
      if (viewDownloader) viewDownloader.style.display = '';
      if (headerEl) headerEl.style.display = '';
    } else if (config.type === 'coming-soon') {
      setAppMode('dashboard');
      renderComingSoon(uiText(config.titleKey) || config.title, uiText(config.badgeKey) || config.badge, uiText(config.descriptionKey) || config.description);
      if (viewComingSoon) viewComingSoon.style.display = '';
      if (headerEl) headerEl.style.display = '';
    } else if (config.type === 'private-vault') {
      setAppMode('dashboard');
      renderPrivateVault();
      if (viewPrivateVault) viewPrivateVault.style.display = '';
      if (headerEl) headerEl.style.display = '';
    } else if (config.type === 'store') {
      setAppMode('dashboard');
      renderStore();
      if (viewStore) viewStore.style.display = '';
      if (headerEl) headerEl.style.display = '';
    } else if (config.type === 'control') {
      setAppMode('dashboard');
      renderControl();
      if (viewControl) viewControl.style.display = '';
      if (headerEl) headerEl.style.display = '';
    } else if (config.type === 'makima-ai') {
      setAppMode('makima');
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
    if (window._closeDrawer) window._closeDrawer();

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
      '<button class="coming-soon-btn" onclick="showMainView()" data-i18n="back_to_downloader">' + uiText('back_to_downloader') + '</button>' +
      '</div>';
    // Use textContent to avoid XSS from any future dynamic values
    var titleEl = container.querySelector('.coming-soon-title');
    var badgeEl = container.querySelector('.coming-soon-badge');
    var subtitleEl = container.querySelector('.coming-soon-subtitle');
    if (titleEl) titleEl.textContent = title;
    if (badgeEl) badgeEl.textContent = badge;
    if (subtitleEl) subtitleEl.textContent = description;
    if (window.refreshLanguage) window.refreshLanguage();
  }


  function renderPrivateVaultGate() {
    var container = document.getElementById('viewPrivateVault');
    if (!container) return;
    pauseVaultMusic();
    container.innerHTML = '<section class="vault-human-gate" aria-label="Private Vault human verification">' +
      '<div class="vault-gate-grid"></div>' +
      '<div class="vault-gate-noise"></div>' +
      '<form class="vault-gate-card" id="vaultGateForm" autocomplete="off">' +
        '<span class="vault-gate-scanline"></span>' +
        '<div class="vault-gate-kicker">' + uiText('premium_access_terminal') + '</div>' +
        '<h2 class="vault-gate-title">' + uiText('are_you_human') + '</h2>' +
        '<p class="vault-gate-subtitle">' + uiText('type_confirm') + '</p>' +
        '<label class="vault-gate-label" for="vaultConfirmInput">' + uiText('verification_token') + '</label>' +
        '<div class="vault-gate-input-wrap">' +
          '<input id="vaultConfirmInput" class="vault-gate-input" type="text" inputmode="latin" autocapitalize="characters" spellcheck="false" aria-describedby="vaultGateMessage" data-i18n-placeholder="type_confirm_placeholder" placeholder="' + uiText('type_confirm_placeholder') + '">' +
          '<span class="vault-gate-cursor" aria-hidden="true"></span>' +
        '</div>' +
        '<button type="submit" class="vault-gate-button">' + uiText('confirm_access') + '</button>' +
        '<div id="vaultGateMessage" class="vault-gate-message" role="status" aria-live="polite"></div>' +
      '</form>' +
    '</section>';

    var input = container.querySelector('#vaultConfirmInput');
    if (window.refreshLanguage) window.refreshLanguage();
    if (input) input.focus({ preventScroll: true });
  }

  function revealPrivateVaultFromGate() {
    var container = document.getElementById('viewPrivateVault');
    if (!container) return;
    setPrivateVaultVerified();
    startVaultMusic();
    container.innerHTML = '<section class="vault-init-screen" aria-label="Private Vault initialization">' +
      '<div class="vault-gate-grid"></div>' +
      '<div class="vault-init-lines">' +
        '<span>' + uiText('human_signal_confirmed') + '</span>' +
        '<span>' + uiText('private_vault_initialized') + '</span>' +
      '</div>' +
    '</section>';
    window.setTimeout(function() {
      renderPrivateVaultContent();
    }, 980);
  }

  function renderPrivateVault() {
    if (isPrivateVaultVerified()) {
      renderPrivateVaultContent();
      startVaultMusic();
      return;
    }
    renderPrivateVaultGate();
  }

  function renderPrivateVaultContent() {
    var container = document.getElementById('viewPrivateVault');
    if (!container) return;

    var tools = [
      { name: 'Auto Hitter Lab', description: 'Automation risk preview.', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 13a8 8 0 0 1 16 0"/><path d="M12 13l4-5"/><path d="M6.5 18h11"/></svg>' },
      { name: 'CC Research', description: 'Payment security awareness.', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M3 10h18"/><path d="M7 15h4"/></svg>' },
      { name: 'BIN Vault', description: 'Issuer data education.', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M8 7h8"/><path d="M8 12h8"/><path d="M8 17h5"/></svg>' },
      { name: 'Password Audit', description: 'Password strength awareness.', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/><path d="M12 14v2"/></svg>' },
      { name: 'License Vault', description: 'Premium access notes.', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M15 7a4 4 0 1 1-3-3.87"/><path d="M14 14l7 7"/><path d="M19 19l-2 2"/><path d="M17 17l-2 2"/></svg>' },
      { name: 'Carding Notes', description: 'Anti-fraud awareness.', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4h10l4 4v12H5z"/><path d="M15 4v4h4"/><path d="M8 13h8"/><path d="M8 17h6"/></svg>' },
      { name: 'Mobile Toolkit', description: 'Mobile privacy utilities.', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/><path d="M10 6h4"/></svg>' },
      { name: 'VIP Methods', description: 'Private workflow notes.', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l2.7 5.47 6.03.88-4.36 4.25 1.03 6-5.4-2.84-5.4 2.84 1.03-6-4.36-4.25 6.03-.88z"/></svg>' }
    ];

    var cards = tools.map(function(tool) {
      return '<article class="vault-tool-card" aria-label="Locked preview: ' + tool.name + '">' +
        '<div class="vault-tool-top">' +
          '<span class="vault-tool-icon" aria-hidden="true">' + tool.icon + '</span>' +
          '<span class="vault-lock-mark">' + uiText('locked') + '</span>' +
        '</div>' +
        '<h4 class="vault-tool-name">' + tool.name + '</h4>' +
        '<p class="vault-tool-desc">' + tool.description + '</p>' +
        '<button type="button" class="vault-action-btn">' + uiText('request_access_contact_admin') + '</button>' +
      '</article>';
    }).join('');

    container.innerHTML = '<section class="private-vault-page" aria-label="Private Vault">' +
      '<div class="vault-bg-grid"></div>' +
      '<div class="vault-bg-noise"></div>' +
      '<header class="vault-hero">' +
        '<span class="vault-kicker">' + uiText('locked_showcase') + '</span>' +
        '<h2 class="vault-title">PRIVATE VAULT</h2>' +
        '<p class="vault-subtitle">' + uiText('classified_showcase') + '</p>' +
      '</header>' +
      '<div class="vault-main-layout">' +
        '<button type="button" class="vault-admin-card vault-flip-card" aria-label="Flip admin profile card">' +
          '<span class="vault-flip-inner">' +
            '<span class="vault-face vault-admin-front">' +
              '<span class="vault-code-crawler" aria-hidden="true"><span>LV.99999 // RESTRICTED // CONTROL MODE // OWNER ACCESS // PRIVATE VAULT // UNKNOWN ENTITY // </span></span>' +
              '<span class="vault-scanline"></span>' +
              '<span class="vault-card-badge vault-card-badge-left">LV.99999</span>' +
              '<span class="vault-card-badge vault-card-badge-right">ONLINE</span>' +
              '<span class="vault-admin-photo-wrap"><span class="vault-avatar-scan"></span><img class="vault-admin-photo" src="/static/img/Admin.png" alt="NO NAME admin profile" draggable="false" oncontextmenu="return false" ondragstart="return false"></span>' +
              '<span class="vault-admin-name">NO NAME</span>' +
              '<span class="vault-admin-title">UNKNOWN ENTITY</span>' +
              '<span class="vault-admin-meta"><span>CLEARANCE: UNKNOWN</span><span>POLICY: RESTRICTED</span><span>PROTOCOL: CONTROL MODE</span></span>' +
              '<span class="vault-tap-hint">' + uiText('tap_to_reveal') + '</span>' +
            '</span>' +
            '<span class="vault-face vault-admin-back">' +
              '<span class="vault-code-crawler" aria-hidden="true"><span>IDENTITY TRACE // OWNER ACCESS // VAULT POLICY // CONTROL MODE // </span></span>' +
              '<span class="vault-scanline vault-scanline-once"></span>' +
              '<span class="vault-reveal vault-reveal-1">IDENTITY UNSEALED</span>' +
              '<span class="vault-reveal vault-reveal-2">NO NAME</span>' +
              '<span class="vault-reveal vault-reveal-final vault-reveal-3">UNKNOWN ENTITY</span>' +
              '<span class="vault-reveal vault-reveal-4">LV.99999</span>' +
              '<span class="vault-reveal vault-reveal-5">OWNER ACCESS</span>' +
              '<span class="vault-reveal vault-reveal-6">PRIVATE VAULT</span>' +
              '<span class="vault-reveal vault-reveal-7">POLICY: RESTRICTED</span>' +
              '<span class="vault-reveal vault-reveal-8">PROTOCOL: CONTROL MODE</span>' +
            '</span>' +
          '</span>' +
        '</button>' +
        '<aside class="vault-access-panel">' +
          '<div class="vault-panel-label">' + uiText('access_panel') + '</div>' +
          '<div class="vault-panel-row"><span>' + uiText('vault_state') + '</span><strong>' + uiText('locked_showcase') + '</strong></div>' +
          '<div class="vault-panel-row"><span>' + uiText('policy') + '</span><strong>' + uiText('restricted') + '</strong></div>' +
          '<div class="vault-panel-row"><span>' + uiText('protocol') + '</span><strong>CONTROL MODE</strong></div>' +
          '<div class="vault-panel-row"><span>' + uiText('execution') + '</span><strong>' + uiText('disabled') + '</strong></div>' +
          '<p class="vault-panel-note">' + uiText('visual_showcase_only') + '</p>' +
        '</aside>' +
      '</div>' +
      '<section class="vault-tools-section">' +
        '<div class="vault-tools-head"><h3>' + uiText('locked_modules') + '</h3><p>' + uiText('compact_locked_previews') + '</p></div>' +
        '<div class="vault-tools-grid">' + cards + '</div>' +
      '</section>' +
    '</section>';
    if (window.refreshLanguage) window.refreshLanguage();
  }

  function renderStore() {
    var container = document.getElementById('viewStore');
    if (!container) return;
    container.innerHTML = '<div class="store-page">' +
      '<div class="store-header">' +
        '<h2 class="store-title">' + uiText('premium_apps_store') + '</h2>' +
        '<p class="store-subtitle">' + uiText('digital_products') + '</p>' +
      '</div>' +
      '<div class="store-grid">' +
        '<a href="https://www.instagram.com/miistore.99?igsh=ZmFqanZuOXo4cG92" target="_blank" rel="noopener noreferrer" class="store-card">' +
          '<div class="store-card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="28" height="28"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"/><circle cx="12" cy="12" r="4.5"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none"/></svg></div>' +
          '<div class="store-card-title">INSTAGRAM</div>' +
          '<div class="store-card-desc">' + uiText('follow_updates') + '</div>' +
        '</a>' +
        '<a href="https://t.me/asami_am0" target="_blank" rel="noopener noreferrer" class="store-card">' +
          '<div class="store-card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="28" height="28"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg></div>' +
          '<div class="store-card-title">TELEGRAM</div>' +
          '<div class="store-card-desc">' + uiText('join_telegram') + '</div>' +
        '</a>' +
        '<a href="https://wa.me/6282191223912" target="_blank" rel="noopener noreferrer" class="store-card">' +
          '<div class="store-card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="28" height="28"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg></div>' +
          '<div class="store-card-title">WHATSAPP</div>' +
          '<div class="store-card-desc">' + uiText('chat_with_us') + '</div>' +
        '</a>' +
        '<a href="#social-media" class="store-card">' +
          '<div class="store-card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="28" height="28"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg></div>' +
          '<div class="store-card-title">Social Media / All Links</div>' +
          '<div class="store-card-desc">' + uiText('browse_products') + '</div>' +
        '</a>' +
      '</div>' +
      '<button class="coming-soon-btn" onclick="showMainView()" style="margin-top:24px;">' + uiText('back_to_downloader') + '</button>' +
    '</div>';
    if (window.refreshLanguage) window.refreshLanguage();
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
        '<h2 class="control-title">' + uiText('control_panel') + '</h2>' +
        '<p class="control-subtitle">' + uiText('mii_network_system') + '</p>' +
      '</div>' +
      '<div class="control-grid">' +
        '<div class="control-status-card"><span class="control-dot green"></span><span>' + uiText('server_online') + '</span></div>' +
        '<div class="control-status-card"><span class="control-dot green"></span><span>' + uiText('video_ready') + '</span></div>' +
        '<div class="control-status-card"><span class="control-dot yellow"></span><span>' + uiText('status_tools_soon') + '</span></div>' +
        '<div class="control-status-card"><span class="control-dot green"></span><span>' + uiText('downloads_active') + '</span></div>' +
      '</div>' +
      '<div class="control-stats">' +
        '<div class="control-stat-box"><div class="control-stat-value" id="ctrlViews">0</div><div class="control-stat-label">' + uiText('views') + '</div></div>' +
        '<div class="control-stat-box"><div class="control-stat-value" id="ctrlDownloads">0</div><div class="control-stat-label">' + uiText('downloads') + '</div></div>' +
        '<div class="control-stat-box"><div class="control-stat-value" id="ctrlVisitors">0</div><div class="control-stat-label">' + uiText('visitors') + '</div></div>' +
      '</div>' +
      '<button class="coming-soon-btn" onclick="showMainView()" style="margin-top:24px;">' + uiText('back_to_downloader') + '</button>' +
    '</div>';
    if (window.refreshLanguage) window.refreshLanguage();

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
    navigateTo('downloader');
  }


  document.addEventListener('mii:languagechange', function() {
    if (currentView && currentView !== 'downloader' && viewConfig[currentView]) navigateTo(currentView, true);
  });

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


  function showDashboardToast(message) {
    var old = document.querySelector('.dashboard-toast');
    if (old) old.remove();
    var toast = document.createElement('div');
    toast.className = 'dashboard-toast';
    toast.textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(function() { toast.classList.add('show'); });
    window.setTimeout(function() {
      toast.classList.remove('show');
      window.setTimeout(function() { if (toast.parentNode) toast.remove(); }, 220);
    }, 2200);
  }

  window.showDashboardToast = showDashboardToast;

  // Feature mapping for Coming Soon items
  var featureMap = {
    'wa-status': { titleKey: 'wa_status_converter', descriptionKey: 'wa_status_desc' },
    'status-splitter': { titleKey: 'status_splitter', descriptionKey: 'status_splitter_desc' },
    'caption-copier': { titleKey: 'caption_copier', descriptionKey: 'caption_desc' },
    'hinter-mt': { titleKey: 'private_vault', descriptionKey: 'classified_showcase' }
  };

  // Wire up drawer items using event delegation on the drawer (robust on mobile)
  var sideDrawer = document.getElementById('sideDrawer');
  if (sideDrawer) {
    sideDrawer.addEventListener('click', function(e) {
      var item = e.target.closest('.drawer-item[data-view]');
      if (!item) return;

      var feature = item.getAttribute('data-feature');
      var view = item.getAttribute('data-view');

      // If item has data-feature, use featureMap for Coming Soon
      if (feature && featureMap[feature]) {
        e.preventDefault();
        if (window._closeDrawer) window._closeDrawer();

        var viewDownloader = document.getElementById('viewDownloader');
        var viewComingSoon = document.getElementById('viewComingSoon');
        var viewPrivateVault = document.getElementById('viewPrivateVault');
        var viewStore = document.getElementById('viewStore');
        var viewControl = document.getElementById('viewControl');
        var viewMakimaAI = document.getElementById('viewMakimaAI');

        if (currentView === 'hinter-mt' && view !== 'hinter-mt') pauseVaultMusic();

        if (viewDownloader) viewDownloader.style.display = 'none';
        if (viewComingSoon) viewComingSoon.style.display = 'none';
        if (viewPrivateVault) viewPrivateVault.style.display = 'none';
        if (viewStore) viewStore.style.display = 'none';
        if (viewControl) viewControl.style.display = 'none';
        if (viewMakimaAI) viewMakimaAI.style.display = 'none';
        setAppMode('dashboard');
        document.body.classList.remove('makima-ai-body');

        // Show header again when leaving AI view
        var headerEl = document.querySelector('.page > .header');
        if (headerEl) headerEl.style.display = '';

        var fm = featureMap[feature];
        renderComingSoon(uiText(fm.titleKey), uiText('coming_soon'), uiText(fm.descriptionKey));
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


  document.addEventListener('submit', function(e) {
    var form = e.target.closest('#vaultGateForm');
    if (!form) return;
    e.preventDefault();
    var input = form.querySelector('#vaultConfirmInput');
    var message = form.querySelector('#vaultGateMessage');
    var token = input ? input.value.trim() : '';

    if (token === 'CONFIRM') {
      if (message) {
        message.className = 'vault-gate-message is-success';
        message.innerHTML = '<span>' + uiText('human_signal_confirmed') + '</span><span>' + uiText('private_vault_initialized') + '</span>';
      }
      form.classList.add('is-unlocking');
      revealPrivateVaultFromGate();
      return;
    }

    if (message) {
      message.className = 'vault-gate-message is-denied';
      message.textContent = uiText('access_denied');
    }
    form.classList.remove('is-unlocking');
    if (input) {
      input.value = '';
      input.focus();
    }
  });

  document.addEventListener('input', function(e) {
    if (!e.target.matches('#vaultConfirmInput')) return;
    e.target.value = e.target.value.toUpperCase();
  });

  document.addEventListener('visibilitychange', function() {
    if (document.hidden) pauseVaultMusic();
    else if (currentView === 'hinter-mt' && isPrivateVaultVerified()) startVaultMusic();
  });

  document.addEventListener('click', function(e) {
    var flipCard = e.target.closest('.vault-flip-card');
    if (!flipCard) return;
    e.preventDefault();
    flipCard.classList.toggle('is-flipped');
  });

})();

/* MII STORE homepage social hub interactions */
(function() {
  function initCharacterReveal() {
    var stage = document.getElementById('characterStage');
    if (!stage || stage.dataset.bound === 'true') return;
    stage.dataset.bound = 'true';
    var hideTimer = null;

    function setReveal(clientX, clientY, active) {
      var rect = stage.getBoundingClientRect();
      var x = ((clientX - rect.left) / rect.width) * 100;
      var y = ((clientY - rect.top) / rect.height) * 100;
      x = Math.max(0, Math.min(100, x));
      y = Math.max(0, Math.min(100, y));
      stage.style.setProperty('--mx', x + '%');
      stage.style.setProperty('--my', y + '%');
      if (hideTimer) clearTimeout(hideTimer);
      stage.style.setProperty('--r', active ? (window.matchMedia('(max-width: 700px)').matches ? '96px' : '126px') : '0px');
      stage.classList.toggle('is-revealing', !!active);
    }

    function endReveal() {
      if (hideTimer) clearTimeout(hideTimer);
      hideTimer = window.setTimeout(function() {
        stage.style.setProperty('--r', '0px');
        stage.classList.remove('is-revealing');
      }, 180);
    }

    stage.addEventListener('pointerenter', function(e) { setReveal(e.clientX, e.clientY, true); });
    stage.addEventListener('pointermove', function(e) { setReveal(e.clientX, e.clientY, true); });
    stage.addEventListener('pointerdown', function(e) { stage.setPointerCapture && stage.setPointerCapture(e.pointerId); setReveal(e.clientX, e.clientY, true); });
    stage.addEventListener('pointerup', endReveal);
    stage.addEventListener('pointercancel', endReveal);
    stage.addEventListener('pointerleave', endReveal);
  }

  function clearUiCache() {
    try {
      var keep = {};
      Object.keys(localStorage).forEach(function(k) {
        if (/vault|private/i.test(k)) keep[k] = localStorage.getItem(k);
      });
      localStorage.clear();
      Object.keys(keep).forEach(function(k) { localStorage.setItem(k, keep[k]); });
    } catch (e) {}
    try { sessionStorage.clear(); } catch (e) {}
    var jobs = [];
    if ('serviceWorker' in navigator) jobs.push(navigator.serviceWorker.getRegistrations().then(function(regs) { regs.forEach(function(reg) { reg.unregister(); }); }));
    if ('caches' in window) jobs.push(caches.keys().then(function(keys) { return Promise.all(keys.map(function(key) { return caches.delete(key); })); }));
    Promise.allSettled(jobs).then(function() {
      var url = new URL(window.location.href);
      url.searchParams.set('v', '20260614-final-hero-' + Date.now());
      window.location.replace(url.toString());
    });
  }

  function goHomeSection(id) {
    if (typeof window.navigateTo === 'function' && window.currentView !== 'downloader') {
      window.navigateTo('downloader', true);
    }
    window.setTimeout(function() {
      var target = document.getElementById(id);
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 40);
  }

  function initHomepageCharacterFlip() {
    var card = document.getElementById('characterFlipCard');
    if (!card || card.dataset.flipBound === 'true') return;
    card.dataset.flipBound = 'true';
    card.addEventListener('click', function(e) {
      var toggle = e.target.closest('[data-flip-card]');
      if (!toggle) return;
      e.preventDefault();
      e.stopPropagation();
      card.classList.toggle('is-flipped');
    });
  }

  document.addEventListener('DOMContentLoaded', function() {
    initCharacterReveal();
    initHomepageCharacterFlip();
    var clearBtn = document.getElementById('clearCacheBtn');
    if (clearBtn && clearBtn.dataset.bound !== 'true') {
      clearBtn.dataset.bound = 'true';
      clearBtn.addEventListener('click', clearUiCache);
    }
  });
  document.addEventListener('click', function(e) {
    var scrollItem = e.target.closest('[data-scroll-target]');
    if (scrollItem) {
      e.preventDefault();
      if (window._closeDrawer) window._closeDrawer();
      goHomeSection(scrollItem.getAttribute('data-scroll-target'));
      return;
    }
    var anchor = e.target.closest('a[href^="#"]');
    if (!anchor) return;
    var id = anchor.getAttribute('href').slice(1);
    if (!id) return;
    var target = document.getElementById(id);
    if (target) {
      e.preventDefault();
      goHomeSection(id);
    }
  });
  initCharacterReveal();
  initHomepageCharacterFlip();
})();
