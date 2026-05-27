/* ── MAKIMA AI CHAT (ChatGPT-style Multi-Chat) ──── */

var _makimaAvatarSrc = '/static/img/makima-ai-profile.png';
var _makimaIsSpeaking = false;
var _makimaSidebarOpen = false;
var _makimaVoiceDropdownOpen = false;

/* ── MULTI-CHAT STORAGE ──────────────────────────── */

function loadChats() {
  try {
    var stored = localStorage.getItem('makima_ai_chats');
    if (stored) return JSON.parse(stored);
  } catch (e) {}
  return [];
}

function saveChats(chats) {
  try {
    localStorage.setItem('makima_ai_chats', JSON.stringify(chats));
  } catch (e) {
    console.warn('MAKIMA AI: localStorage penuh atau tidak tersedia.');
  }
}

/* ── STORAGE CAPS ────────────────────────────────── */

var _MAKIMA_MAX_CHATS = 50;
var _MAKIMA_MAX_MESSAGES_PER_CHAT = 200;

function _enforceStorageCaps(chats) {
  // Prune oldest chats if over cap
  if (chats.length > _MAKIMA_MAX_CHATS) {
    chats.splice(_MAKIMA_MAX_CHATS);
  }
  // Prune oldest messages per chat if over cap
  for (var i = 0; i < chats.length; i++) {
    if (chats[i].messages.length > _MAKIMA_MAX_MESSAGES_PER_CHAT) {
      chats[i].messages = chats[i].messages.slice(-_MAKIMA_MAX_MESSAGES_PER_CHAT);
    }
  }
  return chats;
}

function getActiveChatId() {
  try {
    return localStorage.getItem('makima_ai_active_chat_id') || '';
  } catch (e) {
    return '';
  }
}

function setActiveChatId(id) {
  try {
    localStorage.setItem('makima_ai_active_chat_id', id);
  } catch (e) {}
}

function getActiveChat() {
  var chats = loadChats();
  var activeId = getActiveChatId();
  for (var i = 0; i < chats.length; i++) {
    if (chats[i].id === activeId) return chats[i];
  }
  return null;
}

function createNewChat() {
  var chat = {
    id: 'chat_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6),
    title: 'Chat baru',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    messages: []
  };
  var chats = loadChats();
  chats.unshift(chat);
  chats = _enforceStorageCaps(chats);
  saveChats(chats);
  setActiveChatId(chat.id);
  return chat;
}

function switchChat(id) {
  setActiveChatId(id);
  _renderChatArea();
  _renderSidebarList();
}

function deleteChat(id) {
  var chats = loadChats();
  chats = chats.filter(function(c) { return c.id !== id; });
  saveChats(chats);
  var activeId = getActiveChatId();
  if (activeId === id) {
    if (chats.length > 0) {
      setActiveChatId(chats[0].id);
    } else {
      var newChat = createNewChat();
      setActiveChatId(newChat.id);
      _renderChatArea();
      _renderSidebarList();
      return;
    }
  }
  _renderChatArea();
  _renderSidebarList();
}

function clearAllChats() {
  var newChat = {
    id: 'chat_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6),
    title: 'Chat baru',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    messages: []
  };
  saveChats([newChat]);
  setActiveChatId(newChat.id);
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  _makimaIsSpeaking = false;
  _renderChatArea();
  _renderSidebarList();
}

/* ── VOICE SETTINGS ──────────────────────────────── */

function _getVoiceSetting() {
  try {
    return localStorage.getItem('makima_ai_voice_setting') || 'Kore';
  } catch (e) {
    return 'Kore';
  }
}

function _setVoiceSetting(voice) {
  try {
    localStorage.setItem('makima_ai_voice_setting', voice);
  } catch (e) {}
}

/* ── LEGACY MIGRATION ─────────────────────────────── */

function _migrateLegacyChat() {
  try {
    var legacy = localStorage.getItem('makima_ai_chat_history');
    if (!legacy) return;
    var msgs = JSON.parse(legacy);
    if (msgs && msgs.length > 0) {
      var migratedChat = {
        id: 'chat_' + Date.now() + '_migrated',
        title: (msgs[0].text || 'Chat lama').substring(0, 30),
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        messages: msgs
      };
      var chats = loadChats();
      chats.unshift(migratedChat);
      chats = _enforceStorageCaps(chats);
      saveChats(chats);
      setActiveChatId(migratedChat.id);
    }
    localStorage.removeItem('makima_ai_chat_history');
  } catch (e) {
    // If migration fails, just remove the old key to prevent repeated attempts
    try { localStorage.removeItem('makima_ai_chat_history'); } catch (e2) {}
  }
}

/* ── MAIN RENDER ─────────────────────────────────── */

function renderMakimaAI() {
  var container = document.getElementById('viewMakimaAI');
  if (!container) return;

  // Migrate legacy single-chat localStorage if present
  _migrateLegacyChat();

  // Ensure at least one chat exists
  var chats = loadChats();
  if (chats.length === 0) {
    createNewChat();
  } else {
    var activeId = getActiveChatId();
    var found = false;
    for (var i = 0; i < chats.length; i++) {
      if (chats[i].id === activeId) { found = true; break; }
    }
    if (!found) setActiveChatId(chats[0].id);
  }

  container.innerHTML =
    '<div class="makima-ai-page makima-chatgpt-layout">' +
      '<!-- SIDEBAR -->' +
      '<div class="makima-sidebar" id="makimaSidebar">' +
        '<div class="makima-sidebar-header">' +
          '<img src="' + _makimaAvatarSrc + '" alt="MAKIMA" class="makima-sidebar-avatar makima-avatar-protected" draggable="false" oncontextmenu="return false" ondragstart="return false" />' +
          '<span class="makima-sidebar-brand">MAKIMA AI</span>' +
        '</div>' +
        '<button class="makima-new-chat-btn" id="makimaNewChatBtn">+ NEW CHAT</button>' +
        '<div class="makima-sidebar-list" id="makimaSidebarList"></div>' +
        '<div class="makima-sidebar-footer">' +
          '<button class="makima-clear-all-btn" id="makimaClearAllBtn">CLEAR ALL</button>' +
          '<button class="makima-back-link" onclick="showMainView()">KEMBALI KE DOWNLOADER</button>' +
        '</div>' +
      '</div>' +
      '<!-- SIDEBAR OVERLAY (mobile) -->' +
      '<div class="makima-sidebar-overlay" id="makimaSidebarOverlay"></div>' +
      '<!-- MAIN CHAT AREA -->' +
      '<div class="makima-chat-main">' +
        '<!-- COMPACT HEADER -->' +
        '<div class="makima-compact-header">' +
          '<button class="makima-menu-btn" id="makimaMenuBtn" title="Menu">&#9776;</button>' +
          '<img src="' + _makimaAvatarSrc + '" alt="MAKIMA" class="makima-header-avatar makima-avatar-protected" draggable="false" oncontextmenu="return false" ondragstart="return false" />' +
          '<span class="makima-header-title">MAKIMA AI</span>' +
          '<span class="makima-online-badge">ONLINE</span>' +
          '<div class="makima-voice-gear-wrap">' +
            '<button class="makima-gear-btn" id="makimaGearBtn" title="Voice Settings">&#9881;</button>' +
            '<div class="makima-voice-dropdown" id="makimaVoiceDropdown"></div>' +
          '</div>' +
        '</div>' +
        '<!-- MESSAGES -->' +
        '<div class="makima-ai-messages" id="makimaMessages"></div>' +
        '<!-- INPUT -->' +
        '<div class="makima-ai-input-area">' +
          '<div class="makima-ai-input-wrap">' +
            '<input type="text" id="makimaInput" class="makima-ai-input" placeholder="Ketik pesan untuk MAKIMA AI..." autocomplete="off" autocorrect="off" spellcheck="false" />' +
            '<button class="makima-ai-send-btn" id="makimaSendBtn">SEND</button>' +
          '</div>' +
          '<p class="makima-ai-disclaimer">MAKIMA AI dapat membuat kesalahan. Periksa informasi penting.</p>' +
          '<div class="makima-ai-error" id="makimaError"></div>' +
        '</div>' +
      '</div>' +
    '</div>';

  // Bind events
  _bindMakimaEvents();

  // Render sidebar list and chat messages
  _renderSidebarList();
  _renderChatArea();
  _renderVoiceDropdown();
}

/* ── EVENT BINDING ───────────────────────────────── */

function _bindMakimaEvents() {
  var inputEl = document.getElementById('makimaInput');
  var sendBtn = document.getElementById('makimaSendBtn');
  var newChatBtn = document.getElementById('makimaNewChatBtn');
  var clearAllBtn = document.getElementById('makimaClearAllBtn');
  var menuBtn = document.getElementById('makimaMenuBtn');
  var overlay = document.getElementById('makimaSidebarOverlay');
  var gearBtn = document.getElementById('makimaGearBtn');

  if (inputEl) {
    inputEl.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') sendMakimaMessage();
    });
  }
  if (sendBtn) sendBtn.addEventListener('click', sendMakimaMessage);
  if (newChatBtn) newChatBtn.addEventListener('click', function() {
    createNewChat();
    _renderSidebarList();
    _renderChatArea();
    _closeMakimaSidebar();
  });
  if (clearAllBtn) clearAllBtn.addEventListener('click', function() {
    if (confirm('Hapus semua chat?')) clearAllChats();
  });
  if (menuBtn) menuBtn.addEventListener('click', _toggleMakimaSidebar);
  if (overlay) overlay.addEventListener('click', _closeMakimaSidebar);
  if (gearBtn) gearBtn.addEventListener('click', _toggleVoiceDropdown);

  // Close voice dropdown on outside click
  document.addEventListener('click', function(e) {
    if (_makimaVoiceDropdownOpen) {
      var dropdown = document.getElementById('makimaVoiceDropdown');
      var gear = document.getElementById('makimaGearBtn');
      if (dropdown && gear && !dropdown.contains(e.target) && !gear.contains(e.target)) {
        _makimaVoiceDropdownOpen = false;
        dropdown.classList.remove('open');
      }
    }
  });

  // Preload speech synthesis voices (some browsers load them async)
  if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    if (window.speechSynthesis.onvoiceschanged !== undefined) {
      window.speechSynthesis.onvoiceschanged = function() {
        window.speechSynthesis.getVoices();
      };
    }
  }
}

/* ── SIDEBAR TOGGLE ──────────────────────────────── */

function _toggleMakimaSidebar() {
  _makimaSidebarOpen = !_makimaSidebarOpen;
  var sidebar = document.getElementById('makimaSidebar');
  var overlay = document.getElementById('makimaSidebarOverlay');
  if (sidebar) sidebar.classList.toggle('open', _makimaSidebarOpen);
  if (overlay) overlay.classList.toggle('open', _makimaSidebarOpen);
}

function _closeMakimaSidebar() {
  _makimaSidebarOpen = false;
  var sidebar = document.getElementById('makimaSidebar');
  var overlay = document.getElementById('makimaSidebarOverlay');
  if (sidebar) sidebar.classList.remove('open');
  if (overlay) overlay.classList.remove('open');
}

/* ── VOICE DROPDOWN ──────────────────────────────── */

function _toggleVoiceDropdown() {
  _makimaVoiceDropdownOpen = !_makimaVoiceDropdownOpen;
  var dropdown = document.getElementById('makimaVoiceDropdown');
  if (dropdown) dropdown.classList.toggle('open', _makimaVoiceDropdownOpen);
}

function _renderVoiceDropdown() {
  var dropdown = document.getElementById('makimaVoiceDropdown');
  if (!dropdown) return;
  var voices = ['Kore', 'Charon', 'Aoede', 'Sulafat', 'Achernar'];
  var current = _getVoiceSetting();
  var html = '<div class="makima-voice-dropdown-title">Voice Settings</div>';
  for (var i = 0; i < voices.length; i++) {
    var v = voices[i];
    var activeClass = (v === current) ? ' active' : '';
    html += '<button class="makima-voice-opt' + activeClass + '" data-voice="' + _escapeHtml(v) + '">' + _escapeHtml(v) + '</button>';
  }
  dropdown.innerHTML = html;

  var btns = dropdown.querySelectorAll('.makima-voice-opt');
  for (var j = 0; j < btns.length; j++) {
    btns[j].addEventListener('click', function() {
      var voice = this.getAttribute('data-voice');
      _setVoiceSetting(voice);
      var allBtns = dropdown.querySelectorAll('.makima-voice-opt');
      for (var k = 0; k < allBtns.length; k++) allBtns[k].classList.remove('active');
      this.classList.add('active');
    });
  }
}

/* ── SIDEBAR LIST RENDER ─────────────────────────── */

function _renderSidebarList() {
  var listEl = document.getElementById('makimaSidebarList');
  if (!listEl) return;
  var chats = loadChats();
  var activeId = getActiveChatId();
  var html = '';
  for (var i = 0; i < chats.length; i++) {
    var chat = chats[i];
    var isActive = (chat.id === activeId) ? ' active' : '';
    var dateStr = '';
    try {
      var d = new Date(chat.updatedAt);
      dateStr = d.toLocaleDateString('id-ID', { day: 'numeric', month: 'short' });
    } catch (e) { dateStr = ''; }
    html +=
      '<div class="makima-sidebar-item' + isActive + '" data-chatid="' + _escapeHtml(chat.id) + '">' +
        '<div class="makima-sidebar-item-info">' +
          '<span class="makima-sidebar-item-title">' + _escapeHtml(chat.title) + '</span>' +
          '<span class="makima-sidebar-item-date">' + _escapeHtml(dateStr) + '</span>' +
        '</div>' +
        '<button class="makima-sidebar-item-delete" data-deleteid="' + _escapeHtml(chat.id) + '" title="Hapus chat">&#10005;</button>' +
      '</div>';
  }
  listEl.innerHTML = html;

  // Bind click events
  var items = listEl.querySelectorAll('.makima-sidebar-item');
  for (var j = 0; j < items.length; j++) {
    items[j].addEventListener('click', function(e) {
      if (e.target.classList.contains('makima-sidebar-item-delete')) return;
      var chatId = this.getAttribute('data-chatid');
      switchChat(chatId);
      _closeMakimaSidebar();
    });
  }

  var deleteBtns = listEl.querySelectorAll('.makima-sidebar-item-delete');
  for (var k = 0; k < deleteBtns.length; k++) {
    deleteBtns[k].addEventListener('click', function(e) {
      e.stopPropagation();
      var id = this.getAttribute('data-deleteid');
      deleteChat(id);
    });
  }
}

/* ── CHAT AREA RENDER ────────────────────────────── */

function _renderChatArea() {
  var messagesEl = document.getElementById('makimaMessages');
  if (!messagesEl) return;
  messagesEl.innerHTML = '';

  var chat = getActiveChat();
  if (!chat || chat.messages.length === 0) return;

  for (var i = 0; i < chat.messages.length; i++) {
    var entry = chat.messages[i];
    if (entry.role === 'user') {
      _appendUserBubble(messagesEl, entry.text);
    } else {
      _appendAIBubble(messagesEl, entry.text);
    }
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

/* ── MESSAGE BUBBLES ─────────────────────────────── */

function _appendUserBubble(container, text) {
  var row = document.createElement('div');
  row.className = 'makima-msg-row makima-msg-row-user';

  var bubble = document.createElement('div');
  bubble.className = 'makima-msg makima-msg-user';
  bubble.textContent = text;

  row.appendChild(bubble);
  container.appendChild(row);
}

function _appendAIBubble(container, text) {
  var row = document.createElement('div');
  row.className = 'makima-msg-row makima-msg-row-ai';

  var avatar = document.createElement('img');
  avatar.className = 'makima-msg-avatar makima-avatar-protected';
  avatar.src = _makimaAvatarSrc;
  avatar.alt = 'MAKIMA AI';
  avatar.draggable = false;
  avatar.setAttribute('oncontextmenu', 'return false');
  avatar.setAttribute('ondragstart', 'return false');

  var bubble = document.createElement('div');
  bubble.className = 'makima-msg makima-msg-ai';
  bubble.textContent = text;

  // Speaker button
  var speakerBtn = document.createElement('button');
  speakerBtn.className = 'makima-speaker-btn';
  speakerBtn.innerHTML = '&#128264;';
  speakerBtn.title = 'Dengarkan';
  speakerBtn.addEventListener('click', function() {
    _speakMakimaText(text, speakerBtn);
  });
  bubble.appendChild(speakerBtn);

  row.appendChild(avatar);
  row.appendChild(bubble);
  container.appendChild(row);
}

/* ── TTS (SPEECH) ────────────────────────────────── */

function _speakMakimaText(text, btn) {
  if (!window.speechSynthesis) return;

  if (window.speechSynthesis.speaking) {
    var wasThisButton = btn.classList.contains('speaking');
    window.speechSynthesis.cancel();
    _makimaIsSpeaking = false;
    var allSpeakerBtns = document.querySelectorAll('.makima-speaker-btn.speaking');
    for (var i = 0; i < allSpeakerBtns.length; i++) {
      allSpeakerBtns[i].classList.remove('speaking');
      allSpeakerBtns[i].innerHTML = '&#128264;';
    }
    if (wasThisButton) return;
  }

  var utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'id-ID';
  utterance.rate = 0.95;
  utterance.pitch = 0.9;

  // Apply voice setting from stored preference
  var voiceName = _getVoiceSetting();
  var availableVoices = window.speechSynthesis.getVoices();
  for (var v = 0; v < availableVoices.length; v++) {
    if (availableVoices[v].name.indexOf(voiceName) !== -1) {
      utterance.voice = availableVoices[v];
      break;
    }
  }

  btn.classList.add('speaking');
  btn.innerHTML = '&#9632;';
  _makimaIsSpeaking = true;

  utterance.onend = function() {
    btn.classList.remove('speaking');
    btn.innerHTML = '&#128264;';
    _makimaIsSpeaking = false;
  };

  utterance.onerror = function() {
    btn.classList.remove('speaking');
    btn.innerHTML = '&#128264;';
    _makimaIsSpeaking = false;
  };

  window.speechSynthesis.speak(utterance);
}

/* ── LOADING BUBBLE ──────────────────────────────── */

function _showLoadingBubble(container) {
  var row = document.createElement('div');
  row.className = 'makima-msg-row makima-msg-row-ai';
  row.id = 'makimaLoadingRow';

  var avatar = document.createElement('img');
  avatar.className = 'makima-msg-avatar makima-avatar-protected';
  avatar.src = _makimaAvatarSrc;
  avatar.alt = 'MAKIMA AI';
  avatar.draggable = false;
  avatar.setAttribute('oncontextmenu', 'return false');
  avatar.setAttribute('ondragstart', 'return false');

  var bubble = document.createElement('div');
  bubble.className = 'makima-msg-loading';
  bubble.innerHTML =
    '<span class="makima-msg-loading-text">MAKIMA AI sedang berpikir...</span>' +
    '<span class="makima-loading-dots"><span></span><span></span><span></span></span>';

  row.appendChild(avatar);
  row.appendChild(bubble);
  container.appendChild(row);
  return row;
}

function _removeLoadingBubble() {
  var loadingRow = document.getElementById('makimaLoadingRow');
  if (loadingRow && loadingRow.parentNode) {
    loadingRow.parentNode.removeChild(loadingRow);
  }
}

/* ── SEND MESSAGE ────────────────────────────────── */

function sendMakimaMessage() {
  var input = document.getElementById('makimaInput');
  var messagesEl = document.getElementById('makimaMessages');
  var errorEl = document.getElementById('makimaError');

  if (!input || !messagesEl || !errorEl) return;

  var message = input.value.trim();
  errorEl.textContent = '';

  if (!message) {
    errorEl.textContent = 'Pesan tidak boleh kosong.';
    return;
  }

  // Get active chat
  var chat = getActiveChat();
  if (!chat) {
    chat = createNewChat();
    _renderSidebarList();
  }

  // Display user message
  _appendUserBubble(messagesEl, message);

  // Prepare history to send (last 20 messages of active chat)
  var historyToSend = chat.messages.slice(-20);

  // Add message to chat
  chat.messages.push({ role: 'user', text: message });

  // Auto-title: first user message sets the title
  if (chat.title === 'Chat baru') {
    chat.title = message.substring(0, 30);
    _renderSidebarList();
  }

  chat.updatedAt = new Date().toISOString();

  // Save
  var chats = loadChats();
  for (var i = 0; i < chats.length; i++) {
    if (chats[i].id === chat.id) {
      chats[i] = chat;
      break;
    }
  }
  chats = _enforceStorageCaps(chats);
  saveChats(chats);

  input.value = '';
  messagesEl.scrollTop = messagesEl.scrollHeight;

  // Show loading
  _showLoadingBubble(messagesEl);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  // Send to API
  var targetChatId = chat.id;

  fetch('/api/ai-chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: message, history: historyToSend })
  })
  .then(function(res) {
    return res.json().then(function(data) {
      return { status: res.status, data: data };
    });
  })
  .then(function(result) {
    _removeLoadingBubble();

    if (result.data.reply) {
      _appendAIBubble(messagesEl, result.data.reply);

      // Save assistant reply - use pinned targetChatId, not current active chat
      var allChats = loadChats();
      var targetChat = null;
      for (var j = 0; j < allChats.length; j++) {
        if (allChats[j].id === targetChatId) {
          targetChat = allChats[j];
          break;
        }
      }
      // Guard: only write if chat still exists (not cleared/deleted)
      if (targetChat) {
        targetChat.messages.push({ role: 'assistant', text: result.data.reply });
        targetChat.updatedAt = new Date().toISOString();
        allChats = _enforceStorageCaps(allChats);
        saveChats(allChats);
      }

      messagesEl.scrollTop = messagesEl.scrollHeight;
    } else if (result.data.error) {
      errorEl.textContent = result.data.error;
    }
  })
  .catch(function() {
    _removeLoadingBubble();
    errorEl.textContent = 'Koneksi gagal. Coba lagi nanti.';
  });
}

/* ── UTILS ───────────────────────────────────────── */

function _escapeHtml(str) {
  var div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
