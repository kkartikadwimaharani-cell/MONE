(() => {
  'use strict';
  const form = document.getElementById('publisherLockForm');
  const input = document.getElementById('publisherPassword');
  const button = document.getElementById('unlockPublisher');
  const toggle = document.getElementById('togglePassword');
  const message = document.getElementById('lockMessage');
  const attempts = Array.from(document.querySelectorAll('.attempt-pip'));
  const attemptsCount = document.getElementById('attemptsCount');
  const visitTotal = document.getElementById('publisherVisitTotal');
  let busy = false;
  let remaining = Number.parseInt(document.body.dataset.retryAfter || '0', 10) || 0;
  const attemptLimit = Number.parseInt(document.body.dataset.attemptLimit || '3', 10) || 3;
  let attemptsLeft = Number.parseInt(document.body.dataset.attemptsLeft || String(attemptLimit), 10);

  function renderAttempts(value) {
    attemptsLeft = Math.max(0, Math.min(attemptLimit, Number.parseInt(value, 10) || 0));
    const lost = attemptLimit - attemptsLeft;
    attempts.forEach((pip, index) => pip.classList.toggle('lost', index < lost));
    attemptsCount.textContent = `${attemptsLeft} OF ${attemptLimit}`;
  }

  function showMessage(text) {
    message.textContent = text || '';
    message.hidden = !text;
  }

  function newDeviceId() {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
      const random = Math.floor(Math.random() * 16);
      const value = character === 'x' ? random : ((random & 3) | 8);
      return value.toString(16);
    });
  }

  function getPublisherDeviceId() {
    const key = 'mii_publisher_device_id_v1';
    try {
      const existing = window.localStorage.getItem(key);
      if (existing) return existing;
      const created = newDeviceId();
      window.localStorage.setItem(key, created);
      return created;
    } catch (_) {
      return newDeviceId();
    }
  }

  async function trackPublisherView() {
    if (!visitTotal) return;
    try {
      const response = await fetch('/mii-publisher/lock-visit', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        referrerPolicy: 'no-referrer',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ device_id: getPublisherDeviceId() }),
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok && Number.isInteger(data.total) && data.total >= 0) {
        visitTotal.textContent = data.total.toLocaleString('en-US');
      }
    } catch (_) {
      // Device-view tracking is non-critical and must never block login.
    }
  }

  function updateLockout() {
    if (remaining <= 0) {
      button.disabled = false;
      input.disabled = false;
      button.innerHTML = 'UNLOCK PUBLISHER <span aria-hidden="true">→</span>';
      if (attemptsLeft === 0) renderAttempts(attemptLimit);
      return;
    }
    button.disabled = true;
    input.disabled = true;
    const minutes = String(Math.floor(remaining / 60)).padStart(2, '0');
    const seconds = String(remaining % 60).padStart(2, '0');
    button.textContent = `LOCKED • ${minutes}:${seconds}`;
    showMessage(`THREE FAILED ATTEMPTS. TRY AGAIN IN ${minutes}:${seconds}.`);
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
      if (typeof data.attempts_left === 'number') renderAttempts(data.attempts_left);
      if (data.locked) {
        remaining = Number.parseInt(data.retry_after || '300', 10) || 300;
        renderAttempts(0);
        updateLockout();
      } else {
        showMessage(data.attempts_left > 0
          ? `INCORRECT PASSWORD • ${data.attempts_left} ATTEMPT${data.attempts_left === 1 ? '' : 'S'} LEFT.`
          : (data.error || 'ACCESS DENIED.'));
      }
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

  renderAttempts(attemptsLeft);
  updateLockout();
  trackPublisherView();
})();
