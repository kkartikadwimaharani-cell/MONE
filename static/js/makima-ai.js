console.log('MAKIMA AI VERSION 20260528_7');
/* == MAKIMA AI CHAT (ChatGPT-style Multi-Chat) == */

var _makimaAvatarSrc = '/static/img/makima-ai-profile.png';
var _makimaIsSpeaking = false;
var _makimaSidebarOpen = false;
var _makimaVoiceDropdownOpen = false;
var _makimaCooldownActive = false;
var _makimaRequestInProgress = false;

/* == PROVIDER/MODEL STATE == */

var _makimaProvider = 'auto';
var _makimaModel = 'gemini-2.0-flash';

var _makimaModelOptions = {
  auto: ['gemini-2.0-flash', 'gemini-2.5-flash'],
  gemini: ['gemini-2.0-flash', 'gemini-2.5-flash'],
  groq: ['llama-3.1-8b-instant', 'llama-3.3-70b-versatile']
};

function _loadProviderSettings() {
  try {
    var p = localStorage.getItem('makima_ai_provider');
    if (p && (p === 'auto' || p === 'gemini' || p === 'groq')) _makimaProvider = p;
    var m = localStorage.getItem('makima_ai_model');
    if (m) _makimaModel = m;
  } catch (e) {}
}

function _saveProviderSettings() {
  try {
    localStorage.setItem('makima_ai_provider', _makimaProvider);
    localStorage.setItem('makima_ai_model', _makimaModel);
  } catch (e) {}
}

/* == MULTI-CHAT STORAGE == */

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

/* == STORAGE CAPS == */

var _MAKIMA_MAX_CHATS = 50;
var _MAKIMA_MAX_MESSAGES_PER_CHAT = 200;

function _enforceStorageCaps(chats) {
  if (chats.length > _MAKIMA_MAX_CHATS) {
    chats.splice(_MAKIMA_MAX_CHATS);
  }
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

/* == VOICE SETTINGS == */

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

/* == LEGACY MIGRATION == */

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
    try { localStorage.removeItem('makima_ai_chat_history'); } catch (e2) {}
  }
}

/* == PASSWORD GATE == */

var _MAKIMA_ACCESS_CODE = 'MYBINI02';

function _isMakimaUnlocked() {
  try {
    return localStorage.getItem('makima_ai_unlocked') === 'true';
  } catch (e) {
    return false;
  }
}

function _renderPasswordGate(container) {
  container.innerHTML =
    '<div class="makima-password-gate">' +
      '<div class="makima-password-modal">' +
        '<div class="makima-password-title">MAKIMA AI ACCESS</div>' +
        '<div class="makima-password-subtitle">Private Feature</div>' +
        '<input type="password" id="makimaPasswordInput" class="makima-password-input" placeholder="Enter access code..." autocomplete="off" />' +
        '<button class="makima-password-btn" id="makimaPasswordBtn">ENTER</button>' +
        '<div class="makima-password-error" id="makimaPasswordError"></div>' +
      '</div>' +
    '</div>';

  var passInput = document.getElementById('makimaPasswordInput');
  var passBtn = document.getElementById('makimaPasswordBtn');
  var passError = document.getElementById('makimaPasswordError');

  if (passBtn) {
    passBtn.addEventListener('click', function() {
      _checkMakimaPassword(passInput, passError);
    });
  }
  if (passInput) {
    passInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') _checkMakimaPassword(passInput, passError);
    });
    passInput.focus();
  }
}

function _checkMakimaPassword(inputEl, errorEl) {
  var value = inputEl ? inputEl.value.trim() : '';
  if (value === _MAKIMA_ACCESS_CODE) {
    try {
      localStorage.setItem('makima_ai_unlocked', 'true');
      sessionStorage.setItem('makima_ai_password', value);
    } catch (e) {}
    renderMakimaAI();
  } else {
    if (errorEl) errorEl.textContent = 'Access denied.';
    if (inputEl) { inputEl.value = ''; inputEl.focus(); }
  }
}

function _lockMakimaAI() {
  try {
    localStorage.removeItem('makima_ai_unlocked');
    sessionStorage.removeItem('makima_ai_password');
  } catch (e) {}
  renderMakimaAI();
}

/* == MAIN RENDER == */

function renderMakimaAI() {
  var container = document.getElementById('viewMakimaAI');
  if (!container) return;

  if (!_isMakimaUnlocked()) {
    _renderPasswordGate(container);
    return;
  }

  try {
    if (!sessionStorage.getItem('makima_ai_password')) {
      sessionStorage.setItem('makima_ai_password', _MAKIMA_ACCESS_CODE);
    }
  } catch (e) {}

  _loadProviderSettings();
  _migrateLegacyChat();

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
      '<div class="makima-sidebar" id="makimaSidebar">' +
        '<div class="makima-sidebar-header">' +
          '<img src="' + _makimaAvatarSrc + '" alt="MAKIMA" class="makima-sidebar-avatar makima-avatar-protected" draggable="false" oncontextmenu="return false" ondragstart="return false" />' +
          '<span class="makima-sidebar-brand">MAKIMA AI</span>' +
        '</div>' +
        '<button class="makima-new-chat-btn" id="makimaNewChatBtn">+ NEW CHAT</button>' +
        '<div class="makima-sidebar-list" id="makimaSidebarList"></div>' +
        '<div class="makima-sidebar-footer">' +
          '<button class="makima-clear-all-btn" id="makimaClearAllBtn">CLEAR ALL</button>' +
          '<button class="makima-back-link" onclick="showMainView()">← KEMBALI KE DOWNLOADER</button>' +
        '</div>' +
      '</div>' +
      '<div class="makima-sidebar-overlay" id="makimaSidebarOverlay"></div>' +
      '<div class="makima-chat-main">' +
        '<div class="makima-compact-header">' +
          '<button class="makima-menu-btn" id="makimaMenuBtn" title="Menu">&#9776;</button>' +
          '<img src="' + _makimaAvatarSrc + '" alt="MAKIMA" class="makima-header-avatar makima-avatar-protected" draggable="false" oncontextmenu="return false" ondragstart="return false" />' +
          '<span class="makima-header-title">MAKIMA AI</span>' +
          '<span class="makima-online-badge">ONLINE</span>' +
          '<div class="makima-voice-gear-wrap">' +
            '<button class="makima-gear-btn" id="makimaGearBtn" title="Settings">&#9881;</button>' +
            '<div class="makima-voice-dropdown" id="makimaVoiceDropdown"></div>' +
          '</div>' +
        '</div>' +
        '<div class="makima-ai-messages" id="makimaMessages"></div>' +
        '<div class="makima-ai-input-area">' +
          '<div class="makima-ai-input-wrap">' +
            '<input type="text" id="makimaInput" class="makima-ai-input" placeholder="Ketik pesan untuk MAKIMA AI..." autocomplete="off" autocorrect="off" spellcheck="false" />' +
            '<button class="makima-ai-send-btn" id="makimaSendBtn">SEND</button>' +
          '</div>' +
          '<div class="makima-ai-error" id="makimaError"></div>' +
        '</div>' +
      '</div>' +
    '</div>';

  _bindMakimaEvents();
  _renderSidebarList();
  _renderChatArea();
  _renderVoiceDropdown();
}

/* == EVENT BINDING == */

function _bindMakimaEvents() {
  var inputEl = document.getElementById('makimaInput');
  var sendBtn = document.getElementById('makimaSendBtn');
  var newChatBtn = document.getElementById('makimaNewChatBtn');
  var clearAllBtn = document.getElementById('makimaClearAllBtn');
  var menuBtn = document.getElementById('makimaMenuBtn');
  var overlay = document.getElementById('makimaSidebarOverlay');
  var gearBtn = document.getElementById('makimaGearBtn');

  if ((_makimaCooldownActive || _makimaRequestInProgress) && sendBtn) {
    sendBtn.disabled = true;
  }

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
    _showClearConfirmModal();
  });
  if (menuBtn) menuBtn.addEventListener('click', _toggleMakimaSidebar);
  if (overlay) overlay.addEventListener('click', _closeMakimaSidebar);
  if (gearBtn) gearBtn.addEventListener('click', _toggleVoiceDropdown);

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

  if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    if (window.speechSynthesis.onvoiceschanged !== undefined) {
      window.speechSynthesis.onvoiceschanged = function() {
        window.speechSynthesis.getVoices();
      };
    }
  }
}

/* == SIDEBAR TOGGLE == */

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

/* == VOICE/SETTINGS DROPDOWN == */

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

  // Settings panel
  html += '<div class="makima-settings-panel">';
  html += '<div class="makima-voice-dropdown-title" style="margin-top:8px;border-top:1px solid rgba(204,0,0,0.15);padding-top:8px;">AI MODE</div>';

  // Segmented control
  html += '<div class="makima-mode-selector">';
  var modes = ['auto', 'gemini', 'groq'];
  var modeLabels = ['AUTO', 'GEMINI', 'GROQ'];
  for (var m = 0; m < modes.length; m++) {
    var mActive = (_makimaProvider === modes[m]) ? ' active' : '';
    html += '<button class="makima-mode-btn' + mActive + '" data-provider="' + modes[m] + '">' + modeLabels[m] + '</button>';
  }
  html += '</div>';

  // Model selector
  var models = _makimaModelOptions[_makimaProvider] || _makimaModelOptions.auto;
  html += '<select class="makima-model-select" id="makimaModelSelect">';
  for (var mi = 0; mi < models.length; mi++) {
    var sel = (models[mi] === _makimaModel) ? ' selected' : '';
    html += '<option value="' + models[mi] + '"' + sel + '>' + models[mi] + '</option>';
  }
  html += '</select>';

  // Save button
  html += '<button class="makima-save-model-btn" id="makimaSaveModelBtn">SAVE MODEL</button>';
  html += '</div>';

  // Security section
  html += '<div class="makima-voice-dropdown-title" style="margin-top:8px;border-top:1px solid rgba(204,0,0,0.15);padding-top:8px;">Security</div>';
  html += '<button class="makima-voice-opt makima-lock-btn" id="makimaLockBtn">LOCK</button>';
  dropdown.innerHTML = html;

  // Bind voice buttons
  var btns = dropdown.querySelectorAll('.makima-voice-opt:not(.makima-lock-btn)');
  for (var j = 0; j < btns.length; j++) {
    btns[j].addEventListener('click', function() {
      var voice = this.getAttribute('data-voice');
      _setVoiceSetting(voice);
      var allBtns = dropdown.querySelectorAll('.makima-voice-opt:not(.makima-lock-btn)');
      for (var k = 0; k < allBtns.length; k++) allBtns[k].classList.remove('active');
      this.classList.add('active');
    });
  }

  // Bind mode buttons
  var modeBtns = dropdown.querySelectorAll('.makima-mode-btn');
  for (var mb = 0; mb < modeBtns.length; mb++) {
    modeBtns[mb].addEventListener('click', function() {
      var newProvider = this.getAttribute('data-provider');
      _makimaProvider = newProvider;
      // Update model to first of new provider
      var newModels = _makimaModelOptions[newProvider] || _makimaModelOptions.auto;
      _makimaModel = newModels[0];
      _renderVoiceDropdown();
    });
  }

  // Bind save button
  var saveBtn = document.getElementById('makimaSaveModelBtn');
  if (saveBtn) {
    saveBtn.addEventListener('click', function() {
      var selectEl = document.getElementById('makimaModelSelect');
      if (selectEl) _makimaModel = selectEl.value;
      _saveProviderSettings();
      _showMakimaToast('MODEL SAVED');
    });
  }

  // Bind lock button
  var lockBtn = document.getElementById('makimaLockBtn');
  if (lockBtn) {
    lockBtn.addEventListener('click', function() {
      _lockMakimaAI();
    });
  }
}

/* == TOAST NOTIFICATION == */

function _showMakimaToast(msg) {
  var existing = document.getElementById('makimaToast');
  if (existing && existing.parentNode) existing.parentNode.removeChild(existing);

  var toast = document.createElement('div');
  toast.className = 'makima-toast';
  toast.id = 'makimaToast';
  toast.textContent = msg;
  document.body.appendChild(toast);

  setTimeout(function() {
    toast.classList.add('fade-out');
    setTimeout(function() {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 400);
  }, 2000);
}

/* == SIDEBAR LIST RENDER == */

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

/* == CHAT AREA RENDER == */

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

/* == MESSAGE BUBBLES == */

function _renderMarkdown(text) {
  // Escape HTML entities first to prevent XSS
  text = text.replace(/&/g, '&amp;')
             .replace(/</g, '&lt;')
             .replace(/>/g, '&gt;')
             .replace(/"/g, '&quot;')
             .replace(/'/g, '&#039;');
  // Convert **bold** to <strong>
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Convert *italic* to <em>
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Convert `code` to <code>
  text = text.replace(/`(.+?)`/g, '<code>$1</code>');
  // Convert newlines to <br>
  text = text.replace(/\n/g, '<br>');
  return text;
}

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
  avatar.className = 'makima-msg-avatar makima-avatar-protected protected-img';
  avatar.src = _makimaAvatarSrc;
  avatar.alt = 'MAKIMA AI';
  avatar.draggable = false;
  avatar.setAttribute('oncontextmenu', 'return false');
  avatar.setAttribute('ondragstart', 'return false');

  var bubble = document.createElement('div');
  bubble.className = 'makima-msg makima-msg-ai';
  bubble.innerHTML = _renderMarkdown(text);

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

/* == TTS (SPEECH) == */

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

/* == LOADING BUBBLE == */

function _showLoadingBubble(container) {
  var row = document.createElement('div');
  row.className = 'makima-msg-row makima-msg-row-ai';
  row.id = 'makimaLoadingRow';

  var avatar = document.createElement('img');
  avatar.className = 'makima-msg-avatar makima-avatar-protected protected-img';
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

/* == COOLDOWN HELPER == */

function _startCooldown() {
  _makimaCooldownActive = true;
  var btn = document.getElementById('makimaSendBtn');
  if (btn) btn.disabled = true;
  setTimeout(function() {
    _makimaCooldownActive = false;
    var btn = document.getElementById('makimaSendBtn');
    if (btn && !_makimaRequestInProgress) btn.disabled = false;
  }, 5000);
}

/* == SEND MESSAGE == */

function sendMakimaMessage() {
  var input = document.getElementById('makimaInput');
  var messagesEl = document.getElementById('makimaMessages');
  var errorEl = document.getElementById('makimaError');
  var sendBtn = document.getElementById('makimaSendBtn');

  if (!input || !messagesEl || !errorEl) return;

  var message = input.value.trim();
  errorEl.textContent = '';

  if (!message) {
    errorEl.textContent = 'Pesan tidak boleh kosong.';
    return;
  }

  if (_makimaCooldownActive) {
    errorEl.textContent = 'Tunggu beberapa detik sebelum mengirim lagi.';
    return;
  }

  if (_makimaRequestInProgress) {
    errorEl.textContent = 'Tunggu respons sebelumnya.';
    return;
  }

  var provider = _makimaProvider || 'auto';
  var model = _makimaModel || 'gemini-2.0-flash';
  console.log('[MAKIMA] AI REQUEST ONLY FROM SEND', { provider: provider, model: model });

  var chat = getActiveChat();
  if (!chat) {
    chat = createNewChat();
    _renderSidebarList();
  }

  _makimaRequestInProgress = true;
  if (sendBtn) sendBtn.disabled = true;

  _appendUserBubble(messagesEl, message);

  var historyToSend = chat.messages.slice(-20);

  chat.messages.push({ role: 'user', text: message, createdAt: new Date().toISOString() });

  if (chat.title === 'Chat baru') {
    chat.title = message.substring(0, 30);
    _renderSidebarList();
  }

  chat.updatedAt = new Date().toISOString();

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

  _showLoadingBubble(messagesEl);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  var targetChatId = chat.id;

  fetch('/api/ai-chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: message,
      history: historyToSend,
      password: sessionStorage.getItem('makima_ai_password') || '',
      provider: provider,
      model: model
    })
  })
  .then(function(res) {
    return res.json().then(function(data) {
      return { status: res.status, data: data };
    });
  })
  .then(function(result) {
    _removeLoadingBubble();
    _makimaRequestInProgress = false;

    if (result.data.reply) {
      _appendAIBubble(messagesEl, result.data.reply);

      var allChats = loadChats();
      var targetChat = null;
      for (var j = 0; j < allChats.length; j++) {
        if (allChats[j].id === targetChatId) {
          targetChat = allChats[j];
          break;
        }
      }
      if (targetChat) {
        targetChat.messages.push({ role: 'assistant', text: result.data.reply, createdAt: new Date().toISOString() });
        targetChat.updatedAt = new Date().toISOString();
        allChats = _enforceStorageCaps(allChats);
        saveChats(allChats);
      }

      messagesEl.scrollTop = messagesEl.scrollHeight;
    } else if (result.data.error) {
      var errMsg = '';
      if (result.status === 429) {
        errMsg = result.data.error || 'KUOTA SEDANG HABIS. COBA LAGI NANTI.';
      } else if (result.status === 503) {
        errMsg = result.data.error || 'API PROVIDER BELUM DIKONFIGURASI.';
      } else if (result.status === 403) {
        errMsg = 'MAKIMA AI KHUSUS ADMIN.';
        _appendAIBubble(messagesEl, errMsg);
        var allChats403 = loadChats();
        var targetChat403 = null;
        for (var j3 = 0; j3 < allChats403.length; j3++) {
          if (allChats403[j3].id === targetChatId) {
            targetChat403 = allChats403[j3];
            break;
          }
        }
        if (targetChat403) {
          targetChat403.messages.push({ role: 'assistant', text: errMsg, createdAt: new Date().toISOString() });
          targetChat403.updatedAt = new Date().toISOString();
          allChats403 = _enforceStorageCaps(allChats403);
          saveChats(allChats403);
        }
        messagesEl.scrollTop = messagesEl.scrollHeight;
        _lockMakimaAI();
        _startCooldown();
        return;
      } else {
        errMsg = result.data.error || 'MAKIMA AI SEDANG TIDAK BISA MERESPONS. COBA LAGI NANTI.';
      }
      _appendAIBubble(messagesEl, errMsg);
      var allChatsErr = loadChats();
      var targetChatErr = null;
      for (var j2 = 0; j2 < allChatsErr.length; j2++) {
        if (allChatsErr[j2].id === targetChatId) {
          targetChatErr = allChatsErr[j2];
          break;
        }
      }
      if (targetChatErr) {
        targetChatErr.messages.push({ role: 'assistant', text: errMsg, createdAt: new Date().toISOString() });
        targetChatErr.updatedAt = new Date().toISOString();
        allChatsErr = _enforceStorageCaps(allChatsErr);
        saveChats(allChatsErr);
      }
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    _startCooldown();
  })
  .catch(function() {
    _removeLoadingBubble();
    _makimaRequestInProgress = false;
    var errMsg = 'MAKIMA AI SEDANG TIDAK BISA MERESPONS. COBA LAGI NANTI.';
    _appendAIBubble(messagesEl, errMsg);
    var allChatsCatch = loadChats();
    var targetChatCatch = null;
    for (var jc = 0; jc < allChatsCatch.length; jc++) {
      if (allChatsCatch[jc].id === targetChatId) {
        targetChatCatch = allChatsCatch[jc];
        break;
      }
    }
    if (targetChatCatch) {
      targetChatCatch.messages.push({ role: 'assistant', text: errMsg, createdAt: new Date().toISOString() });
      targetChatCatch.updatedAt = new Date().toISOString();
      allChatsCatch = _enforceStorageCaps(allChatsCatch);
      saveChats(allChatsCatch);
    }
    messagesEl.scrollTop = messagesEl.scrollHeight;

    _startCooldown();
  });
}

/* == UTILS == */

function _escapeHtml(str) {
  var div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

/* == CUSTOM CONFIRM MODAL == */

var _makimaConfirmEscHandler = null;

function _showClearConfirmModal() {
  _closeClearConfirmModal();

  var overlay = document.createElement('div');
  overlay.className = 'makima-confirm-overlay';
  overlay.id = 'makimaConfirmOverlay';

  var modal = document.createElement('div');
  modal.className = 'makima-confirm-modal';

  var title = document.createElement('div');
  title.className = 'makima-confirm-title';
  title.textContent = 'HAPUS SEMUA CHAT?';

  var text = document.createElement('div');
  text.className = 'makima-confirm-text';
  text.textContent = 'Semua riwayat chat lokal akan dihapus dari perangkat ini.';

  var actions = document.createElement('div');
  actions.className = 'makima-confirm-actions';

  var cancelBtn = document.createElement('button');
  cancelBtn.className = 'makima-confirm-btn-cancel';
  cancelBtn.textContent = 'BATAL';
  cancelBtn.addEventListener('click', function() {
    _closeClearConfirmModal();
  });

  var deleteBtn = document.createElement('button');
  deleteBtn.className = 'makima-confirm-btn-delete';
  deleteBtn.textContent = 'HAPUS';
  deleteBtn.addEventListener('click', function() {
    clearAllChats();
    _closeClearConfirmModal();
  });

  actions.appendChild(cancelBtn);
  actions.appendChild(deleteBtn);

  modal.appendChild(title);
  modal.appendChild(text);
  modal.appendChild(actions);
  overlay.appendChild(modal);

  document.body.appendChild(overlay);

  overlay.addEventListener('click', function(e) {
    if (e.target === overlay) {
      _closeClearConfirmModal();
    }
  });

  _makimaConfirmEscHandler = function(e) {
    if (e.key === 'Escape') {
      _closeClearConfirmModal();
    }
  };
  document.addEventListener('keydown', _makimaConfirmEscHandler);
}

function _closeClearConfirmModal() {
  var overlay = document.getElementById('makimaConfirmOverlay');
  if (overlay && overlay.parentNode) {
    overlay.parentNode.removeChild(overlay);
  }
  if (_makimaConfirmEscHandler) {
    document.removeEventListener('keydown', _makimaConfirmEscHandler);
    _makimaConfirmEscHandler = null;
  }
}
