/* ── STATE ────────────────────────────────────── */
let selectedQuality = 'best';
let isDownloading      = false;
let isDownloadingAudio = false;
let previewData     = null;
let previewTimer    = null;
let photoUrls       = [];
let isPhotoMode     = false;
let lastPreviewUrl  = null;
let currentView     = 'downloader';

const qualityLabel = { best:'BEST', '1080':'1080P', '720':'720P', photo:'PHOTO' };
const typeLabel    = { best:'MP4', '1080':'MP4', '720':'MP4', photo:'IMAGE' };

/* ── CLIENT-SIDE ROUTING (pathname only) ────────── */
(function() {
  var path = window.location.pathname;
  if (path === '/ai' || path === '/ai/') {
    currentView = 'makima-ai';
  } else {
    currentView = 'downloader';
  }
})();
