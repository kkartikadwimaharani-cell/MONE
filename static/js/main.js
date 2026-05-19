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
    dlBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" width="16" height="16" style="margin-right:8px; vertical-align:middle;"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>FETCH PHOTOS';
    dlBtn.onclick = function() {
      var url = document.getElementById('urlInput').value.trim();
      if (!url) { setStatus('Paste TikTok link first.', 'err'); return; }
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
    dlBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" width="16" height="16" style="margin-right:8px; vertical-align:middle;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>DOWNLOAD';
    dlBtn.onclick = function() { handleVideoDownload(); };
  }
}

function onUrlInput() {
  const val = document.getElementById('urlInput').value.trim();
  const clearBtn = document.getElementById('clearBtn');
  clearBtn.classList.toggle('visible', val.length > 0);

  clearTimeout(previewTimer);
  setStatus('', '');

  if (val.length > 10 && (val.includes('tiktok.com') || val.includes('vt.tiktok'))) {
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
  dlBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" width="16" height="16" style="margin-right:8px; vertical-align:middle;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>DOWNLOAD';
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
