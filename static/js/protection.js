// Image Protection - Block context menu on images
document.addEventListener("contextmenu", function(e) {
  if (e.target.closest(".protected-img, .makima-avatar, .nav-logo-img, .drawer-avatar, .makima-sidebar-avatar, img")) {
    e.preventDefault();
  }
});

// Block drag on all images
document.addEventListener("dragstart", function(e) {
  if (e.target.tagName === "IMG") {
    e.preventDefault();
  }
});

// Long press mobile protection - already handled by CSS -webkit-touch-callout: none
// Additional: prevent default touch actions on images
document.addEventListener("touchstart", function(e) {
  if (e.target.tagName === "IMG" || e.target.closest(".protected-img, .makima-avatar, .nav-logo-img, .drawer-avatar, .makima-sidebar-avatar")) {
    e.target.style.webkitTouchCallout = "none";
  }
}, { passive: true });

// Temporarily disable service workers so fresh CSS/JS assets load immediately.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations()
    .then(registrations => {
      registrations.forEach(reg => reg.unregister());
      console.log('[CACHE] Service workers unregistered');
    });
}

// Temporarily clear Cache Storage to avoid mixed old/new assets.
if ('caches' in window) {
  caches.keys().then(keys => {
    keys.forEach(key => caches.delete(key));
    console.log('[CACHE] Cache storage cleared');
  });
}

// Offline detection overlay
(function() {
  function _createOfflineOverlay() {
    var overlay = document.getElementById('miiOfflineOverlay');
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'miiOfflineOverlay';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(5,0,0,0.97);display:flex;align-items:center;justify-content:center;flex-direction:column;gap:16px;';
    overlay.innerHTML =
      '<div style="color:#ff4444;font-family:var(--font-logo,sans-serif);font-size:1.2rem;letter-spacing:2px;text-transform:uppercase;">OFFLINE</div>' +
      '<div style="color:#ccc;font-family:var(--font-body,sans-serif);font-size:0.85rem;text-align:center;max-width:280px;">Koneksi internet diperlukan untuk menggunakan MII NETWORK.</div>';
    document.body.appendChild(overlay);
    return overlay;
  }

  function _showOfflineOverlay() {
    var overlay = _createOfflineOverlay();
    overlay.style.display = 'flex';
  }

  function _hideOfflineOverlay() {
    var overlay = document.getElementById('miiOfflineOverlay');
    if (overlay) overlay.style.display = 'none';
  }

  window.addEventListener('offline', _showOfflineOverlay);
  window.addEventListener('online', _hideOfflineOverlay);

  // Check initial state
  if (!navigator.onLine) {
    // Defer to ensure body exists
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', _showOfflineOverlay);
    } else {
      _showOfflineOverlay();
    }
  }
})();
