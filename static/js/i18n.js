/* ── GLOBAL LANGUAGE SYSTEM ───────────────────── */
(function() {
  'use strict';

  var storageKey = 'mii_network_language';
  var defaultLang = 'id';

  var dictionaries = {
    id: {
      language: 'Bahasa',
      main: 'Utama', promo: 'Promo', system: 'Sistem', help: 'Bantuan',
      downloader_store_tools: 'Downloader • Store • Tools',
      control_mode: 'Mode Kontrol', server_online: 'Server Online', active: 'Aktif', soon: 'Segera', coming_soon: 'Segera Hadir',
      tiktok_downloader: 'TikTok Downloader', wa_status_converter: 'WA Status Converter', status_splitter: 'Status Splitter', caption_copier: 'Caption Copier',
      premium_apps_store: 'Premium Apps Store', lynk_store: 'Lynk.id Store', join_telegram: 'Gabung Telegram', contact_whatsapp: 'Kontak WhatsApp',
      control_panel: 'Control Panel', private_vault: 'Private Vault', report_bug: 'Laporkan Bug', how_to_use: 'Cara Pakai', server_status: 'Status Server',
      no_watermark: 'No Watermark', free_fast_no_watermark: 'Gratis • Cepat • No Watermark',
      paste_tiktok_link_here: 'Tempel link TikTok di sini...', paste: 'Tempel', download: 'Download', download_now: 'Download Sekarang', cancel: 'Batal', copy_link: 'Salin Link',
      fast: 'Cepat', safe: 'Aman', high_quality: 'Berkualitas', total_views: 'Total Views', total_downloads: 'Total Downloads', total_visitors: 'Total Visitors',
      control_mode_active: 'Mode Kontrol Aktif', mii_network_system: 'MII NETWORK System', active_text: 'Aktif', confirmation_download: 'Konfirmasi Download',
      paste_valid_tiktok_link: 'Paste a valid TikTok link.', paste_tiktok_link_first: 'Tempel link TikTok terlebih dahulu.', clipboard_empty: 'Clipboard kosong atau tidak berisi link TikTok.', clipboard_unavailable: 'Clipboard tidak bisa diakses. Paste manual link TikTok.',
      audio_failed: 'Audio belum bisa diproses. Coba video lain.', audio_success: 'Audio download berhasil!', download_failed: 'Download gagal.', empty_file: 'Download gagal, file kosong.', download_success: 'Download berhasil!', generic_error: 'Terjadi kesalahan, coba lagi.',
      fetch_photos: 'Ambil Foto', download_all: 'Download Semua',
      premium_access_terminal: 'Terminal Akses Premium', are_you_human: 'Apakah Anda Manusia?', type_confirm: 'Ketik CONFIRM untuk membuka Private Vault.', verification_token: 'Token Verifikasi', confirm_access: 'Konfirmasi Akses', human_signal_confirmed: 'Sinyal Manusia Dikonfirmasi', private_vault_initialized: 'Private Vault Diinisialisasi',
      locked_showcase: 'Etalase Terkunci', classified_showcase: 'Etalase rahasia untuk modul terbatas MII NETWORK.', locked: 'Terkunci', request_access_contact_admin: 'Minta Akses / Hubungi Admin', contact_admin: 'Hubungi Admin', access_panel: 'Panel Akses', vault_state: 'Status Vault', policy: 'Kebijakan', protocol: 'Protokol', execution: 'Eksekusi', restricted: 'Terbatas', disabled: 'Nonaktif', visual_showcase_only: 'Hanya etalase visual. Tidak ada tool backend yang aktif.', locked_modules: 'Modul Terkunci', compact_locked_previews: 'Preview terkunci ringkas untuk tinjauan visual.', tap_to_reveal: 'Ketuk untuk Membuka', back_to_downloader: 'Kembali ke Downloader',
      digital_products: 'Produk Digital MII NETWORK', follow_updates: 'Ikuti update terbaru', browse_products: 'Lihat semua produk', chat_with_us: 'Chat dengan kami',
      video_ready: 'Video Siap', status_tools_soon: 'Tool Status Segera', downloads_active: 'Download Aktif', views: 'Views', downloads: 'Downloads', visitors: 'Visitors',
      wa_status_desc: 'Konversi video ke format siap WhatsApp Status.', status_splitter_desc: 'Pisah video panjang menjadi bagian WhatsApp Status.', caption_desc: 'Tool salin caption sedang dikembangkan.', server_desc: 'Dashboard monitoring server sedang dikembangkan.', howto_desc: 'Panduan penggunaan sedang dikembangkan.', report_desc: 'Sistem laporan bug sedang dikembangkan.'
    },
    en: {
      language: 'Language', main: 'Main', promo: 'Promo', system: 'System', help: 'Help', downloader_store_tools: 'Downloader • Store • Tools', control_mode: 'Control Mode', server_online: 'Server Online', active: 'Active', soon: 'Soon', coming_soon: 'Coming Soon', tiktok_downloader: 'TikTok Downloader', wa_status_converter: 'WA Status Converter', status_splitter: 'Status Splitter', caption_copier: 'Caption Copier', premium_apps_store: 'Premium Apps Store', lynk_store: 'Lynk.id Store', join_telegram: 'Join Telegram', contact_whatsapp: 'Contact WhatsApp', control_panel: 'Control Panel', private_vault: 'Private Vault', report_bug: 'Report Bug', how_to_use: 'How To Use', server_status: 'Server Status', no_watermark: 'No Watermark', free_fast_no_watermark: 'Free • Fast • No Watermark', paste_tiktok_link_here: 'Paste TikTok link here...', paste: 'Paste', download: 'Download', download_now: 'Download Now', cancel: 'Cancel', copy_link: 'Copy Link', fast: 'Fast', safe: 'Safe', high_quality: 'High Quality', total_views: 'Total Views', total_downloads: 'Total Downloads', total_visitors: 'Total Visitors', control_mode_active: 'Control Mode Active', mii_network_system: 'MII NETWORK System', active_text: 'Active', confirmation_download: 'Confirmation Download', paste_valid_tiktok_link: 'Paste a valid TikTok link.', paste_tiktok_link_first: 'Paste TikTok link first.', clipboard_empty: 'Clipboard is empty or has no TikTok link.', clipboard_unavailable: 'Clipboard cannot be accessed. Paste the TikTok link manually.', audio_failed: 'Audio cannot be processed yet. Try another video.', audio_success: 'Audio download completed.', download_failed: 'Download failed.', empty_file: 'Download failed, empty file.', download_success: 'Download completed.', generic_error: 'Something went wrong, try again.', fetch_photos: 'Fetch Photos', download_all: 'Download All', premium_access_terminal: 'Premium Access Terminal', are_you_human: 'Are you human?', type_confirm: 'Type CONFIRM to unlock Private Vault.', verification_token: 'Verification Token', confirm_access: 'Confirm Access', human_signal_confirmed: 'Human Signal Confirmed', private_vault_initialized: 'Private Vault Initialized', locked_showcase: 'Locked Showcase', classified_showcase: 'Classified showcase for restricted MII NETWORK modules.', locked: 'Locked', request_access_contact_admin: 'Request Access / Contact Admin', contact_admin: 'Contact Admin', access_panel: 'Access Panel', vault_state: 'Vault State', policy: 'Policy', protocol: 'Protocol', execution: 'Execution', restricted: 'Restricted', disabled: 'Disabled', visual_showcase_only: 'Visual showcase only. No backend tools enabled.', locked_modules: 'Locked Modules', compact_locked_previews: 'Compact locked previews for visual review.', tap_to_reveal: 'Tap To Reveal', back_to_downloader: 'Back To Downloader', digital_products: 'MII NETWORK Digital Products', follow_updates: 'Follow for updates', browse_products: 'Browse all products', chat_with_us: 'Chat with us', video_ready: 'Video Ready', status_tools_soon: 'Status Tools Soon', downloads_active: 'Downloads Active', views: 'Views', downloads: 'Downloads', visitors: 'Visitors', wa_status_desc: 'Convert video to WhatsApp Status ready format.', status_splitter_desc: 'Split long videos into WhatsApp Status parts.', caption_desc: 'Caption copy tool is under development.', server_desc: 'Server monitoring dashboard is under development.', howto_desc: 'Usage guide is under development.', report_desc: 'Bug reporting system is under development.'
    },
    ja: { language:'言語', paste_tiktok_link_here:'TikTokリンクを貼り付け...', download:'ダウンロード', fast:'高速', safe:'安全', high_quality:'高画質', no_watermark:'透かしなし', contact_admin:'管理者に連絡', paste:'貼り付け', paste_valid_tiktok_link:'有効なTikTokリンクを貼り付けてください。', paste_tiktok_link_first:'TikTokリンクを先に貼り付けてください。', clipboard_empty:'クリップボードにTikTokリンクがありません。', clipboard_unavailable:'クリップボードにアクセスできません。手動で貼り付けてください。', download_success:'ダウンロード完了。', download_failed:'ダウンロード失敗。', generic_error:'エラーが発生しました。もう一度お試しください。', audio_success:'音声ダウンロード完了。', audio_failed:'音声を処理できません。別の動画をお試しください。', private_vault:'Private Vault', control_panel:'Control Panel', premium_apps_store:'Premium Apps Store', join_telegram:'Telegramに参加', contact_whatsapp:'WhatsApp連絡', request_access_contact_admin:'アクセス申請 / 管理者に連絡' },
    ko: { language:'언어', paste_tiktok_link_here:'TikTok 링크를 붙여넣으세요...', download:'다운로드', fast:'빠름', safe:'안전', high_quality:'고화질', no_watermark:'워터마크 없음', contact_admin:'관리자 문의', paste:'붙여넣기', paste_valid_tiktok_link:'유효한 TikTok 링크를 붙여넣으세요.', paste_tiktok_link_first:'TikTok 링크를 먼저 붙여넣으세요.', clipboard_empty:'클립보드에 TikTok 링크가 없습니다.', clipboard_unavailable:'클립보드에 접근할 수 없습니다. 직접 붙여넣으세요.', download_success:'다운로드 완료.', download_failed:'다운로드 실패.', generic_error:'오류가 발생했습니다. 다시 시도하세요.', audio_success:'오디오 다운로드 완료.', audio_failed:'오디오를 처리할 수 없습니다. 다른 영상을 시도하세요.', private_vault:'Private Vault', control_panel:'Control Panel', premium_apps_store:'Premium Apps Store', join_telegram:'Telegram 참여', contact_whatsapp:'WhatsApp 문의', request_access_contact_admin:'접근 요청 / 관리자 문의' },
    zh: { language:'语言', paste_tiktok_link_here:'粘贴 TikTok 链接...', download:'下载', fast:'快速', safe:'安全', high_quality:'高质量', no_watermark:'无水印', contact_admin:'联系管理员', paste:'粘贴', paste_valid_tiktok_link:'请粘贴有效的 TikTok 链接。', paste_tiktok_link_first:'请先粘贴 TikTok 链接。', clipboard_empty:'剪贴板为空或没有 TikTok 链接。', clipboard_unavailable:'无法访问剪贴板。请手动粘贴 TikTok 链接。', download_success:'下载完成。', download_failed:'下载失败。', generic_error:'出现错误，请重试。', audio_success:'音频下载完成。', audio_failed:'暂时无法处理音频。请尝试其他视频。', private_vault:'Private Vault', control_panel:'Control Panel', premium_apps_store:'Premium Apps Store', join_telegram:'加入 Telegram', contact_whatsapp:'联系 WhatsApp', request_access_contact_admin:'请求访问 / 联系管理员' },
    ru: { language:'Язык', paste_tiktok_link_here:'Вставьте ссылку TikTok...', download:'Скачать', fast:'Быстро', safe:'Безопасно', high_quality:'Высокое качество', no_watermark:'Без водяного знака', contact_admin:'Связаться с админом', paste:'Вставить', paste_valid_tiktok_link:'Вставьте действительную ссылку TikTok.', paste_tiktok_link_first:'Сначала вставьте ссылку TikTok.', clipboard_empty:'Буфер пуст или не содержит ссылку TikTok.', clipboard_unavailable:'Нет доступа к буферу. Вставьте ссылку TikTok вручную.', download_success:'Скачивание завершено.', download_failed:'Ошибка скачивания.', generic_error:'Произошла ошибка, попробуйте снова.', audio_success:'Аудио скачано.', audio_failed:'Аудио пока не обработано. Попробуйте другое видео.', private_vault:'Private Vault', control_panel:'Control Panel', premium_apps_store:'Premium Apps Store', join_telegram:'Вступить в Telegram', contact_whatsapp:'Написать в WhatsApp', request_access_contact_admin:'Запросить доступ / Связаться с админом' }
  };

  var languages = [
    { code: 'id', label: 'Indonesian' }, { code: 'en', label: 'English' }, { code: 'ja', label: 'Japanese' },
    { code: 'ko', label: 'Korean' }, { code: 'zh', label: 'Chinese' }, { code: 'ru', label: 'Russian' }
  ];

  function getLanguage() {
    try {
      var saved = window.localStorage.getItem(storageKey);
      return dictionaries[saved] ? saved : defaultLang;
    } catch (e) { return defaultLang; }
  }

  function translate(key) {
    var lang = window.currentLanguage || getLanguage();
    return (dictionaries[lang] && dictionaries[lang][key]) || (dictionaries.en && dictionaries.en[key]) || (dictionaries.id && dictionaries.id[key]) || key;
  }

  function applyLanguage(lang) {
    if (!dictionaries[lang]) lang = defaultLang;
    window.currentLanguage = lang;
    try { window.localStorage.setItem(storageKey, lang); } catch (e) {}
    document.documentElement.setAttribute('lang', lang);

    document.querySelectorAll('[data-i18n]').forEach(function(el) { el.textContent = translate(el.getAttribute('data-i18n')); });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(function(el) { el.setAttribute('placeholder', translate(el.getAttribute('data-i18n-placeholder'))); });
    document.querySelectorAll('[data-i18n-title]').forEach(function(el) { el.setAttribute('title', translate(el.getAttribute('data-i18n-title'))); });
    document.querySelectorAll('[data-i18n-aria]').forEach(function(el) { el.setAttribute('aria-label', translate(el.getAttribute('data-i18n-aria'))); });
    document.querySelectorAll('.language-option').forEach(function(el) { el.classList.toggle('active', el.getAttribute('data-lang') === lang); });
    var current = document.getElementById('languageCurrent');
    if (current) current.textContent = translate('language');
  }

  function initLanguageSelector() {
    var toggle = document.getElementById('languageToggle');
    var menu = document.getElementById('languageMenu');
    if (!toggle || !menu) return;

    menu.innerHTML = languages.map(function(item) {
      return '<button type="button" class="language-option" data-lang="' + item.code + '">' + item.label + '</button>';
    }).join('');

    toggle.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      var open = menu.classList.toggle('show');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });

    menu.addEventListener('click', function(e) {
      var option = e.target.closest('.language-option');
      if (!option) return;
      applyLanguage(option.getAttribute('data-lang'));
      menu.classList.remove('show');
      toggle.setAttribute('aria-expanded', 'false');
    });

    document.addEventListener('click', function(e) {
      if (!e.target.closest('.language-selector')) {
        menu.classList.remove('show');
        toggle.setAttribute('aria-expanded', 'false');
      }
    });
  }

  window.t = translate;
  window.i18nText = translate;
  window.applyLanguage = applyLanguage;
  window.refreshLanguage = function() { applyLanguage(window.currentLanguage || getLanguage()); };

  document.addEventListener('DOMContentLoaded', function() {
    initLanguageSelector();
    applyLanguage(getLanguage());
  });
})();
