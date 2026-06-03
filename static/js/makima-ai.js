// ============================================================
// MAKIMA AI — Final Chat UI + History + ElevenLabs click TTS
// ============================================================

(function () {
  'use strict';

  try {
    const oldTtsStorageKeys = [
      "elevenlabs_disabled",
      "tts_disabled",
      "old_tts_error",
      "tts_cache",
      "tts_voice_id",
      "elevenlabs_voice_id",
      "makima_tts_voice_id",
      "makima_ai_tts_cache"
    ];
    const oldUiStorageKeys = [
      "old_chat_ui",
      "old_code_renderer",
      "makima_thinking_old",
      "ai_ui_cache"
    ];

    oldTtsStorageKeys.concat(oldUiStorageKeys).forEach(key => {
      try { sessionStorage.removeItem(key); } catch (e) {}
      try { localStorage.removeItem(key); } catch (e) {}
    });

    [sessionStorage, localStorage].forEach(storage => {
      try {
        Object.keys(storage).forEach(key => {
          if (key.toLowerCase().includes("tts") || key.toLowerCase().includes("elevenlabs")) {
            storage.removeItem(key);
          }
        });
      } catch (e) {}
    });

    if ("caches" in window) {
      caches.keys().then(keys => {
        keys.forEach(key => {
          if (
            key.toLowerCase().includes("makima") ||
            key.toLowerCase().includes("ai") ||
            key.toLowerCase().includes("tts")
          ) {
            caches.delete(key);
          }
        });
      });
    }

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.getRegistrations().then(regs => {
        regs.forEach(reg => reg.unregister());
      });
    }
  } catch (e) {
    console.warn("[CACHE] clear skipped:", e);
  }

  const STORAGE_KEYS = {
    chats: 'makima_ai_chats',
    activeChatId: 'makima_ai_active_chat_id',
    provider: 'makima_ai_provider',
    model: 'makima_ai_model'
  };

  const MODEL_OPTIONS = [
    { value: 'auto', label: 'Auto', provider: 'auto' },
    { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', provider: 'gemini' },
    { value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash', provider: 'gemini' },
    { value: 'llama-3.3-70b-versatile', label: 'LLaMA 70B', provider: 'groq' },
    { value: 'llama-3.1-8b-instant', label: 'LLaMA 8B', provider: 'groq' }
  ];

  const DEFAULT_MODEL = 'auto';
  const MAX_API_HISTORY = 12;

  let chats = [];
  let activeChatId = null;
  let chatHistory = [];
  let isTyping = false;
  let currentAudio = null;
  let currentAudioUrl = null;
  let currentSpeakerBtn = null;
  let thinkingBubble = null;
  let storageReady = false;

  function safeJsonParse(value, fallback) {
    try {
      return value ? JSON.parse(value) : fallback;
    } catch (e) {
      console.warn('[MAKIMA] localStorage JSON parse error:', e);
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

  function removeStorage(key) {
    try { window.localStorage.removeItem(key); } catch (e) {}
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function createChat() {
    const at = nowIso();
    return {
      id: 'chat_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8),
      title: 'New Chat',
      createdAt: at,
      updatedAt: at,
      messages: []
    };
  }

  function normalizeMessage(msg) {
    if (!msg || typeof msg !== 'object') return null;
    const role = msg.role === 'assistant' ? 'assistant' : msg.role === 'user' ? 'user' : '';
    const text = typeof msg.text === 'string' ? msg.text : '';
    if (!role || !text) return null;
    return {
      role,
      text,
      createdAt: typeof msg.createdAt === 'string' && msg.createdAt ? msg.createdAt : nowIso(),
      ...(msg.error ? { error: true } : {})
    };
  }

  function normalizeChats(value) {
    if (!Array.isArray(value)) return [];
    return value.filter(chat => chat && typeof chat === 'object').map(chat => {
      const fallback = createChat();
      const messages = Array.isArray(chat.messages) ? chat.messages.map(normalizeMessage).filter(Boolean) : [];
      const firstUser = messages.find(msg => msg.role === 'user' && msg.text);
      return {
        id: typeof chat.id === 'string' && chat.id ? chat.id : fallback.id,
        title: typeof chat.title === 'string' && chat.title ? chat.title : titleFromText(firstUser ? firstUser.text : ''),
        createdAt: typeof chat.createdAt === 'string' && chat.createdAt ? chat.createdAt : fallback.createdAt,
        updatedAt: typeof chat.updatedAt === 'string' && chat.updatedAt ? chat.updatedAt : fallback.updatedAt,
        messages
      };
    });
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
      activeChat = chats[0] || createChat();
      if (!chats.length) chats.push(activeChat);
      activeChatId = activeChat.id;
    }

    chatHistory = activeChat.messages.slice();

    const storedModel = readStorage(STORAGE_KEYS.model, DEFAULT_MODEL);
    const selectedModel = MODEL_OPTIONS.some(item => item.value === storedModel) ? storedModel : DEFAULT_MODEL;
    writeStorage(STORAGE_KEYS.model, selectedModel);
    writeStorage(STORAGE_KEYS.provider, providerForModel(selectedModel));
    persistAll();
    storageReady = true;
  }

  function persistAll() {
    writeStorage(STORAGE_KEYS.chats, chats);
    writeStorage(STORAGE_KEYS.activeChatId, activeChatId);
  }

  function persistActiveChat() {
    if (!storageReady) ensureStorageDefaults();
    const chat = getActiveChat();
    if (chat) {
      chat.messages = chatHistory.slice();
      chat.title = titleFromText((chat.messages.find(msg => msg.role === 'user') || {}).text || '');
      chat.updatedAt = nowIso();
    }
    persistAll();
    renderHistoryList();
  }

  function getActiveChat() {
    return chats.find(chat => chat.id === activeChatId) || null;
  }

  function titleFromText(text) {
    const clean = String(text || '').replace(/\s+/g, ' ').trim();
    return clean ? (clean.length > 34 ? clean.slice(0, 34) + '…' : clean) : 'New Chat';
  }

  function sortedChats() {
    return chats.slice().sort((a, b) => String(b.updatedAt || '').localeCompare(String(a.updatedAt || '')));
  }

  function providerForModel(model) {
    const found = MODEL_OPTIONS.find(item => item.value === model);
    return found ? found.provider : 'auto';
  }

  function modelLabel(model) {
    const found = MODEL_OPTIONS.find(item => item.value === model);
    return found ? found.label : 'Auto';
  }

  function getAccessPassword() {
    try { return window.sessionStorage.getItem('makima_ai_access_password') || ''; } catch (e) { return ''; }
  }

  function setAccessPassword(value) {
    try { window.sessionStorage.setItem('makima_ai_access_password', value || ''); } catch (e) {}
  }

  function hasAccess() {
    return !!getAccessPassword();
  }

  function renderAccess() {
    const wrap = document.getElementById('viewMakimaAI');
    if (!wrap) return;
    setMakimaMode();
    wrap.innerHTML = `
      <div class="mkai-access-wrap makima-access-page">
        <div class="mkai-access-card">
          <button class="mkai-back-btn mkai-access-back" id="mkaiAccessBack" type="button">← KEMBALI</button>
          <img class="mkai-access-avatar makima-access-avatar" src="/static/img/makima-ai-profile.png" alt="MAKIMA AI" draggable="false" oncontextmenu="return false">
          <div class="mkai-access-title">MAKIMA AI ACCESS</div>
          <div class="mkai-access-sub">Masukkan password untuk membuka ruang chat.</div>
          <form class="mkai-access-form" id="mkaiAccessForm">
            <input class="mkai-access-input" id="mkaiAccessPassword" type="password" autocomplete="current-password" placeholder="Password" required>
            <button class="mkai-access-submit" type="submit">BUKA MAKIMA AI</button>
          </form>
        </div>
      </div>`;

    document.getElementById('mkaiAccessBack')?.addEventListener('click', goBackToDashboard);
    document.getElementById('mkaiAccessForm')?.addEventListener('submit', function (e) {
      e.preventDefault();
      const password = document.getElementById('mkaiAccessPassword')?.value.trim() || '';
      if (!password) return;
      setAccessPassword(password);
      renderUI();
    });
  }

  function renderUI() {
    const wrap = document.getElementById('viewMakimaAI');
    if (!wrap) return;
    setMakimaMode();
    document.getElementById('mkaiModelPopover')?.remove();
    ensureStorageDefaults();

    const selectedModel = readStorage(STORAGE_KEYS.model, DEFAULT_MODEL) || DEFAULT_MODEL;
    wrap.innerHTML = `
      <div class="mkai-wrap makima-chat-page">
        <aside class="mkai-history-sidebar" aria-label="History chat MAKIMA AI">
          ${historyPanelHTML()}
        </aside>
        <div class="mkai-mobile-drawer" id="mkaiMobileDrawer" aria-hidden="true">
          <div class="mkai-mobile-history-panel">${historyPanelHTML()}</div>
        </div>
        <div class="mkai-drawer-backdrop" id="mkaiDrawerBackdrop"></div>

        <main class="mkai-main">
          <header class="mkai-header makima-header">
            <div class="mkai-header-left">
              <button class="mkai-history-toggle" id="mkaiHistoryToggle" type="button" title="History">☰</button>
              <button class="mkai-back-btn" id="mkaiBack" type="button" title="Kembali ke dashboard">← KEMBALI</button>
              <div class="mkai-avatar-wrap">
                <img class="mkai-avatar makima-avatar" src="/static/img/makima-ai-profile.png" alt="MAKIMA AI" draggable="false" oncontextmenu="return false">
                <span class="mkai-online-dot"></span>
              </div>
              <div class="mkai-title-wrap">
                <div class="mkai-name">MAKIMA AI</div>
                <div class="mkai-sub">Online</div>
              </div>
            </div>
            <div class="mkai-header-right">
              <div class="mkai-model-picker" id="mkaiModelPicker">
                <button class="mkai-model-btn" id="mkaiModelBtn" type="button" aria-haspopup="listbox" aria-expanded="false">
                  <span>${escHtml(modelLabel(selectedModel))}</span><b>▾</b>
                </button>
                <div class="mkai-model-popover" id="mkaiModelPopover" role="listbox">
                  ${MODEL_OPTIONS.map(item => modelOptionHTML(item, selectedModel)).join('')}
                </div>
              </div>
            </div>
          </header>

          <section class="mkai-messages" id="mkaiMessages">
            ${chatHistory.length ? '' : welcomeHTML()}
          </section>

          <div class="mkai-typing-row" id="mkaiTyping">
            <img class="mkai-typing-avatar" src="/static/img/makima-ai-profile.png" alt="">
            <div class="mkai-dots"><span class="mkai-dot"></span><span class="mkai-dot"></span><span class="mkai-dot"></span></div>
          </div>

          <div class="mkai-input-area makima-input-bar">
            <div class="mkai-input-inner">
              <textarea id="mkaiInput" class="mkai-textarea" rows="1" placeholder="Ketik pesan..." maxlength="4000"></textarea>
              <button class="mkai-send-btn" id="mkaiSend" title="Kirim" type="button">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" width="16" height="16">
                  <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
                </svg>
              </button>
            </div>
            <div class="mkai-input-hint">Enter kirim · Shift+Enter baris baru</div>
          </div>
        </main>
      </div>`;

    chatHistory.forEach(msg => {
      if (msg.role === 'user') appendUser(msg.text, false);
      if (msg.role === 'assistant') appendAI(msg.text, !!msg.error, false);
    });

    bindUI();
    renderHistoryList();
    scrollDown();
  }

  function historyPanelHTML() {
    return `
      <div class="mkai-history-head">
        <div>
          <div class="mkai-history-title">History</div>
          <div class="mkai-history-sub">Chat lokal</div>
        </div>
        <button class="mkai-new-chat-btn" data-mkai-new-chat type="button">+ NEW CHAT</button>
      </div>
      <div class="mkai-history-list" data-mkai-history-list></div>
      <button class="mkai-clear-all-btn" data-mkai-clear-all type="button">CLEAR ALL</button>`;
  }

  function modelOptionHTML(item, selected) {
    const active = item.value === selected;
    return `<button class="mkai-model-option${active ? ' active' : ''}" type="button" role="option" aria-selected="${active}" data-model="${escAttr(item.value)}">
      <span class="mkai-model-check">${active ? '●' : '○'}</span><span>${escHtml(item.label)}</span>
    </button>`;
  }

  function bindUI() {
    document.getElementById('mkaiSend')?.addEventListener('click', send);
    document.getElementById('mkaiBack')?.addEventListener('click', goBackToDashboard);
    document.getElementById('mkaiHistoryToggle')?.addEventListener('click', openHistoryDrawer);
    document.getElementById('mkaiDrawerBackdrop')?.addEventListener('click', closeHistoryDrawer);

    document.querySelectorAll('[data-mkai-new-chat]').forEach(btn => btn.addEventListener('click', newChat));
    document.querySelectorAll('[data-mkai-clear-all]').forEach(btn => btn.addEventListener('click', clearAllChats));

    const modelBtn = document.getElementById('mkaiModelBtn');
    modelBtn?.addEventListener('click', function (e) {
      e.stopPropagation();
      toggleModelPopover();
    });
    document.querySelectorAll('.mkai-model-option').forEach(btn => btn.addEventListener('click', selectModel));
    document.addEventListener('click', closeModelPopover);
    window.addEventListener('resize', closeModelPopover);

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
  }

  function renderHistoryList() {
    document.querySelectorAll('[data-mkai-history-list]').forEach(list => {
      list.innerHTML = sortedChats().map(chat => `
        <button class="mkai-history-item${chat.id === activeChatId ? ' active' : ''}" type="button" data-chat-id="${escAttr(chat.id)}">
          <span class="mkai-history-item-title">${escHtml(chat.title || 'New Chat')}</span>
          <span class="mkai-history-item-meta">${chat.messages.length ? chat.messages.length + ' pesan' : 'Kosong'}</span>
        </button>`).join('');
      list.querySelectorAll('.mkai-history-item').forEach(btn => {
        btn.addEventListener('click', function () { loadChat(this.dataset.chatId); });
      });
    });
  }

  function renderMessages() {
    const container = msgs();
    if (!container) return;
    stopAudio();
    container.innerHTML = chatHistory.length ? '' : welcomeHTML();
    chatHistory.forEach(msg => {
      if (msg.role === 'user') appendUser(msg.text, false);
      if (msg.role === 'assistant') appendAI(msg.text, !!msg.error, false);
    });
    scrollDown();
  }

  function welcomeHTML() {
    return `
      <div class="mkai-welcome">
        <img src="/static/img/makima-ai-profile.png" alt="MAKIMA AI" draggable="false" oncontextmenu="return false">
        <div class="mkai-welcome-title">Tanyakan apapun.</div>
        <div class="mkai-welcome-hint">Aku siap bantu coding, UI, bug fixing, dan ide.</div>
      </div>`;
  }

  function newChat() {
    if (!storageReady) ensureStorageDefaults();
    stopAudio();
    const chat = createChat();
    chats.unshift(chat);
    activeChatId = chat.id;
    chatHistory = [];
    persistAll();
    renderHistoryList();
    renderMessages();
    closeHistoryDrawer();
  }

  function loadChat(chatId) {
    if (!chatId || chatId === activeChatId) { closeHistoryDrawer(); return; }
    const chat = chats.find(item => item.id === chatId);
    if (!chat) return;
    stopAudio();
    activeChatId = chat.id;
    chatHistory = chat.messages.slice();
    persistAll();
    renderHistoryList();
    renderMessages();
    closeHistoryDrawer();
  }

  function clearAllChats() {
    stopAudio();
    const chat = createChat();
    chats = [chat];
    activeChatId = chat.id;
    chatHistory = [];
    removeStorage(STORAGE_KEYS.chats);
    removeStorage(STORAGE_KEYS.activeChatId);
    persistAll();
    renderHistoryList();
    renderMessages();
    closeHistoryDrawer();
  }

  function send() {
    if (isTyping) return;
    const ta = document.getElementById('mkaiInput');
    if (!ta) return;
    const text = ta.value.trim();
    if (!text) return;

    ta.value = '';
    ta.style.height = 'auto';

    const userMsg = { role: 'user', text, createdAt: nowIso() };
    appendUser(text);
    chatHistory.push(userMsg);
    persistActiveChat();

    isTyping = true;
    thinkingBubble = appendThinkingBubble();
    setTyping(false);
    setSendDisabled(true);

    const model = readStorage(STORAGE_KEYS.model, DEFAULT_MODEL) || DEFAULT_MODEL;
    const provider = providerForModel(model);
    writeStorage(STORAGE_KEYS.provider, provider);

    fetch('/api/ai-chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history: chatHistory.slice(0, -1).slice(-MAX_API_HISTORY),
        model,
        provider,
        password: getAccessPassword()
      })
    })
      .then(r => r.json())
      .then(data => {
        removeThinkingBubble();
        setTyping(false);
        isTyping = false;
        setSendDisabled(false);
        const reply = data.reply || data.error || 'Terjadi kesalahan. Coba lagi.';
        const isErr = !data.reply;
        chatHistory.push({ role: 'assistant', text: reply, createdAt: nowIso(), ...(isErr ? { error: true } : {}) });
        persistActiveChat();
        appendAI(reply, isErr);
      })
      .catch(() => {
        removeThinkingBubble();
        setTyping(false);
        isTyping = false;
        setSendDisabled(false);
        const reply = 'Koneksi bermasalah. Coba lagi.';
        chatHistory.push({ role: 'assistant', text: reply, createdAt: nowIso(), error: true });
        persistActiveChat();
        appendAI(reply, true);
      });
  }

  function appendThinkingBubble() {
    removeWelcome();
    removeThinkingBubble();
    const container = msgs();
    if (!container) return null;
    const el = document.createElement('div');
    el.className = 'mkai-msg mkai-msg-ai mkai-thinking-message';
    el.innerHTML = `
      <div class="mkai-ai-row">
        <img class="mkai-ai-avatar" src="/static/img/makima-ai-profile.png" alt="" draggable="false" oncontextmenu="return false">
        <div class="mkai-ai-body">
          <div class="mkai-ai-sender">MAKIMA AI</div>
          <div class="thinking-bubble" aria-live="polite">
            <span>Makima sedang berpikir</span>
            <i></i><i></i><i></i>
          </div>
        </div>
      </div>`;
    container.appendChild(el);
    scrollDown();
    return el;
  }

  function removeThinkingBubble() {
    if (thinkingBubble && thinkingBubble.parentNode) {
      thinkingBubble.parentNode.removeChild(thinkingBubble);
    }
    document.querySelectorAll('.mkai-thinking-message').forEach(el => el.remove());
    thinkingBubble = null;
  }

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

  function appendAI(text, isErr = false, shouldScroll = true) {
    removeWelcome();
    const container = msgs();
    if (!container) return;
    const el = document.createElement('div');
    el.className = 'mkai-msg mkai-msg-ai';
    const codeBlocks = [];
    const bodyHTML = isErr
      ? `<div class="mkai-ai-text error">${escHtml(text)}</div>`
      : `<div class="mkai-ai-text">${renderMarkdown(text, codeBlocks)}</div>`;
    el.innerHTML = `
      <div class="mkai-ai-row">
        <img class="mkai-ai-avatar" src="/static/img/makima-ai-profile.png" alt="" draggable="false" oncontextmenu="return false">
        <div class="mkai-ai-body"><div class="mkai-ai-sender">MAKIMA AI</div>${bodyHTML}</div>
      </div>
      ${!isErr ? `<div class="mkai-msg-actions">
        <button class="mkai-action-btn speaker" data-msg="${encodeURIComponent(text)}" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" width="13" height="13">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>
          </svg><span>Dengarkan</span>
        </button>
        <button class="mkai-action-btn copy" data-msg="${encodeURIComponent(text)}" type="button"><span>Salin</span></button>
      </div>` : ''}`;
    container.appendChild(el);
    hydrateCodeBlocks(el, codeBlocks);
    el.querySelector('.mkai-action-btn.speaker')?.addEventListener('click', handleSpeak);
    el.querySelector('.mkai-action-btn.copy')?.addEventListener('click', handleCopy);
    if (shouldScroll) scrollDown();
  }

  async function handleSpeak(e) {
    const btn = e.currentTarget;
    const text = decodeURIComponent(btn.dataset.msg || '');
    console.log('[TTS] clicked');
    console.log('[TTS] text length:', text.length);
    if (!text || !text.trim()) return;

    if (currentSpeakerBtn === btn && currentAudio) {
      stopAudio();
      return;
    }

    stopAudio();
    currentSpeakerBtn = btn;
    btn.disabled = true;
    btn.classList.add('loading');
    setButtonLabel(btn, 'Memuat...');

    try {
      const assistantText = text;

      console.log('[TTS] calling /api/tts');
      const res = await fetch('/api/tts', {
        method: 'POST',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-store'
        },
        body: JSON.stringify({ text: assistantText })
      });

      console.log('[TTS] response status:', res.status);
      console.log('[TTS] response content-type:', res.headers.get('content-type'));
      const contentType = res.headers.get('content-type') || '';
      if (!res.ok || !contentType.toLowerCase().includes('audio')) {
        const errorPayload = await readTtsErrorPayload(res);
        console.warn('[TTS] JSON error:', errorPayload || { status: res.status, contentType });
        fallbackSpeak(text, btn);
        return;
      }

      const blob = await res.blob();
      if (!blob || blob.size === 0) throw new Error('TTS returned empty audio');

      currentAudioUrl = URL.createObjectURL(blob);
      currentAudio = new Audio(currentAudioUrl);

      currentAudio.onended = resetAudioButton;
      currentAudio.onerror = () => fallbackSpeak(text, btn);

      btn.disabled = false;
      btn.classList.remove('loading');
      btn.classList.add('playing');
      setButtonLabel(btn, 'Berhenti');

      await currentAudio.play();
    } catch (err) {
      console.warn('[TTS] ElevenLabs failed, fallback browser:', err);
      fallbackSpeak(text, btn);
    }
  }

  async function readTtsErrorPayload(res) {
    const contentType = res.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      return { status: res.status, contentType };
    }

    try {
      return await res.json();
    } catch (err) {
      return { status: res.status, contentType, detail: 'Unable to parse TTS error JSON' };
    }
  }

  function fallbackSpeak(text, btn) {
    revokeAudioUrl();
    currentAudio = null;
    btn.disabled = false;
    btn.classList.remove('loading');
    if (!('speechSynthesis' in window) || typeof SpeechSynthesisUtterance === 'undefined') {
      setButtonLabel(btn, 'Gagal');
      currentSpeakerBtn = null;
      setTimeout(() => setButtonLabel(btn, 'Dengarkan'), 1800);
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'id-ID';
    utterance.rate = 0.88;
    utterance.pitch = 0.85;
    currentAudio = { pause: () => window.speechSynthesis.cancel() };
    btn.classList.add('playing');
    setButtonLabel(btn, 'Berhenti');
    utterance.onend = utterance.onerror = resetAudioButton;
    window.speechSynthesis.speak(utterance);
  }

  function stopAudio() {
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    if (currentAudio) currentAudio.pause();
    currentAudio = null;
    resetAudioButton();
  }

  function resetAudioButton() {
    revokeAudioUrl();
    if (currentSpeakerBtn) {
      currentSpeakerBtn.disabled = false;
      currentSpeakerBtn.classList.remove('playing', 'loading');
      setButtonLabel(currentSpeakerBtn, 'Dengarkan');
    }
    currentSpeakerBtn = null;
    currentAudio = null;
  }

  function revokeAudioUrl() {
    if (currentAudioUrl) {
      URL.revokeObjectURL(currentAudioUrl);
      currentAudioUrl = null;
    }
  }

  function handleCopy(e) {
    const btn = e.currentTarget;
    const text = decodeURIComponent(btn.dataset.msg || '');
    copyText(text, () => {
      setButtonLabel(btn, 'Disalin!');
      setTimeout(() => setButtonLabel(btn, 'Salin'), 1500);
    });
  }

  function handleCodeCopy(e) {
    const btn = e.currentTarget;
    const block = btn.closest('.mkai-code-block');
    const code = block?.querySelector('code')?.textContent || '';
    copyText(code, () => {
      btn.textContent = 'Disalin';
      setTimeout(() => { btn.textContent = 'Salin'; }, 1500);
    });
  }

  function handleCodeExpand(e) {
    const btn = e.currentTarget;
    const block = btn.closest('.mkai-code-block');
    if (!block) return;
    const expanded = block.classList.toggle('expanded');
    btn.textContent = expanded ? 'Tutup' : 'Lihat penuh';
  }

  function copyText(text, done) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(() => {});
    }
  }

  function placeModelPopover(popover, btn) {
    if (!popover || !btn) return;
    if (popover.parentNode !== document.body) document.body.appendChild(popover);
    const rect = btn.getBoundingClientRect();
    const isMobile = window.matchMedia('(max-width: 900px)').matches;

    if (isMobile) {
      popover.style.top = 'auto';
      popover.style.left = '12px';
      popover.style.right = '12px';
      popover.style.bottom = 'calc(92px + env(safe-area-inset-bottom))';
      popover.style.width = 'auto';
    } else {
      popover.style.top = Math.max(12, rect.bottom + 10) + 'px';
      popover.style.left = 'auto';
      popover.style.right = Math.max(16, window.innerWidth - rect.right) + 'px';
      popover.style.bottom = 'auto';
      popover.style.width = 'min(92vw, 320px)';
    }
  }

  function toggleModelPopover() {
    const picker = document.getElementById('mkaiModelPicker');
    const btn = document.getElementById('mkaiModelBtn');
    const popover = document.getElementById('mkaiModelPopover');
    const open = !(popover?.classList.contains('open'));
    picker?.classList.toggle('open', open);
    popover?.classList.toggle('open', open);
    btn?.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) placeModelPopover(popover, btn);
  }

  function closeModelPopover(e) {
    if (e && e.target.closest && (e.target.closest('#mkaiModelPicker') || e.target.closest('#mkaiModelPopover'))) return;
    document.getElementById('mkaiModelPicker')?.classList.remove('open');
    document.getElementById('mkaiModelPopover')?.classList.remove('open');
    document.getElementById('mkaiModelBtn')?.setAttribute('aria-expanded', 'false');
  }

  function selectModel(e) {
    const model = e.currentTarget.dataset.model || DEFAULT_MODEL;
    writeStorage(STORAGE_KEYS.model, model);
    writeStorage(STORAGE_KEYS.provider, providerForModel(model));
    const btn = document.getElementById('mkaiModelBtn');
    if (btn) btn.innerHTML = `<span>${escHtml(modelLabel(model))}</span><b>▾</b>`;
    const popover = document.getElementById('mkaiModelPopover');
    if (popover) popover.innerHTML = MODEL_OPTIONS.map(item => modelOptionHTML(item, model)).join('');
    popover?.querySelectorAll('.mkai-model-option').forEach(option => option.addEventListener('click', selectModel));
    closeModelPopover();
  }

  function openHistoryDrawer() {
    document.getElementById('mkaiMobileDrawer')?.classList.add('open');
    document.getElementById('mkaiDrawerBackdrop')?.classList.add('open');
  }

  function closeHistoryDrawer() {
    document.getElementById('mkaiMobileDrawer')?.classList.remove('open');
    document.getElementById('mkaiDrawerBackdrop')?.classList.remove('open');
  }

  function goBackToDashboard() {
    stopAudio();
    closeHistoryDrawer();
    if (typeof window.closeDashboardDrawer === 'function') window.closeDashboardDrawer();
    else if (typeof window.closeAllDrawers === 'function') window.closeAllDrawers();
    if (typeof window.setAppMode === 'function') window.setAppMode('dashboard');
    if (typeof window.showMainView === 'function') window.showMainView();
    else if (typeof window.navigateTo === 'function') window.navigateTo('downloader');
    else location.href = '/';
  }

  function setMakimaMode() {
    if (typeof window.closeDashboardDrawer === 'function') window.closeDashboardDrawer();
    else if (typeof window.closeAllDrawers === 'function') window.closeAllDrawers();
    if (typeof window.setAppMode === 'function') window.setAppMode('makima');
  }

  function msgs() { return document.getElementById('mkaiMessages'); }
  function scrollDown() {
    const m = msgs();
    if (!m) return;
    const run = () => { m.scrollTop = m.scrollHeight; };
    run();
    requestAnimationFrame(run);
    setTimeout(run, 60);
  }
  function removeWelcome() { document.querySelector('.mkai-welcome')?.remove(); }
  function setTyping(v) { const t = document.getElementById('mkaiTyping'); if (t) t.classList.toggle('visible', v); if (v) scrollDown(); }
  function setSendDisabled(v) { const b = document.getElementById('mkaiSend'); if (b) b.disabled = v; }
  function setButtonLabel(btn, label) { const span = btn?.querySelector('span'); if (span) span.textContent = label; }

  function escHtml(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function escAttr(s) {
    return escHtml(s).replace(/'/g, '&#39;');
  }

  function renderMarkdown(text, codeBlocks = []) {
    const source = String(text || '').replace(/\r\n/g, '\n');
    const parts = [];
    const fenceRe = /```([^\n`]*)\n?([\s\S]*?)```/g;
    let lastIndex = 0;
    let match;

    while ((match = fenceRe.exec(source)) !== null) {
      if (match.index > lastIndex) {
        parts.push(renderTextMarkdown(source.slice(lastIndex, match.index)));
      }
      const lang = (match[1] || '').trim() || 'CODE';
      const code = (match[2] || '').replace(/^\n|\n$/g, '');
      const index = codeBlocks.push({ lang, code }) - 1;
      parts.push(`<div class="mkai-code-placeholder" data-code-index="${index}"></div>`);
      lastIndex = fenceRe.lastIndex;
    }

    if (lastIndex < source.length) {
      parts.push(renderTextMarkdown(source.slice(lastIndex)));
    }

    return parts.join('').trim();
  }

  function hydrateCodeBlocks(root, codeBlocks) {
    root.querySelectorAll('.mkai-code-placeholder').forEach(placeholder => {
      const index = Number(placeholder.dataset.codeIndex || 0);
      const item = codeBlocks[index] || { lang: 'CODE', code: '' };
      const block = document.createElement('div');
      block.className = 'mkai-code-block compact';

      const header = document.createElement('div');
      header.className = 'mkai-code-header';

      const lang = document.createElement('span');
      lang.className = 'mkai-code-lang';
      lang.textContent = normalizeCodeLabel(item.lang);

      const controls = document.createElement('div');
      controls.className = 'mkai-code-controls';

      const expand = document.createElement('button');
      expand.className = 'mkai-code-expand';
      expand.type = 'button';
      expand.textContent = 'Lihat penuh';
      expand.addEventListener('click', handleCodeExpand);

      const copy = document.createElement('button');
      copy.className = 'mkai-code-copy';
      copy.type = 'button';
      copy.textContent = 'Salin';
      copy.addEventListener('click', handleCodeCopy);

      controls.append(expand, copy);
      header.append(lang, controls);

      const pre = document.createElement('pre');
      const code = document.createElement('code');
      code.textContent = item.code || '';
      pre.appendChild(code);
      block.append(header, pre);
      placeholder.replaceWith(block);

      requestAnimationFrame(() => {
        const longCode = pre.scrollHeight > pre.clientHeight + 8 || code.textContent.split('\n').length > 18;
        block.classList.toggle('is-long', longCode);
      });
    });
  }

  function normalizeCodeLabel(label) {
    const clean = String(label || 'CODE').trim();
    return /[./\\]/.test(clean) ? clean : clean.toUpperCase();
  }

  function renderTextMarkdown(chunk) {
    const blocks = String(chunk || '').split(/\n{2,}/).map(block => block.trim()).filter(Boolean);
    return blocks.map(block => {
      const lines = block.split('\n').map(line => line.trim()).filter(Boolean);
      if (!lines.length) return '';

      const unordered = lines.every(line => /^[-*+]\s+/.test(line));
      if (unordered) {
        return `<ul>${lines.map(line => `<li>${renderInlineMarkdown(line.replace(/^[-*+]\s+/, ''))}</li>`).join('')}</ul>`;
      }

      const ordered = lines.every(line => /^\d+[.)]\s+/.test(line));
      if (ordered) {
        return `<ol>${lines.map(line => `<li>${renderInlineMarkdown(line.replace(/^\d+[.)]\s+/, ''))}</li>`).join('')}</ol>`;
      }

      const heading = block.match(/^(#{1,3})\s+(.+)$/);
      if (heading) {
        const level = Math.min(heading[1].length + 2, 4);
        return `<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`;
      }

      return `<p>${lines.map(renderInlineMarkdown).join('<br>')}</p>`;
    }).join('');
  }

  function renderInlineMarkdown(value) {
    let html = escHtml(value);
    html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/(^|\s)\*([^*]+)\*(?=\s|$|[.,!?])/g, '$1<em>$2</em>');
    return html;
  }

  function tryRender() {
    const c = document.getElementById('viewMakimaAI');
    if (!c || c.style.display === 'none') return;
    setMakimaMode();
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
  window.showMakimaAccess = renderAccess;
  window.safeJsonParse = window.safeJsonParse || safeJsonParse;

  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();
})();
