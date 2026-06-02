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
from urllib.parse import urlparse, urljoin
import requests as requests_lib
import analytics
import google.generativeai as genai

# ---------------------------------------------------------------------------
# Gemini model (lazy initialization for Railway env timing)
# ---------------------------------------------------------------------------
_gemini_model_cache = {}  # {model_name: GenerativeModel}
_gemini_configured = False

_MAKIMA_SYSTEM_INSTRUCTION = (
    'Kamu adalah MAKIMA AI, asisten pribadi pemilik MII NETWORK. '
    'Jawab dengan bahasa Indonesia santai, tenang, elegan, sedikit dingin, dan personal. '
    'Gunakan "kamu", bukan "Anda". '
    'Jawaban pendek, jelas, tidak kaku. Maksimal 1-4 kalimat kecuali user minta teknis. '
    'Jangan terdengar seperti chatbot customer service. '
    'Jangan mengaku sudah browsing atau mengakses web. '
    'Kamu TIDAK punya kemampuan browsing real-time. '
    'Kalau user minta cek web/link terbaru, jawab: '
    '"Aku belum bisa mengecek web langsung dari sini. Tapi aku bisa bantu beri arahan umum atau susun langkah ceknya." '
    'Jangan mengarang link atau URL. '
    'Jangan memberi rekomendasi website spesifik kalau tidak yakin URL-nya benar. '
    'Jangan pura-pura bisa membuat gambar atau video. '
    'Kalau user minta buat gambar, jawab: "Aku belum bisa membuat gambar langsung di sini. Tapi aku bisa buatkan prompt gambarnya." '
    'Jangan tutup jawaban dengan pertanyaan template seperti "Apakah kamu ingin saya membantu..." atau "Ada yang bisa saya bantu lagi?". '
    'Kalau tidak tahu, katakan dengan tenang. '
    'Kalau user minta sesuatu yang belum bisa dilakukan, tawarkan alternatif berupa prompt, langkah, atau ide. '
    'Jangan membahas API key atau sistem internal. '
    'Jangan mengaku manusia. '
    'Ingat informasi penting yang user berikan selama percakapan. '
    '\n\n'
    '== KEMAMPUAN CODING ==\n'
    'Kamu bisa membantu coding: HTML, CSS, JavaScript, Python, Flask, Node.js, UI/UX design, bug fixing, deploy ke Railway/GitHub, integrasi API, frontend dan backend. '
    '\n\n'
    '== GAYA CODING ==\n'
    'Berikan solusi langsung tanpa basa-basi. '
    'Kode harus rapi dan siap pakai. '
    'Penjelasan cukup 1-2 kalimat sebelum kode. '
    'Tulis kode dalam markdown code block. '
    'Kalau ada banyak file, pisahkan dan beri label nama file. '
    'Gunakan bahasa Indonesia natural, panggil user dengan "kamu". '
    '\n\n'
    '== KEAMANAN ==\n'
    'Tolak permintaan membuat: malware, phishing, token stealing, hack, spam, bypass payment, pencurian data, atau kerusakan sistem. '
    'Kalau user minta hal berbahaya, jawab: "Aku tidak bisa bantu membuat itu. Tapi aku bisa bantu buat versi aman, edukasi, atau proteksinya." '
    'Lalu tawarkan alternatif aman: versi edukasi, proteksi, atau penjelasan defensif.'
)

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
print("[TTS] ELEVENLABS_API_KEY exists:", bool(os.getenv("ELEVENLABS_API_KEY")))
print("[TTS] ELEVENLABS_VOICE_ID exists:", bool(os.getenv("ELEVENLABS_VOICE_ID")))

import shutil, subprocess
print("[startup] FFMPEG PATH:", shutil.which("ffmpeg"))
try:
    print(subprocess.check_output(["ffmpeg", "-version"]).decode()[:300])
except Exception as e:
    print("[startup] FFMPEG ERROR:", e)

app = Flask(__name__, static_folder='static', static_url_path='/static')
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
_rate_store_tts = {}       # {ip: last_request_timestamp} for /api/tts

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
        'scan_mode': 'MI NETWORK OBSERVATION'
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


def _filter_makima_output(text):
    """Filter AI output to remove forbidden phrases and patterns."""
    if not text:
        return text

    # Forbidden phrases that indicate fake browsing
    _forbidden_phrases = [
        'setelah mencari',
        'saya menemukan',
        'berikut sumber web',
        'saya mengakses web',
        'setelah saya telusuri',
        'berdasarkan pencarian',
        'saya browsing',
        'saya cari di web',
        'setelah menelusuri',
        'hasil pencarian',
        'saya temukan di web',
        'menurut hasil pencarian',
    ]

    # Check and replace sentences containing forbidden phrases
    sentences = re.split(r'(?<=[.!?])\s+', text)
    filtered_sentences = []
    has_forbidden = False

    for sentence in sentences:
        sentence_lower = sentence.lower()
        contains_forbidden = False
        for phrase in _forbidden_phrases:
            if phrase in sentence_lower:
                contains_forbidden = True
                has_forbidden = True
                break
        if not contains_forbidden:
            filtered_sentences.append(sentence)

    if has_forbidden:
        # Prepend the standard disclaimer if we removed browsing claims
        disclaimer = 'Aku belum bisa mengecek web langsung dari sini.'
        if filtered_sentences:
            text = disclaimer + ' ' + ' '.join(filtered_sentences)
        else:
            text = disclaimer
    else:
        text = ' '.join(filtered_sentences) if filtered_sentences else text

    # Remove fabricated URLs (any http/https links)
    text = re.sub(r'https?://[^\s\)]+', '', text)
    # Clean up extra spaces from removed URLs
    text = re.sub(r'  +', ' ', text).strip()

    # Replace "Anda" with "kamu" (capital Anda is always the pronoun, safe to replace directly)
    text = text.replace('Anda', 'kamu')
    # Use word-boundary regex for lowercase to avoid corrupting words like "tanda", "menandaskan"
    text = re.sub(r'\banda\b', 'kamu', text, flags=re.IGNORECASE)

    # Remove template closing questions
    _template_patterns = [
        r'Apakah kamu ingin saya membantu[^.?!]*[.?!]?',
        r'Ada yang bisa saya bantu[^.?!]*[.?!]?',
        r'Apakah ada yang ingin[^.?!]*[.?!]?',
        r'Mau saya bantu[^.?!]*[.?!]?',
    ]
    for pattern in _template_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    # Final cleanup
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\s+([.!?,])', r'\1', text)

    return text


@app.route('/api/ai-chat', methods=['POST'])
def ai_chat():
    data = request.get_json(silent=True) or {}
    message = data.get('message', '').strip()

    if not message:
        return jsonify({'error': 'Pesan tidak boleh kosong'}), 400

    if len(message) > 2000:
        return jsonify({'error': 'Pesan terlalu panjang (maks 2000 karakter)'}), 400

    # Password protection
    admin_password = os.environ.get('MAKIMA_ADMIN_PASSWORD', '')
    if admin_password:
        provided_password = data.get('password', '')
        if not provided_password or provided_password != admin_password:
            return jsonify({'error': 'MAKIMA AI KHUSUS ADMIN.'}), 403

    # Rate limiting
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    if not _check_rate_limit(client_ip, _rate_store_ai, RATE_LIMIT_AI_SECONDS):
        return jsonify({'error': 'Terlalu cepat, coba lagi beberapa saat'}), 429

    # Provider and model selection
    provider = data.get('provider', 'auto').strip().lower()
    model = data.get('model', 'gemini-2.0-flash').strip()
    if provider not in ('auto', 'gemini', 'groq'):
        provider = 'auto'

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
        contents.append({'role': 'user', 'parts': [message]})
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

    # Route to provider
    if provider == 'gemini':
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return jsonify({'error': 'API PROVIDER BELUM DIKONFIGURASI.'}), 503
        reply, err = _call_gemini(model)
        if reply:
            return jsonify({'reply': _filter_makima_output(reply)})
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
            return jsonify({'reply': _filter_makima_output(reply)})
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
                return jsonify({'reply': _filter_makima_output(reply)})
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
                return jsonify({'reply': _filter_makima_output(reply)})
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


def _add_no_store_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/api/tts-status', methods=['GET'])
def tts_status():
    """Safe ElevenLabs TTS env fingerprint without exposing full secrets."""
    api_key = os.getenv('ELEVENLABS_API_KEY') or ''
    voice_id = os.getenv('ELEVENLABS_VOICE_ID') or ''
    response = jsonify({
        'elevenlabs_key_exists': bool(api_key),
        'elevenlabs_voice_id_exists': bool(voice_id),
        'key_prefix': api_key[:6],
        'key_suffix': api_key[-6:],
        'voice_prefix': voice_id[:6],
        'voice_suffix': voice_id[-6:]
    })
    return _add_no_store_headers(response)


@app.route('/api/tts', methods=['POST'])
def tts():
    """ElevenLabs Text-to-Speech — returns raw MP3 audio on click only."""
    @after_this_request
    def add_tts_no_store_headers(response):
        return _add_no_store_headers(response)

    print("[TTS] /api/tts called")
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()

    api_key = os.environ.get('ELEVENLABS_API_KEY')
    voice_id = os.environ.get('ELEVENLABS_VOICE_ID')

    print("[TTS] text length:", len(text))
    print("[TTS] key exists:", str(bool(api_key)).lower())
    print("[TTS] voice exists:", str(bool(voice_id)).lower())
    print("[TTS] voice id safe:", voice_id[:4] if voice_id else '', voice_id[-4:] if voice_id else '')

    if not text:
        return jsonify({'error': 'Text is required'}), 400

    if not api_key or not voice_id:
        return jsonify({'error': 'ElevenLabs env missing'}), 500

    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    if not _check_rate_limit(ip, _rate_store_tts, 5):
        return jsonify({'error': 'Too many requests'}), 429

    url = f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128'
    payload = {
        'text': text[:300],
        'model_id': 'eleven_multilingual_v2',
        'voice_settings': {
            'stability': 0.45,
            'similarity_boost': 0.8,
            'style': 0.25,
            'use_speaker_boost': True
        }
    }

    try:
        resp = requests_lib.post(
            url,
            headers={
                'xi-api-key': api_key,
                'Content-Type': 'application/json',
                'Accept': 'audio/mpeg'
            },
            json=payload,
            timeout=30
        )

        print("[TTS] elevenlabs status:", resp.status_code)
        print("[TTS] content-type:", resp.headers.get("content-type"))
        print("[TTS] elevenlabs body preview:", resp.text[:300] if not resp.ok else "AUDIO_OK")

        if not resp.ok:
            body_preview = resp.text[:300]
            app.logger.error('ElevenLabs TTS error: status=%d body=%s', resp.status_code, body_preview)
            return jsonify({
                'error': 'ELEVENLABS_FAILED',
                'status': resp.status_code,
                'detail': body_preview
            }), 502

        return Response(resp.content, mimetype='audio/mpeg')

    except Exception as e:
        app.logger.error('TTS exception: %s', str(e))
        return jsonify({
            'error': 'ELEVENLABS_FAILED',
            'status': 502,
            'detail': str(e)[:300]
        }), 502


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
