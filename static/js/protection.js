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

// Disable offline/PWA - Unregister all service workers
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.getRegistrations().then(function(regs) {
    regs.forEach(function(reg) { reg.unregister(); });
  });
}

// Clear all caches
if ("caches" in window) {
  caches.keys().then(function(keys) {
    keys.forEach(function(key) { caches.delete(key); });
  });
}
