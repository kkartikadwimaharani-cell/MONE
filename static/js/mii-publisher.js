(() => {
  'use strict';

  const state = { connected: false, configured: false, account: null, media: null, submitting: false, pollTimer: null };
  const $ = (id) => document.getElementById(id);
  const els = {
    notice: $('globalNotice'), connectionBadge: $('connectionBadge'), connect: $('connectInstagramBtn'),
    reconnect: $('reconnectInstagramBtn'), disconnect: $('disconnectInstagramBtn'), accounts: $('accountGrid'),
    healthBadge: $('healthBadge'), healthDot: $('healthDot'), healthStatus: $('healthStatus'),
    healthSummary: $('healthSummary'), healthChecked: $('healthChecked'), warning: $('warningPanel'),
    warningTitle: $('warningTitle'), warningMessage: $('warningMessage'), warningDetails: $('warningDetails'),
    warningReconnect: $('warningReconnectBtn'), warningDetail: $('warningDetailBtn'),
    form: $('publisherForm'), mediaUrl: $('mediaUrl'), loadMedia: $('loadMediaBtn'), clearMedia: $('clearMediaBtn'),
    mediaPreview: $('mediaPreview'), previewSurface: $('previewSurface'), mediaType: $('mediaType'),
    mediaName: $('mediaName'), mediaHost: $('mediaHost'), caption: $('caption'), captionCount: $('captionCount'),
    publish: $('publishBtn'), history: $('historyList'), activities: $('activityList'), refreshHistory: $('refreshHistoryBtn'),
    dialog: $('confirmDialog'), confirmSummary: $('confirmSummary'), confirmButton: $('confirmPublishBtn'),
    logout: $('logoutPublisherBtn'),
  };

  class ApiError extends Error {
    constructor(message, body, status) { super(message); this.body = body || {}; this.status = status; }
  }

  function csrfToken() {
    const item = document.cookie.split('; ').find((part) => part.startsWith('mii_publisher_csrf='));
    return item ? decodeURIComponent(item.split('=').slice(1).join('=')) : '';
  }

  async function api(path, options = {}) {
    const method = options.method || 'GET';
    const headers = { Accept: 'application/json', ...(options.headers || {}) };
    if (method !== 'GET') {
      headers['Content-Type'] = 'application/json';
      headers['X-CSRF-Token'] = csrfToken();
    }
    const response = await fetch(path, { ...options, method, headers, credentials: 'same-origin' });
    let body = {};
    try { body = await response.json(); } catch (_) { body = {}; }
    if (response.status === 401) {
      window.location.assign('/mii-publisher');
      throw new ApiError('Workspace session expired.', body, response.status);
    }
    if (!response.ok || body.ok === false) throw new ApiError(body.error || `Request failed (${response.status}).`, body, response.status);
    return body;
  }

  function clearNode(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function empty(text) { const el = document.createElement('div'); el.className = 'empty-state'; el.textContent = text; return el; }

  function showNotice(message, success = false) {
    els.notice.textContent = String(message || '');
    els.notice.classList.toggle('success', success);
    els.notice.hidden = !message;
  }

  function detailRows(detail) {
    const fields = [
      ['SUBSYSTEM', detail?.subsystem], ['TIME', detail?.time], ['HTTP STATUS', detail?.http_status],
      ['CODE', detail?.code], ['REQUEST ID', detail?.correlation_id], ['RECOMMENDED ACTION', detail?.recommended_action],
    ];
    const fragment = document.createDocumentFragment();
    fields.filter(([, value]) => value !== null && value !== undefined && value !== '').forEach(([label, value]) => {
      const row = document.createElement('div');
      const key = document.createElement('span'); key.textContent = label;
      const copy = document.createElement('strong'); copy.textContent = String(value);
      row.append(key, copy); fragment.appendChild(row);
    });
    return fragment;
  }

  function showIssue(title, message, detail = null, reconnect = true) {
    els.warning.hidden = false;
    els.warningTitle.textContent = title || 'ACTION REQUIRED';
    els.warningMessage.textContent = message || 'Instagram integration requires attention.';
    clearNode(els.warningDetails);
    if (detail) els.warningDetails.appendChild(detailRows(detail));
    els.warningDetails.hidden = true;
    els.warningDetail.hidden = !detail;
    els.warningReconnect.hidden = !reconnect;
  }

  function clearIssue() { els.warning.hidden = true; clearNode(els.warningDetails); }

  function renderHealth(health) {
    const status = String(health?.status || 'UNKNOWN').toUpperCase();
    const className = status.toLowerCase().replaceAll(' ', '-');
    els.healthBadge.textContent = status;
    els.healthBadge.className = `status-badge ${className}`;
    els.healthDot.className = `health-dot ${className}`;
    els.healthStatus.textContent = status;
    els.healthSummary.textContent = health?.summary || 'Health has not been checked yet.';
    els.healthChecked.textContent = health?.checked_at ? `LAST CHECK ${health.checked_at}` : '';
    if (status === 'OPERATIONAL') {
      clearIssue();
    } else {
      const title = status === 'AUTHORIZATION REQUIRED' ? 'INSTAGRAM AUTHORIZATION REQUIRED'
        : status === 'CONFIGURATION ERROR' ? 'INSTAGRAM CONFIGURATION REQUIRED'
          : 'INSTAGRAM INTEGRATION ISSUE';
      showIssue(title, health?.summary, health?.detail, state.configured && status !== 'CONFIGURATION ERROR');
    }
  }

  function renderConnection(data) {
    state.connected = Boolean(data.connected);
    state.configured = Boolean(data.configured);
    state.account = data.account || null;
    els.connectionBadge.textContent = state.connected ? 'CONNECTED' : 'NOT CONNECTED';
    els.connectionBadge.className = `status-badge ${state.connected ? 'online' : 'offline'}`;
    els.connect.hidden = state.connected;
    els.connect.disabled = !state.configured;
    els.reconnect.hidden = !state.connected;
    els.disconnect.hidden = !state.connected;
    clearNode(els.accounts);
    if (state.connected && state.account) {
      const card = document.createElement('article'); card.className = 'account-card instagram-account';
      const mark = document.createElement('span'); mark.className = 'account-avatar'; mark.textContent = 'IG';
      const copy = document.createElement('div');
      const name = document.createElement('strong'); name.textContent = `@${state.account.username || 'instagram'}`;
      const meta = document.createElement('span'); meta.textContent = `${state.account.account_type || 'PROFESSIONAL'} • CONNECTED`;
      copy.append(name, meta); card.append(mark, copy); els.accounts.appendChild(card);
    } else {
      const message = state.configured ? 'INSTAGRAM IS NOT CONNECTED' : 'INSTAGRAM SERVER CONFIGURATION REQUIRED';
      els.accounts.appendChild(empty(message));
    }
    renderHealth(data.health || {});
    updateSubmitState();
  }

  async function loadStatus() {
    try { renderConnection(await api('/api/mii-publisher/status')); }
    catch (error) {
      showIssue('INSTAGRAM INTEGRATION ISSUE', error.message, error.body?.detail, true);
      showNotice(error.message);
    }
  }

  async function connectInstagram(reconnect = false) {
    showNotice(''); els.connect.disabled = true; els.reconnect.disabled = true;
    try {
      const data = await api('/api/mii-publisher/instagram/connect', {
        method: 'POST', body: JSON.stringify({ reconnect }),
      });
      if (!data.authorization_url) throw new Error('Instagram authorization URL was not returned.');
      window.location.assign(data.authorization_url);
    } catch (error) {
      showIssue('INSTAGRAM CONNECTION FAILED', error.message, error.body?.detail, false);
      showNotice(error.message);
    } finally { els.connect.disabled = !state.configured; els.reconnect.disabled = false; }
  }

  async function disconnectInstagram() {
    if (!window.confirm('Disconnect Instagram from MII PUBLISHER?')) return;
    try {
      await api('/api/mii-publisher/instagram/disconnect', { method: 'POST', body: '{}' });
      state.connected = false; state.account = null; state.media = null;
      showNotice('Instagram disconnected. Stored authorization was removed.', true);
      await loadStatus(); await loadHistory();
    } catch (error) { showNotice(error.message); showIssue('DISCONNECT FAILED', error.message, error.body?.detail, false); }
  }

  async function lockPublisher() {
    try { await api('/mii-publisher/logout', { method: 'POST', body: '{}' }); }
    finally { window.location.assign('/mii-publisher'); }
  }

  function clearMedia() {
    state.media = null; els.mediaUrl.value = ''; els.mediaPreview.hidden = true;
    clearNode(els.previewSurface); updateSubmitState();
  }

  async function loadMedia() {
    showNotice(''); els.loadMedia.disabled = true;
    try {
      const data = await api('/api/mii-publisher/media/validate', {
        method: 'POST', body: JSON.stringify({ url: els.mediaUrl.value.trim() }),
      });
      state.media = data.media; clearNode(els.previewSurface);
      const preview = document.createElement('video');
      preview.src = state.media.url; preview.controls = true; preview.preload = 'metadata'; preview.referrerPolicy = 'no-referrer';
      preview.addEventListener('error', () => showNotice('The video could not be previewed. Confirm that the direct URL is public.'));
      els.previewSurface.appendChild(preview); els.mediaType.textContent = 'INSTAGRAM REEL';
      els.mediaName.textContent = state.media.filename; els.mediaHost.textContent = state.media.host;
      els.mediaPreview.hidden = false;
      showNotice('Video URL validated. No video file was stored on the MII server.', true);
    } catch (error) {
      state.media = null; els.mediaPreview.hidden = true; showNotice(error.message);
      if (error.body?.detail) showIssue('MEDIA VALIDATION FAILED', error.message, error.body.detail, state.connected);
    } finally { els.loadMedia.disabled = false; updateSubmitState(); }
  }

  function newSubmissionKey() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
    const bytes = new Uint8Array(16); window.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    const hex = [...bytes].map((value) => value.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  function updateSubmitState() { els.publish.disabled = !(state.connected && state.media && !state.submitting); }

  function confirmAction() {
    const username = state.account?.username ? `@${state.account.username}` : 'the connected Instagram account';
    els.confirmSummary.textContent = `PUBLISH THIS VIDEO AS AN INSTAGRAM REEL TO ${username.toUpperCase()}?`;
    els.confirmButton.value = 'confirm'; els.dialog.showModal();
    return new Promise((resolve) => {
      els.dialog.addEventListener('close', () => resolve(els.dialog.returnValue === 'confirm'), { once: true });
    });
  }

  async function pollJob(jobId, attempt = 0) {
    if (!jobId || attempt >= 60) {
      showNotice('Instagram is still processing the Reel. Use REFRESH to check again.');
      return;
    }
    window.clearTimeout(state.pollTimer);
    state.pollTimer = window.setTimeout(async () => {
      try {
        const data = await api(`/api/mii-publisher/publish/${encodeURIComponent(jobId)}/status`);
        await loadHistory(); await loadStatus();
        const status = data.job?.status;
        if (status === 'PUBLISHED') showNotice('Instagram confirmed that the Reel is published.', true);
        else if (status === 'FAILED') showIssue('PUBLISHING FAILED', data.job?.error || 'Instagram rejected the publishing request.', data.job?.detail, state.connected);
        else pollJob(jobId, attempt + 1);
      } catch (error) {
        showIssue('PUBLISHING STATUS ERROR', error.message, error.body?.detail, state.connected);
      }
    }, 5000);
  }

  async function submitPublisher(event) {
    event.preventDefault();
    if (state.submitting || !state.media || !state.connected) return;
    if (!(await confirmAction())) return;
    state.submitting = true; updateSubmitState(); els.publish.textContent = 'VALIDATING…'; showNotice('VALIDATING INSTAGRAM REEL…');
    try {
      const payload = {
        media_url: state.media.url,
        caption: els.caption.value,
        confirmed: true,
        idempotency_key: newSubmissionKey(),
      };
      const data = await api('/api/mii-publisher/publish', { method: 'POST', body: JSON.stringify(payload) });
      const job = data.job || {};
      if (job.status === 'PUBLISHED') showNotice('Instagram confirmed that the Reel is published.', true);
      else {
        showNotice(data.duplicate_prevented ? 'Duplicate submission prevented.' : 'Instagram is processing the Reel.', true);
        pollJob(job.id);
      }
      await loadHistory(); await loadStatus();
    } catch (error) {
      showNotice(error.message);
      showIssue('PUBLISHING FAILED', error.message, error.body?.detail, state.connected);
      await loadHistory();
    } finally {
      state.submitting = false; els.publish.innerHTML = 'PUBLISH NOW <span aria-hidden="true">→</span>'; updateSubmitState();
    }
  }

  function statusClass(value) { return String(value || 'UNKNOWN').toLowerCase().replaceAll(' ', '-'); }

  function renderJobs(items) {
    clearNode(els.history);
    if (!items.length) { els.history.appendChild(empty('NO INSTAGRAM PUBLISHING ACTIVITY YET')); return; }
    items.forEach((item) => {
      const card = document.createElement('article'); card.className = 'history-item';
      const main = document.createElement('div'); main.className = 'history-main';
      const top = document.createElement('div'); top.className = 'history-top';
      const name = document.createElement('strong'); name.textContent = item.account_username ? `@${item.account_username}` : 'INSTAGRAM REELS';
      const platform = document.createElement('span'); platform.className = 'history-chip'; platform.textContent = 'INSTAGRAM';
      const status = document.createElement('span'); status.className = `history-chip ${statusClass(item.status)}`; status.textContent = item.status || 'UNKNOWN';
      top.append(name, platform, status);
      const meta = document.createElement('p'); meta.className = 'history-meta';
      meta.textContent = `VIDEO • ${item.created_at || ''}`;
      main.append(top, meta);
      if (item.error) { const error = document.createElement('p'); error.className = 'history-error'; error.textContent = item.error; main.appendChild(error); }
      const actions = document.createElement('div'); actions.className = 'history-actions';
      if (item.detail) {
        const details = document.createElement('div'); details.className = 'safe-details'; details.hidden = true; details.appendChild(detailRows(item.detail));
        const detailButton = document.createElement('button'); detailButton.className = 'button quiet'; detailButton.type = 'button'; detailButton.textContent = 'DETAIL';
        detailButton.addEventListener('click', () => { details.hidden = !details.hidden; });
        actions.appendChild(detailButton); main.appendChild(details);
      }
      if (item.status === 'FAILED') {
        const retry = document.createElement('button'); retry.className = 'button secondary'; retry.type = 'button'; retry.textContent = 'RETRY';
        retry.addEventListener('click', async () => {
          els.mediaUrl.value = item.media_url || ''; els.caption.value = item.caption || '';
          els.caption.dispatchEvent(new Event('input')); await loadMedia();
          els.form.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
        actions.appendChild(retry);
      } else if (item.status === 'PROCESSING' || item.status === 'PUBLISHING') {
        const check = document.createElement('button'); check.className = 'button secondary'; check.type = 'button'; check.textContent = 'CHECK STATUS';
        check.addEventListener('click', () => pollJob(item.id)); actions.appendChild(check);
      }
      card.append(main, actions); els.history.appendChild(card);
    });
  }

  function renderActivities(items) {
    clearNode(els.activities);
    if (!items.length) { els.activities.appendChild(empty('NO INTEGRATION EVENTS YET')); return; }
    items.forEach((item) => {
      const card = document.createElement('article'); card.className = 'activity-item';
      const dot = document.createElement('span'); dot.className = `activity-dot ${statusClass(item.status)}`;
      const copy = document.createElement('div');
      const title = document.createElement('strong'); title.textContent = item.event || 'INSTAGRAM EVENT';
      const message = document.createElement('p'); message.textContent = item.message || '';
      const time = document.createElement('small'); time.textContent = item.created_at || '';
      copy.append(title, message, time); card.append(dot, copy); els.activities.appendChild(card);
    });
  }

  async function loadHistory() {
    els.refreshHistory.disabled = true;
    try {
      const data = await api('/api/mii-publisher/history');
      renderJobs(Array.isArray(data.jobs) ? data.jobs : []);
      renderActivities(Array.isArray(data.activities) ? data.activities : []);
    } catch (error) { showNotice(error.message); }
    finally { els.refreshHistory.disabled = false; }
  }

  els.connect.addEventListener('click', () => connectInstagram(false));
  els.reconnect.addEventListener('click', () => connectInstagram(true));
  els.warningReconnect.addEventListener('click', () => connectInstagram(true));
  els.disconnect.addEventListener('click', disconnectInstagram);
  els.loadMedia.addEventListener('click', loadMedia); els.clearMedia.addEventListener('click', clearMedia);
  els.logout.addEventListener('click', lockPublisher); els.refreshHistory.addEventListener('click', async () => { await loadHistory(); await loadStatus(); });
  els.warningDetail.addEventListener('click', () => { els.warningDetails.hidden = !els.warningDetails.hidden; });
  els.caption.addEventListener('input', () => { els.captionCount.textContent = `${els.caption.value.length} / 2200`; });
  els.mediaUrl.addEventListener('input', () => {
    if (state.media && els.mediaUrl.value.trim() !== state.media.url) { state.media = null; els.mediaPreview.hidden = true; updateSubmitState(); }
  });
  els.form.addEventListener('submit', submitPublisher);

  const params = new URLSearchParams(window.location.search);
  if (params.get('instagram') === 'connected') showNotice('Instagram connected securely.', true);
  else if (params.get('instagram_error')) showIssue('INSTAGRAM CONNECTION FAILED', 'Instagram authorization was not completed.', null, true);
  if (params.has('instagram') || params.has('instagram_error')) window.history.replaceState({}, '', '/mii-publisher');
  loadStatus(); loadHistory();
})();
