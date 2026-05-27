/* ── MAKIMA AI CHAT (ChatGPT-style) ──────────────── */

var _makimaChatHistory = [];
var _makimaAvatarSrc = '/static/img/makima-ai-profile.png';

function renderMakimaAI() {
  var container = document.getElementById('viewMakimaAI');
  if (!container) return;

  container.innerHTML =
    '<div class="makima-ai-page">' +
      '<button class="makima-ai-back-btn" onclick="showMainView()">&#8592; BACK TO DOWNLOADER</button>' +
      '<div class="makima-ai-header">' +
        '<img src="' + _makimaAvatarSrc + '" alt="MAKIMA AI" class="makima-ai-header-avatar" />' +
        '<h2 class="makima-ai-title">MAKIMA AI</h2>' +
        '<p class="makima-ai-subtitle">MII NETWORK CHARACTER ASSISTANT</p>' +
      '</div>' +
      '<div class="makima-ai-messages" id="makimaMessages"></div>' +
      '<div class="makima-ai-input-area">' +
        '<div class="makima-ai-input-wrap">' +
          '<input type="text" id="makimaInput" class="makima-ai-input" placeholder="Ketik pesan..." autocomplete="off" autocorrect="off" spellcheck="false" />' +
          '<button class="makima-ai-send-btn" id="makimaSendBtn">SEND</button>' +
        '</div>' +
        '<div class="makima-ai-error" id="makimaError"></div>' +
      '</div>' +
    '</div>';

  // Bind events
  var inputEl = document.getElementById('makimaInput');
  var sendBtn = document.getElementById('makimaSendBtn');

  if (inputEl) {
    inputEl.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') sendMakimaMessage();
    });
  }
  if (sendBtn) {
    sendBtn.addEventListener('click', sendMakimaMessage);
  }

  // Restore chat history
  _restoreMakimaHistory();
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

  row.appendChild(avatar);
  row.appendChild(bubble);
  container.appendChild(row);
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
    '<span class="makima-msg-loading-text">MAKIMA AI sedang berpikir</span>' +
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
  _makimaChatHistory.push({ role: 'user', text: message });

  input.value = '';
  messagesEl.scrollTop = messagesEl.scrollHeight;

  // Show loading
  _showLoadingBubble(messagesEl);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  // Send to API
  fetch('/api/ai-chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: message })
  })
  .then(function(res) {
    return res.json().then(function(data) {
      return { status: res.status, data: data };
    });
  })
  .then(function(result) {
    _removeLoadingBubble();

    if (result.status === 429) {
      errorEl.textContent = result.data.error || 'Terlalu cepat, coba lagi.';
      return;
    }

    if (result.data.reply) {
      _appendAIBubble(messagesEl, result.data.reply);
      _makimaChatHistory.push({ role: 'ai', text: result.data.reply });
      messagesEl.scrollTop = messagesEl.scrollHeight;
    } else if (result.data.error) {
      _appendAIBubble(messagesEl, 'MAKIMA AI sedang tidak bisa merespons. Coba lagi nanti.');
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  })
  .catch(function() {
    _removeLoadingBubble();
    _appendAIBubble(messagesEl, 'MAKIMA AI sedang tidak bisa merespons. Coba lagi nanti.');
    messagesEl.scrollTop = messagesEl.scrollHeight;
  });
}
