
function i18nText(key, vars) {
  return (window.t && window.t(key, vars)) || key;
}

function extractTikTokUrl(text) {
  if (!text) return '';
  var matches = String(text).match(/https?:\/\/[^\s<>()"']+/gi) || [];
  for (var i = 0; i < matches.length; i++) {
    var url = matches[i].replace(/[\]\),.;!?]+$/g, '');
    if (/(^|\.)((www|m)\.)?tiktok\.com/i.test(new URLSafeHost(url)) || /(^|\.)(vt|vm)\.tiktok\.com/i.test(new URLSafeHost(url))) {
      return url;
    }
    if (/tiktok\.com/i.test(url) || /https?:\/\/(vt|vm)\.tiktok\.com/i.test(url)) return url;
  }
  return '';
}

function URLSafeHost(url) {
  try { return new URL(url).hostname; } catch (e) { return ''; }
}

function normalizeTikTokInput(showError) {
  var input = document.getElementById('urlInput');
  if (!input) return '';
  var raw = input.value.trim();
  if (!raw) {
    if (showError) setStatus(i18nText('paste_tiktok_link_first'), 'err');
    return '';
  }
  var extracted = extractTikTokUrl(raw);
  if (!extracted) {
    if (showError) setStatus(i18nText('paste_valid_tiktok_link'), 'err');
    return '';
  }
  if (raw !== extracted) input.value = extracted;
  var clearBtn = document.getElementById('clearBtn');
  if (clearBtn) clearBtn.classList.toggle('visible', extracted.length > 0);
  return extracted;
}

async function pasteTikTokFromClipboard() {
  try {
    if (!navigator.clipboard || !navigator.clipboard.readText) {
      setStatus(i18nText('clipboard_unavailable'), 'err');
      return;
    }
    var text = await navigator.clipboard.readText();
    var url = extractTikTokUrl(text);
    if (!url) {
      setStatus(i18nText('clipboard_empty'), 'err');
      return;
    }
    var input = document.getElementById('urlInput');
    if (input) input.value = url;
    setStatus('', '');
    onUrlInput();
  } catch (e) {
    setStatus(i18nText('clipboard_unavailable'), 'err');
  }
}


function downloadButtonHtml(key) {
  var icon = key === 'fetch_photos'
    ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" width="16" height="16" style="margin-right:8px; vertical-align:middle;"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>'
    : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" width="16" height="16" style="margin-right:8px; vertical-align:middle;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';
  return icon + '<span data-i18n="' + key + '">' + i18nText(key) + '</span>';
}

function refreshDownloaderLanguage() {
  var dlBtn = document.getElementById('dlBtn');
  if (dlBtn) dlBtn.innerHTML = downloadButtonHtml(isPhotoMode ? 'fetch_photos' : 'download');
  var qualityBadge = document.getElementById('qualityBadge');
  if (qualityBadge && selectedQuality === 'best' && !previewData) qualityBadge.textContent = 'BEST';
  if (typeof updatePhotoCount === 'function' && photoUrls && photoUrls.length) updatePhotoCount(photoUrls.length);
}

/* ── MAIN ORCHESTRATION ────────────────────────── */

function setQuality(el, q) {
  isDownloading = false;
  // Clear status and photo section on tab switch
  setStatus('', '');
  document.getElementById('photoSection').style.display = 'none';
  document.getElementById('photoCarousel').innerHTML = '';
  document.getElementById('photoCount').textContent = '';
  document.getElementById('downloadAllBtn').style.display = 'none';
  photoUrls = [];
  document.querySelectorAll('.q-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  selectedQuality = q;

  const dlBtn = document.getElementById('dlBtn');
  const dlWrap = document.getElementById('dlWrap');
  const qualityBadge = document.getElementById('qualityBadge');

  if (q === 'photo') {
    isPhotoMode = true;
    hidePreview();
    dlWrap.style.display = '';
    if (qualityBadge) qualityBadge.style.display = 'none';
    // Change button to FETCH PHOTOS mode
    dlBtn.innerHTML = downloadButtonHtml('fetch_photos');
    dlBtn.onclick = function() {
      var url = normalizeTikTokInput(true);
      if (!url) return;
      fetchPhotos(url);
    };
  } else {
    isPhotoMode = false;
    dlWrap.style.display = '';
    // Update quality badge text
    if (qualityBadge) {
      qualityBadge.style.display = '';
      if (q === 'best' && previewData) {
        qualityBadge.textContent = getBestLabel(previewData);
      } else {
        qualityBadge.textContent = qualityLabel[q] || q.toUpperCase();
      }
    }
    // Restore button to DOWNLOAD mode
    dlBtn.innerHTML = downloadButtonHtml('download');
    dlBtn.onclick = function() { handleVideoDownload(); };
  }
}

function onUrlInput() {
  const input = document.getElementById('urlInput');
  var val = input.value.trim();
  var extracted = extractTikTokUrl(val);
  if (extracted && val !== extracted) {
    input.value = extracted;
    val = extracted;
  }
  const clearBtn = document.getElementById('clearBtn');
  clearBtn.classList.toggle('visible', val.length > 0);

  clearTimeout(previewTimer);
  setStatus('', '');

  if (val.length > 10 && (val.includes('tiktok.com') || val.includes('vt.tiktok') || val.includes('vm.tiktok'))) {
    if (!isPhotoMode && val !== lastPreviewUrl) {
      hidePreview();
      previewTimer = setTimeout(() => fetchPreview(val), 900);
    }
    // In photo mode, user clicks FETCH PHOTOS manually
  } else {
    hidePreview();
    lastPreviewUrl = null;
  }
}

function clearUrl() {
  document.getElementById('urlInput').value = '';
  document.getElementById('clearBtn').classList.remove('visible');
  clearTimeout(previewTimer);
  // Full state reset
  previewData = null;
  lastPreviewUrl = null;
  isDownloading = false;
  isDownloadingAudio = false;
  selectedQuality = 'best';
  // Reset quality buttons UI
  document.querySelectorAll('.q-btn').forEach(b => b.classList.remove('active'));
  document.querySelector('.q-btn').classList.add('active');
  // Reset quality badge
  var qualityBadge = document.getElementById('qualityBadge');
  if (qualityBadge) { qualityBadge.textContent = 'BEST'; qualityBadge.style.display = ''; }
  // Restore download button (in case it was in photo mode)
  isPhotoMode = false;
  var dlBtn = document.getElementById('dlBtn');
  dlBtn.innerHTML = downloadButtonHtml('download');
  dlBtn.onclick = function() { handleVideoDownload(); };
  dlBtn.disabled = false;
  // Hide preview and progress
  hidePreview();
  hideProgress();
  // Clear status
  setStatus('', '');
  // Hide photo section
  document.getElementById('photoSection').style.display = 'none';
  document.getElementById('photoCarousel').innerHTML = '';
  document.getElementById('photoCount').textContent = '';
  document.getElementById('downloadAllBtn').style.display = 'none';
  photoUrls = [];
}


document.addEventListener('mii:languagechange', function() {
  refreshDownloaderLanguage();
});
