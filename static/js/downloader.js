/* ── DOWNLOADER ────────────────────────────────── */

function showProgress(percent) {
  var wrap = document.getElementById('spinnerWrap');
  if (!wrap) return;
  wrap.classList.add('show');
  var fill = document.getElementById('progressFill');
  var text = document.getElementById('progressText');
  if (fill) fill.style.width = percent + '%';
  if (text) text.textContent = percent + '%';
}

function hideProgress() {
  var wrap = document.getElementById('spinnerWrap');
  if (!wrap) return;
  wrap.classList.remove('show');
  var fill = document.getElementById('progressFill');
  var text = document.getElementById('progressText');
  if (fill) fill.style.width = '0%';
  if (text) text.textContent = '0%';
}

async function fetchPreview(url) {
  try {
    const fd = new FormData();
    fd.append('url', url);
    const res = await fetch('/preview', { method: 'POST', body: fd });
    const data = await res.json();
    if (data.error || !data.title) return;
    previewData = data;
    lastPreviewUrl = url;
    document.getElementById('previewTitle').textContent = data.title || '';
    document.getElementById('previewUploader').textContent = data.uploader ? '@' + data.uploader : '';
    if (data.duration) {
      const m = Math.floor(data.duration / 60);
      const s = data.duration % 60;
      document.getElementById('previewDuration').textContent = m + ':' + String(s).padStart(2,'0');
    }
    const thumb = document.getElementById('previewThumb');
    if (data.thumbnail) {
      thumb.src = data.thumbnail;
      thumb.classList.remove('preview-thumb-fallback');
      thumb.onerror = function() {
        thumb.classList.add('preview-thumb-fallback');
        thumb.alt = 'MII';
        thumb.src = '';
      };
    } else {
      thumb.classList.add('preview-thumb-fallback');
      thumb.alt = 'MII';
      thumb.src = '';
    }
    // Update BEST quality badge based on resolution metadata
    var qualityBadge = document.getElementById('qualityBadge');
    if (qualityBadge && selectedQuality === 'best') {
      qualityBadge.textContent = getBestLabel(data);
    }
    document.getElementById('previewCard').classList.add('show');
  } catch(e) {}
}

/* ── BEST LABEL HELPER ────────────────────────── */
function getBestLabel(data) {
  var height = data.height || data.resolution_height || 0;
  if (height >= 2160) return 'BEST 4K';
  if (height >= 1440) return 'BEST 2K';
  if (height >= 1080) return 'BEST 1080P';
  if (height >= 720) return 'BEST 720P';
  return 'BEST';
}

/* ── AUDIO DOWNLOAD (MP3 button only) ─────────── */

function handleAudioDownload(event) {
  if (event) {
    event.stopPropagation();
    event.preventDefault();
  }
  if (isDownloadingAudio) return;
  const url = document.getElementById('urlInput').value.trim();
  if (!url) {
    setStatus('Paste TikTok link first.', 'err');
    return;
  }
  isDownloadingAudio = true;
  var mp3Btn = document.getElementById('mp3Btn');
  if (mp3Btn) mp3Btn.classList.add('loading');
  setStatus('', '');

  // Use a local fake progress that only shows on the MP3 button text
  var audioPercent = 0;
  var audioProgressInterval = setInterval(function() {
    if (audioPercent < 90) {
      audioPercent += Math.floor(Math.random() * 8) + 2;
      if (audioPercent > 90) audioPercent = 90;
      if (mp3Btn) mp3Btn.textContent = audioPercent + '%';
    }
  }, 300);

  fetch('/download-audio', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: url })
  }).then(function(response) {
    if (!response.ok) {
      return response.json().then(function(errData) {
        throw new Error(errData.error || 'Audio belum bisa diproses. Coba video lain.');
      }).catch(function(e) {
        if (e.message) throw e;
        throw new Error('Audio belum bisa diproses. Coba video lain.');
      });
    }
    return response.blob();
  }).then(function(blob) {
    var blobUrl = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = blobUrl;
    a.download = 'miitok_audio.mp3';
    document.body.appendChild(a);
    a.click();
    setTimeout(function() {
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    }, 1000);
    if (mp3Btn) mp3Btn.textContent = '100%';
    setStatus('Audio download berhasil!', 'ok');
  }).catch(function(e) {
    setStatus(e.message || 'Audio belum bisa diproses. Coba video lain.', 'err');
  }).finally(function() {
    isDownloadingAudio = false;
    clearInterval(audioProgressInterval);
    setTimeout(function() {
      if (mp3Btn) {
        mp3Btn.classList.remove('loading');
        mp3Btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg> MP3';
      }
    }, 600);
  });
}

/* ── VIDEO DOWNLOAD (DOWNLOAD button only) ────── */

function handleVideoDownload() {
  openModal();
}

function openModal() {
  const url = document.getElementById('urlInput').value.trim();
  if (!url) {
    setStatus('Paste TikTok link first.', 'err');
    return;
  }
  // Populate modal info
  if (previewData) {
    document.getElementById('modalTitle').textContent = previewData.title || 'TikTok Video';
    document.getElementById('modalUploader').textContent = previewData.uploader ? '@' + previewData.uploader : '';
    const thumb = document.getElementById('modalThumb');
    if (previewData.thumbnail) {
      thumb.src = previewData.thumbnail;
      thumb.classList.add('show');
    } else {
      thumb.classList.remove('show');
    }
  } else {
    document.getElementById('modalTitle').textContent = 'TikTok Video';
    document.getElementById('modalUploader').textContent = '';
    document.getElementById('modalThumb').classList.remove('show');
  }
  // Pills
  const pills = document.getElementById('modalPills');
  pills.innerHTML = '';
  const qPill = document.createElement('span');
  qPill.className = 'pill highlight';
  qPill.textContent = qualityLabel[selectedQuality] || selectedQuality;
  pills.appendChild(qPill);
  const tPill = document.createElement('span');
  tPill.className = 'pill';
  tPill.textContent = typeLabel[selectedQuality] || 'MP4';
  pills.appendChild(tPill);

  document.getElementById('modalBackdrop').classList.add('show');
}

function closeModal() {
  document.getElementById('modalBackdrop').classList.remove('show');
}

function backdropClick(event) {
  if (event.target === document.getElementById('modalBackdrop')) {
    closeModal();
  }
}

function copyLink() {
  const url = document.getElementById('urlInput').value.trim();
  if (url) {
    navigator.clipboard.writeText(url).catch(() => {});
  }
  closeModal();
}

async function confirmDownload() {
  if (isDownloading) return;
  const url = document.getElementById('urlInput').value.trim();
  if (!url) {
    setStatus('Paste TikTok link first.', 'err');
    closeModal();
    return;
  }
  closeModal();
  trackEvent('download_click');
  isDownloading = true;
  const btn = document.getElementById('dlBtn');
  btn.disabled = true;
  setStatus('', '');

  showProgress(0);
  var progressInterval = setInterval(function() {
    var fill = document.getElementById('progressFill');
    if (!fill) return;
    var current = parseInt(fill.style.width) || 0;
    if (current < 90) {
      var next = current + Math.floor(Math.random() * 8) + 2;
      if (next > 90) next = 90;
      showProgress(next);
    }
  }, 300);

  try {
    const formData = new FormData();
    formData.append('url', url);
    formData.append('quality', selectedQuality);

    const response = await fetch('/download', {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      let errMsg = 'Download gagal.';
      try {
        const errData = await response.json();
        if (errData.error) errMsg = errData.error;
      } catch(e) {}
      setStatus(errMsg, 'err');
      hideProgress();
      return;
    }

    // Trigger file download
    const blob = await response.blob();
    if (!blob || blob.size <= 0) {
      setStatus('Download gagal, file kosong.', 'err');
      hideProgress();
      return;
    }
    const contentDisposition = response.headers.get('Content-Disposition') || '';
    let filename = 'miitok_video.mp4';
    const match = contentDisposition.match(/filename="?([^";\n]+)"?/);
    if (match) filename = match[1];
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    }, 1000);
    showProgress(100);
    setStatus('Download berhasil!', 'ok');
    trackEvent('download_success');

  } catch(e) {
    setStatus('Terjadi kesalahan, coba lagi.', 'err');
  } finally {
    isDownloading = false;
    btn.disabled = false;
    clearInterval(progressInterval);
    setTimeout(function() { hideProgress(); }, 600);
  }
}
