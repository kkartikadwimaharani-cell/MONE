(() => {
  'use strict';

  const state = { connected: false, channels: [], media: null, submitting: false };
  const $ = (id) => document.getElementById(id);
  const els = {
    notice: $('globalNotice'), badge: $('connectionBadge'), connect: $('connectBufferBtn'),
    reconnect: $('reconnectBufferBtn'), disconnect: $('disconnectBufferBtn'), accounts: $('accountGrid'),
    form: $('publisherForm'), mediaUrl: $('mediaUrl'), loadMedia: $('loadMediaBtn'), clearMedia: $('clearMediaBtn'),
    mediaPreview: $('mediaPreview'), previewSurface: $('previewSurface'), mediaType: $('mediaType'),
    mediaName: $('mediaName'), mediaHost: $('mediaHost'), caption: $('caption'), captionCount: $('captionCount'),
    channels: $('channelSelector'), channelCount: $('channelCount'), scheduleFields: $('scheduleFields'),
    scheduleDate: $('scheduleDate'), scheduleTime: $('scheduleTime'), timezone: $('scheduleTimezone'),
    publish: $('publishBtn'), history: $('historyList'), refreshHistory: $('refreshHistoryBtn'),
    dialog: $('confirmDialog'), confirmSummary: $('confirmSummary'), confirmButton: $('confirmPublishBtn'),
    logout: $('logoutPublisherBtn'),
  };

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
      throw new Error('Workspace session expired.');
    }
    if (!response.ok || body.ok === false) throw new Error(body.error || `Request failed (${response.status}).`);
    return body;
  }

  function showNotice(message, success = false) {
    els.notice.textContent = String(message || '');
    els.notice.classList.toggle('success', success);
    els.notice.hidden = !message;
    if (message) els.notice.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function clearNode(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function empty(text) { const el = document.createElement('div'); el.className = 'empty-state'; el.textContent = text; return el; }
  function platformInitial(platform) { return String(platform || '?').slice(0, 2).toUpperCase(); }

  function renderConnection(data) {
    state.connected = Boolean(data.connected);
    state.channels = Array.isArray(data.channels) ? data.channels : [];
    els.badge.textContent = state.connected ? 'CONNECTED' : 'NOT CONNECTED';
    els.badge.className = `status-badge ${state.connected ? 'online' : 'offline'}`;
    els.connect.hidden = state.connected;
    els.reconnect.hidden = !state.connected;
    els.disconnect.hidden = !state.connected;
    clearNode(els.accounts);
    if (!state.channels.length) {
      els.accounts.appendChild(empty(state.connected
        ? 'NO SUPPORTED BUFFER CHANNELS FOUND'
        : (data.connect_available ? 'NO BUFFER CHANNELS CONNECTED' : 'BUFFER SERVER CONNECTION NOT CONFIGURED')));
    } else {
      state.channels.forEach((channel) => {
        const card = document.createElement('article'); card.className = 'account-card';
        const mark = document.createElement('span'); mark.className = 'account-avatar'; mark.textContent = platformInitial(channel.platform);
        const copy = document.createElement('div');
        const name = document.createElement('strong'); name.textContent = channel.name;
        const meta = document.createElement('span'); meta.textContent = `${channel.platform} • CONNECTED`;
        copy.append(name, meta); card.append(mark, copy); els.accounts.appendChild(card);
      });
    }
    renderChannels();
    if (data.connection_error) showNotice(data.connection_error);
    updateSubmitState();
  }

  function renderChannels() {
    const selected = new Set([...els.channels.querySelectorAll('input:checked')].map((item) => item.value));
    clearNode(els.channels);
    if (!state.channels.length) {
      els.channels.appendChild(empty(state.connected ? 'NO SUPPORTED CHANNELS AVAILABLE' : 'CONNECT BUFFER TO SELECT CHANNELS'));
      updateChannelCount();
      return;
    }
    state.channels.forEach((channel) => {
      const label = document.createElement('label'); label.className = 'channel-option';
      const input = document.createElement('input'); input.type = 'checkbox'; input.name = 'channel'; input.value = channel.id;
      input.checked = selected.has(channel.id); input.addEventListener('change', () => { updateChannelCount(); updateSubmitState(); });
      const mark = document.createElement('span'); mark.className = 'platform-mark'; mark.textContent = platformInitial(channel.platform);
      const copy = document.createElement('span'); copy.className = 'channel-copy';
      const name = document.createElement('strong'); name.textContent = channel.name;
      const meta = document.createElement('span'); meta.textContent = channel.platform;
      copy.append(name, meta); label.append(input, mark, copy); els.channels.appendChild(label);
    });
    updateChannelCount();
  }

  function updateChannelCount() {
    const count = els.channels.querySelectorAll('input:checked').length;
    els.channelCount.textContent = `${count} SELECTED`;
  }

  async function loadStatus() {
    try { renderConnection(await api('/api/mii-publisher/status')); }
    catch (error) { showNotice(error.message); }
  }

  async function connectBuffer() {
    showNotice('');
    els.connect.disabled = true; els.reconnect.disabled = true;
    try {
      const data = await api('/api/mii-publisher/buffer/connect', { method: 'POST', body: '{}' });
      if (data.authorization_url) window.location.assign(data.authorization_url);
      else { showNotice('Buffer connected.', true); await loadStatus(); }
    } catch (error) { showNotice(error.message); }
    finally { els.connect.disabled = false; els.reconnect.disabled = false; }
  }

  async function disconnectBuffer() {
    if (!window.confirm('Disconnect Buffer from MII PUBLISHER?')) return;
    try {
      await api('/api/mii-publisher/buffer/disconnect', { method: 'POST', body: '{}' });
      state.channels = []; state.connected = false; showNotice('Buffer disconnected.', true);
      renderConnection({ connected: false, channels: [], oauth_available: true });
    } catch (error) { showNotice(error.message); }
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
      const preview = document.createElement(state.media.type === 'video' ? 'video' : 'img');
      preview.src = state.media.url;
      if (state.media.type === 'video') { preview.controls = true; preview.preload = 'metadata'; }
      else preview.alt = 'Remote media preview';
      preview.referrerPolicy = 'no-referrer';
      preview.addEventListener('error', () => showNotice('The remote file could not be previewed. Confirm that it is public and directly accessible.'));
      els.previewSurface.appendChild(preview); els.mediaType.textContent = state.media.type.toUpperCase();
      els.mediaName.textContent = state.media.filename; els.mediaHost.textContent = state.media.host;
      els.mediaPreview.hidden = false; showNotice('Media URL validated. No file was stored on the MII server.', true);
    } catch (error) { state.media = null; els.mediaPreview.hidden = true; showNotice(error.message); }
    finally { els.loadMedia.disabled = false; updateSubmitState(); }
  }

  function selectedMode() { return els.form.querySelector('input[name="mode"]:checked').value; }
  function selectedChannels() { return [...els.channels.querySelectorAll('input:checked')].map((item) => item.value); }
  function newSubmissionKey() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
    const bytes = new Uint8Array(16); window.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    const hex = [...bytes].map((value) => value.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  function updateSubmitState() {
    const ready = state.connected && state.media && selectedChannels().length > 0 && !state.submitting;
    els.publish.disabled = !ready;
    els.publish.firstChild.textContent = selectedMode() === 'schedule' ? 'SCHEDULE POST ' : 'PUBLISH NOW ';
  }

  function populateTimezones() {
    let zones = ['UTC', 'Asia/Jakarta', 'Asia/Makassar', 'Asia/Jayapura', 'Asia/Singapore', 'America/New_York', 'Europe/London'];
    const local = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    try { if (Intl.supportedValuesOf) zones = Intl.supportedValuesOf('timeZone'); } catch (_) { /* fallback */ }
    if (!zones.includes(local)) zones.unshift(local);
    zones.forEach((zone) => { const option = document.createElement('option'); option.value = zone; option.textContent = zone.replaceAll('_', ' '); els.timezone.appendChild(option); });
    els.timezone.value = local;
    const later = new Date(Date.now() + 60 * 60 * 1000);
    els.scheduleDate.value = `${later.getFullYear()}-${String(later.getMonth() + 1).padStart(2, '0')}-${String(later.getDate()).padStart(2, '0')}`;
    els.scheduleTime.value = `${String(later.getHours()).padStart(2, '0')}:${String(later.getMinutes()).padStart(2, '0')}`;
  }

  function confirmAction(summary) {
    els.confirmSummary.textContent = summary;
    els.confirmButton.value = 'confirm';
    els.dialog.showModal();
    return new Promise((resolve) => {
      els.dialog.addEventListener('close', () => resolve(els.dialog.returnValue === 'confirm'), { once: true });
    });
  }

  async function submitPublisher(event) {
    event.preventDefault();
    if (state.submitting || !state.media) return;
    const channelIds = selectedChannels(); const mode = selectedMode();
    if (!channelIds.length) { showNotice('Select at least one connected channel.'); return; }
    if (mode === 'schedule' && (!els.scheduleDate.value || !els.scheduleTime.value || !els.timezone.value)) {
      showNotice('Complete the date, time, and timezone.'); return;
    }
    const action = mode === 'schedule' ? `schedule this post for ${els.scheduleDate.value} at ${els.scheduleTime.value} ${els.timezone.value}` : 'publish this post now';
    if (!(await confirmAction(`You are about to ${action} on ${channelIds.length} channel${channelIds.length > 1 ? 's' : ''}.`))) return;
    state.submitting = true; updateSubmitState(); els.publish.textContent = 'SUBMITTING…'; showNotice('');
    try {
      const payload = {
        media_url: state.media.url, caption: els.caption.value, channel_ids: channelIds, mode,
        date: els.scheduleDate.value, time: els.scheduleTime.value, timezone: els.timezone.value,
        confirmed: true, idempotency_key: newSubmissionKey(),
      };
      const data = await api('/api/mii-publisher/publish', { method: 'POST', body: JSON.stringify(payload) });
      showNotice(data.duplicate_prevented ? 'Duplicate submission prevented.' : (mode === 'schedule' ? 'Post scheduled through Buffer.' : 'Publishing request sent to Buffer.'), true);
      await loadHistory();
    } catch (error) { showNotice(error.message); await loadHistory(); }
    finally { state.submitting = false; els.publish.innerHTML = `${mode === 'schedule' ? 'SCHEDULE POST' : 'PUBLISH NOW'} <span aria-hidden="true">→</span>`; updateSubmitState(); }
  }

  function renderHistory(items) {
    clearNode(els.history);
    if (!items.length) { els.history.appendChild(empty('NO PUBLISHING ACTIVITY YET')); return; }
    items.forEach((item) => {
      const card = document.createElement('article'); card.className = 'history-item';
      const main = document.createElement('div'); main.className = 'history-main';
      const top = document.createElement('div'); top.className = 'history-top';
      const name = document.createElement('strong'); name.textContent = item.channel_name || 'BUFFER CHANNEL';
      const platform = document.createElement('span'); platform.className = 'history-chip'; platform.textContent = String(item.platform || '').toUpperCase();
      const status = document.createElement('span'); status.className = `history-chip ${String(item.status || '').toLowerCase()}`; status.textContent = item.status || 'PUBLISHING';
      top.append(name, platform, status);
      const meta = document.createElement('p'); meta.className = 'history-meta';
      meta.textContent = `${String(item.media_type || 'media').toUpperCase()} • ${item.scheduled_at ? `SCHEDULED ${item.scheduled_at}` : `SUBMITTED ${item.created_at || ''}`}`;
      main.append(top, meta);
      if (item.error) { const error = document.createElement('p'); error.className = 'history-error'; error.textContent = item.error; main.appendChild(error); }
      card.appendChild(main); els.history.appendChild(card);
    });
  }

  async function loadHistory() {
    els.refreshHistory.disabled = true;
    try { const data = await api('/api/mii-publisher/history'); renderHistory(Array.isArray(data.history) ? data.history : []); }
    catch (error) { showNotice(error.message); }
    finally { els.refreshHistory.disabled = false; }
  }

  els.connect.addEventListener('click', connectBuffer); els.reconnect.addEventListener('click', connectBuffer);
  els.disconnect.addEventListener('click', disconnectBuffer); els.loadMedia.addEventListener('click', loadMedia);
  els.logout.addEventListener('click', lockPublisher);
  els.clearMedia.addEventListener('click', clearMedia); els.refreshHistory.addEventListener('click', loadHistory);
  els.caption.addEventListener('input', () => { els.captionCount.textContent = `${els.caption.value.length} / 5000`; });
  els.mediaUrl.addEventListener('input', () => { if (state.media && els.mediaUrl.value.trim() !== state.media.url) { state.media = null; els.mediaPreview.hidden = true; updateSubmitState(); } });
  els.form.querySelectorAll('input[name="mode"]').forEach((input) => input.addEventListener('change', () => {
    const schedule = selectedMode() === 'schedule'; els.scheduleFields.hidden = !schedule; updateSubmitState();
  }));
  els.form.addEventListener('submit', submitPublisher);

  const params = new URLSearchParams(window.location.search);
  if (params.get('buffer') === 'connected') showNotice('Buffer connected securely.', true);
  else if (params.get('buffer_error')) showNotice('Buffer connection failed. Please try again.');
  populateTimezones(); loadStatus(); loadHistory();
})();
