(() => {
  'use strict';
  const form = document.getElementById('publisherLockForm');
  const input = document.getElementById('publisherPassword');
  const button = document.getElementById('unlockPublisher');
  const toggle = document.getElementById('togglePassword');
  const message = document.getElementById('lockMessage');
  let busy = false;
  let remaining = Number.parseInt(document.body.dataset.retryAfter || '0', 10) || 0;

  function showMessage(text) {
    message.textContent = text || '';
    message.hidden = !text;
  }

  function updateLockout() {
    if (remaining <= 0) {
      button.disabled = false;
      button.innerHTML = 'UNLOCK PUBLISHER <span aria-hidden="true">→</span>';
      return;
    }
    button.disabled = true;
    button.textContent = `LOCKED • ${remaining}s`;
    showMessage('TOO MANY FAILED ATTEMPTS. WAIT BEFORE TRYING AGAIN.');
    remaining -= 1;
    window.setTimeout(updateLockout, 1000);
  }

  toggle.addEventListener('click', () => {
    const reveal = input.type === 'password';
    input.type = reveal ? 'text' : 'password';
    toggle.textContent = reveal ? 'HIDE' : 'VIEW';
    toggle.setAttribute('aria-label', reveal ? 'Hide password' : 'Show password');
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy || remaining > 0) return;
    const password = input.value;
    if (!password) { showMessage('ENTER THE MII PUBLISHER PASSWORD.'); input.focus(); return; }
    busy = true; button.disabled = true; button.textContent = 'VERIFYING…'; showMessage('');
    try {
      const response = await fetch('/mii-publisher/unlock', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ password }),
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.ok) { window.location.replace('/mii-publisher'); return; }
      input.value = '';
      if (data.locked) { remaining = Number.parseInt(data.retry_after || '900', 10) || 900; updateLockout(); }
      else showMessage(data.error || 'ACCESS DENIED.');
    } catch (_) {
      showMessage('SECURE GATEWAY IS TEMPORARILY UNAVAILABLE.');
    } finally {
      busy = false;
      if (remaining <= 0) {
        button.disabled = false;
        button.innerHTML = 'UNLOCK PUBLISHER <span aria-hidden="true">→</span>';
      }
    }
  });

  updateLockout();
})();
