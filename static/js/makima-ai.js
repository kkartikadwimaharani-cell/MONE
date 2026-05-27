/* ── MAKIMA AI CHAT (ChatGPT-style) ──────────────── */

var _makimaChatHistory = [];
var _makimaAvatarSrc = '/static/img/makima-ai-profile.png';
var _makimaIsSpeaking = false;

function _loadMakimaHistory() {
  try {
    var stored = localStorage.getItem('makima_ai_chat_history');
    if (stored) {
      _makimaChatHistory = JSON.parse(stored);
    } else {
      _makimaChatHistory = [];
    }
  } catch (e) {
    _makimaChatHistory = [];
  }
}

function _saveMakimaHistory() {
  try {
    localStorage.setItem('makima_ai_chat_history', JSON.stringify(_makimaChatHistory));
  } catch (e) {
    // localStorage full or unavailable
  }
}

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
  } catch (e) {
    // ignore
  }
}

function renderMakimaAI() {
  var container = document.getElementById('viewMakimaAI');
  if (!container) return;

  _loadMakimaHistory();

  var voiceSetting = _getVoiceSetting();

  container.innerHTML =
    '<div class="makima-ai-page">' +
      '<button class="makima-ai-back-btn" onclick="showMainView()">&#8592; KEMBALI KE DOWNLOADER</button>' +
      '<div class="makima-ai-header">' +
        '<img src="' + _makimaAvatarSrc + '" alt="MAKIMA AI" class="makima-ai-header-avatar" />' +
        '<h2 class="makima-ai-title">MAKIMA AI</h2>' +
        '<p class="makima-ai-subtitle">MII NETWORK CHARACTER ASSISTANT</p>' +
        '<span class="makima-ai-online-badge">ONLINE</span>' +
        '<button class="makima-clear-memory-btn" id="makimaClearMemoryBtn">CLEAR MEMORY</button>' +
        '<div class="makima-voice-settings" id="makimaVoiceSettings">' +
          '<span class="makima-voice-settings-label">Voice:</span>' +
          '<button class="makima-voice-option' + (voiceSetting === 'Kore' ? ' active' : '') + '" data-voice="Kore">Kore</button>' +
          '<button class="makima-voice-option' + (voiceSetting === 'Charon' ? ' active' : '') + '" data-voice="Charon">Charon</button>' +
          '<button class="makima-voice-option' + (voiceSetting === 'Aoede' ? ' active' : '') + '" data-voice="Aoede">Aoede</button>' +
          '<button class="makima-voice-option' + (voiceSetting === 'Sulafat' ? ' active' : '') + '" data-voice="Sulafat">Sulafat</button>' +
          '<button class="makima-voice-option' + (voiceSetting === 'Achernar' ? ' active' : '') + '" data-voice="Achernar">Achernar</button>' +
        '</div>' +
      '</div>' +
      '<div class="makima-ai-messages" id="makimaMessages"></div>' +
      '<div class="makima-ai-input-area">' +
        '<div class="makima-ai-input-wrap">' +
          '<input type="text" id="makimaInput" class="makima-ai-input" placeholder="Ketik pesan untuk MAKIMA AI..." autocomplete="off" autocorrect="off" spellcheck="false" />' +
          '<button class="makima-ai-send-btn" id="makimaSendBtn">SEND</button>' +
        '</div>' +
        '<p class="makima-ai-disclaimer">MAKIMA AI dapat membuat kesalahan. Periksa informasi penting.</p>' +
        '<div class="makima-ai-error" id="makimaError"></div>' +
      '</div>' +
    '</div>';

  // Bind events
  var inputEl = document.getElementById('makimaInput');
  var sendBtn = document.getElementById('makimaSendBtn');
  var clearBtn = document.getElementById('makimaClearMemoryBtn');

  if (inputEl) {
    inputEl.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') sendMakimaMessage();
    });
  }
  if (sendBtn) {
    sendBtn.addEventListener('click', sendMakimaMessage);
  }
  if (clearBtn) {
    clearBtn.addEventListener('click', _clearMakimaMemory);
  }

  // Bind voice settings
  var voiceButtons = document.querySelectorAll('.makima-voice-option');
  for (var i = 0; i < voiceButtons.length; i++) {
    voiceButtons[i].addEventListener('click', function() {
      var voice = this.getAttribute('data-voice');
      _setVoiceSetting(voice);
      var allBtns = document.querySelectorAll('.makima-voice-option');
      for (var j = 0; j < allBtns.length; j++) {
        allBtns[j].classList.remove('active');
      }
      this.classList.add('active');
    });
  }

  // Restore chat history
  _restoreMakimaHistory();
}

function _clearMakimaMemory() {
  _makimaChatHistory = [];
  try {
    localStorage.removeItem('makima_ai_chat_history');
  } catch (e) {
    // ignore
  }
  var messagesEl = document.getElementById('makimaMessages');
  if (messagesEl) {
    messagesEl.innerHTML = '';
  }
  // Stop any ongoing speech
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
  _makimaIsSpeaking = false;
}

function _restoreMakimaHistory() {
  if (_makimaChatHistory.length === 0) return;
  var messagesEl = document.getElementById('makimaMessages');
  if (!messagesEl) return;

  for (var i = 0; i < _makimaChatHistory.length; i++) {
    var entry = _makimaChatHistory[i];
    if (entry.role === 'user') {
      _appendUserBubble(messagesEl, entry.text);
    } else {
      _appendAIBubble(messagesEl, entry.text);
    }
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
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
  avatar.className = 'makima-msg-avatar';
  avatar.src = _makimaAvatarSrc;
  avatar.alt = 'MAKIMA AI';

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

function _speakMakimaText(text, btn) {
  if (!window.speechSynthesis) return;

  // If already speaking, stop
  if (window.speechSynthesis.speaking) {
    window.speechSynthesis.cancel();
    _makimaIsSpeaking = false;
    // Remove speaking class from all buttons
    var allSpeakerBtns = document.querySelectorAll('.makima-speaker-btn.speaking');
    for (var i = 0; i < allSpeakerBtns.length; i++) {
      allSpeakerBtns[i].classList.remove('speaking');
      allSpeakerBtns[i].innerHTML = '&#128264;';
    }
    return;
  }

  var utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'id-ID';
  utterance.rate = 0.95;
  utterance.pitch = 0.9;

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

function _showLoadingBubble(container) {
  var row = document.createElement('div');
  row.className = 'makima-msg-row makima-msg-row-ai';
  row.id = 'makimaLoadingRow';

  var avatar = document.createElement('img');
  avatar.className = 'makima-msg-avatar';
  avatar.src = _makimaAvatarSrc;
  avatar.alt = 'MAKIMA AI';

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

  // Display user message
  _appendUserBubble(messagesEl, message);

  // Prepare history to send (last 20 messages before current)
  var historyToSend = _makimaChatHistory.slice(-20);

  // Add to local history
  _makimaChatHistory.push({ role: 'user', text: message });
  _saveMakimaHistory();

  input.value = '';
  messagesEl.scrollTop = messagesEl.scrollHeight;

  // Show loading
  _showLoadingBubble(messagesEl);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  // Send to API
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
      _makimaChatHistory.push({ role: 'assistant', text: result.data.reply });
      _saveMakimaHistory();
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
