// ============================================================
// MAKIMA AI — Clean Chat (Claude-style UI + ElevenLabs TTS)
// ============================================================

(function () {
  'use strict';

  const STORAGE_KEYS = {
    chats: 'makima_ai_chats',
    activeChatId: 'makima_ai_active_chat_id',
    provider: 'makima_ai_provider',
    model: 'makima_ai_model',
    voiceSettings: 'makima_ai_voice_settings',
    voiceId: 'makima_ai_voice_id',
    ttsModel: 'makima_ai_tts_model'
  };

  const DEFAULTS = {
    provider: 'auto',
    model: 'auto',
    voiceSettings: { enabled: true, voiceId: '', model: 'eleven_multilingual_v2' },
    voiceId: '',
    ttsModel: 'eleven_multilingual_v2'
  };

  let chats = [];
  let activeChatId = null;
  let chatHistory = [];
  let isTyping    = false;
  let currentAudio = null;
  let currentSpeakerBtn = null;
  let storageReady = false;

  console.log('[MAKIMA] app init');
  console.log('[MAKIMA] page:', location.pathname);

  function safeJsonParse(value, fallback) {
    try {
      return value ? JSON.parse(value) : fallback;
    } catch (e) {
      console.warn('[MAKIMA] localStorage parse failed:', e);
      return fallback;
    }
  }

  function readStorage(key, fallback) {
    try {
      return safeJsonParse(window.localStorage.getItem(key), fallback);
    } catch (e) {
      console.warn('[MAKIMA] localStorage read failed:', e);
      return fallback;
    }
  }

  function writeStorage(key, value) {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (e) {
      console.warn('[MAKIMA] localStorage write failed:', e);
      return false;
    }
  }

  function createChat() {
    return {
      id: 'mkai_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8),
      title: 'Chat Baru',
      messages: []
    };
  }

  function normalizeChats(value) {
    return Array.isArray(value)
      ? value.filter(chat => chat && typeof chat === 'object').map(chat => ({
          id: typeof chat.id === 'string' && chat.id ? chat.id : createChat().id,
          title: typeof chat.title === 'string' && chat.title ? chat.title : 'Chat Baru',
          messages: Array.isArray(chat.messages) ? chat.messages.filter(Boolean) : []
        }))
      : [];
  }

  function ensureStorageDefaults() {
    chats = normalizeChats(readStorage(STORAGE_KEYS.chats, []));
    activeChatId = readStorage(STORAGE_KEYS.activeChatId, null);

    if (!chats.length) {
      const chat = createChat();
      chats = [chat];
      activeChatId = chat.id;
    }

    let activeChat = chats.find(chat => chat.id === activeChatId);
    if (!activeChat) {
      activeChat = createChat();
      chats.push(activeChat);
      activeChatId = activeChat.id;
    }

    chatHistory = activeChat.messages.slice();

    const provider = readStorage(STORAGE_KEYS.provider, DEFAULTS.provider) || DEFAULTS.provider;
    const model = readStorage(STORAGE_KEYS.model, DEFAULTS.model) || DEFAULTS.model;
    const voiceSettings = readStorage(STORAGE_KEYS.voiceSettings, DEFAULTS.voiceSettings) || DEFAULTS.voiceSettings;
    const voiceId = readStorage(STORAGE_KEYS.voiceId, DEFAULTS.voiceId);
    const ttsModel = readStorage(STORAGE_KEYS.ttsModel, DEFAULTS.ttsModel) || DEFAULTS.ttsModel;

    writeStorage(STORAGE_KEYS.chats, chats);
    writeStorage(STORAGE_KEYS.activeChatId, activeChatId);
    writeStorage(STORAGE_KEYS.provider, provider);
    writeStorage(STORAGE_KEYS.model, model);
    writeStorage(STORAGE_KEYS.voiceSettings, voiceSettings);
    writeStorage(STORAGE_KEYS.voiceId, voiceId || DEFAULTS.voiceId);
    writeStorage(STORAGE_KEYS.ttsModel, ttsModel);

    storageReady = true;
    console.log('[MAKIMA] localStorage ready');
  }

  function persistChat() {
    if (!storageReady) ensureStorageDefaults();
    const chat = chats.find(item => item.id === activeChatId);
    if (chat) {
      chat.messages = chatHistory.slice();
      const firstUser = chat.messages.find(msg => msg && msg.role === 'user' && msg.text);
      if (firstUser) chat.title = firstUser.text.slice(0, 42);
    }
    writeStorage(STORAGE_KEYS.chats, chats);
    writeStorage(STORAGE_KEYS.activeChatId, activeChatId);
  }

  function getAccessPassword() {
    try {
      return window.sessionStorage.getItem('makima_ai_access_password') || '';
    } catch (e) {
      return '';
    }
  }

  function setAccessPassword(value) {
    try {
      window.sessionStorage.setItem('makima_ai_access_password', value || '');
    } catch (e) {
      console.warn('[MAKIMA] sessionStorage write failed:', e);
    }
  }

  function hasAccess() {
    return !!getAccessPassword();
  }

  // ── Access Gate ─────────────────────────────────────────────
  function renderAccess() {
    const wrap = document.getElementById('viewMakimaAI');
    if (!wrap) return;

    if (typeof window.closeAllDrawers === 'function') window.closeAllDrawers();
    if (typeof window.setAppMode === 'function') window.setAppMode('makima');
    console.log("[MAKIMA] access page loaded - no API call");

    wrap.innerHTML = `
      <div class="mkai-access-wrap makima-access-page">
        <div class="mkai-access-card">
          <button class="mkai-back-btn mkai-access-back" id="mkaiAccessBack" type="button">← KEMBALI</button>
          <img class="mkai-access-avatar" src="/static/img/makima-ai-profile.png" alt="MAKIMA AI" draggable="false" oncontextmenu="return false">
          <div class="mkai-access-title">MAKIMA AI ACCESS</div>
          <div class="mkai-access-sub">Masukkan password untuk membuka ruang chat.</div>
          <form class="mkai-access-form" id="mkaiAccessForm">
            <input class="mkai-access-input" id="mkaiAccessPassword" type="password" autocomplete="current-password" placeholder="Password" required>
            <button class="mkai-access-submit" type="submit">BUKA MAKIMA AI</button>
          </form>
        </div>
      </div>`;

    const back = document.getElementById('mkaiAccessBack');
    if (back) back.addEventListener('click', function () {
      if (typeof window.closeAllDrawers === 'function') window.closeAllDrawers();
      goBackToDashboard();
    });

    const form = document.getElementById('mkaiAccessForm');
    if (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        const input = document.getElementById('mkaiAccessPassword');
        const password = input ? input.value.trim() : '';
        if (!password) return;
        if (typeof window.closeAllDrawers === 'function') window.closeAllDrawers();
        if (typeof window.setAppMode === 'function') window.setAppMode('makima');
        setAccessPassword(password);
        renderUI();
      });
    }
  }

  // ── Build UI ───────────────────────────────────────────────
  function renderUI() {
    const wrap = document.getElementById('viewMakimaAI');
    if (!wrap) return;
    ensureStorageDefaults();

    wrap.innerHTML = `
      <div class="mkai-wrap makima-chat-page">
        <div class="mkai-header">
          <div class="mkai-header-left">
            <button class="mkai-back-btn" id="mkaiBack" type="button" title="Kembali ke dashboard">← KEMBALI</button>
            <div class="mkai-avatar-wrap">
              <img class="mkai-avatar" src="/static/img/makima-ai-profile.png" alt="MAKIMA AI"
                   draggable="false" oncontextmenu="return false">
              <span class="mkai-online-dot"></span>
            </div>
            <div>
              <div class="mkai-name">MAKIMA AI</div>
              <div class="mkai-sub">Online &bull; Siap membantu</div>
            </div>
          </div>
          <div class="mkai-header-right">
            <select class="mkai-model-select" id="mkaiModel">
              <option value="auto">⚡ Auto</option>
              <option value="gemini-2.5-flash">✦ Gemini 2.5 Flash</option>
              <option value="gemini-2.0-flash">✦ Gemini 2.0 Flash</option>
              <option value="llama-3.3-70b-versatile">▲ LLaMA 70B</option>
              <option value="llama-3.1-8b-instant">▲ LLaMA 8B</option>
            </select>
            <button class="mkai-clear-btn" id="mkaiClear" title="Hapus riwayat">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                   stroke-linecap="round" width="15" height="15">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                <path d="M10 11v6M14 11v6"/>
                <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
              </svg>
            </button>
          </div>
        </div>

        <div class="mkai-messages" id="mkaiMessages">
          ${chatHistory.length ? '' : welcomeHTML()}
        </div>

        <div class="mkai-typing-row" id="mkaiTyping">
          <img class="mkai-typing-avatar" src="/static/img/makima-ai-profile.png" alt="">
          <div class="mkai-dots">
            <span class="mkai-dot"></span><span class="mkai-dot"></span><span class="mkai-dot"></span>
          </div>
        </div>

        <div class="mkai-input-area">
          <div class="mkai-input-inner">
            <textarea id="mkaiInput" class="mkai-textarea" rows="1" placeholder="Ketik pesan..." maxlength="4000"></textarea>
            <button class="mkai-send-btn" id="mkaiSend" title="Kirim">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
                   stroke-linecap="round" stroke-linejoin="round" width="16" height="16">
                <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            </button>
          </div>
          <div class="mkai-input-hint">Enter kirim &bull; Shift+Enter baris baru</div>
        </div>
      </div>`;

    const selectedModel = readStorage(STORAGE_KEYS.model, DEFAULTS.model) || DEFAULTS.model;
    const modelSelect = document.getElementById('mkaiModel');
    if (modelSelect) {
      modelSelect.value = selectedModel;
      if (modelSelect.value !== selectedModel) modelSelect.value = DEFAULTS.model;
      modelSelect.addEventListener('change', function () {
        const model = this.value || DEFAULTS.model;
        const provider = model === 'auto' ? 'auto' : model.startsWith('gemini') ? 'gemini' : 'groq';
        writeStorage(STORAGE_KEYS.model, model);
        writeStorage(STORAGE_KEYS.provider, provider);
      });
    }

    chatHistory.forEach(msg => {
      if (!msg || !msg.text) return;
      if (msg.role === 'user') appendUser(msg.text, false);
      if (msg.role === 'assistant') appendAI(msg.text, !!msg.error, false);
    });

    const sendBtn = document.getElementById('mkaiSend');
    if (sendBtn) sendBtn.addEventListener('click', send);

    const clearBtn = document.getElementById('mkaiClear');
    if (clearBtn) clearBtn.addEventListener('click', clearChat);

    const backBtn = document.getElementById('mkaiBack');
    if (backBtn) backBtn.addEventListener('click', goBackToDashboard);

    const ta = document.getElementById('mkaiInput');
    if (ta) {
      ta.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
      });
      ta.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 160) + 'px';
      });
    }

    scrollDown();
  }

  function welcomeHTML() {
    return `
      <div class="mkai-welcome">
        <img src="/static/img/makima-ai-profile.png" alt="MAKIMA AI" draggable="false" oncontextmenu="return false">
        <div class="mkai-welcome-title">Tanyakan apapun.</div>
        <div class="mkai-welcome-hint">Aku siap membantu.</div>
      </div>`;
  }

  // ── Send ───────────────────────────────────────────────────
  function send() {
    if (isTyping) return;
    const ta = document.getElementById('mkaiInput');
    if (!ta) return;
    const text = ta.value.trim();
    if (!text) return;

    ta.value = '';
    ta.style.height = 'auto';

    appendUser(text);
    chatHistory.push({ role: 'user', text });
    persistChat();

    isTyping = true;
    setTyping(true);
    setSendDisabled(true);

    const modelEl = document.getElementById('mkaiModel');
    const model = modelEl ? modelEl.value : (readStorage(STORAGE_KEYS.model, DEFAULTS.model) || DEFAULTS.model);
    const provider = model === 'auto' ? 'auto' : model.startsWith('gemini') ? 'gemini' : 'groq';
    writeStorage(STORAGE_KEYS.model, model);
    writeStorage(STORAGE_KEYS.provider, provider);

    fetch('/api/ai-chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history: chatHistory.slice(-20),
        model,
        provider,
        password: getAccessPassword()
      })
    })
    .then(r => r.json())
    .then(data => {
      setTyping(false);
      isTyping = false;
      setSendDisabled(false);
      const reply = data.reply || data.error || 'Terjadi kesalahan. Coba lagi.';
      const isErr = !data.reply;
      chatHistory.push({ role: 'assistant', text: reply, error: isErr });
      persistChat();
      appendAI(reply, isErr);
    })
    .catch(() => {
      setTyping(false);
      isTyping = false;
      setSendDisabled(false);
      const reply = 'Koneksi bermasalah. Coba lagi.';
      chatHistory.push({ role: 'assistant', text: reply, error: true });
      persistChat();
      appendAI(reply, true);
    });
  }

  // ── Append User ────────────────────────────────────────────
  function appendUser(text, shouldScroll = true) {
    removeWelcome();
    const container = msgs();
    if (!container) return;
    const el = document.createElement('div');
    el.className = 'mkai-msg mkai-msg-user';
    el.innerHTML = `<div class="mkai-bubble-user">${escHtml(text)}</div>`;
    container.appendChild(el);
    if (shouldScroll) scrollDown();
  }

  // ── Append AI ──────────────────────────────────────────────
  function appendAI(text, isErr = false, shouldScroll = true) {
    removeWelcome();
    const container = msgs();
    if (!container) return;
    const el = document.createElement('div');
    el.className = 'mkai-msg mkai-msg-ai';

    const bodyHTML = isErr
      ? `<div class="mkai-ai-text error">${escHtml(text)}</div>`
      : `<div class="mkai-ai-text">${renderMarkdown(text)}</div>`;

    el.innerHTML = `
      <div class="mkai-ai-row">
        <img class="mkai-ai-avatar" src="/static/img/makima-ai-profile.png" alt="" draggable="false" oncontextmenu="return false">
        <div class="mkai-ai-body"><div class="mkai-ai-sender">MAKIMA AI</div>${bodyHTML}</div>
      </div>
      ${!isErr ? `
      <div class="mkai-msg-actions">
        <button class="mkai-action-btn speaker" data-msg="${encodeURIComponent(text)}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" width="13" height="13">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>
          </svg><span>Dengarkan</span>
        </button>
        <button class="mkai-action-btn copy" data-msg="${encodeURIComponent(text)}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" width="13" height="13">
            <rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
          </svg><span>Salin</span>
        </button>
      </div>` : ''}`;

    container.appendChild(el);

    const spk = el.querySelector('.mkai-action-btn.speaker');
    if (spk) spk.addEventListener('click', handleSpeak);

    const cpy = el.querySelector('.mkai-action-btn.copy');
    if (cpy) cpy.addEventListener('click', handleCopy);

    el.querySelectorAll('.mkai-code-copy').forEach(btn => {
      btn.addEventListener('click', function () {
        const code = decodeURIComponent(this.dataset.code || '');
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(code).then(() => {
            this.textContent = 'Disalin!';
            setTimeout(() => { this.textContent = 'Salin'; }, 1500);
          });
        }
      });
    });

    if (shouldScroll) scrollDown();
  }

  // ── Speaker / TTS ──────────────────────────────────────────
  function handleSpeak(e) {
    const btn = e.currentTarget;
    if (!btn) return;
    const text = decodeURIComponent(btn.dataset.msg || '');
    if (!text) return;

    if (currentSpeakerBtn === btn && currentAudio) {
      stopAudio(); return;
    }

    stopAudio();
    currentSpeakerBtn = btn;
    btn.classList.add('loading');
    setButtonLabel(btn, 'Memuat...');

    fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    })
    .then(r => { if (!r.ok) throw new Error('tts-unavailable'); return r.blob(); })
    .then(blob => {
      const url = URL.createObjectURL(blob);
      currentAudio = new Audio(url);
      btn.classList.remove('loading');
      btn.classList.add('playing');
      setButtonLabel(btn, 'Stop');
      const playPromise = currentAudio.play();
      if (playPromise && typeof playPromise.catch === 'function') {
        playPromise.catch(() => fallbackSpeak(text, btn));
      }
      currentAudio.onended = () => {
        btn.classList.remove('playing');
        setButtonLabel(btn, 'Dengarkan');
        URL.revokeObjectURL(url);
        currentAudio = null;
        currentSpeakerBtn = null;
      };
    })
    .catch(() => {
      fallbackSpeak(text, btn);
    });
  }

  function fallbackSpeak(text, btn) {
    if (!btn) return;
    btn.classList.remove('loading');

    if (!('speechSynthesis' in window) || typeof SpeechSynthesisUtterance === 'undefined') {
      setButtonLabel(btn, 'Gagal');
      currentSpeakerBtn = null;
      setTimeout(() => { setButtonLabel(btn, 'Dengarkan'); }, 2000);
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'id-ID';
    utterance.rate = 0.95;
    utterance.pitch = 1;
    currentAudio = { pause: () => window.speechSynthesis.cancel() };
    btn.classList.add('playing');
    setButtonLabel(btn, 'Stop');

    utterance.onend = utterance.onerror = () => {
      btn.classList.remove('playing', 'loading');
      setButtonLabel(btn, 'Dengarkan');
      currentAudio = null;
      currentSpeakerBtn = null;
    };

    window.speechSynthesis.speak(utterance);
  }

  function stopAudio() {
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    if (currentAudio) { currentAudio.pause(); currentAudio = null; }
    if (currentSpeakerBtn) {
      currentSpeakerBtn.classList.remove('playing', 'loading');
      setButtonLabel(currentSpeakerBtn, 'Dengarkan');
      currentSpeakerBtn = null;
    }
  }

  function setButtonLabel(btn, label) {
    const span = btn ? btn.querySelector('span') : null;
    if (span) span.textContent = label;
  }

  // ── Copy ───────────────────────────────────────────────────
  function handleCopy(e) {
    const btn = e.currentTarget;
    if (!btn) return;
    const text = decodeURIComponent(btn.dataset.msg || '');
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        setButtonLabel(btn, 'Disalin!');
        setTimeout(() => { setButtonLabel(btn, 'Salin'); }, 1500);
      });
    }
  }

  // ── Clear ──────────────────────────────────────────────────
  function clearChat() {
    chatHistory = [];
    stopAudio();
    const container = msgs();
    if (container) container.innerHTML = welcomeHTML();
    persistChat();
  }

  function goBackToDashboard() {
    if (typeof window.closeAllDrawers === 'function') window.closeAllDrawers();
    if (typeof window.setAppMode === 'function') window.setAppMode('dashboard');
    stopAudio();
    if (typeof window.showMainView === 'function') {
      window.showMainView();
    } else if (typeof window.navigateTo === 'function') {
      window.navigateTo('downloader');
    } else {
      location.href = '/';
    }
  }

  // ── Helpers ────────────────────────────────────────────────
  function msgs() { return document.getElementById('mkaiMessages'); }
  function scrollDown() { const m = msgs(); if (m) setTimeout(() => { m.scrollTop = m.scrollHeight; }, 40); }
  function removeWelcome() { const w = document.querySelector('.mkai-welcome'); if (w) w.remove(); }
  function setTyping(v) { const t = document.getElementById('mkaiTyping'); if (t) t.classList.toggle('visible', v); if (v) scrollDown(); }
  function setSendDisabled(v) { const b = document.getElementById('mkaiSend'); if (b) b.disabled = v; }

  function escHtml(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function renderMarkdown(text) {
    text = escHtml(text);
    text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
      const encoded = encodeURIComponent(code.trim());
      return `<div class="mkai-code-block">
        <div class="mkai-code-header"><span class="mkai-code-lang">${lang || 'code'}</span><button class="mkai-code-copy" data-code="${encoded}">Salin</button></div>
        <pre><code>${code.trim()}</code></pre>
      </div>`;
    });
    text = text.replace(/`([^`\n]+)`/g, '<code>$1</code>');
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
    text = text.replace(/\n/g, '<br>');
    return text;
  }

  // ── Init ───────────────────────────────────────────────────
  function tryRender() {
    if (typeof window.closeAllDrawers === 'function') window.closeAllDrawers();
    const c = document.getElementById('viewMakimaAI');
    if (!c || c.style.display === 'none') return;
    if (typeof window.closeAllDrawers === 'function') window.closeAllDrawers();
    if (typeof window.setAppMode === 'function') window.setAppMode('makima');
    if (!storageReady) ensureStorageDefaults();
    if (!hasAccess()) {
      if (!c.querySelector('.mkai-access-wrap')) renderAccess();
      return;
    }
    if (!c.querySelector('.mkai-wrap')) renderUI();
  }

  function init() {
    const c = document.getElementById('viewMakimaAI');
    if (!c) return;

    ensureStorageDefaults();
    new MutationObserver(tryRender).observe(c, { attributes: true, attributeFilter: ['style'] });
    tryRender();

    document.addEventListener('click', e => {
      const target = e.target;
      if (target && target.closest && target.closest('[data-view="makima-ai"]')) setTimeout(tryRender, 60);
    });
  }

  window.renderMakimaAI = tryRender;
  window.safeJsonParse = window.safeJsonParse || safeJsonParse;

  document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', init)
    : init();

})();
