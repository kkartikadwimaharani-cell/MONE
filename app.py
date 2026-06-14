from flask import Flask, render_template, request, jsonify, send_file, Response, after_this_request
import yt_dlp
import os
import uuid
import shutil
import glob
import re
import json
import time
import threading
import subprocess
import hashlib
import base64
import hmac
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
import requests as requests_lib
import analytics
import google.generativeai as genai

# ---------------------------------------------------------------------------
# Gemini model (lazy initialization for Railway env timing)
# ---------------------------------------------------------------------------
_gemini_model_cache = {}  # {model_name: GenerativeModel}
_gemini_configured = False

_MAKIMA_SYSTEM_INSTRUCTION = """
Kamu adalah MAKIMA AI, asisten pribadi milik MII STORE.
Jawab dalam Bahasa Indonesia yang santai, jelas, tenang, elegan, dan profesional.
Gunakan kata “kamu”, jangan “Anda”.
Jangan bilang “sebagai AI”.
Jangan mengarang fakta, website, harga, atau sumber.
Jangan mengaku browsing kalau tidak ada fitur browsing.
Kalau user minta cek web tapi tidak ada akses web, jawab persis:
“Aku belum bisa mengecek web langsung dari sini. Kirim link atau screenshot-nya, nanti aku bantu baca.”
Kalau user kirim screenshot/gambar, baca isi visualnya dan bantu jelaskan dengan jelas.

Format jawaban:
- langsung ke inti
- pakai paragraf pendek
- pakai bullet/list kalau perlu
- code block hanya untuk kode
- jangan bertele-tele
- jangan terlalu panjang kecuali user minta detail
- jangan tutup jawaban dengan pertanyaan template yang kaku

Kalau user minta kode:
- berikan judul singkat
- berikan penjelasan pendek
- semua kode wajib masuk ke markdown code block berpagar tiga backtick dengan label bahasa atau nama file
- jangan tampilkan kode sebagai teks biasa
- jangan membaca ulang isi kode di luar code block
- berikan cara pakai singkat
- jangan menjelaskan setiap baris kode; jelaskan bagian penting saja
- berikan kode yang rapi, utuh, dan indentasinya benar
- jangan mengubah fitur lain yang tidak diminta
- beri peringatan kalau perubahan bisa merusak fitur existing

Kalau user minta prompt Codex, berikan prompt siap copy yang aman dan jelas.

Safety:
- tolak permintaan malware, phishing, mencuri token, spam, hack akun, atau bypass ilegal
- boleh bantu debugging, UI, backend, deploy, API, dan automation yang aman
- kalau user meminta hal berbahaya, jawab singkat bahwa kamu tidak bisa membantu itu, lalu tawarkan alternatif aman seperti debugging, edukasi defensif, atau proteksi.
"""

_GEMINI_ALLOWED_MODELS = ['gemini-2.0-flash', 'gemini-2.5-flash']

def _get_gemini_model(model_name=None):
    global _gemini_configured, _gemini_model_cache
    if model_name is None:
        model_name = 'gemini-2.0-flash'
    if model_name not in _GEMINI_ALLOWED_MODELS:
        model_name = 'gemini-2.0-flash'
    if model_name in _gemini_model_cache:
        return _gemini_model_cache[model_name]
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None
    if not _gemini_configured:
        genai.configure(api_key=api_key)
        _gemini_configured = True
    model = genai.GenerativeModel(
        model_name,
        system_instruction=_MAKIMA_SYSTEM_INSTRUCTION
    )
    _gemini_model_cache[model_name] = model
    return model

print("[startup] Gemini model cache ready")
print("GROQ_API_KEY exists:", bool(os.environ.get("GROQ_API_KEY")))

import shutil, subprocess
print("[startup] FFMPEG PATH:", shutil.which("ffmpeg"))
try:
    print(subprocess.check_output(["ffmpeg", "-version"]).decode()[:300])
except Exception as e:
    print("[startup] FFMPEG ERROR:", e)

app = Flask(__name__, static_folder='static', static_url_path='/static')

APP_VERSION = "20260614-mii-store-final-v2"


def versioned_static(path):
    """Build a /static URL with the current deploy version query string."""
    clean_path = path.lstrip('/')
    if clean_path.startswith('static/'):
        clean_path = clean_path[len('static/'):]
    return f"{app.static_url_path}/{clean_path}?v={APP_VERSION}"

analytics.init_db()

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
_rate_lock = threading.Lock()
_rate_store_download = {}  # {ip: last_request_timestamp} for /download
_rate_store_photos = {}    # {ip: last_request_timestamp} for /photos
_rate_store_proxy = {}     # {ip: last_request_timestamp} for /photo-proxy & /download-photo
_rate_store_track = {}     # {ip: last_request_timestamp} for /track
_rate_store_ghost = {}     # {ip: last_request_timestamp} for /api/ghost-scan
_rate_store_ai = {}        # {ip: last_request_timestamp} for /api/ai-chat

RATE_LIMIT_SECONDS = 10
RATE_LIMIT_TRACK_SECONDS = 2
RATE_LIMIT_PROXY_SECONDS = 1  # Allow 1 request per second per IP for proxy
RATE_LIMIT_GHOST_SECONDS = 2  # Allow 1 request per 2 seconds per IP for ghost-scan
RATE_LIMIT_AI_SECONDS = 3    # Allow 1 request per 3 seconds per IP for ai-chat

# ---------------------------------------------------------------------------
# vpnapi.io response cache
# ---------------------------------------------------------------------------
_ghost_vpn_cache = {}  # {ip: (timestamp, result_dict)}
GHOST_CACHE_TTL = 60  # seconds


def _check_rate_limit(ip, store, limit_seconds=None):
    """Return True if the request is allowed, False if rate-limited."""
    if limit_seconds is None:
        limit_seconds = RATE_LIMIT_SECONDS
    now = time.time()
    with _rate_lock:
        last = store.get(ip)
        if last is not None and (now - last) < limit_seconds:
            return False
        store[ip] = now
        return True


def _check_proxy_rate_limit(ip):
    """Lightweight rate limit for proxy endpoints - 1 req/sec."""
    now = time.time()
    with _rate_lock:
        last = _rate_store_proxy.get(ip)
        if last is not None and (now - last) < RATE_LIMIT_PROXY_SECONDS:
            return False
        _rate_store_proxy[ip] = now
        return True


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------
TIKTOK_DOMAINS = {'tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com', 'www.tiktok.com'}

# Extended domain set for redirect validation (includes CDN hosts that may appear in redirect chains)
_REDIRECT_ALLOWED_DOMAINS = TIKTOK_DOMAINS | {
    'm.tiktok.com',
    't.tiktok.com',
}
_REDIRECT_ALLOWED_SUFFIXES = (
    '.tiktok.com',
    '.tiktokcdn.com',
    '.tiktokcdn-us.com',
    '.musical.ly',
    '.muscdn.com',
    '.ibytedtos.com',
    '.ipstatp.com',
)
_MAX_REDIRECTS = 5

# Allowed CDN domains for photo proxy (to prevent SSRF)
ALLOWED_CDN_SUFFIXES = (
    '.tiktokcdn.com',
    '.tiktokcdn-us.com',
    '.musical.ly',
    '.muscdn.com',
    '.tiktok.com',
    '.ibytedtos.com',
    '.ipstatp.com',
)


def _is_allowed_cdn_url(url):
    """Check that a URL is HTTPS and points to an allowed TikTok CDN domain."""
    try:
        parsed = urlparse(url)
        if parsed.scheme != 'https':
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        hostname = hostname.lower()
        for suffix in ALLOWED_CDN_SUFFIXES:
            if hostname == suffix.lstrip('.') or hostname.endswith(suffix):
                return True
        return False
    except Exception:
        return False


def _is_valid_tiktok_url(url):
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        host = parsed.netloc.lower()
        # Strip port if present
        host = host.split(':')[0]
        return host in TIKTOK_DOMAINS
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self'; "
        "img-src 'self' data: https:; "
        "media-src 'self' blob:;"
    )
    # No-cache headers for HTML responses
    content_type = response.headers.get('Content-Type', '')
    if 'text/html' in content_type:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, proxy-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


@app.context_processor
def inject_asset_helpers():
    return {
        'APP_VERSION': APP_VERSION,
        'asset_url': versioned_static,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/ai')
def ai_view():
    return render_template('index.html')


@app.route('/<path:path>')
def catch_all(path):
    from flask import redirect
    return redirect('/')


# ---------------------------------------------------------------------------
# Analytics routes
# ---------------------------------------------------------------------------
_VALID_EVENT_TYPES = {
    'page_view', 'visitor', 'download_click', 'download_success',
    'instagram_click', 'telegram_click', 'whatsapp_click', 'lynkid_click',
}


@app.route('/track', methods=['POST'])
def track():
    data = request.get_json(silent=True) or {}
    event_type = data.get('event_type', '').strip()

    if event_type not in _VALID_EVENT_TYPES:
        return jsonify({'error': 'Invalid event_type'}), 400

    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()

    # Rate limiting (skip for 'visitor' since it's deduplicated server-side)
    if event_type != 'visitor':
        if not _check_rate_limit(client_ip, _rate_store_track, RATE_LIMIT_TRACK_SECONDS):
            return jsonify({'error': 'Too many requests'}), 429

    salt = os.environ.get('ANALYTICS_SALT', 'mii_network_salt')
    ip_hash = hashlib.sha256((client_ip + salt).encode()).hexdigest()
    user_agent = request.headers.get('User-Agent', '')

    # Deduplicate visitor events by ip_hash
    if event_type == 'visitor' and analytics.has_visitor(ip_hash):
        return jsonify({'success': True})

    analytics.record_event(event_type, ip_hash, user_agent)
    return jsonify({'success': True})


@app.route('/stats')
def stats():
    return jsonify(analytics.get_stats())


@app.route('/api/ghost-scan')
def ghost_scan():
    # Read visitor IP: CF-Connecting-IP > X-Forwarded-For > remote_addr
    ip = request.headers.get('CF-Connecting-IP')
    if not ip:
        forwarded = request.headers.get('X-Forwarded-For', '')
        ip = forwarded.split(',')[0].strip() if forwarded else ''
    if not ip:
        ip = request.remote_addr or 'Unknown'

    # Rate limiting
    if not _check_rate_limit(ip, _rate_store_ghost, RATE_LIMIT_GHOST_SECONDS):
        return jsonify({'error': 'Too many requests'}), 429

    # Read country from Cloudflare header
    country = request.headers.get('CF-IPCountry', 'Unknown')

    # Parse User-Agent to short browser/platform format
    ua = request.headers.get('User-Agent', '')
    browser = 'Unknown'
    if ua:
        # Detect browser
        br = 'Unknown'
        if 'Edg/' in ua or 'Edge/' in ua:
            br = 'Edge'
        elif 'OPR/' in ua or 'Opera' in ua:
            br = 'Opera'
        elif 'Chrome/' in ua and 'Safari/' in ua:
            br = 'Chrome'
        elif 'Firefox/' in ua:
            br = 'Firefox'
        elif 'Safari/' in ua:
            br = 'Safari'
        # Detect platform
        plat = 'Unknown'
        if 'Android' in ua:
            plat = 'Android'
        elif 'iPhone' in ua or 'iPad' in ua:
            plat = 'iOS'
        elif 'Windows' in ua:
            plat = 'Windows'
        elif 'Mac OS' in ua or 'Macintosh' in ua:
            plat = 'macOS'
        elif 'Linux' in ua:
            plat = 'Linux'
        browser = f'{br} / {plat}'

    # Read primary language from Accept-Language
    accept_lang = request.headers.get('Accept-Language', '')
    language = 'Unknown'
    if accept_lang:
        # Extract first language tag (before any comma or semicolon)
        lang_part = accept_lang.split(',')[0].split(';')[0].strip()
        if lang_part:
            language = lang_part

    # VPN detection via vpnapi.io (with in-memory cache)
    vpn_status = 'Basic Scan Only'
    risk_level = 'UNKNOWN'
    vpnapi_key = os.environ.get('VPNAPI_KEY')
    if vpnapi_key:
        # Check cache first
        now = time.time()
        cached = _ghost_vpn_cache.get(ip)
        if cached and (now - cached[0]) < GHOST_CACHE_TTL:
            vpn_status = cached[1]['vpn_status']
            risk_level = cached[1]['risk_level']
        else:
            try:
                vpn_resp = requests_lib.get(
                    f'https://vpnapi.io/api/{ip}?key={vpnapi_key}',
                    timeout=5
                )
                vpn_data = vpn_resp.json()
                security = vpn_data.get('security', {})
                is_vpn = security.get('vpn', False)
                is_proxy = security.get('proxy', False)
                is_tor = security.get('tor', False)
                if is_vpn or is_proxy or is_tor:
                    vpn_status = 'VPN / Proxy Detected'
                    risk_level = 'HIGH'
                else:
                    vpn_status = 'No VPN Detected'
                    risk_level = 'LOW'
                # Store in cache (cap at 1000 entries to bound memory)
                if len(_ghost_vpn_cache) >= 1000:
                    _ghost_vpn_cache.clear()
                _ghost_vpn_cache[ip] = (now, {'vpn_status': vpn_status, 'risk_level': risk_level})
            except Exception as e:
                app.logger.warning('vpnapi.io request failed for ip=%s: %s', ip, e)
                vpn_status = 'Scan Failed'
                risk_level = 'UNKNOWN'

    return jsonify({
        'ip': ip,
        'country': country,
        'browser': browser,
        'language': language,
        'vpn_status': vpn_status,
        'risk_level': risk_level,
        'scan_mode': 'MII STORE OBSERVATION'
    })


@app.route('/admin-stats')
def admin_stats():
    # Token-based authentication
    admin_token = os.environ.get('ADMIN_TOKEN', 'mii_admin_2025')
    provided_token = request.args.get('token', '')
    if not provided_token or provided_token != admin_token:
        return jsonify({'error': 'Forbidden'}), 403

    detailed = analytics.get_detailed_stats()
    summary = analytics.get_stats()

    rows_html = ''
    for item in detailed:
        rows_html += f'<tr><td>{item["event_type"]}</td><td>{item["count"]}</td></tr>'

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Stats - MiiTok</title>
    <style>
        body {{
            background: #1a0a0a;
            color: #f0d0d0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            padding: 2rem;
            margin: 0;
        }}
        h1 {{
            color: #ff4444;
            text-align: center;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin: 2rem 0;
        }}
        .card {{
            background: rgba(255, 68, 68, 0.1);
            border: 1px solid rgba(255, 68, 68, 0.3);
            border-radius: 12px;
            padding: 1.5rem;
            text-align: center;
        }}
        .card .value {{
            font-size: 2rem;
            font-weight: bold;
            color: #ff4444;
        }}
        .card .label {{
            font-size: 0.9rem;
            color: #cc9999;
            margin-top: 0.5rem;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 2rem;
        }}
        th, td {{
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid rgba(255, 68, 68, 0.2);
        }}
        th {{
            background: rgba(255, 68, 68, 0.15);
            color: #ff6666;
        }}
        tr:hover {{
            background: rgba(255, 68, 68, 0.05);
        }}
    </style>
</head>
<body>
    <h1>MiiTok Analytics</h1>
    <div class="summary">
        <div class="card">
            <div class="value">{summary["total_views"]}</div>
            <div class="label">Page Views</div>
        </div>
        <div class="card">
            <div class="value">{summary["total_visitors"]}</div>
            <div class="label">Unique Visitors</div>
        </div>
        <div class="card">
            <div class="value">{summary["total_downloads"]}</div>
            <div class="label">Total Downloads</div>
        </div>
        <div class="card">
            <div class="value">{summary["total_social_clicks"]}</div>
            <div class="label">Social Clicks</div>
        </div>
    </div>
    <h2 style="color: #ff6666;">Detailed Breakdown</h2>
    <table>
        <thead>
            <tr><th>Event Type</th><th>Count</th></tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</body>
</html>'''
    return html


@app.route('/preview', methods=['POST'])
def preview():
    if request.is_json:
        data = request.get_json(silent=True) or {}
        url = data.get('url', '').strip()
    else:
        url = (request.form.get('url') or '').strip()

    if not url:
        return jsonify({'error': 'URL kosong'}), 400

    if not _is_valid_tiktok_url(url):
        return jsonify({'error': 'URL tidak valid atau bukan link TikTok'}), 400

    try:
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'noplaylist': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return jsonify({'error': 'Tidak bisa ambil info'}), 400

        # Hanya return data asli yang tersedia
        result = {}
        if info.get('title'):
            result['title'] = info['title'][:80]
        if info.get('thumbnail'):
            result['thumbnail'] = info['thumbnail']
        if info.get('duration'):
            result['duration'] = int(info['duration'])
        if info.get('uploader'):
            result['uploader'] = info['uploader']
        if info.get('webpage_url'):
            result['webpage_url'] = info['webpage_url']
        # Always scan all formats to find the highest available resolution
        max_h = 0
        best_filesize = None
        if info.get('formats'):
            # First pass: find max height among video formats
            for fmt in info['formats']:
                if fmt.get('vcodec', 'none') == 'none':
                    continue
                h = fmt.get('height') or 0
                if h > max_h:
                    max_h = h
            # Second pass: among video formats at max_h, pick largest filesize
            for fmt in info['formats']:
                if fmt.get('vcodec', 'none') == 'none':
                    continue
                h = fmt.get('height') or 0
                if h == max_h and max_h > 0:
                    fs = fmt.get('filesize') or fmt.get('filesize_approx')
                    if fs and (best_filesize is None or fs > best_filesize):
                        best_filesize = fs
        # Fallback to top-level height if no formats found
        if max_h == 0 and info.get('height'):
            max_h = int(info['height'])
        if max_h > 0:
            result['height'] = max_h
            result['best_height'] = max_h
            if max_h >= 2160:
                result['best_label'] = 'BEST 4K'
            elif max_h >= 1440:
                result['best_label'] = 'BEST 2K'
            elif max_h >= 1080:
                result['best_label'] = 'BEST 1080P'
            elif max_h >= 720:
                result['best_label'] = 'BEST 720P'
            else:
                result['best_label'] = 'BEST'
            if best_filesize:
                result['best_filesize_mb'] = round(best_filesize / 1048576)
            else:
                result['best_filesize_mb'] = None

        # Cek apakah foto/slideshow
        if info.get('_type') == 'playlist':
            result['is_slideshow'] = True

        return jsonify(result)

    except Exception as e:
        return jsonify({'error': 'Terjadi kesalahan, coba lagi'}), 500


@app.route('/download', methods=['POST'])
def download():
    if request.is_json:
        data = request.get_json(silent=True) or {}
        url = data.get('url', '').strip()
        quality = data.get('quality', '').strip()
    else:
        url = (request.form.get('url') or '').strip()
        quality = (request.form.get('quality') or '').strip()

    print(f"[download] url={url!r} quality={quality!r}", flush=True)

    if not url:
        return jsonify({'error': 'Masukkan link TikTok dulu'}), 400

    if not _is_valid_tiktok_url(url):
        return jsonify({'error': 'URL tidak valid atau bukan link TikTok'}), 400

    # Quality validation
    valid_qualities = {'best', '1080', '720'}
    if not quality:
        quality = 'best'
    elif quality not in valid_qualities:
        return jsonify({'error': 'Kualitas tidak valid'}), 400

    print(f"[download] selected quality: {quality}", flush=True)

    # Lightweight probe: reject slideshow/playlist before attempting video download
    try:
        _probe_opts = {'quiet': True, 'skip_download': True, 'noplaylist': False}
        with yt_dlp.YoutubeDL(_probe_opts) as _ydl:
            _probe = _ydl.extract_info(url, download=False)
        if _probe and _probe.get('_type') == 'playlist':
            return jsonify({'error': 'Ini konten foto/slideshow. Gunakan tab PHOTO untuk mengunduh.'}), 400
    except Exception:
        pass  # If probe fails, let the download attempt proceed and surface its own error

    # Rate limiting
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    if not _check_rate_limit(client_ip, _rate_store_download):
        return jsonify({'error': 'Terlalu cepat, coba lagi beberapa saat'}), 429

    tmp_id = str(uuid.uuid4())
    raw_file = None
    output_path = f"/tmp/{tmp_id}_out.mp4"

    try:
        # Check ffmpeg availability
        ffmpeg_bin = shutil.which('ffmpeg')
        if not ffmpeg_bin:
            print("[download] ERROR: ffmpeg not found in PATH", flush=True)
            return jsonify({'error': 'Server belum support FFmpeg. Periksa nixpacks.toml dan redeploy.'}), 500

        # Step 1: Download raw video with yt-dlp
        raw_outtmpl = f"/tmp/{tmp_id}_raw.%(ext)s"
        print(f"[download] tmp_id={tmp_id} raw_outtmpl={raw_outtmpl}", flush=True)

        if quality == 'best':
            fmt = 'bestvideo+bestaudio/best'
        elif quality == '1080':
            fmt = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]'
        elif quality == '720':
            fmt = 'bestvideo[height<=720]+bestaudio/best[height<=720]'
        else:
            fmt = 'bestvideo+bestaudio/best'

        ydl_opts = {
            'outtmpl': raw_outtmpl,
            'format': fmt,
            'merge_output_format': 'mp4',
            'quiet': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Step 2: Find the downloaded raw file
        raw_candidates = glob.glob(f"/tmp/{tmp_id}_raw.*")
        if not raw_candidates:
            print("[download] ERROR: no raw file found after yt-dlp download", flush=True)
            return jsonify({'error': 'File video tidak ditemukan setelah download'}), 500
        raw_file = raw_candidates[0]

        raw_exists = os.path.isfile(raw_file)
        raw_size = os.path.getsize(raw_file) if raw_exists else 0
        print(f"[download] raw_file={raw_file} exists={raw_exists} size={raw_size}", flush=True)

        if not raw_exists or raw_size == 0:
            print("[download] ERROR: raw file missing or empty after download", flush=True)
            return jsonify({'error': 'File video tidak ditemukan setelah download'}), 500

        # Step 3: Remux/convert to compatible MP4 (h264/aac, faststart, yuv420p)
        if quality == '720':
            ffmpeg_cmd = [
                ffmpeg_bin, '-y', '-i', raw_file,
                '-vf', "scale='if(gt(ih,720),-2,iw)':'if(gt(ih,720),720,ih)'",
                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '128k',
                '-movflags', '+faststart',
                output_path,
            ]
        elif quality == '1080':
            ffmpeg_cmd = [
                ffmpeg_bin, '-y', '-i', raw_file,
                '-vf', "scale='if(gt(ih,1080),-2,iw)':'if(gt(ih,1080),1080,ih)'",
                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '128k',
                '-movflags', '+faststart',
                output_path,
            ]
        else:
            # best - probe first, then decide copy vs re-encode
            ffprobe_bin = shutil.which('ffprobe') or 'ffprobe'
            source_is_compatible = False
            try:
                vprobe = subprocess.run(
                    [ffprobe_bin, '-v', 'error', '-select_streams', 'v:0',
                     '-show_entries', 'stream=codec_name,pix_fmt', '-of', 'json', raw_file],
                    capture_output=True, text=True, timeout=15
                )
                aprobe = subprocess.run(
                    [ffprobe_bin, '-v', 'error', '-select_streams', 'a:0',
                     '-show_entries', 'stream=codec_name', '-of', 'json', raw_file],
                    capture_output=True, text=True, timeout=15
                )
                fprobe = subprocess.run(
                    [ffprobe_bin, '-v', 'error', '-show_entries', 'format=format_name',
                     '-of', 'json', raw_file],
                    capture_output=True, text=True, timeout=15
                )
                if vprobe.returncode == 0 and aprobe.returncode == 0 and fprobe.returncode == 0:
                    vinfo = json.loads(vprobe.stdout)
                    ainfo = json.loads(aprobe.stdout)
                    finfo = json.loads(fprobe.stdout)
                    v_streams = vinfo.get('streams', [])
                    a_streams = ainfo.get('streams', [])
                    format_name = finfo.get('format', {}).get('format_name', '')
                    if v_streams and a_streams:
                        v_codec = v_streams[0].get('codec_name', '')
                        v_pix_fmt = v_streams[0].get('pix_fmt', '')
                        a_codec = a_streams[0].get('codec_name', '')
                        is_mp4_container = 'mp4' in format_name or 'mov' in format_name
                        if v_codec == 'h264' and a_codec == 'aac' and v_pix_fmt == 'yuv420p' and is_mp4_container:
                            source_is_compatible = True
                    print(f"[download] probe: v_codec={v_streams[0].get('codec_name', '') if v_streams else 'N/A'} "
                          f"pix_fmt={v_streams[0].get('pix_fmt', '') if v_streams else 'N/A'} "
                          f"a_codec={a_streams[0].get('codec_name', '') if a_streams else 'N/A'} "
                          f"format={format_name} compatible={source_is_compatible}", flush=True)
            except Exception as probe_err:
                print(f"[download] probe failed: {probe_err}", flush=True)

            if source_is_compatible:
                ffmpeg_cmd = [
                    ffmpeg_bin, '-y', '-i', raw_file,
                    '-c:v', 'copy', '-c:a', 'copy',
                    '-movflags', '+faststart',
                    output_path,
                ]
            else:
                ffmpeg_cmd = [
                    ffmpeg_bin, '-y', '-i', raw_file,
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
                    '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-b:a', '192k',
                    '-movflags', '+faststart',
                    output_path,
                ]

        print(f"[download] ffmpeg cmd: {' '.join(ffmpeg_cmd)}", flush=True)
        result = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=300)
        print(f"[download] ffmpeg returncode={result.returncode}", flush=True)

        if result.returncode != 0:
            stderr_output = (result.stderr or b'').decode(errors='replace')[-2000:]
            print(f"[download] ffmpeg FAILED stderr: {stderr_output}", flush=True)

            # Fallback: try remux with stream copy
            print("[download] attempting remux fallback (copy streams)", flush=True)
            remux_cmd = [
                ffmpeg_bin, '-y', '-i', raw_file,
                '-c', 'copy',
                '-movflags', '+faststart',
                output_path,
            ]
            remux_result = subprocess.run(remux_cmd, capture_output=True, timeout=120)
            print(f"[download] remux returncode={remux_result.returncode}", flush=True)

            if remux_result.returncode != 0:
                remux_stderr = (remux_result.stderr or b'').decode(errors='replace')[-1000:]
                print(f"[download] remux FAILED stderr: {remux_stderr}", flush=True)
                _cleanup_files(raw_file, output_path)
                return jsonify({'error': 'Konversi video gagal. Coba kualitas lebih rendah.'}), 500

        # Step 4: Validate output file
        if not os.path.isfile(output_path):
            print(f"[download] ERROR: output file not found at {output_path}", flush=True)
            _cleanup_files(raw_file, None)
            return jsonify({'error': 'File hasil tidak ditemukan.'}), 500

        final_size = os.path.getsize(output_path)
        print(f"[download] output_path={output_path} exists=True size={final_size}", flush=True)

        if final_size == 0:
            print("[download] ERROR: output file is empty (0 bytes)", flush=True)
            _cleanup_files(raw_file, output_path)
            return jsonify({'error': 'File hasil kosong.'}), 500

        # File size check for 'best' quality (100MB limit for free server)
        if quality == 'best' and final_size > 100 * 1024 * 1024:
            print(f"[download] ERROR: file too large ({final_size} bytes) for free server", flush=True)
            _cleanup_files(raw_file, output_path)
            return jsonify({'error': 'Video terlalu besar untuk server gratis. Coba 1080P.'}), 500

        # Step 5: Send file, cleanup AFTER response is sent
        print(f"[download] sending file: {output_path} size={final_size}", flush=True)

        @after_this_request
        def cleanup_video(response):
            try:
                os.remove(raw_file)
            except Exception:
                pass
            try:
                os.remove(output_path)
            except Exception:
                pass
            return response

        return send_file(output_path, as_attachment=True, download_name='miitok_video.mp4', mimetype='video/mp4')

    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        print(f"[download] yt-dlp DownloadError: {msg}", flush=True)
        _cleanup_files(raw_file, output_path)
        if 'Unsupported URL' in msg or 'unsupported url' in msg.lower():
            return jsonify({'error': 'TikTok photo belum didukung oleh extractor server saat ini.'}), 400
        if 'Sign in' in msg or 'login' in msg.lower():
            return jsonify({'error': 'Video ini memerlukan login TikTok'}), 500
        return jsonify({'error': 'Download gagal. Pastikan link valid dan coba lagi.'}), 500
    except subprocess.TimeoutExpired:
        print("[download] ERROR: ffmpeg timed out", flush=True)
        _cleanup_files(raw_file, output_path)
        return jsonify({'error': 'Konversi video gagal. Coba kualitas lebih rendah.'}), 500
    except Exception as e:
        print(f"[download] unexpected error: {type(e).__name__}: {e}", flush=True)
        _cleanup_files(raw_file, output_path)
        return jsonify({'error': 'Terjadi kesalahan, coba lagi'}), 500


def _cleanup_files(*paths):
    """Safely remove temp files, ignoring errors."""
    for p in paths:
        if p:
            try:
                os.remove(p)
            except Exception:
                pass


@app.route('/download-audio', methods=['POST'])
def download_audio():
    data = request.get_json(silent=True) or {}
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'error': 'Masukkan link TikTok dulu'}), 400

    if not _is_valid_tiktok_url(url):
        return jsonify({'error': 'URL tidak valid atau bukan link TikTok'}), 400

    # Rate limiting
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    if not _check_rate_limit(client_ip, _rate_store_download):
        return jsonify({'error': 'Terlalu cepat, coba lagi beberapa saat'}), 429

    tmp_id = str(uuid.uuid4())

    try:
        ffmpeg_bin = shutil.which('ffmpeg')
        if not ffmpeg_bin:
            return jsonify({'error': 'Server belum support FFmpeg.'}), 500

        # Download audio with yt-dlp
        raw_outtmpl = f"/tmp/{tmp_id}_audio_raw.%(ext)s"
        ydl_opts = {
            'outtmpl': raw_outtmpl,
            'format': 'bestaudio/best',
            'quiet': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Find downloaded file
        raw_candidates = glob.glob(f"/tmp/{tmp_id}_audio_raw.*")
        if not raw_candidates:
            return jsonify({'error': 'File audio tidak ditemukan setelah download'}), 500
        raw_file = raw_candidates[0]

        # Convert to MP3 with ffmpeg
        output_path = f"/tmp/{tmp_id}_out.mp3"
        ffmpeg_cmd = [
            ffmpeg_bin, '-y', '-i', raw_file,
            '-vn', '-acodec', 'libmp3lame', '-ab', '192k',
            output_path,
        ]

        result = subprocess.run(ffmpeg_cmd, capture_output=True)
        if result.returncode != 0:
            try:
                os.remove(raw_file)
            except Exception:
                pass
            try:
                os.remove(output_path)
            except Exception:
                pass
            return jsonify({'error': 'Konversi audio gagal. Coba lagi.'}), 500

        @after_this_request
        def cleanup_audio(response):
            try:
                os.remove(raw_file)
            except Exception:
                pass
            try:
                os.remove(output_path)
            except Exception:
                pass
            return response

        return send_file(output_path, as_attachment=True, download_name='miitok_audio.mp3', mimetype='audio/mpeg')

    except yt_dlp.utils.DownloadError as e:
        # Clean up any partially-downloaded raw files
        for f in glob.glob(f"/tmp/{tmp_id}_audio_raw.*"):
            try:
                os.remove(f)
            except Exception:
                pass
        return jsonify({'error': 'Audio belum bisa diproses. Coba video lain.'}), 500
    except Exception as e:
        # Clean up any partially-downloaded raw files
        for f in glob.glob(f"/tmp/{tmp_id}_audio_raw.*"):
            try:
                os.remove(f)
            except Exception:
                pass
        return jsonify({'error': 'Terjadi kesalahan, coba lagi'}), 500


# ---------------------------------------------------------------------------
# Fallback photo extractor (when yt-dlp fails)
# ---------------------------------------------------------------------------
def _is_allowed_redirect_host(url):
    """Check whether a redirect destination URL is on an allowed TikTok-related host."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        hostname = hostname.lower()
        if hostname in _REDIRECT_ALLOWED_DOMAINS:
            return True
        for suffix in _REDIRECT_ALLOWED_SUFFIXES:
            if hostname.endswith(suffix):
                return True
        return False
    except Exception:
        return False


def _make_fallback_photos_response(urls):
    """Return a jsonify'd success response for fallback photo results."""
    images = [{'url': u, 'index': i + 1} for i, u in enumerate(urls)]
    return jsonify({
        'success': True,
        'count': len(urls),
        'images': images,
        'photos': urls,  # backward compat
    })


def _extract_photos_fallback(url):
    """
    Fallback extractor for TikTok photo/slideshow posts.
    Fetches the TikTok page HTML, parses embedded JSON state, and extracts image URLs.
    Returns a list of valid image URLs, or None on failure.
    """
    desktop_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.tiktok.com/',
    }
    mobile_headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.tiktok.com/',
    }

    for headers in (desktop_headers, mobile_headers):
        result = _try_extract_photos(url, headers)
        if result:
            return result

    return None


def _try_extract_photos(url, headers):
    """
    Attempt to extract photos from TikTok URL with given headers.
    Returns a list of valid image URLs, or None on failure.
    """
    try:
        # Manually follow redirects to validate each hop's hostname (SSRF protection)
        current_url = url
        resp = None
        for _ in range(_MAX_REDIRECTS):
            resp = requests_lib.get(current_url, headers=headers, timeout=15, allow_redirects=False)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get('Location', '')
                if not location:
                    return None
                # Resolve relative redirects against current URL
                location = urljoin(current_url, location)
                if not _is_allowed_redirect_host(location):
                    return None
                current_url = location
            else:
                break
        else:
            # Exceeded max redirects
            return None

        if resp is None or resp.status_code != 200:
            return None

        html = resp.text
        json_data = None

        # Pattern a: __UNIVERSAL_DATA_FOR_REHYDRATION__
        match = re.search(
            r'<script\s+id="__UNIVERSAL_DATA_FOR_REHYDRATION__"\s+type="application/json">\s*(.*?)\s*</script>',
            html, re.DOTALL
        )
        if match:
            try:
                json_data = json.loads(match.group(1))
                images = _extract_images_universal(json_data)
                if images:
                    return images
            except (json.JSONDecodeError, ValueError):
                pass

        # Pattern b: SIGI_STATE script tag
        match = re.search(
            r'<script\s+id="SIGI_STATE"\s+type="application/json">\s*(.*?)\s*</script>',
            html, re.DOTALL
        )
        if match:
            try:
                json_data = json.loads(match.group(1))
                images = _extract_images_sigi(json_data, url)
                if images:
                    return images
            except (json.JSONDecodeError, ValueError):
                pass

        # Pattern c: window['SIGI_STATE'] inline JS assignment
        match = re.search(
            r"window\['SIGI_STATE'\]\s*=\s*(\{.*?\})\s*;",
            html, re.DOTALL
        )
        if match:
            try:
                json_data = json.loads(match.group(1))
                images = _extract_images_sigi(json_data, url)
                if images:
                    return images
            except (json.JSONDecodeError, ValueError):
                pass

        app.logger.info('fallback: no JSON pattern matched for %s', url)
        return None
    except Exception as e:
        app.logger.warning('_try_extract_photos failed: %s', e, exc_info=True)
        return None


def _extract_images_universal(data):
    """Extract image URLs from __UNIVERSAL_DATA_FOR_REHYDRATION__ JSON structure."""
    try:
        item_struct = (
            data.get("__DEFAULT_SCOPE__", {})
            .get("webapp.video-detail", {})
            .get("itemInfo", {})
            .get("itemStruct", {})
        )
        image_post = item_struct.get("imagePost", {})
        images_list = image_post.get("images", [])
        if not images_list:
            return None

        result = []
        for img in images_list:
            image_url = img.get("imageURL", {})
            url_list = image_url.get("urlList", [])
            if url_list:
                candidate = url_list[0]
                if _is_allowed_cdn_url(candidate):
                    result.append(candidate)
        return result if result else None
    except Exception:
        return None


def _extract_images_sigi(data, url=None):
    """Extract image URLs from SIGI_STATE JSON structure."""
    try:
        item_module = data.get("ItemModule", {})
        if not item_module:
            return None

        # Try to extract item ID from the URL to prefer matching entry
        item_id = None
        if url:
            id_match = re.search(r'/(?:photo|video)/(\d+)', url)
            if id_match:
                item_id = id_match.group(1)

        def _images_from_item(item):
            """Extract validated image URLs from an item dict."""
            if not isinstance(item, dict):
                return None
            image_post = item.get("imagePost", {})
            if not image_post:
                return None
            images_list = image_post.get("images", [])
            if not images_list:
                return None
            result = []
            for img in images_list:
                image_url = img.get("imageURL", {})
                url_list = image_url.get("urlList", [])
                if url_list:
                    candidate = url_list[0]
                    if _is_allowed_cdn_url(candidate):
                        result.append(candidate)
            return result if result else None

        # If we have an item ID, try to match it directly
        if item_id and item_id in item_module:
            images = _images_from_item(item_module[item_id])
            if images:
                return images

        # Fall back to first entry that has images
        for item_key in item_module:
            images = _images_from_item(item_module[item_key])
            if images:
                return images
        return None
    except Exception:
        return None


@app.route('/photos', methods=['POST'])
def photos():
    if request.is_json:
        data = request.get_json(silent=True) or {}
        url = data.get('url', '').strip()
    else:
        url = (request.form.get('url') or '').strip()

    if not url:
        return jsonify({'success': False, 'error': 'Masukkan link TikTok dulu'}), 400

    if not _is_valid_tiktok_url(url):
        return jsonify({'success': False, 'error': 'URL tidak valid atau bukan link TikTok'}), 400

    # Rate limiting
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    if not _check_rate_limit(client_ip, _rate_store_photos):
        return jsonify({'success': False, 'error': 'Terlalu cepat, coba lagi beberapa saat'}), 429

    # PRIMARY: Try custom fallback extractor first
    fallback_photos = _extract_photos_fallback(url)
    if fallback_photos:
        return _make_fallback_photos_response(fallback_photos)

    # SECONDARY: Fall back to yt-dlp if custom extractor returned nothing
    try:
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'noplaylist': False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return jsonify({'success': False, 'error': 'PHOTO slideshow belum tersedia untuk link ini.'}), 400

        # Check if it's a slideshow/photo post
        photo_urls = []

        if info.get('_type') == 'playlist' and info.get('entries'):
            # It's a slideshow - extract image URLs from entries
            for entry in info['entries']:
                if entry and entry.get('url'):
                    photo_urls.append(entry['url'])
                elif entry and entry.get('thumbnails'):
                    # Some versions put the image in thumbnails
                    for thumb in entry['thumbnails']:
                        if thumb.get('url'):
                            photo_urls.append(thumb['url'])
                            break
        elif info.get('thumbnails'):
            # Try to find images in format list or thumbnails for single-image posts
            formats = info.get('formats', [])
            for fmt in formats:
                if fmt.get('vcodec') == 'none' and fmt.get('acodec') == 'none':
                    if fmt.get('url') and any(ext in fmt.get('url', '') for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                        photo_urls.append(fmt['url'])

        if not photo_urls:
            return jsonify({'success': False, 'error': 'PHOTO slideshow belum tersedia untuk link ini.'}), 400

        images = [{'url': u, 'index': i + 1} for i, u in enumerate(photo_urls)]
        result = {
            'success': True,
            'images': images,
            'count': len(photo_urls),
            'photos': photo_urls,  # backward compat
        }
        if info.get('title'):
            result['title'] = info['title'][:80]
        if info.get('uploader'):
            result['uploader'] = info['uploader']
        if info.get('thumbnail'):
            result['thumbnail'] = info['thumbnail']

        return jsonify(result)

    except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError) as e:
        msg = str(e)
        if 'Sign in' in msg or 'login' in msg.lower():
            return jsonify({'success': False, 'error': 'Konten ini memerlukan login TikTok'}), 400
        return jsonify({'success': False, 'error': 'PHOTO slideshow belum tersedia untuk link ini.'}), 400
    except Exception as e:
        app.logger.warning('/photos endpoint failed: %s', e, exc_info=True)
        return jsonify({'success': False, 'error': 'PHOTO slideshow belum tersedia untuk link ini.'}), 502


@app.route('/photo-proxy')
def photo_proxy():
    import requests as req_lib

    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'error': 'URL parameter required'}), 400

    # Validate URL against CDN allowlist (SSRF protection)
    if not _is_allowed_cdn_url(url):
        return jsonify({'error': 'Invalid URL'}), 400

    # Rate limiting
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    if not _check_proxy_rate_limit(client_ip):
        return jsonify({'error': 'Too many requests'}), 429

    MAX_PROXY_BYTES = 20 * 1024 * 1024  # 20 MB

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.tiktok.com/',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        }
        resp = req_lib.get(url, headers=headers, timeout=15, stream=True, allow_redirects=False)

        if resp.status_code != 200:
            return '', 502

        content_type = resp.headers.get('Content-Type', 'image/jpeg')
        # Ensure it's actually an image
        if not content_type.startswith('image/'):
            content_type = 'image/jpeg'

        def generate():
            bytes_sent = 0
            for chunk in resp.iter_content(chunk_size=8192):
                bytes_sent += len(chunk)
                if bytes_sent > MAX_PROXY_BYTES:
                    break
                yield chunk

        return Response(
            generate(),
            content_type=content_type,
            headers={
                'Cache-Control': 'public, max-age=86400',
                'Access-Control-Allow-Origin': '*',
            }
        )
    except Exception:
        return '', 502


@app.route('/download-photo')
def download_photo():
    import requests as req_lib

    url = request.args.get('url', '').strip()
    filename = request.args.get('filename', 'miitok_photo.jpg').strip()

    if not url:
        return jsonify({'error': 'URL parameter required'}), 400

    # Validate URL against CDN allowlist (SSRF protection)
    if not _is_allowed_cdn_url(url):
        return jsonify({'error': 'Invalid URL'}), 400

    # Rate limiting
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    if not _check_proxy_rate_limit(client_ip):
        return jsonify({'error': 'Too many requests'}), 429

    # Sanitize filename
    filename = re.sub(r'[^\w\-_.]', '_', filename)
    if not filename.endswith(('.jpg', '.jpeg', '.png', '.webp')):
        filename += '.jpg'

    MAX_PROXY_BYTES = 20 * 1024 * 1024  # 20 MB

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.tiktok.com/',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        }
        resp = req_lib.get(url, headers=headers, timeout=15, stream=True, allow_redirects=False)

        if resp.status_code != 200:
            return jsonify({'error': 'Gagal mengunduh foto'}), 502

        content_type = resp.headers.get('Content-Type', 'image/jpeg')
        if not content_type.startswith('image/'):
            content_type = 'image/jpeg'

        def generate():
            bytes_sent = 0
            for chunk in resp.iter_content(chunk_size=8192):
                bytes_sent += len(chunk)
                if bytes_sent > MAX_PROXY_BYTES:
                    break
                yield chunk

        return Response(
            generate(),
            content_type=content_type,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Access-Control-Allow-Origin': '*',
            }
        )
    except Exception:
        return jsonify({'error': 'Gagal mengunduh foto'}), 502


@app.route('/api/test-gemini', methods=['GET'])
def test_gemini():
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return jsonify({
            'configured': False,
            'error': 'GEMINI_API_KEY missing',
            'env_debug_url': '/api/test-env'
        })

    # Key exists, try actual API call
    try:
        model = _get_gemini_model()
        if not model:
            return jsonify({
                'configured': False,
                'error': 'Gemini model initialization failed',
                'env_debug_url': '/api/test-env'
            })
        response = model.generate_content("Balas satu kata: aktif")
        reply_text = response.text.strip() if response.text else ''
        return jsonify({
            'configured': True,
            'gemini_key_exists': True,
            'gemini_working': True,
            'reply': reply_text
        })
    except Exception as e:
        err_msg = str(e)
        # Redact API key from error message
        if api_key:
            err_msg = err_msg.replace(api_key, '[REDACTED]')
        return jsonify({
            'configured': True,
            'gemini_key_exists': True,
            'gemini_working': False,
            'error': err_msg
        })


def _filter_makima_output(text, user_message=''):
    """Filter AI output to keep Makima honest, readable, and safe."""
    if not text:
        return text

    safe_web_reply = 'Aku belum bisa mengecek web langsung dari sini. Kirim link atau screenshot-nya, nanti aku bantu baca.'
    original = str(text).strip()
    text_lower = original.lower()

    # If the model falsely claims browsing/search/link access, replace the whole reply.
    forbidden_browsing_claims = [
        'setelah mencari di web',
        'setelah saya mencari di web',
        'saya menemukan sumber',
        'berikut hasil pencarian',
        'saya membuka website',
        'saya sudah mengakses link',
        'saya mengakses link',
        'saya sudah membuka link',
        'saya membuka link',
        'setelah browsing',
        'saya browsing',
        'berdasarkan hasil pencarian',
        'menurut hasil pencarian',
        'hasil penelusuran web',
        'setelah menelusuri web',
    ]
    if any(phrase in text_lower for phrase in forbidden_browsing_claims):
        return safe_web_reply

    user_lower = str(user_message or '').lower()
    user_requested_ascii = any(word in user_lower for word in ('ascii', 'gambar teks', 'text art', 'ascii art'))
    has_ascii_art = _looks_like_ascii_art(original)
    if has_ascii_art and not user_requested_ascii:
        return 'Aku tidak akan membuat gambar palsu dari teks kalau kamu tidak memintanya. Kalau kamu butuh, aku bisa bantu buat prompt atau struktur desainnya.'

    # Remove fabricated URLs, while preserving markdown/newlines/code blocks.
    original = re.sub(r'https?://[^\s\)\]]+', '', original)

    # Replace Anda safely without flattening markdown formatting.
    original = original.replace('Anda', 'kamu')
    original = re.sub(r'\banda\b', 'kamu', original, flags=re.IGNORECASE)

    # Remove stiff template closing questions.
    template_patterns = [
        r'Apakah kamu ingin saya membantu[^.?!\n]*[.?!]?',
        r'Ada yang bisa saya bantu[^.?!\n]*[.?!]?',
        r'Apakah ada yang ingin[^.?!\n]*[.?!]?',
        r'Mau saya bantu[^.?!\n]*[.?!]?',
    ]
    for pattern in template_patterns:
        original = re.sub(pattern, '', original, flags=re.IGNORECASE)

    # Clean spacing per line without destroying paragraphs or code blocks.
    lines = [re.sub(r'[ \t]{2,}', ' ', line).rstrip() for line in original.splitlines()]
    cleaned = '\n'.join(lines).strip()
    cleaned = re.sub(r'\n{4,}', '\n\n\n', cleaned)
    cleaned = re.sub(r'\s+([.!?,])', r'\1', cleaned)
    return cleaned or safe_web_reply


def _looks_like_ascii_art(text):
    """Detect obvious non-code ASCII/text drawings in model output."""
    if '```' in text:
        # Code examples often contain symbols; do not treat fenced code as fake art.
        return False
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if len(lines) < 4:
        return False
    art_chars = set('/\\|_-=+*#~`^<>[]{}().,:;\'"')
    symbol_heavy = 0
    for line in lines:
        stripped = line.strip()
        if len(stripped) < 6:
            continue
        symbol_count = sum(1 for ch in stripped if ch in art_chars)
        if symbol_count / max(len(stripped), 1) >= 0.55:
            symbol_heavy += 1
    return symbol_heavy >= 3


def _parse_makima_image_payload(image_payload):
    """Validate and convert a MAKIMA image payload into a Gemini inline_data part."""
    if not isinstance(image_payload, dict):
        raise ValueError('Format gambar tidak valid.')

    raw_data = str(image_payload.get('data', '') or '')
    mime_type = str(image_payload.get('mimeType', '') or '').lower().strip()
    allowed_mime_types = {'image/jpeg', 'image/png', 'image/webp'}

    if raw_data.startswith('data:'):
        header, _, encoded = raw_data.partition(',')
        match = re.match(r'^data:([^;]+);base64$', header, flags=re.IGNORECASE)
        if not match:
            raise ValueError('Format gambar tidak valid.')
        mime_type = match.group(1).lower().strip()
        raw_data = encoded

    if mime_type in {'image/jpg', 'image/pjpeg'}:
        mime_type = 'image/jpeg'
    if mime_type not in allowed_mime_types:
        raise ValueError('Format gambar harus JPG, PNG, atau WEBP.')

    try:
        image_bytes = base64.b64decode(raw_data, validate=True)
    except Exception:
        raise ValueError('Gambar gagal dibaca. Coba upload ulang dengan format JPG, PNG, atau WEBP.')

    if not image_bytes:
        raise ValueError('Gambar kosong. Coba upload ulang.')
    if len(image_bytes) > 5 * 1024 * 1024:
        raise ValueError('Ukuran gambar maksimal 5MB.')

    return {'mime_type': mime_type, 'data': image_bytes}



def _get_makima_access_password():
    return os.environ.get('MAKIMA_ADMIN_PASSWORD', '') or 'MYBINI02'


def _is_valid_makima_access_key(provided_password):
    expected_password = _get_makima_access_password()
    if not isinstance(provided_password, str) or not provided_password:
        return False
    return hmac.compare_digest(provided_password, expected_password)


@app.route('/api/makima-access', methods=['POST'])
def makima_access():
    data = request.get_json(silent=True) or {}
    if _is_valid_makima_access_key(data.get('password', '')):
        return jsonify({'ok': True})
    return jsonify({'error': 'ACCESS DENIED'}), 403


@app.route('/api/ai-chat', methods=['POST'])
def ai_chat():
    data = request.get_json(silent=True) or {}
    message = data.get('message', '').strip()
    image_payload = data.get('image')
    has_image = isinstance(image_payload, dict) and bool(image_payload.get('data'))

    if not message and not has_image:
        return jsonify({'error': 'Pesan atau gambar tidak boleh kosong'}), 400

    if len(message) > 2000:
        return jsonify({'error': 'Pesan terlalu panjang (maks 2000 karakter)'}), 400

    # Password protection: always require the access gate key for MAKIMA AI.
    if not _is_valid_makima_access_key(data.get('password', '')):
        return jsonify({'error': 'ACCESS DENIED'}), 403

    # Rate limiting
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    if not _check_rate_limit(client_ip, _rate_store_ai, RATE_LIMIT_AI_SECONDS):
        return jsonify({'error': 'Terlalu cepat, coba lagi beberapa saat'}), 429

    # Provider and model selection
    provider = data.get('provider', 'auto').strip().lower()
    model = data.get('model', 'gemini-2.0-flash').strip()
    if provider not in ('auto', 'gemini', 'groq'):
        provider = 'auto'
    if has_image:
        provider = 'gemini'
        if model not in _GEMINI_ALLOWED_MODELS:
            model = 'gemini-2.0-flash'

    image_part = None
    if has_image:
        try:
            image_part = _parse_makima_image_payload(image_payload)
        except ValueError as image_error:
            return jsonify({'error': str(image_error)}), 400

    # Build conversation context from history
    history = data.get('history', [])
    if not isinstance(history, list):
        history = []
    recent_history = history[-12:] if len(history) > 12 else history

    # Validate total history size to prevent oversized payloads
    MAX_HISTORY_CHARS = 40000
    total_chars = sum(len(entry.get('text', '')) for entry in recent_history if isinstance(entry, dict))
    if total_chars > MAX_HISTORY_CHARS:
        return jsonify({'error': 'History terlalu panjang. Silakan bersihkan riwayat chat.'}), 400

    # Build Gemini-style contents
    def _build_gemini_contents():
        contents = []
        for entry in recent_history:
            if not isinstance(entry, dict):
                continue
            role = entry.get('role', '')
            text = entry.get('text', '')
            if not text:
                continue
            if role == 'assistant':
                contents.append({'role': 'model', 'parts': [text]})
            elif role == 'user':
                contents.append({'role': 'user', 'parts': [text]})
        user_parts = []
        if message:
            user_parts.append(message)
        elif image_part:
            user_parts.append('Tolong baca dan jelaskan gambar ini dengan jelas.')
        if image_part:
            user_parts.append(image_part)
        contents.append({'role': 'user', 'parts': user_parts})
        return contents

    # Build OpenAI-style messages for Groq
    def _build_groq_messages():
        messages = [{'role': 'system', 'content': _MAKIMA_SYSTEM_INSTRUCTION}]
        for entry in recent_history:
            if not isinstance(entry, dict):
                continue
            role = entry.get('role', '')
            text = entry.get('text', '')
            if not text:
                continue
            if role in ('user', 'assistant'):
                messages.append({'role': role, 'content': text})
        messages.append({'role': 'user', 'content': message})
        return messages

    def _call_gemini(gemini_model_name):
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return None, 'not_configured'
        gemini_model = _get_gemini_model(gemini_model_name)
        if not gemini_model:
            return None, 'not_configured'
        contents = _build_gemini_contents()
        try:
            response = gemini_model.generate_content(contents)
            reply_text = response.text if response.text else ''
            if not reply_text:
                return None, 'empty_response'
            return reply_text, None
        except Exception as e:
            err_msg = str(e)
            api_key_val = os.environ.get("GEMINI_API_KEY")
            if api_key_val:
                err_msg = err_msg.replace(api_key_val, '[REDACTED]')
            app.logger.error('Gemini API error: %s', err_msg)
            if '429' in err_msg or 'quota' in err_msg.lower() or 'resource exhausted' in err_msg.lower():
                return None, 'quota'
            return None, 'error'

    def _call_groq(groq_model_name):
        groq_key = os.environ.get("GROQ_API_KEY")
        if not groq_key:
            return None, 'not_configured'
        allowed_groq_models = ['llama-3.1-8b-instant', 'llama-3.3-70b-versatile']
        if groq_model_name not in allowed_groq_models:
            groq_model_name = 'llama-3.1-8b-instant'
        messages = _build_groq_messages()
        try:
            resp = requests_lib.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={
                    'Authorization': 'Bearer ' + groq_key,
                    'Content-Type': 'application/json'
                },
                json={
                    'model': groq_model_name,
                    'messages': messages,
                    'max_tokens': 2048,
                    'temperature': 0.7
                },
                timeout=30
            )
            if resp.status_code == 429:
                return None, 'quota'
            if resp.status_code != 200:
                app.logger.error('Groq API error: status=%d body=%s', resp.status_code, resp.text[:500])
                return None, 'error'
            try:
                resp_data = resp.json()
            except (ValueError, Exception) as json_err:
                app.logger.error('Groq response JSON parse failed: %s body=%s', json_err, resp.text[:500])
                return None, 'error'
            choices = resp_data.get('choices', [])
            if not isinstance(choices, list) or not choices:
                app.logger.error('Groq response missing choices: %s', resp.text[:500])
                return None, 'empty_response'
            content = choices[0].get('message', {}).get('content') if isinstance(choices[0], dict) else None
            if content:
                return content, None
            return None, 'empty_response'
        except Exception as e:
            err_msg = str(e)
            app.logger.error('Groq API error: %s', err_msg)
            return None, 'error'

    if image_part:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return jsonify({'error': 'Vision belum dikonfigurasi. Aktifkan GEMINI_API_KEY dulu.'}), 503
        reply, err = _call_gemini(model if model in _GEMINI_ALLOWED_MODELS else 'gemini-2.0-flash')
        if reply:
            app.logger.info('MAKIMA AI vision provider used: gemini model=%s', model if model in _GEMINI_ALLOWED_MODELS else 'gemini-2.0-flash')
            return jsonify({'reply': _filter_makima_output(reply, message)})
        if err == 'quota':
            return jsonify({'error': 'Kuota Gemini vision sedang habis. Coba lagi nanti.'}), 429
        return jsonify({'error': 'Gambar gagal dibaca. Coba kirim ulang dengan gambar yang lebih jelas.'}), 500

    # Route to provider
    if provider == 'gemini':
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return jsonify({'error': 'API PROVIDER BELUM DIKONFIGURASI.'}), 503
        reply, err = _call_gemini(model)
        if reply:
            app.logger.info('MAKIMA AI provider used: gemini model=%s', model if model in _GEMINI_ALLOWED_MODELS else 'gemini-2.0-flash')
            return jsonify({'reply': _filter_makima_output(reply, message)})
        if err == 'not_configured':
            return jsonify({'error': 'API PROVIDER BELUM DIKONFIGURASI.'}), 503
        if err == 'quota':
            return jsonify({'error': 'KUOTA GEMINI SEDANG HABIS. COBA LAGI NANTI.'}), 429
        return jsonify({'error': 'MAKIMA AI SEDANG TIDAK BISA MERESPONS. COBA LAGI NANTI.'}), 500

    elif provider == 'groq':
        groq_key = os.environ.get("GROQ_API_KEY")
        if not groq_key:
            return jsonify({'error': 'API PROVIDER BELUM DIKONFIGURASI.'}), 503
        reply, err = _call_groq(model)
        if reply:
            app.logger.info('MAKIMA AI provider used: groq model=%s', model)
            return jsonify({'reply': _filter_makima_output(reply, message)})
        if err == 'not_configured':
            return jsonify({'error': 'API PROVIDER BELUM DIKONFIGURASI.'}), 503
        if err == 'quota':
            return jsonify({'error': 'KUOTA GROQ SEDANG HABIS. COBA LAGI NANTI.'}), 429
        return jsonify({'error': 'MAKIMA AI SEDANG TIDAK BISA MERESPONS. COBA LAGI NANTI.'}), 500

    else:
        # Auto mode: try Gemini first, fallback to Groq only on quota error
        gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        groq_key = os.environ.get("GROQ_API_KEY")
        if not gemini_key and not groq_key:
            return jsonify({'error': 'API PROVIDER BELUM DIKONFIGURASI.'}), 503

        if gemini_key:
            reply, err = _call_gemini(model if model in _GEMINI_ALLOWED_MODELS else 'gemini-2.0-flash')
            if reply:
                app.logger.info('MAKIMA AI provider used: gemini model=%s', model if model in _GEMINI_ALLOWED_MODELS else 'gemini-2.0-flash')
                return jsonify({'reply': _filter_makima_output(reply, message)})
            if err != 'quota':
                # Non-quota error from Gemini: return the error, do not fall through to Groq
                if err == 'not_configured':
                    return jsonify({'error': 'API PROVIDER BELUM DIKONFIGURASI.'}), 503
                return jsonify({'error': 'MAKIMA AI SEDANG TIDAK BISA MERESPONS. COBA LAGI NANTI.'}), 500

        # Fallback to Groq (only reached on Gemini quota error or missing Gemini key)
        if groq_key:
            # Respect user's Groq model selection if applicable
            groq_allowed = ['llama-3.1-8b-instant', 'llama-3.3-70b-versatile']
            groq_model = model if model in groq_allowed else 'llama-3.1-8b-instant'
            reply, err = _call_groq(groq_model)
            if reply:
                app.logger.info('MAKIMA AI provider used: groq model=%s', groq_model)
                return jsonify({'reply': _filter_makima_output(reply, message)})
            if err == 'quota':
                return jsonify({'error': 'SEMUA PROVIDER AI SEDANG TIDAK TERSEDIA. COBA LAGI NANTI.'}), 429
            return jsonify({'error': 'SEMUA PROVIDER AI SEDANG TIDAK TERSEDIA. COBA LAGI NANTI.'}), 500

        return jsonify({'error': 'SEMUA PROVIDER AI SEDANG TIDAK TERSEDIA. COBA LAGI NANTI.'}), 500


@app.route('/api/test-env', methods=['GET'])
def test_env():
    import sys
    import platform
    # Find env var names containing GEMINI or GOOGLE (names only, not values)
    env_names = [k for k in os.environ.keys() if 'GEMINI' in k.upper() or 'GOOGLE' in k.upper()]
    return jsonify({
        'gemini_key_exists': bool(os.environ.get("GEMINI_API_KEY")),
        'google_key_exists': bool(os.environ.get("GOOGLE_API_KEY")),
        'env_names': env_names,
        'cwd': os.getcwd(),
        'backend_file': 'app.py',
        'python_version': platform.python_version(),
        'node_version': None
    })



if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
