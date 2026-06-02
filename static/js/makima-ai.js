// ============================================================
// MAKIMA AI — Clean Chat (Claude-style UI + ElevenLabs TTS)
// ============================================================

(function () {
  'use strict';

  let chatHistory = [];
  let isTyping    = false;
  let currentAudio = null;
  let currentSpeakerBtn = null;

  // ── Build UI ───────────────────────────────────────────────
  function renderUI() {
    const wrap = document.getElementById('viewMakimaAI');
    if (!wrap) return;

    wrap.innerHTML = `
      <div class="mkai-wrap">

        <!-- Header -->
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

        <!-- Messages -->
        <div class="mkai-messages" id="mkaiMessages">
          ${welcomeHTML()}
        </div>

        <!-- Typing indicator -->
        <div class="mkai-typing-row" id="mkaiTyping">
          <img class="mkai-typing-avatar" src="/static/img/makima-ai-profile.png" alt="">
          <div class="mkai-dots">
            <span class="mkai-dot"></span>
            <span class="mkai-dot"></span>
            <span class="mkai-dot"></span>
          </div>
        </div>

        <!-- Input -->
        <div class="mkai-input-area">
          <div class="mkai-input-inner">
            <textarea id="mkaiInput" class="mkai-textarea" rows="1"
              placeholder="Ketik pesan..." maxlength="4000"></textarea>
            <button class="mkai-send-btn" id="mkaiSend" title="Kirim">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
                   stroke-linecap="round" stroke-linejoin="round" width="16" height="16">
                <line x1="22" y1="2" x2="11" y2="13"/>
                <polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            </button>
          </div>
          <div class="mkai-input-hint">Enter kirim &bull; Shift+Enter baris baru</div>
        </div>

      </div>
    `;

    // Events
    document.getElementById('mkaiSend').addEventListener('click', send);
    document.getElementById('mkaiClear').addEventListener('click', clearChat);
    document.getElementById('mkaiBack').addEventListener('click', goBackToDashboard);
    const ta = document.getElementById('mkaiInput');
    ta.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
    ta.addEventListener('input', function () {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 160) + 'px';
    });
  }

  function welcomeHTML() {
    return `
      <div class="mkai-welcome">
        <img src="/static/img/makima-ai-profile.png" alt="MAKIMA AI"
             draggable="false" oncontextmenu="return false">
        <div class="mkai-welcome-title">Tanyakan apapun.</div>
        <div class="mkai-welcome-hint">Aku siap membantu.</div>
      </div>`;
  }

  // ── Send ───────────────────────────────────────────────────
  function send() {
    if (isTyping) return;
    const ta   = document.getElementById('mkaiInput');
    const text = ta.value.trim();
    if (!text) return;

    ta.value = '';
    ta.style.height = 'auto';

    appendUser(text);
    chatHistory.push({ role: 'user', text });

    isTyping = true;
    setTyping(true);
    setSendDisabled(true);

    const model    = document.getElementById('mkaiModel').value;
    const provider = model === 'auto' ? 'auto'
                   : model.startsWith('gemini') ? 'gemini' : 'groq';

    fetch('/api/ai-chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history: chatHistory.slice(-20),
        model,
        provider
      })
    })
    .then(r => r.json())
    .then(data => {
      setTyping(false);
      isTyping = false;
      setSendDisabled(false);
      const reply = data.reply || data.error || 'Terjadi kesalahan. Coba lagi.';
      const isErr = !data.reply;
      chatHistory.push({ role: 'assistant', text: reply });
      appendAI(reply, isErr);
    })
    .catch(() => {
      setTyping(false);
      isTyping = false;
      setSendDisabled(false);
      appendAI('Koneksi bermasalah. Coba lagi.', true);
    });
  }

  // ── Append User ────────────────────────────────────────────
  function appendUser(text) {
    removeWelcome();
    const el = document.createElement('div');
    el.className = 'mkai-msg mkai-msg-user';
    el.innerHTML = `<div class="mkai-bubble-user">${escHtml(text)}</div>`;
    msgs().appendChild(el);
    scrollDown();
  }

  // ── Append AI ──────────────────────────────────────────────
  function appendAI(text, isErr = false) {
    removeWelcome();
    const el = document.createElement('div');
    el.className = 'mkai-msg mkai-msg-ai';

    const bodyHTML = isErr
      ? `<div class="mkai-ai-text error">${escHtml(text)}</div>`
      : `<div class="mkai-ai-text">${renderMarkdown(text)}</div>`;

    el.innerHTML = `
      <div class="mkai-ai-row">
        <img class="mkai-ai-avatar" src="/static/img/makima-ai-profile.png" alt=""
             draggable="false" oncontextmenu="return false">
        <div class="mkai-ai-body">
          <div class="mkai-ai-sender">MAKIMA AI</div>
          ${bodyHTML}
        </div>
      </div>
      ${!isErr ? `
      <div class="mkai-msg-actions">
        <button class="mkai-action-btn speaker" data-msg="${encodeURIComponent(text)}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
               stroke-linecap="round" width="13" height="13">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>
          </svg>
          <span>Dengarkan</span>
        </button>
        <button class="mkai-action-btn copy" data-msg="${encodeURIComponent(text)}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
               stroke-linecap="round" width="13" height="13">
            <rect x="9" y="9" width="13" height="13" rx="2"/>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
          </svg>
          <span>Salin</span>
        </button>
      </div>` : ''}
    `;

    msgs().appendChild(el);

    // Bind buttons
    const spk = el.querySelector('.mkai-action-btn.speaker');
    if (spk) spk.addEventListener('click', handleSpeak);

    const cpy = el.querySelector('.mkai-action-btn.copy');
    if (cpy) cpy.addEventListener('click', handleCopy);

    // Bind inline code-copy buttons
    el.querySelectorAll('.mkai-code-copy').forEach(btn => {
      btn.addEventListener('click', function () {
        navigator.clipboard.writeText(decodeURIComponent(this.dataset.code))
          .then(() => { this.textContent = 'Disalin!'; setTimeout(() => { this.textContent = 'Salin'; }, 1500); });
      });
    });

    scrollDown();
  }

  // ── Speaker / TTS ──────────────────────────────────────────
  function handleSpeak(e) {
    const btn  = e.currentTarget;
    const text = decodeURIComponent(btn.dataset.msg);

    if (currentSpeakerBtn === btn && currentAudio) {
      stopAudio(); return;
    }

    stopAudio();
    currentSpeakerBtn = btn;
    btn.classList.add('loading');
    btn.querySelector('span').textContent = 'Memuat...';

    fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    })
    .then(r => { if (!r.ok) throw new Error('tts-unavailable'); return r.blob(); })
    .then(blob => {
      const url  = URL.createObjectURL(blob);
      currentAudio = new Audio(url);
      btn.classList.remove('loading');
      btn.classList.add('playing');
      btn.querySelector('span').textContent = 'Stop';
      const playPromise = currentAudio.play();
      if (playPromise && typeof playPromise.catch === 'function') {
        playPromise.catch(() => fallbackSpeak(text, btn));
      }
      currentAudio.onended = () => {
        btn.classList.remove('playing');
        btn.querySelector('span').textContent = 'Dengarkan';
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
    btn.classList.remove('loading');

    if (!('speechSynthesis' in window) || typeof SpeechSynthesisUtterance === 'undefined') {
      btn.querySelector('span').textContent = 'Gagal';
      currentSpeakerBtn = null;
      setTimeout(() => { btn.querySelector('span').textContent = 'Dengarkan'; }, 2000);
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'id-ID';
    utterance.rate = 0.95;
    utterance.pitch = 1;
    currentAudio = { pause: () => window.speechSynthesis.cancel() };
    btn.classList.add('playing');
    btn.querySelector('span').textContent = 'Stop';

    utterance.onend = utterance.onerror = () => {
      btn.classList.remove('playing', 'loading');
      btn.querySelector('span').textContent = 'Dengarkan';
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
      const s = currentSpeakerBtn.querySelector('span');
      if (s) s.textContent = 'Dengarkan';
      currentSpeakerBtn = null;
    }
  }

  // ── Copy ───────────────────────────────────────────────────
  function handleCopy(e) {
    const btn  = e.currentTarget;
    const text = decodeURIComponent(btn.dataset.msg);
    navigator.clipboard.writeText(text).then(() => {
      btn.querySelector('span').textContent = 'Disalin!';
      setTimeout(() => { btn.querySelector('span').textContent = 'Salin'; }, 1500);
    });
  }

  // ── Clear ──────────────────────────────────────────────────
  function clearChat() {
    chatHistory = [];
    stopAudio();
    msgs().innerHTML = welcomeHTML();
  }

  function goBackToDashboard() {
    stopAudio();
    if (typeof window.showMainView === 'function') {
      window.showMainView();
    } else if (typeof window.navigateTo === 'function') {
      window.navigateTo('downloader');
    }
  }

  // ── Helpers ────────────────────────────────────────────────
  function msgs()  { return document.getElementById('mkaiMessages'); }
  function scrollDown() { const m = msgs(); if (m) setTimeout(() => m.scrollTop = m.scrollHeight, 40); }
  function removeWelcome() { const w = document.querySelector('.mkai-welcome'); if (w) w.remove(); }
  function setTyping(v) { const t = document.getElementById('mkaiTyping'); if (t) t.classList.toggle('visible', v); if (v) scrollDown(); }
  function setSendDisabled(v) { const b = document.getElementById('mkaiSend'); if (b) b.disabled = v; }

  function escHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function renderMarkdown(text) {
    // Code blocks
    text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
      const escaped = escHtml(code.trim());
      const encoded = encodeURIComponent(code.trim());
      return `<div class="mkai-code-block">
        <div class="mkai-code-header">
          <span class="mkai-code-lang">${lang || 'code'}</span>
          <button class="mkai-code-copy" data-code="${encoded}">Salin</button>
        </div>
        <pre><code>${escaped}</code></pre>
      </div>`;
    });
    // Inline code
    text = text.replace(/`([^`\n]+)`/g, '<code>$1</code>');
    // Bold
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Italic
    text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
    // Newlines
    text = text.replace(/\n/g, '<br>');
    return text;
  }

  // ── Init ───────────────────────────────────────────────────
  function tryRender() {
    const c = document.getElementById('viewMakimaAI');
    if (c && c.style.display !== 'none' && !c.querySelector('.mkai-wrap')) renderUI();
  }

  function init() {
    const c = document.getElementById('viewMakimaAI');
    if (!c) return;

    new MutationObserver(tryRender).observe(c, { attributes: true, attributeFilter: ['style'] });
    tryRender();

    document.addEventListener('click', e => {
      if (e.target.closest('[data-view="makima-ai"]')) setTimeout(tryRender, 60);
    });
  }

  window.renderMakimaAI = tryRender;

  document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', init)
    : init();

})();
