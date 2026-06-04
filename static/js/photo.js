/* ── PHOTO MODE ───────────────────────────────── */

function flattenPhotoItems(value, output) {
  if (!value) return output;
  if (typeof value === 'string') {
    output.push(value);
    return output;
  }
  if (Array.isArray(value)) {
    value.forEach(function(item) { flattenPhotoItems(item, output); });
    return output;
  }
  if (typeof value === 'object') {
    ['url', 'src', 'image', 'image_url', 'download_url', 'display_url', 'thumbnail'].forEach(function(key) {
      if (typeof value[key] === 'string') output.push(value[key]);
    });
    ['images', 'photos', 'image_urls', 'entries', 'media'].forEach(function(key) {
      if (value[key]) flattenPhotoItems(value[key], output);
    });
  }
  return output;
}

function extractPhotoUrls(data) {
  var photos = [];
  ['images', 'photos', 'image_urls', 'entries', 'media'].forEach(function(key) {
    if (data && data[key]) flattenPhotoItems(data[key], photos);
  });
  return photos.filter(function(url, index, arr) {
    return /^https?:\/\//i.test(url) && arr.indexOf(url) === index;
  });
}

async function fetchPhotos(url) {
  if (isDownloading) return;
  isDownloading = true;
  var spinner = document.getElementById('spinnerWrap');
  if (spinner) spinner.classList.add('show');
  var section = document.getElementById('photoSection');
  if (section) section.style.display = 'none';
  setStatus(i18nText('processing') + '...', 'ok');
  try {
    const fd = new FormData();
    fd.append('url', url);
    const res = await fetch('/photos', { method: 'POST', body: fd });
    let data = {};
    try { data = await res.json(); } catch (e) {}
    if (!res.ok || data.error || data.success === false) {
      setStatus(i18nText('no_photos_found'), 'err');
      return;
    }
    const photos = extractPhotoUrls(data);
    renderCarousel(photos, data.count || photos.length);
    if (photos.length) setStatus(i18nText('download_ready'), 'ok');

    if (data.title || data.uploader || data.thumbnail) {
      previewData = { title: data.title || '', uploader: data.uploader || '', thumbnail: data.thumbnail || null };
      document.getElementById('previewTitle').textContent = previewData.title;
      document.getElementById('previewUploader').textContent = previewData.uploader ? '@' + previewData.uploader : '';
      document.getElementById('previewDuration').textContent = '';
      if (previewData.thumbnail) document.getElementById('previewThumb').src = previewData.thumbnail;
      document.getElementById('previewCard').classList.add('show');
    }
  } catch(e) {
    setStatus(i18nText('generic_error'), 'err');
  } finally {
    isDownloading = false;
    if (spinner) spinner.classList.remove('show');
  }
}

function updatePhotoCount(count) {
  const countEl = document.getElementById('photoCount');
  if (!countEl) return;
  countEl.textContent = count > 0 ? i18nText('photos_found', { count: count }) : '';
}

function renderCarousel(photos, count) {
  if (!isPhotoMode) return;
  const carousel  = document.getElementById('photoCarousel');
  const dlAllBtn  = document.getElementById('downloadAllBtn');
  const section   = document.getElementById('photoSection');
  if (!carousel || !dlAllBtn || !section) return;
  carousel.innerHTML = '';
  if (!photos || !photos.length) {
    photoUrls = [];
    setStatus(i18nText('no_photos_found'), 'err');
    updatePhotoCount(0);
    dlAllBtn.style.display = 'none';
    section.style.display = 'none';
    return;
  }
  photoUrls = photos;
  var hiddenCount = 0;
  updatePhotoCount(count || photos.length);
  photos.forEach(function(url, i) {
    const card = document.createElement('div');
    card.className = 'photo-card';

    const badge = document.createElement('div');
    badge.className = 'photo-number';
    badge.textContent = String(i + 1);

    const img = document.createElement('img');
    img.src     = '/photo-proxy?url=' + encodeURIComponent(url);
    img.alt     = i18nText('photo_number', { number: i + 1 });
    img.loading = 'lazy';
    img.onerror = function() {
      card.style.display = 'none';
      hiddenCount++;
      var visibleCount = photos.length - hiddenCount;
      updatePhotoCount(visibleCount);
      if (visibleCount === 0) {
        setStatus(i18nText('no_photos_found'), 'err');
        dlAllBtn.style.display = 'none';
        section.style.display = 'none';
      }
    };
    const footer = document.createElement('div');
    footer.className = 'photo-card-footer';
    const btn = document.createElement('button');
    btn.className = 'photo-dl-btn';
    btn.setAttribute('data-i18n', 'download_photo');
    btn.textContent = i18nText('download_photo');
    btn.onclick = (function(u, idx) { return function() { downloadPhoto(u, idx); }; })(url, i + 1);
    footer.appendChild(btn);
    card.appendChild(badge);
    card.appendChild(img);
    card.appendChild(footer);
    carousel.appendChild(card);
  });
  dlAllBtn.style.display = photos.length > 1 ? 'inline-block' : 'none';
  section.style.display  = 'block';
  if (window.refreshLanguage) window.refreshLanguage();
}

async function downloadPhoto(url, index) {
  try {
    const filename = 'miitok_photo_' + index + '.jpg';
    const res = await fetch('/download-photo?url=' + encodeURIComponent(url) + '&filename=' + encodeURIComponent(filename));
    if (!res.ok) { setStatus(i18nText('photo_download_failed', { number: index }), 'err'); return; }
    const blob = await res.blob();
    if (!blob || blob.size <= 0) { setStatus(i18nText('photo_download_failed', { number: index }), 'err'); return; }
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(function() { document.body.removeChild(a); URL.revokeObjectURL(blobUrl); }, 1000);
  } catch(e) {
    setStatus(i18nText('photo_download_failed', { number: index }), 'err');
  }
}

async function downloadAllPhotos() {
  if (!photoUrls.length) return;
  setStatus(i18nText('downloading_photos', { count: photoUrls.length }), 'ok');
  for (let i = 0; i < photoUrls.length; i++) {
    await downloadPhoto(photoUrls[i], i + 1);
    if (i < photoUrls.length - 1) await new Promise(function(resolve) { setTimeout(resolve, 350); });
  }
  setStatus(i18nText('all_photos_downloaded'), 'ok');
}

function carouselScroll(direction) {
  const carousel = document.getElementById('photoCarousel');
  if (!carousel) return;
  const card = carousel.querySelector('.photo-card');
  const cardWidth = card ? (card.offsetWidth + 12) : 280;
  carousel.scrollBy({ left: direction * cardWidth, behavior: 'smooth' });
}
