// ============================================================
// MAKIMA AI — Final Chat UI + History
// ============================================================

(function () {
  'use strict';

  try {
    const oldUiStorageKeys = [
      "old_chat_ui",
      "old_code_renderer",
      "makima_thinking_old",
      "ai_ui_cache"
    ];

    oldUiStorageKeys.forEach(key => {
      try { sessionStorage.removeItem(key); } catch (e) {}
      try { localStorage.removeItem(key); } catch (e) {}
    });
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
  const ARTIFACT_LANG_ALIASES = {
    javascript: 'JS',
    js: 'JS',
    jsx: 'JSX',
    typescript: 'TS',
    ts: 'TS',
    tsx: 'TSX',
    python: 'PY',
    py: 'PY',
    css: 'CSS',
    html: 'HTML',
    json: 'JSON',
    markdown: 'MD',
    md: 'MD',
    shell: 'SH',
    bash: 'SH',
    sh: 'SH'
  };

  let chats = [];
  let activeChatId = null;
  let chatHistory = [];
  let isTyping = false;
  let thinkingBubble = null;
  let storageReady = false;
  let selectedImage = null;
  let selectedImageUrl = null;

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
      ...(msg.error ? { error: true } : {}),
      ...(msg.imagePreview ? { imagePreview: msg.imagePreview } : {})
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

  const ACCESS_UNLOCK_KEY = 'makima_ai_access_unlocked';

  function getAccessPassword() {
    try { return window.sessionStorage.getItem('makima_ai_access_password') || ''; } catch (e) { return ''; }
  }

  function setAccessPassword(value) {
    try {
      window.sessionStorage.setItem('makima_ai_access_password', value || '');
      window.sessionStorage.setItem(ACCESS_UNLOCK_KEY, value ? 'true' : 'false');
    } catch (e) {}
  }

  function hasAccess() {
    try { return window.sessionStorage.getItem(ACCESS_UNLOCK_KEY) === 'true' && !!getAccessPassword(); } catch (e) { return false; }
  }

  function renderAccess() {
    const wrap = document.getElementById('viewMakimaAI');
    if (!wrap) return;
    setMakimaMode();
    wrap.innerHTML = `
      <div class="mkai-access-wrap makima-access-page">
        <div class="mkai-access-card">
          <button class="mkai-back-btn mkai-access-back" id="mkaiAccessBack" type="button" data-i18n="back_to_downloader">${window.i18nText ? window.i18nText('back_to_downloader') : 'BACK'}</button>
          <img class="mkai-access-avatar makima-access-avatar" src="/static/img/makima-ai-profile.png" alt="MAKIMA AI" draggable="false" oncontextmenu="return false">
          <div class="mkai-access-title" data-i18n="makima_access_title">${window.i18nText ? window.i18nText('makima_access_title') : 'PRIVATE ACCESS'}</div>
          <div class="mkai-access-sub" data-i18n="makima_access_subtitle">${window.i18nText ? window.i18nText('makima_access_subtitle') : 'Enter access key to continue.'}</div>
          <form class="mkai-access-form" id="mkaiAccessForm">
            <input class="mkai-access-input" id="mkaiAccessPassword" type="password" autocomplete="current-password" data-i18n-placeholder="makima_access_placeholder" placeholder="${window.i18nText ? window.i18nText('makima_access_placeholder') : 'Access Key'}" required>
            <button class="mkai-access-submit" id="mkaiAccessSubmit" type="submit" data-i18n="makima_access_button">${window.i18nText ? window.i18nText('makima_access_button') : 'UNLOCK MAKIMA AI'}</button>
          </form>
          <div class="mkai-access-message" id="mkaiAccessMessage" role="status" aria-live="polite"></div>
        </div>
      </div>`;

    if (window.refreshLanguage) window.refreshLanguage();
    document.getElementById('mkaiAccessBack')?.addEventListener('click', goBackToDashboard);
    document.getElementById('mkaiAccessForm')?.addEventListener('submit', function (e) {
      e.preventDefault();
      const passwordInput = document.getElementById('mkaiAccessPassword');
      const submit = document.getElementById('mkaiAccessSubmit');
      const message = document.getElementById('mkaiAccessMessage');
      const password = passwordInput?.value.trim() || '';
      if (!password) return;
      if (submit) submit.disabled = true;
      if (message) {
        message.className = 'mkai-access-message';
        message.textContent = '';
      }
      fetch('/api/makima-access', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password })
      })
        .then(r => r.ok ? r.json() : Promise.reject(r))
        .then(() => {
          setAccessPassword(password);
          if (message) {
            message.className = 'mkai-access-message is-success';
            message.textContent = window.i18nText ? window.i18nText('makima_access_success') : 'ACCESS GRANTED';
          }
          window.setTimeout(renderUI, 260);
        })
        .catch(() => {
          setAccessPassword('');
          if (message) {
            message.className = 'mkai-access-message is-denied';
            message.textContent = window.i18nText ? window.i18nText('makima_access_error') : 'ACCESS DENIED';
          }
          if (passwordInput) {
            passwordInput.value = '';
            passwordInput.focus();
          }
        })
        .finally(() => {
          if (submit) submit.disabled = false;
        });
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
            <div class="mkai-image-preview" id="mkaiImagePreview" hidden></div>
            <div class="mkai-input-inner">
              <input id="mkaiImageInput" class="mkai-image-input" type="file" accept="image/jpeg,image/png,image/webp" hidden>
              <button class="mkai-image-btn" id="mkaiImageBtn" title="Upload gambar" type="button" aria-label="Upload gambar">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="17" height="17">
                  <rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>
                </svg>
              </button>
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
      if (msg.role === 'user') appendUser(msg.text, msg.imagePreview || null, false);
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
    document.getElementById('mkaiImageBtn')?.addEventListener('click', () => document.getElementById('mkaiImageInput')?.click());
    document.getElementById('mkaiImageInput')?.addEventListener('change', handleImageSelect);
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
    container.innerHTML = chatHistory.length ? '' : welcomeHTML();
    chatHistory.forEach(msg => {
      if (msg.role === 'user') appendUser(msg.text, msg.imagePreview || null, false);
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
    activeChatId = chat.id;
    chatHistory = chat.messages.slice();
    persistAll();
    renderHistoryList();
    renderMessages();
    closeHistoryDrawer();
  }

  function clearAllChats() {
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
    const image = selectedImage;
    if (!text && !image) return;

    ta.value = '';
    ta.style.height = 'auto';
    clearSelectedImage();

    const displayText = text || 'Gambar dikirim';
    const userMsg = {
      role: 'user',
      text: displayText,
      createdAt: nowIso(),
      ...(image ? { imagePreview: image.preview } : {})
    };
    appendUser(displayText, image ? image.preview : null);
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
        password: getAccessPassword(),
        ...(image ? { image: { data: image.data, mimeType: image.mimeType, name: image.name } } : {})
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


  async function handleImageSelect(e) {
    const input = e.currentTarget;
    const file = input.files && input.files[0];
    input.value = '';
    if (!file) return;

    const allowed = ['image/jpeg', 'image/png', 'image/webp'];
    const extAllowed = /\.(jpe?g|png|webp)$/i.test(file.name || '');
    if (!allowed.includes(file.type) || !extAllowed) {
      showImageError('Format gambar harus JPG, PNG, atau WEBP.');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      showImageError('Ukuran gambar maksimal 5MB.');
      return;
    }

    try {
      const image = await prepareImage(file);
      clearSelectedImage();
      selectedImage = image;
      selectedImageUrl = image.preview;
      renderImagePreview();
    } catch (err) {
      console.warn('[MAKIMA] image prepare failed:', err);
      showImageError('Gambar gagal diproses. Coba upload ulang.');
    }
  }

  function prepareImage(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = reject;
      reader.onload = () => {
        const originalDataUrl = String(reader.result || '');
        resizeImageDataUrl(originalDataUrl, file.type)
          .then(dataUrl => resolve({
            name: file.name || 'image',
            mimeType: dataUrl.slice(5, dataUrl.indexOf(';')) || file.type,
            data: dataUrl,
            preview: dataUrl
          }))
          .catch(reject);
      };
      reader.readAsDataURL(file);
    });
  }

  function resizeImageDataUrl(dataUrl, mimeType) {
    return new Promise(resolve => {
      const img = new Image();
      img.onload = () => {
        const maxSide = 1600;
        const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
        if (!scale || scale >= 1 || !document.createElement('canvas').getContext) {
          resolve(dataUrl);
          return;
        }
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(img.width * scale));
        canvas.height = Math.max(1, Math.round(img.height * scale));
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          resolve(dataUrl);
          return;
        }
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL(mimeType === 'image/png' ? 'image/png' : 'image/jpeg', 0.86));
      };
      img.onerror = () => resolve(dataUrl);
      img.src = dataUrl;
    });
  }

  function renderImagePreview() {
    const wrap = document.getElementById('mkaiImagePreview');
    if (!wrap) return;
    if (!selectedImage) {
      wrap.hidden = true;
      wrap.innerHTML = '';
      return;
    }
    wrap.hidden = false;
    wrap.innerHTML = `
      <div class="mkai-image-chip">
        <img src="${escAttr(selectedImage.preview)}" alt="Preview gambar">
        <span>${escHtml(selectedImage.name || 'Gambar')}</span>
        <button type="button" id="mkaiRemoveImage" aria-label="Hapus gambar">×</button>
      </div>`;
    document.getElementById('mkaiRemoveImage')?.addEventListener('click', clearSelectedImage);
  }

  function clearSelectedImage() {
    selectedImage = null;
    selectedImageUrl = null;
    renderImagePreview();
  }

  function showImageError(message) {
    const wrap = document.getElementById('mkaiImagePreview');
    if (!wrap) return;
    wrap.hidden = false;
    wrap.innerHTML = `<div class="mkai-image-error">${escHtml(message)}</div>`;
    setTimeout(() => {
      if (!selectedImage && wrap.querySelector('.mkai-image-error')) {
        wrap.hidden = true;
        wrap.innerHTML = '';
      }
    }, 2200);
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

  function appendUser(text, imagePreview = null, shouldScroll = true) {
    removeWelcome();
    const container = msgs();
    if (!container) return;
    const el = document.createElement('div');
    el.className = 'mkai-msg mkai-msg-user';
    el.innerHTML = `<div class="mkai-bubble-user">
      ${imagePreview ? `<img class="mkai-user-image" src="${escAttr(imagePreview)}" alt="Gambar yang dikirim">` : ''}
      ${text ? `<span>${escHtml(text)}</span>` : ''}
    </div>`;
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
    const artifacts = isErr ? [] : detectArtifacts(text);
    const bodyHTML = isErr
      ? `<div class="mkai-ai-text error">${escHtml(text)}</div>`
      : `<div class="mkai-ai-text">${renderMarkdown(text, codeBlocks)}</div>${renderArtifactPanelHTML(artifacts)}`;
    el.innerHTML = `
      <div class="mkai-ai-row">
        <img class="mkai-ai-avatar" src="/static/img/makima-ai-profile.png" alt="" draggable="false" oncontextmenu="return false">
        <div class="mkai-ai-body"><div class="mkai-ai-sender">MAKIMA AI</div>${bodyHTML}</div>
      </div>
      ${!isErr ? `<div class="mkai-msg-actions">
        <button class="mkai-action-btn copy" data-msg="${encodeURIComponent(text)}" type="button"><span>Salin</span></button>
      </div>` : ''}`;
    container.appendChild(el);
    hydrateCodeBlocks(el, codeBlocks);
    hydrateArtifactPanel(el, artifacts);
    el.querySelector('.mkai-action-btn.copy')?.addEventListener('click', handleCopy);
    if (shouldScroll) scrollDown();
  }


  function detectArtifacts(text) {
    const source = String(text || '').replace(/\r\n/g, '\n');
    const artifacts = [];
    const seen = new Set();
    const addArtifact = (name, lang, code) => {
      const fileName = normalizeArtifactFileName(name);
      const body = String(code || '').replace(/^\n|\n$/g, '');
      if (!fileName || !body.trim()) return;
      const key = fileName + '\u0000' + body;
      if (seen.has(key)) return;
      seen.add(key);
      artifacts.push({
        id: 'artifact_' + artifacts.length,
        name: fileName,
        lang: normalizeArtifactLang(lang, fileName),
        code: body
      });
    };

    const fileBeforeFenceRe = /(?:^|\n)\s*(?:FILE|File|file)\s*:\s*([^\n]+?)\s*\n```([^\n`]*)\n?([\s\S]*?)```/g;
    let match;
    while ((match = fileBeforeFenceRe.exec(source)) !== null) {
      addArtifact(match[1], match[2], match[3]);
    }

    const fenceWithFileAttrRe = /```([^\n`]*?)(?:\s+(?:file|filename|path)\s*=\s*(["']?)([^"'\n]+)\2)[^\n`]*\n?([\s\S]*?)```/gi;
    while ((match = fenceWithFileAttrRe.exec(source)) !== null) {
      addArtifact(match[3], match[1], match[4]);
    }

    const fileCommentRe = /```([^\n`]*)\n\s*(?:\/\/|#|<!--|\/\*)\s*(?:FILE|File|file)\s*:\s*([^\n*\-]+?)(?:\s*-->|\s*\*\/)?\s*\n([\s\S]*?)```/g;
    while ((match = fileCommentRe.exec(source)) !== null) {
      addArtifact(match[2], match[1], match[3]);
    }

    return artifacts;
  }

  function normalizeArtifactFileName(name) {
    return String(name || '')
      .trim()
      .replace(/^['"`]+|['"`]+$/g, '')
      .replace(/[\s:;,.]+$/g, '')
      .replace(/^[\-•*]\s*/, '')
      .slice(0, 180);
  }

  function normalizeArtifactLang(lang, fileName) {
    const clean = String(lang || '').trim().split(/\s+/)[0].toLowerCase();
    if (clean && ARTIFACT_LANG_ALIASES[clean]) return ARTIFACT_LANG_ALIASES[clean];
    const extMatch = String(fileName || '').match(/\.([a-z0-9]+)$/i);
    const ext = extMatch ? extMatch[1].toLowerCase() : clean;
    return ARTIFACT_LANG_ALIASES[ext] || (ext ? ext.toUpperCase() : 'CODE');
  }

  function renderArtifactPanelHTML(artifacts) {
    if (!artifacts.length) return '';
    const allButton = artifacts.length > 1
      ? `<button class="mkai-artifact-all" type="button" data-artifact-all>Unduh semua</button>`
      : '';
    return `<section class="mkai-artifacts" aria-label="Artefak kode MAKIMA AI">
      <div class="mkai-artifacts-head">
        <div>
          <div class="mkai-artifacts-title">Artefak</div>
          <div class="mkai-artifacts-sub">${artifacts.length} file terdeteksi</div>
        </div>
        ${allButton}
      </div>
      <div class="mkai-artifact-list">
        ${artifacts.map(item => `<article class="mkai-artifact-item" data-artifact-id="${escAttr(item.id)}">
          <button class="mkai-artifact-open" type="button" data-artifact-open="${escAttr(item.id)}">
            <span class="mkai-artifact-icon">⌘</span>
            <span class="mkai-artifact-meta">
              <strong>${escHtml(item.name)}</strong>
              <small>Kode · ${escHtml(item.lang)}</small>
            </span>
          </button>
          <div class="mkai-artifact-actions">
            <button type="button" data-artifact-copy="${escAttr(item.id)}">Copy</button>
            <button type="button" data-artifact-download="${escAttr(item.id)}">Download</button>
          </div>
        </article>`).join('')}
      </div>
    </section>`;
  }

  function hydrateArtifactPanel(root, artifacts) {
    if (!artifacts.length) return;
    const byId = new Map(artifacts.map(item => [item.id, item]));
    root.querySelectorAll('[data-artifact-open]').forEach(btn => {
      btn.addEventListener('click', () => openArtifactViewer(byId.get(btn.dataset.artifactOpen), artifacts));
    });
    root.querySelectorAll('[data-artifact-copy]').forEach(btn => {
      btn.addEventListener('click', () => {
        const item = byId.get(btn.dataset.artifactCopy);
        if (!item) return;
        copyText(item.code, () => {
          btn.textContent = 'Disalin';
          setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
        });
      });
    });
    root.querySelectorAll('[data-artifact-download]').forEach(btn => {
      btn.addEventListener('click', () => downloadArtifact(byId.get(btn.dataset.artifactDownload)));
    });
    root.querySelector('[data-artifact-all]')?.addEventListener('click', () => downloadAllArtifacts(artifacts));
  }

  function openArtifactViewer(item, artifacts) {
    if (!item) return;
    closeArtifactViewer();
    const overlay = document.createElement('div');
    overlay.className = 'mkai-artifact-viewer';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.innerHTML = `<div class="mkai-artifact-viewer-shell">
      <header class="mkai-artifact-viewer-head">
        <div class="mkai-artifact-viewer-title">
          <strong>${escHtml(item.name)}</strong>
          <span>Kode · ${escHtml(item.lang)}</span>
        </div>
        <div class="mkai-artifact-viewer-actions">
          <button type="button" data-viewer-copy>Copy</button>
          <button type="button" data-viewer-download>Download</button>
          ${artifacts.length > 1 ? '<button type="button" data-viewer-download-all>Unduh semua</button>' : ''}
          <button class="mkai-artifact-viewer-close" type="button" data-viewer-close aria-label="Tutup viewer">×</button>
        </div>
      </header>
      <main class="mkai-artifact-code-wrap">
        <pre><code>${escHtml(item.code)}</code></pre>
      </main>
    </div>`;
    document.body.appendChild(overlay);
    document.body.classList.add('mkai-artifact-open');
    overlay.querySelector('[data-viewer-close]')?.addEventListener('click', closeArtifactViewer);
    overlay.addEventListener('click', e => { if (e.target === overlay) closeArtifactViewer(); });
    overlay.querySelector('[data-viewer-copy]')?.addEventListener('click', e => {
      const btn = e.currentTarget;
      copyText(item.code, () => {
        btn.textContent = 'Disalin';
        setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
      });
    });
    overlay.querySelector('[data-viewer-download]')?.addEventListener('click', () => downloadArtifact(item));
    overlay.querySelector('[data-viewer-download-all]')?.addEventListener('click', () => downloadAllArtifacts(artifacts));
    document.addEventListener('keydown', handleArtifactEsc);
  }

  function closeArtifactViewer() {
    document.querySelector('.mkai-artifact-viewer')?.remove();
    document.body.classList.remove('mkai-artifact-open');
    document.removeEventListener('keydown', handleArtifactEsc);
  }

  function handleArtifactEsc(e) {
    if (e.key === 'Escape') closeArtifactViewer();
  }

  function downloadArtifact(item) {
    if (!item) return;
    downloadBlob(item.code, artifactDownloadName(item.name), 'text/plain;charset=utf-8');
  }

  function downloadAllArtifacts(artifacts) {
    artifacts.forEach((item, index) => {
      setTimeout(() => downloadArtifact(item), index * 180);
    });
  }

  function artifactDownloadName(name) {
    return String(name || 'artifact.txt').split(/[\\/]/).filter(Boolean).pop() || 'artifact.txt';
  }

  function downloadBlob(content, filename, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'artifact.txt';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 500);
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
  function setSendDisabled(v) {
    const b = document.getElementById('mkaiSend');
    const imageBtn = document.getElementById('mkaiImageBtn');
    if (b) b.disabled = v;
    if (imageBtn) imageBtn.disabled = v;
  }
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
