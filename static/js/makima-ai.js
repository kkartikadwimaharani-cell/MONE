/* ── MAKIMA AI CHAT ─────────────────────────────── */

function renderMakimaAI() {
  var container = document.getElementById('viewMakimaAI');
  if (!container) return;
  container.innerHTML = '<div class="makima-ai-page">' +
    '<div class="makima-ai-header">' +
      '<h2 class="makima-ai-title">MAKIMA AI</h2>' +
      '<p class="makima-ai-subtitle">AI CHARACTER ASSISTANT</p>' +
    '</div>' +
    '<div class="makima-ai-chat-container">' +
      '<div class="makima-ai-messages" id="makimaMessages"></div>' +
      '<div class="makima-ai-input-area">' +
        '<div class="makima-ai-input-wrap">' +
          '<input type="text" id="makimaInput" class="makima-ai-input" placeholder="Ketik pesan..." autocomplete="off" autocorrect="off" spellcheck="false" onkeydown="if(event.key===\'Enter\')sendMakimaMessage()" />' +
          '<button class="makima-ai-send-btn" onclick="sendMakimaMessage()">SEND</button>' +
        '</div>' +
        '<div class="makima-ai-error" id="makimaError"></div>' +
      '</div>' +
    '</div>' +
    '<button class="coming-soon-btn" onclick="showMainView()" style="margin-top:24px;">BACK TO DOWNLOADER</button>' +
  '</div>';
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
  var userBubble = document.createElement('div');
  userBubble.className = 'makima-msg makima-msg-user';
  userBubble.textContent = message;
  messagesEl.appendChild(userBubble);

  input.value = '';
  messagesEl.scrollTop = messagesEl.scrollHeight;

  // Show loading
  var loadingBubble = document.createElement('div');
  loadingBubble.className = 'makima-msg makima-msg-ai makima-msg-loading';
  loadingBubble.textContent = 'Makima sedang mengetik...';
  messagesEl.appendChild(loadingBubble);
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
    // Remove loading bubble
    if (loadingBubble.parentNode) {
      loadingBubble.parentNode.removeChild(loadingBubble);
    }

    if (result.status === 429) {
      errorEl.textContent = result.data.error || 'Terlalu cepat, coba lagi.';
      return;
    }

    if (result.data.reply) {
      var aiBubble = document.createElement('div');
      aiBubble.className = 'makima-msg makima-msg-ai';
      aiBubble.textContent = result.data.reply;
      messagesEl.appendChild(aiBubble);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    } else if (result.data.error) {
      errorEl.textContent = result.data.error;
    }
  })
  .catch(function() {
    // Remove loading bubble
    if (loadingBubble.parentNode) {
      loadingBubble.parentNode.removeChild(loadingBubble);
    }
    errorEl.textContent = 'Gagal menghubungi server. Coba lagi.';
  });
}
