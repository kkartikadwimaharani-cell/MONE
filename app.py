from flask import Flask, render_template, request, jsonify, send_file, Response, after_this_request, session
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
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(32))

APP_VERSION = "20260615-maintenance-v15"


def versioned_static(path):
    """Build a /static URL with the current deploy version query string."""
    clean_path = path.lstrip('/')
    if clean_path.startswith('static/'):
        clean_path = clean_path[len('static/'):]
    return f"{app.static_url_path}/{clean_path}?v={APP_VERSION}"

analytics.init_db()


# ---------------------------------------------------------------------------
# Maintenance status storage, Telegram bot control panel, and event rewards
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
SITE_STATUS_FILE = os.path.join(DATA_DIR, 'site_status.json')
EVENT_DATA_FILE = os.path.join(DATA_DIR, 'event_data.json')
_STATUS_LOCK = threading.Lock()
_EVENT_LOCK = threading.Lock()
_BOT_SESSION_LOCK = threading.Lock()
_BOT_AUTHENTICATED_CHATS = set()
_BOT_LOGIN_PENDING_CHATS = set()
_BOT_USER_STATES = {}
_BOT_LAST_PANEL_MESSAGES = {}
_BOT_PROCESSED_UPDATE_IDS = set()
_BOT_POLLING_STARTED = False
_BOT_LAST_UPDATE_ID = None
TELEGRAM_CHANNEL_LINK = 'https://t.me/+L0mZsWxq30cxZmM1'
TELEGRAM_CHANNEL_CHAT_ID = (os.environ.get('TELEGRAM_CHANNEL_ID') or os.environ.get('TELEGRAM_EVENT_CHANNEL_ID') or '').strip()
WHATSAPP_GROUP_LINK = 'https://chat.whatsapp.com/DtpSUf90QIOCmxjACXAySl'
TOKEN_TTL_SECONDS = 16 * 24 * 60 * 60


def _utc_timestamp():
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None


def _default_site_status():
    return {
        'maintenance': False,
        'message': 'Kami sedang melakukan pembaruan sistem.',
        'updated_at': _utc_timestamp(),
        'community_name': 'COMMUNITY',
        'community_link': '',
        'telegram_channel_link': 'https://t.me/+L0mZsWxq30cxZmM1'
    }


def _ensure_status_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(SITE_STATUS_FILE):
        with open(SITE_STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(_default_site_status(), f, ensure_ascii=False, indent=2)


def get_site_status():
    with _STATUS_LOCK:
        _ensure_status_file()
        try:
            with open(SITE_STATUS_FILE, 'r', encoding='utf-8') as f:
                status = json.load(f)
        except (OSError, json.JSONDecodeError):
            status = _default_site_status()
        status.setdefault('maintenance', False)
        status.setdefault('message', 'Kami sedang melakukan pembaruan sistem.')
        status.setdefault('updated_at', _utc_timestamp())
        status.setdefault('community_name', 'COMMUNITY')
        status.setdefault('community_link', '')
        status.setdefault('community_btn_label', 'GABUNG')
        status.setdefault('telegram_channel_link', 'https://t.me/+L0mZsWxq30cxZmM1')
        return status


def _save_site_status(status):
    with _STATUS_LOCK:
        _ensure_status_file()
        try:
            with open(SITE_STATUS_FILE, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            if isinstance(existing, dict):
                existing.update(status)
                status = existing
        except (OSError, json.JSONDecodeError):
            pass
        with open(SITE_STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False, indent=2)


def set_maintenance_status(enabled):
    with _STATUS_LOCK:
        _ensure_status_file()
        status = _default_site_status()
        try:
            with open(SITE_STATUS_FILE, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                if isinstance(existing, dict):
                    status.update(existing)
        except (OSError, json.JSONDecodeError):
            pass
        status['maintenance'] = bool(enabled)
        status['updated_at'] = _utc_timestamp()
        with open(SITE_STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
        return status


def _default_event_data():
    return {
        'users': {},
        'event_tokens': {},
        'reward_codes': {},
        'reward_items': [],
        'winning_keys': {},
        'claims': [],
        'event_settings': {
            'bounty_event_status': 'locked',
            'draw_status': 'locked',
            'event_name': 'MII Reward Draw',
            'reward_name': 'CloudMoon Pro 1 Bulan',
            'event_date': '15 Juni 2026',
            'event_time': '20:00 WIB',
            'announcement': '',
            'countdown_seconds': 10,
            'reward_info': 'CloudMoon Pro 1 Bulan',
            'winner': None,
            'winners': [],
            'current_round': 0,
            'win_quota': 1,
        },
    }


def _load_event_data():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(EVENT_DATA_FILE):
        return _default_event_data()
    try:
        with open(EVENT_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = _default_event_data()
    data.setdefault('users', {})
    data.setdefault('event_tokens', {})
    data.setdefault('reward_codes', {})
    data.setdefault('reward_items', [])
    data.setdefault('winning_keys', {})
    data.setdefault('claims', [])
    data.setdefault('event_settings', {})
    data['event_settings'].setdefault('bounty_event_status', 'locked')
    data['event_settings'].setdefault('draw_status', data['event_settings'].get('bounty_event_status', 'locked'))
    data['event_settings'].setdefault('event_name', 'MII Reward Draw')
    data['event_settings'].setdefault('reward_name', data['event_settings'].get('reward_info', 'CloudMoon Pro 1 Bulan'))
    data['event_settings'].setdefault('event_date', '15 Juni 2026')
    data['event_settings'].setdefault('event_time', '20:00 WIB')
    data['event_settings'].setdefault('announcement', '')
    data['event_settings'].setdefault('countdown_seconds', 10)
    data['event_settings'].setdefault('reward_info', data['event_settings'].get('reward_name', 'CloudMoon Pro 1 Bulan'))
    data['event_settings'].setdefault('winner', None)
    data['event_settings'].setdefault('winners', [])
    data['event_settings'].setdefault('current_round', 0)
    data['event_settings'].setdefault('win_quota', 1)
    return data


def _save_event_data(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = EVENT_DATA_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, EVENT_DATA_FILE)


def _user_from_telegram_actor(actor, chat=None):
    actor = actor or {}
    chat = chat or {}
    now = _utc_timestamp()
    return {
        'telegram_user_id': str(actor.get('id') or chat.get('id')),
        'chat_id': str(chat.get('id') or ''),
        'username': actor.get('username') or '', 'first_name': actor.get('first_name') or '', 'last_name': actor.get('last_name') or '',
        'started_at': now, 'telegram_join_verified': False, 'verified': False,
        'token_active': False, 'token': '', 'token_created_at': '', 'token_expired_at': '',
        'token_used_for_event': False, 'reward_claimed': False, 'game_attempts': 0,
        'is_admin': False, 'reward_claims': [], 'reward_status': 'none', 'state': '',
        'start_message_id': None, 'inline_message_id': None, 'last_inline_message_id': None, 'admin_panel_message_id': None, 'last_action_at': now,
    }


def _user_from_message(message):
    return _user_from_telegram_actor((message or {}).get('from') or {}, (message or {}).get('chat') or {})


def _upsert_event_user(message=None, actor=None, chat=None):
    if actor is not None or chat is not None:
        incoming = _user_from_telegram_actor(actor or {}, chat or {})
    else:
        incoming = _user_from_message(message or {})
    uid = incoming['telegram_user_id']
    with _EVENT_LOCK:
        data = _load_event_data()
        user = data['users'].get(uid, incoming)
        for k in ('username', 'first_name', 'last_name', 'chat_id'):
            user[k] = incoming[k]
        user.setdefault('started_at', incoming['started_at'])
        for k, v in incoming.items():
            user.setdefault(k, v)
        user['is_admin'] = _is_admin_chat(uid)
        user.setdefault('reward_claims', [])
        user['last_action_at'] = _utc_timestamp()
        data['users'][uid] = user
        _save_event_data(data)
        return user




def _event_settings(data=None):
    data = data or _load_event_data()
    settings = data.setdefault('event_settings', {})
    settings.setdefault('bounty_event_status', 'locked')
    settings.setdefault('draw_status', settings.get('bounty_event_status', 'locked'))
    settings.setdefault('event_name', 'MII Reward Draw')
    settings.setdefault('reward_name', settings.get('reward_info', 'CloudMoon Pro 1 Bulan'))
    settings.setdefault('event_date', '15 Juni 2026')
    settings.setdefault('event_time', '20:00 WIB')
    settings.setdefault('announcement', '')
    settings.setdefault('countdown_seconds', 10)
    settings.setdefault('reward_info', settings.get('reward_name', 'CloudMoon Pro 1 Bulan'))
    settings.setdefault('winner', None)
    settings.setdefault('winners', [])
    settings.setdefault('current_round', 0)
    return settings


def _bounty_event_status(data=None):
    status = (_event_settings(data).get('draw_status') or _event_settings(data).get('bounty_event_status') or 'locked').strip().lower()
    if status == 'active':
        status = 'open'
    return status if status in {'locked', 'open', 'drawing', 'finished'} else 'locked'


def _set_bounty_event_status(status):
    clean = (status or 'locked').strip().lower()
    if clean == 'active':
        clean = 'open'
    if clean not in {'locked', 'open'}:
        clean = 'locked'
    with _EVENT_LOCK:
        data = _load_event_data()
        settings = data.setdefault('event_settings', {})
        settings['draw_status'] = clean
        settings['bounty_event_status'] = 'active' if clean == 'open' else 'locked'
        settings['updated_at'] = _utc_timestamp()
        _save_event_data(data)
    return clean


def _reward_info_text(data=None):
    return (_event_settings(data).get('reward_info') or '').strip()


def _set_reward_info(text):
    clean = (text or '').strip()[:1200]
    with _EVENT_LOCK:
        data = _load_event_data()
        data.setdefault('event_settings', {})['reward_info'] = clean
        data['event_settings']['reward_info_updated_at'] = _utc_timestamp()
        _save_event_data(data)
    return clean


def _format_reward_info(data=None):
    info = _reward_info_text(data)
    if not info:
        return '🎁 Info Hadiah\nPremium App Random'
    parts = [part.strip() for part in info.split('|') if part.strip()]
    if len(parts) >= 3:
        return (
            '🎁 Info Hadiah\n'
            f'{parts[0]}\n'
            f'Slot: {parts[1]}\n'
            f'Claim: {parts[2]}'
        )
    return '🎁 Info Hadiah\n' + info

def _event_stats(data=None):
    data = data or _load_event_data()
    users = list(data['users'].values())
    return {
        'total_user_start': len(users), 'total_verified': sum(1 for u in users if u.get('verified')),
        'total_token_issued': sum(1 for u in users if u.get('token')), 'total_token_used': sum(1 for u in users if u.get('token_used_for_event') or u.get('token_used')),
        'total_reward_pending': sum(1 for u in users if u.get('reward_status') == 'pending'),
        'total_reward_claimed': len([c for c in data['claims'] if c.get('status') == 'claimed']),
    }


def _is_token_active(user):
    exp = _parse_ts(user.get('token_expired_at'))
    return bool(user.get('token') and exp and exp > datetime.now(timezone.utc))


def _expire_token_record(data, token):
    rec = data.get('event_tokens', {}).get(token)
    if rec and rec.get('status') == 'active':
        rec['status'] = 'expired'
    return rec


def _generate_code(prefix='MII-WIN'):
    return f"{prefix}-2026-{base64.b32encode(os.urandom(3)).decode('ascii').rstrip('=')[:4]}"


def _normalize_reward_expires(value):
    value = (value or '').strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return value + 'T23:59:59+00:00'
    return value


def validate_event_token(token):
    token = (token or '').strip().upper()
    with _EVENT_LOCK:
        data = _load_event_data()
        status = _bounty_event_status(data)
        if status != 'open':
            return False, None, 'Event draw belum dibuka.' if status == 'locked' else 'Event sudah tidak menerima token baru.'
        rec = data.get('event_tokens', {}).get(token)
        user = data['users'].get(str(rec.get('telegram_user_id'))) if rec else None
        if not rec or not user or not user.get('verified'):
            return False, None, 'Token tidak valid atau belum terdaftar.'
        if rec.get('joined_draw') or rec.get('draw_status') in {'joined', 'winner', 'lose'}:
            return False, None, 'Token ini sudah terdaftar di event draw.'
        now = _utc_timestamp()
        rec['joined_draw'] = True
        rec['draw_status'] = 'joined'
        rec['joined_at'] = now
        user['token_used_for_event'] = True
        user['token_used'] = True
        user['last_action_at'] = now
        data['users'][str(user.get('telegram_user_id'))] = user
        _save_event_data(data)
        return True, user, ''

def _new_token():
    return 'MII-DRAW-2026-' + base64.b32encode(os.urandom(4)).decode('ascii').rstrip('=')[:6]


def _claim_or_get_token(uid):
    uid = str(uid)
    with _EVENT_LOCK:
        data = _load_event_data()
        user = data['users'].get(uid)
        if not user or not user.get('verified'):
            return None, '❌ Kamu belum verifikasi Channel Telegram.'
        if user.get('token'):
            return user, (
                '🎟 TOKEN KAMU SUDAH TERDAFTAR\n\n'
                'Token:\n'
                f'{_md_code(user.get("token", "-"))}\n\n'
                'Telegram ID:\n'
                f'{_md_code(uid)}\n\n'
                'Masukkan token ini di halaman MII Reward Draw:\n'
                'https://makima.cloud/bounty\n\n'
                '1 akun Telegram hanya bisa memiliki 1 token event.'
            )
        token = _new_token()
        while token in data.get('event_tokens', {}):
            token = _new_token()
        now = _utc_timestamp()
        user.update({'token': token, 'token_active': True, 'token_created_at': now, 'token_expired_at': '', 'token_used_for_event': False, 'reward_claimed': False, 'last_action_at': now})
        data['event_tokens'][token] = {
            'token': token,
            'telegram_id': uid,
            'telegram_user_id': uid,
            'username': user.get('username', ''),
            'first_name': user.get('first_name', ''),
            'created_at': now,
            'status': 'active',
            'joined_draw': False,
            'draw_status': 'unused',
            'result': 'none',
            'winning_key': '',
            'reward_claimed': False,
        }
        data['users'][uid] = user
        _save_event_data(data)
        return user, (
            '🎟 TOKEN EVENT KAMU\n\n'
            'Token:\n'
            f'{_md_code(token)}\n\n'
            'Telegram ID:\n'
            f'{_md_code(uid)}\n\n'
            'Masukkan token ini di halaman MII Reward Draw:\n'
            'https://makima.cloud/bounty\n\n'
            '1 akun Telegram hanya bisa memiliki 1 token event.'
        )


def _valid_draw_tokens(data):
    return [r for r in data.get('event_tokens', {}).values() if r.get('joined_draw') and r.get('draw_status') == 'joined' and r.get('token')]


def _public_winner(rec):
    return {
        'token': rec.get('token', ''),
        'telegram_id': str(rec.get('telegram_id') or rec.get('telegram_user_id') or ''),
        'username': rec.get('username', ''),
        'first_name': rec.get('first_name', ''),
        'round': rec.get('round') or rec.get('draw_round') or 0,
        'selected_at': rec.get('selected_at') or rec.get('created_at', ''),
    }

def _draw_status_payload(data=None):
    data = data or _load_event_data()
    settings = _event_settings(data)
    status = _bounty_event_status(data)
    winners = [_public_winner(w) for w in settings.get('winners', [])]
    return {
        'draw_status': status,
        'event_name': settings.get('event_name', 'MII Reward Draw'),
        'reward_name': settings.get('reward_name') or _reward_info_text(data) or 'CloudMoon Pro 1 Bulan',
        'event_date': settings.get('event_date', ''),
        'event_time': settings.get('event_time', ''),
        'announcement': settings.get('announcement', ''),
        'countdown_seconds': int(settings.get('countdown_seconds') or 10),
        'current_round': int(settings.get('current_round') or (len(winners) if status == 'finished' else 0)),
        'total_tokens': len(_valid_draw_tokens(data)) + len(winners),
        'reward_stock': sum(1 for i in data.get('reward_items', []) if not i.get('used')),
        'slot_winner': int(settings.get('win_quota') or 1),
        'total_winners': len(winners),
        'winners': winners,
        'winner': winners[-1] if winners and status == 'finished' else None,
    }




def _token_room_payload(token, data=None):
    token = (token or '').strip().upper()
    data = data or _load_event_data()
    rec = data.get('event_tokens', {}).get(token)
    if not rec:
        return None
    user = data.get('users', {}).get(str(rec.get('telegram_user_id') or rec.get('telegram_id')))
    if not user or not user.get('verified'):
        return None
    result = rec.get('result') or 'none'
    draw_status = rec.get('draw_status') or 'unused'
    is_winner = draw_status == 'winner' or result == 'win'
    is_loser = draw_status in {'lose', 'lost'} or result in {'lose', 'lost'}
    return {
        'valid': True,
        'token': rec.get('token') or token,
        'joined_draw': bool(rec.get('joined_draw')),
        'joined_at': rec.get('joined_at', ''),
        'draw_status': draw_status,
        'result': 'winner' if is_winner else ('not_winner' if is_loser else result),
        'is_winner': is_winner,
        'is_loser': is_loser,
        'round': rec.get('round') or rec.get('draw_round') or 0,
    }

def _run_web_draw(token):
    ok, user, error = validate_event_token(token)
    if not ok:
        status = 423 if 'dibuka' in error or 'tidak menerima' in error else 409
        return None, error, status
    return {'result': 'joined', 'message': 'Token kamu berhasil masuk ke MII Reward Draw.', 'telegram_id': user.get('telegram_user_id')}, '', 200

def _start_reward_draw():
    notify = []
    with _EVENT_LOCK:
        data = _load_event_data()
        settings = _event_settings(data)
        if _bounty_event_status(data) == 'locked':
            return None, 'locked'
        if _bounty_event_status(data) == 'finished' and settings.get('winners'):
            return settings['winners'][-1], 'finished'
        tokens = _valid_draw_tokens(data)
        if not tokens:
            return None, 'empty'
        stock = [i for i in data.get('reward_items', []) if not i.get('used')]
        if not stock:
            return None, 'no_stock'
        quota = max(1, int(settings.get('win_quota') or len(stock) or 1))
        quota = min(quota, len(stock), len(tokens))
        settings['draw_status'] = 'drawing'
        settings['bounty_event_status'] = 'locked'
        settings['winners'] = []
        settings['current_round'] = 0
        pool = list(tokens)
        now = _utc_timestamp()
        for round_no in range(1, quota + 1):
            idx = int.from_bytes(os.urandom(8), 'big') % len(pool)
            rec = pool.pop(idx)
            winning_key = _generate_code('MII-WIN')
            while winning_key in data.get('winning_keys', {}):
                winning_key = _generate_code('MII-WIN')
            rec.update({'status': 'winner', 'draw_status': 'winner', 'result': 'win', 'winning_key': winning_key, 'selected_at': now, 'round': round_no})
            key_rec = {'winning_key': winning_key, 'token': rec.get('token',''), 'telegram_id': str(rec.get('telegram_id') or rec.get('telegram_user_id')), 'username': rec.get('username',''), 'first_name': rec.get('first_name',''), 'event_id': 'mii-reward-draw-2026', 'round': round_no, 'reward_id': '', 'used': False, 'reward_sent': False, 'created_at': now, 'used_at': ''}
            data.setdefault('winning_keys', {})[winning_key] = key_rec
            settings['winners'].append(key_rec)
            settings['current_round'] = round_no
            user = data.get('users', {}).get(key_rec['telegram_id'])
            if user:
                user['reward_status'] = 'winner'; user['last_action_at'] = now
            notify.append(key_rec)
        for rec in pool:
            rec['draw_status'] = 'lose'; rec['result'] = 'lose'; rec['status'] = 'active'
        settings['winner'] = settings['winners'][-1] if settings['winners'] else None
        settings['draw_status'] = 'finished'
        settings['updated_at'] = now
        _save_event_data(data)
    for win in notify:
        _telegram_send_message(win['telegram_id'], '🏆 SELAMAT KAMU MENANG\n\nToken:\n' + _md_code(win['token']) + '\n\nWinning Key:\n' + _md_code(win['winning_key']) + '\n\nKlik Claim Reward untuk mengambil hadiah kamu.', _user_keyboard(), parse_mode='Markdown')
    return (notify[-1] if notify else None), 'selected'


def _reset_reward_draw():
    with _EVENT_LOCK:
        data = _load_event_data()
        settings = _event_settings(data)
        for rec in data.get('event_tokens', {}).values():
            if rec.get('status') == 'winner':
                rec['status'] = 'active'
                rec.pop('selected_at', None)
        settings['winner'] = None
        settings['winners'] = []
        settings['current_round'] = 0
        settings['draw_status'] = 'locked'
        settings['bounty_event_status'] = 'locked'
        settings['updated_at'] = _utc_timestamp()
        _save_event_data(data)


def _format_expiry(value):
    dt = _parse_ts(value) if value else None
    if not dt:
        return '-'
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M')


def _md_code(value):
    return '`' + str(value).replace('`', "'") + '`'

def _telegram_api_url(method):
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    return f'https://api.telegram.org/bot{token}/{method}' if token else None


def _telegram_send_message(chat_id, text, reply_markup=None, parse_mode=None):
    url = _telegram_api_url('sendMessage')
    if not url:
        app.logger.warning('Telegram bot token is not configured.'); return None
    payload = {'chat_id': chat_id, 'text': text}
    if parse_mode:
        payload['parse_mode'] = parse_mode
    if reply_markup is not None: payload['reply_markup'] = reply_markup
    try:
        response = requests_lib.post(url, json=payload, timeout=10)
        return response
    except Exception as exc: app.logger.warning('Telegram sendMessage failed: %s', exc); return None


def _telegram_edit_message(chat_id, message_id, text, reply_markup=None):
    url = _telegram_api_url('editMessageText')
    if not url or not message_id: return None
    payload = {'chat_id': chat_id, 'message_id': message_id, 'text': text}
    if reply_markup is not None: payload['reply_markup'] = reply_markup
    try:
        response = requests_lib.post(url, json=payload, timeout=10)
        return response if response.ok else None
    except Exception as exc: app.logger.warning('Telegram editMessageText failed: %s', exc); return None




def _telegram_edit_reply_markup(chat_id, message_id, reply_markup=None):
    url = _telegram_api_url('editMessageReplyMarkup')
    if not url or not message_id:
        return None
    payload = {'chat_id': chat_id, 'message_id': message_id, 'reply_markup': reply_markup}
    try:
        response = requests_lib.post(url, json=payload, timeout=10)
        return response if response.ok else None
    except Exception as exc:
        app.logger.warning('Telegram editMessageReplyMarkup failed: %s', exc)
        return None


def _telegram_delete_message(chat_id, message_id):
    url = _telegram_api_url('deleteMessage')
    if not url or not message_id:
        return None
    try:
        response = requests_lib.post(url, json={'chat_id': chat_id, 'message_id': message_id}, timeout=10)
        return response if response.ok else None
    except Exception as exc:
        app.logger.warning('Telegram deleteMessage failed: %s', exc)
        return None

def _telegram_show_panel(chat_id, text, reply_markup, message_id=None):
    mid = message_id or _BOT_LAST_PANEL_MESSAGES.get(str(chat_id))
    if mid and _telegram_edit_message(chat_id, mid, text, reply_markup):
        return mid
    response = _telegram_send_message(chat_id, text, reply_markup)
    new_mid = _response_message_id(response)
    if new_mid:
        _BOT_LAST_PANEL_MESSAGES[str(chat_id)] = new_mid
    return new_mid


def _telegram_answer_callback(callback_query_id):
    url = _telegram_api_url('answerCallbackQuery')
    if url and callback_query_id:
        try: requests_lib.post(url, json={'callback_query_id': callback_query_id}, timeout=10)
        except Exception as exc: app.logger.warning('Telegram answerCallbackQuery failed: %s', exc)


def _telegram_get_chat_member(user_id):
    url = _telegram_api_url('getChatMember')
    if not url or not TELEGRAM_CHANNEL_CHAT_ID:
        return 'error'
    try:
        resp = requests_lib.post(url, json={'chat_id': TELEGRAM_CHANNEL_CHAT_ID, 'user_id': user_id}, timeout=10)
        data = resp.json() if resp.ok else {}
        if not resp.ok or not data.get('ok'):
            app.logger.warning('Telegram getChatMember failed: %s', data or resp.text[:300])
            return 'error'
        status = ((data.get('result') or {}).get('status') or '').lower()
        return 'joined' if status in {'creator', 'administrator', 'member'} else 'not_joined'
    except Exception as exc:
        app.logger.warning('Telegram getChatMember failed: %s', exc); return 'error'


def getAdminIdFromEnv():
    return (os.environ.get('TELEGRAM_ADMIN_CHAT_ID') or os.environ.get('TELEGRAM_ADMIN_ID') or '').strip()


def isAdmin(user_id):
    admin_id = getAdminIdFromEnv()
    return bool(admin_id and user_id is not None and str(user_id).strip() == str(admin_id).strip())


def checkAdminPassword(input_value):
    expected = (os.environ.get('BOT_ADMIN_PASSWORD') or os.environ.get('ADMIN_PASSWORD') or '').strip()
    supplied = (input_value or '').strip()
    return bool(expected and supplied and hmac.compare_digest(supplied, expected))


def _admin_chat_id(): return getAdminIdFromEnv()
def _is_admin_chat(user_id): return isAdmin(user_id)
def _is_logged_in(chat_id):
    with _BOT_SESSION_LOCK: return str(chat_id) in _BOT_AUTHENTICATED_CHATS


def _reply_keyboard(rows):
    return {'keyboard': [[{'text': item} for item in row] for row in rows], 'resize_keyboard': True, 'one_time_keyboard': False}


def _inline_url_keyboard(text, url):
    return {'inline_keyboard': [[{'text': text, 'url': url}]]}


def _start_inline_keyboard():
    return {
        'inline_keyboard': [
            [{'text': '📢 Join Channel Telegram', 'url': TELEGRAM_CHANNEL_LINK}],
            [{'text': '💬 Join Grup WhatsApp', 'url': WHATSAPP_GROUP_LINK}],
            [{'text': '✅ Verifikasi Join', 'callback_data': 'event_verify'}],
        ]
    }


def _user_keyboard():
    return _reply_keyboard([
        ['🎟 Claim Token', '🎁 Claim Reward'],
        ['🌐 Buka MII Reward Draw', '📦 Reward Saya'],
        ['🏠 Menu Utama'],
    ])


def _claim_keyboard():
    return _reply_keyboard([['❌ Batal'], ['🏠 Menu Utama']])


def _admin_keyboard():
    maintenance_enabled = bool(get_site_status().get('maintenance'))
    maintenance_button = '🔴 Matikan Maintenance' if maintenance_enabled else '🟢 Hidupkan Maintenance'
    return _reply_keyboard([
        [maintenance_button],
        ['🟢 Open Event', '🔒 Lock Event'],
        ['🎲 Start Draw', '⚙️ Event Settings'],
        ['📦 Reward Stock', '👥 Token List'],
        ['🏆 Winner List', '📊 Status'],
        ['♻️ Reset Event', '🎁 Info Hadiah'],
        ['🔗 Community Link', '📢 Telegram Channel'],
        ['🏠 Menu Utama', '🔐 Logout'],
    ])


def _unverified_start_text():
    return (
        '🎟 MII REWARD DRAW\n\n'
        '1. Join Channel Telegram.\n'
        '2. Grup WhatsApp opsional.\n'
        '3. Tekan Verifikasi Join untuk membuka menu event.'
    )


def _verified_menu_text():
    return '✅ MII REWARD DRAW aktif untuk akun kamu.\nPilih menu di bawah.'


def _response_message_id(response):
    if not response:
        return None
    try:
        if not response.ok:
            return None
        return (response.json().get('result') or {}).get('message_id')
    except Exception:
        return None


def _save_user_message_ids(uid, **message_ids):
    clean_ids = {k: v for k, v in message_ids.items() if v is not None}
    if not clean_ids:
        return
    with _EVENT_LOCK:
        data = _load_event_data()
        user = data['users'].get(str(uid))
        if not user:
            return
        user.update(clean_ids)
        user['last_action_at'] = _utc_timestamp()
        data['users'][str(uid)] = user
        _save_event_data(data)



def _clear_user_inline_join_buttons(chat_id, user, current_message_id=None):
    message_ids = []
    for message_id in (current_message_id, user.get('inline_message_id'), user.get('last_inline_message_id'), user.get('start_message_id')):
        if message_id and message_id not in message_ids:
            message_ids.append(message_id)
    for message_id in message_ids:
        if _telegram_edit_reply_markup(chat_id, message_id, None):
            continue
        _telegram_delete_message(chat_id, message_id)
    _save_user_message_ids(user['telegram_user_id'], inline_message_id=0, last_inline_message_id=0)

def show_unverified_start(chat_id, user=None):
    existing_id = None
    if user:
        existing_id = user.get('start_message_id') or user.get('inline_message_id') or user.get('last_inline_message_id')
    if existing_id and _telegram_edit_message(chat_id, existing_id, _unverified_start_text(), _start_inline_keyboard()):
        if user:
            _save_user_message_ids(
                user['telegram_user_id'],
                start_message_id=existing_id,
                inline_message_id=existing_id,
                last_inline_message_id=existing_id,
            )
        return
    response = _telegram_send_message(chat_id, _unverified_start_text(), _start_inline_keyboard())
    message_id = _response_message_id(response)
    if user and message_id:
        _save_user_message_ids(user['telegram_user_id'], start_message_id=message_id, inline_message_id=message_id, last_inline_message_id=message_id)


def show_verified_menu(chat_id):
    _telegram_send_message(chat_id, _verified_menu_text(), _user_keyboard())


def show_user_home(chat_id, user):
    if user.get('verified'):
        show_verified_menu(chat_id)
    else:
        show_unverified_start(chat_id, user)


def _admin_text(note=None):
    status = 'MAINTENANCE' if get_site_status().get('maintenance') else 'ONLINE'
    data = _load_event_data()
    settings = _event_settings(data)
    payload = _draw_status_payload(data)
    event_status = payload['draw_status'].upper()
    lines = [
        '🛡 MII STORE ADMIN PANEL',
        '',
        'Mode: MII REWARD DRAW',
        f'Web: {status}',
        f'Event: {event_status}',
        f"Hadiah: {payload.get('reward_name') or '-'}",
        f"Total Token: {payload['total_tokens']}",
        f"Winner: {payload['total_winners']} / {payload['slot_winner']}",
        f"Stock: {payload['reward_stock']}",
    ]
    if note:
        lines.extend(['', note])
    lines.extend(['', 'Pilih menu admin:'])
    return '\n'.join(lines)



def show_admin_panel(chat_id, user=None, note=None):
    panel_id = None
    if user:
        panel_id = user.get('admin_panel_message_id')
    message_id = _telegram_show_panel(chat_id, _admin_text(note), _admin_keyboard(), panel_id)
    if user and message_id:
        _save_user_message_ids(user['telegram_user_id'], admin_panel_message_id=message_id)


def refresh_admin_panel(chat_id, user=None, note=None):
    panel_id = user.get('admin_panel_message_id') if user else None
    if panel_id and _telegram_edit_message(chat_id, panel_id, _admin_text(note), _admin_keyboard()):
        return
    cached_id = _BOT_LAST_PANEL_MESSAGES.get(str(chat_id))
    if cached_id and _telegram_edit_message(chat_id, cached_id, _admin_text(note), _admin_keyboard()):
        if user:
            _save_user_message_ids(user['telegram_user_id'], admin_panel_message_id=cached_id)
        return
    message_id = _telegram_show_panel(chat_id, _admin_text(note), _admin_keyboard())
    if user and message_id:
        _save_user_message_ids(user['telegram_user_id'], admin_panel_message_id=message_id)

def _show_login_prompt(chat_id):
    with _BOT_SESSION_LOCK: _BOT_LOGIN_PENDING_CHATS.add(str(chat_id))
    _telegram_send_message(chat_id, 'Masukkan password admin untuk membuka MII STORE ADMIN PANEL.')


def _format_stats():
    st = _event_stats()
    return '\n'.join(['📊 Statistik MII REWARD DRAW', f"Total user start: {st['total_user_start']}", f"Total verified: {st['total_verified']}", f"Total token issued: {st['total_token_issued']}", f"Total token used: {st['total_token_used']}", f"Total reward pending: {st['total_reward_pending']}", f"Total reward claimed: {st['total_reward_claimed']}"])


def _format_users():
    data = _load_event_data(); users = sorted(data['users'].values(), key=lambda u: u.get('last_action_at',''), reverse=True)[:10]
    lines = ['👥 10 User MII REWARD DRAW Terbaru']
    for u in users: lines.append(f"- {u.get('telegram_user_id')} @{u.get('username','-')} verified={u.get('verified')} token={bool(u.get('token'))}")
    return '\n'.join(lines) if len(lines)>1 else 'Belum ada user.'


def _format_reward_codes():
    data = _load_event_data(); lines = ['🎁 Reward Codes']
    for r in list(data['reward_codes'].values())[:10]: lines.append(f"- {r['code']} | {r['name']} | {r['claimed_count']}/{r['max_claim']} | active={r['is_active']}")
    return '\n'.join(lines) if len(lines)>1 else 'Belum ada reward code.'


def _format_claim_history():
    data = _load_event_data(); lines = ['📜 10 Claim Terbaru']
    for c in data['claims'][-10:][::-1]: lines.append(f"- @{c.get('username','-')} {c.get('winning_key') or c.get('reward_code')} {c.get('claimed_at')}")
    return '\n'.join(lines) if len(lines)>1 else 'Belum ada claim.'


def _handle_admin_text(chat_id, text):
    state = _BOT_USER_STATES.get(str(chat_id))
    if state == 'add_reward':
        parts = [p.strip() for p in text.split('|')]
        if len(parts) == 4:
            code, name, rtype, max_claim_raw, expires = _generate_code('MII-WIN'), parts[0], parts[1], parts[2], parts[3]
        elif len(parts) >= 5:
            code, name, rtype, max_claim_raw, expires = parts[0].upper(), parts[1], parts[2], parts[3], parts[4]
        else:
            text = (
                '➕ Generate Reward Code\n\n'
                'Kirim format:\n\n'
                '`Nama Reward | type | max_claim | expired_date`\n\n'
                'Contoh:\n\n'
                '`Premium App Random | account | 3 | 2026-06-30`\n\n'
                'Jika ingin manual:\n\n'
                '`CODE | Nama Reward | type | max_claim | expired_date`'
            )
            _telegram_send_message(chat_id, text, parse_mode='Markdown'); return
        try: max_claim = int(max_claim_raw)
        except ValueError: _telegram_send_message(chat_id, 'max_claim harus angka.'); return
        with _EVENT_LOCK:
            data = _load_event_data(); data['reward_codes'][code] = {'code':code,'name':name,'type':rtype,'max_claim':max_claim,'claimed_count':0,'is_active':True,'expires_at':_normalize_reward_expires(expires),'created_at':_utc_timestamp(),'created_by':str(chat_id)}; _save_event_data(data)
        _clear_bot_state(chat_id)
        text = (
            '✅ Reward code berhasil dibuat.\n\n'
            'Kode:\n'
            f'{_md_code(code)}\n\n'
            'Max claim:\n'
            f'{_md_code(max_claim)}\n\n'
            'Expired:\n'
            f'{_md_code(expires)}'
        )
        _telegram_send_message(chat_id, text, _admin_keyboard(), parse_mode='Markdown'); return
    if state == 'set_reward_info':
        saved = _set_reward_info(text)
        _clear_bot_state(chat_id)
        _telegram_send_message(chat_id, '✅ Info hadiah berhasil disimpan.\n\n' + _format_reward_info(), _admin_keyboard(), parse_mode='Markdown')
        return
    if state == 'set_community_link':
        parts = [p.strip() for p in text.split('|', 2)]
        name = parts[0] if parts else 'COMMUNITY'
        link = parts[1] if len(parts) > 1 else ''
        btn_label = parts[2] if len(parts) > 2 else ('GABUNG' if link else '')
        status = get_site_status()
        status['community_name'] = name
        status['community_link'] = link
        status['community_btn_label'] = btn_label or 'GABUNG'
        status['updated_at'] = _utc_timestamp()
        _save_site_status(status)
        _clear_bot_state(chat_id)
        _telegram_send_message(chat_id, f'✅ Community berhasil diupdate.\n\nNama: *{name}*\nLink: `{link or "(kosong)"}`\nTombol: *{btn_label or "GABUNG"}*', _admin_keyboard(), parse_mode='Markdown')
        return
    if state == 'set_telegram_channel':
        link = text.strip()
        status = get_site_status()
        status['telegram_channel_link'] = link
        status['updated_at'] = _utc_timestamp()
        _save_site_status(status)
        _clear_bot_state(chat_id)
        _telegram_send_message(chat_id, f'✅ Telegram Channel berhasil diupdate.\n\nLink: {link}', _admin_keyboard())
        return
    if state == 'set_event_settings':
        fields = {'nama event':'event_name','nama hadiah':'reward_name','tanggal event':'event_date','jam mulai':'event_time','jumlah winner':'win_quota','countdown per round':'countdown_seconds','announcement':'announcement'}
        updates = {}
        for ln in text.splitlines():
            if ':' not in ln:
                continue
            k, v = [x.strip() for x in ln.split(':', 1)]
            key = fields.get(k.lower())
            if key:
                updates[key] = v
        with _EVENT_LOCK:
            data = _load_event_data(); settings = _event_settings(data)
            for k, v in updates.items():
                if k in {'win_quota','countdown_seconds'}:
                    try: v = max(1, int(re.sub(r'[^0-9]', '', v) or '1'))
                    except ValueError: v = 1
                settings[k] = v
            if 'reward_name' in updates:
                settings['reward_info'] = updates['reward_name']
            settings['updated_at'] = _utc_timestamp(); _save_event_data(data)
        _clear_bot_state(chat_id)
        _telegram_send_message(chat_id, '✅ Event Settings berhasil disimpan.', _admin_keyboard())
        return
    if state == 'add_stock':
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        reward_name = 'CloudMoon Account'; rows = []
        if lines and lines[0].lower().startswith('nama reward:'):
            reward_name = lines[0].split(':', 1)[1].strip() or reward_name
            rows = [ln for ln in lines[1:] if not ln.lower().startswith('data:')]
        elif lines:
            reward_name = lines[0]
            rows = lines[1:]
        if not rows:
            _telegram_send_message(chat_id, 'Format stok tidak valid. Kirim nama reward lalu baris data akun.'); return
        with _EVENT_LOCK:
            data = _load_event_data()
            for row in rows:
                item_id = str(uuid.uuid4())
                data['reward_items'].append({'id':item_id,'reward_id':item_id,'reward_name':reward_name,'content':row,'reward_data':row,'used':False,'used_by_telegram_id':'','used_by_winning_key':'','used_at':'','created_at':_utc_timestamp()})
            _save_event_data(data)
        _clear_bot_state(chat_id)
        _telegram_send_message(chat_id, f'✅ {len(rows)} stok reward berhasil ditambahkan.\nReward: {reward_name}', _admin_keyboard()); return
    _telegram_send_message(chat_id, 'Pilih menu admin di keyboard bawah.', _admin_keyboard())


def _claim_reward(uid, reward_code):
    key = (reward_code or '').strip().upper()
    with _EVENT_LOCK:
        data = _load_event_data(); user = data['users'].get(str(uid))
        if not user or not user.get('verified'): return 'Kamu belum menyelesaikan verifikasi MII REWARD DRAW.'
        win = data.get('winning_keys', {}).get(key)
        if not win: return 'Winning Key tidak valid.'
        if win.get('used'): return 'Winning Key ini sudah pernah digunakan.'
        if str(win.get('telegram_id')) != str(uid): return 'Winning Key ini bukan milik akun Telegram kamu.'
        item = next((i for i in data.get('reward_items', []) if not i.get('used')), None)
        if not item: return 'Reward sedang kosong. Hubungi admin.'
        now = _utc_timestamp()
        item['used'] = True; item['used_by_telegram_id'] = str(uid); item['used_by_winning_key'] = key; item['used_at'] = now; item['used_by'] = str(uid)
        win['used'] = True; win['reward_sent'] = True; win['reward_item_id'] = item.get('id'); win['used_at'] = now
        user['reward_status'] = 'claimed'; user['reward_claimed'] = True
        token_rec = data.get('event_tokens', {}).get(win.get('token'))
        if token_rec: token_rec['reward_claimed'] = True
        reward_name = item.get('reward_name') or _reward_info_text(data) or 'CloudMoon Account'
        data['claims'].append({'telegram_user_id':str(uid),'username':user.get('username',''),'winning_key':key,'reward_name':reward_name,'reward_item_id':item['id'],'token':win.get('token',''),'claimed_at':now,'status':'claimed'}); _save_event_data(data)
        return (
            '🎁 REWARD BERHASIL DIKIRIM\n\n'
            'Winning Key:\n'
            f'{_md_code(key)}\n\n'
            'Reward:\n'
            f'{reward_name}\n\n'
            'Detail Akun:\n'
            f"{_md_code(item.get('content') or item.get('reward_data') or '')}\n\n"
            'Terima kasih sudah ikut MII Reward Draw.'
        )


def _set_bot_state(chat_id, state, uid=None):
    _BOT_USER_STATES[str(chat_id)] = state
    user_key = str(uid if uid is not None else chat_id)
    with _EVENT_LOCK:
        data = _load_event_data(); user = data['users'].get(user_key)
        if user:
            user['state'] = state; user['last_action_at'] = _utc_timestamp(); data['users'][user_key] = user; _save_event_data(data)
    # Also persist admin states to site_status for restart recovery
    if state in ('set_community_link', 'set_telegram_channel'):
        try:
            ss = get_site_status()
            ss[f'_admin_state_{chat_id}'] = state
            _save_site_status(ss)
        except Exception:
            pass


def _clear_bot_state(chat_id, uid=None):
    _BOT_USER_STATES.pop(str(chat_id), None)
    user_key = str(uid if uid is not None else chat_id)
    with _EVENT_LOCK:
        data = _load_event_data(); user = data['users'].get(user_key)
        if user:
            user['state'] = ''; user['last_action_at'] = _utc_timestamp(); data['users'][user_key] = user; _save_event_data(data)
    # Clean admin state from site_status
    try:
        ss = get_site_status()
        key = f'_admin_state_{chat_id}'
        if key in ss:
            del ss[key]
            _save_site_status(ss)
    except Exception:
        pass

def _normalize_bot_action(data):
    mapping = {
        '/menu': 'menu', '/bounty': 'open_bounty', 'MII REWARD DRAW': 'menu', 'MENU UTAMA': 'menu',
        'JOIN WHATSAPP': 'join_wa_link', 'JOIN CHANNEL TELEGRAM': 'join_tg_link',
        'VERIFIKASI JOIN': 'event_verify', '/verify': 'event_verify',
        'CLAIM TOKEN': 'event_claim_token', '/token': 'event_claim_token',
        'CLAIM REWARD': 'event_claim_reward', '/claim': 'event_claim_reward',
        'REWARD SAYA': 'event_myreward', '/myreward': 'event_myreward',
        'BUKA MII REWARD DRAW': 'open_bounty', 'BATAL': 'cancel',
        'STATISTIK EVENT': 'event_stats', '/event_stats': 'event_stats',
        'USER EVENT': 'event_users', '/users': 'event_users',
        'REWARD CODES': 'reward_codes', '/reward_codes': 'reward_codes',
        'GENERATE REWARD': 'reward_generate', 'REWARD STOCK': 'reward_stock', 'ADD REWARD STOCK': 'reward_stock', 'VIEW REWARD STOCK': 'view_reward_stock', 'DRAW SETTINGS': 'event_settings', 'EVENT SETTINGS': 'event_settings',
        'CLAIM HISTORY': 'claim_history', '/claim_history': 'claim_history',
        'LOCK EVENT': 'event_lock', 'LOCK DRAW': 'event_lock', 'ACTIVE EVENT': 'event_active', 'OPEN DRAW': 'event_active', 'OPEN EVENT': 'event_active', 'START DRAW': 'draw_start', 'DRAW STATUS': 'draw_status', 'LIST TOKEN': 'list_token', 'WINNER LIST': 'winner_list', 'RESET DRAW': 'reset_draw', 'INFO HADIAH': 'reward_info',
        'MAINTENANCE ON': 'maintenance_on', 'HIDUPKAN MAINTENANCE': 'maintenance_on', '/maintenance_on': 'maintenance_on',
        'MAINTENANCE OFF': 'maintenance_off', 'MATIKAN MAINTENANCE': 'maintenance_off', '/maintenance_off': 'maintenance_off',
        'LOGOUT': 'logout', '/logout': 'logout', '/admin': 'admin_login',
        'COMMUNITY LINK': 'community_link', 'TELEGRAM CHANNEL': 'telegram_channel',
    }
    clean = (data or '').strip()
    upper_clean = clean.upper()
    no_icon = re.sub(r'^[^A-Za-z0-9/]+\s*', '', clean).strip()
    return mapping.get(clean, mapping.get(upper_clean, mapping.get(no_icon, mapping.get(no_icon.upper(), clean))))


def process_telegram_update(update):
    update_id = update.get('update_id')
    if update_id is not None:
        with _BOT_SESSION_LOCK:
            if update_id in _BOT_PROCESSED_UPDATE_IDS:
                return
            _BOT_PROCESSED_UPDATE_IDS.add(update_id)
            if len(_BOT_PROCESSED_UPDATE_IDS) > 500:
                for old in sorted(_BOT_PROCESSED_UPDATE_IDS)[:250]:
                    _BOT_PROCESSED_UPDATE_IDS.discard(old)
    callback = update.get('callback_query') or {}
    message = (callback.get('message') if callback else update.get('message')) or {}
    chat = message.get('chat') or {}
    chat_id = chat.get('id')
    if not chat_id:
        return
    if callback:
        _telegram_answer_callback(callback.get('id'))
        raw_data = callback.get('data', '')
        telegram_actor = callback.get('from') or {}
    else:
        raw_data = (message.get('text') or '').strip()
        telegram_actor = message.get('from') or {}
    user = _upsert_event_user(actor=telegram_actor, chat=chat)
    uid = user['telegram_user_id']
    data = _normalize_bot_action(raw_data)
    state = _BOT_USER_STATES.get(str(chat_id))
    # Fallback ke db kalau memory kosong (setelah restart Railway)
    if not state and uid:
        try:
            _db_data = _load_event_data()
            _db_user = _db_data.get('users', {}).get(str(uid), {})
            if _db_user.get('state'):
                state = _db_user['state']
                _BOT_USER_STATES[str(chat_id)] = state
        except Exception:
            pass
    # Fallback ke site_status untuk admin states
    if not state:
        try:
            ss = get_site_status()
            saved = ss.get(f'_admin_state_{chat_id}')
            if saved:
                state = saved
                _BOT_USER_STATES[str(chat_id)] = state
        except Exception:
            pass

    if data in ('menu', 'cancel') and state != 'awaiting_reward_code':
        was_admin_input = state in ('add_reward', 'add_stock', 'set_reward_info', 'set_event_settings', 'set_community_link', 'set_telegram_channel')
        _clear_bot_state(chat_id, uid)
        if _is_admin_chat(uid):
            if not _is_logged_in(chat_id):
                _show_login_prompt(chat_id)
                return
            if data == 'cancel' and was_admin_input:
                _telegram_send_message(chat_id, '❌ Dibatalkan.')
            show_admin_panel(chat_id, user)
        else:
            show_user_home(chat_id, user)
        return

    with _BOT_SESSION_LOCK:
        pending = str(chat_id) in _BOT_LOGIN_PENDING_CHATS
    if pending:
        if _is_admin_chat(uid) and checkAdminPassword(raw_data):
            with _BOT_SESSION_LOCK:
                _BOT_AUTHENTICATED_CHATS.add(str(chat_id))
                _BOT_LOGIN_PENDING_CHATS.discard(str(chat_id))
            show_admin_panel(chat_id, user)
        else:
            _telegram_send_message(chat_id, '❌ Password salah.')
        return

    if raw_data in ('/start', '/login') or data == 'admin_login':
        if _is_admin_chat(uid) and not _is_logged_in(chat_id):
            _show_login_prompt(chat_id)
        elif _is_admin_chat(uid):
            show_admin_panel(chat_id, user)
        else:
            show_user_home(chat_id, user)
        return

    if data == 'logout':
        with _BOT_SESSION_LOCK:
            _BOT_AUTHENTICATED_CHATS.discard(str(chat_id))
            _BOT_LOGIN_PENDING_CHATS.discard(str(chat_id))
        _clear_bot_state(chat_id, uid)
        if _is_admin_chat(uid):
            _telegram_send_message(chat_id, '🔐 Logout berhasil. Kirim /start untuk login admin lagi.')
        else:
            _telegram_send_message(chat_id, '🔐 Logout berhasil.', _user_keyboard())
        return

    admin_actions = {'event_stats', 'event_users', 'reward_codes', 'claim_history', 'event_settings', 'reward_generate', 'reward_stock', 'view_reward_stock', 'maintenance_on', 'maintenance_off', 'event_manual_token', 'event_lock', 'event_active', 'draw_start', 'draw_status', 'list_token', 'winner_list', 'reset_draw', 'reward_info'}
    if data in admin_actions and not _is_admin_chat(uid):
        _telegram_send_message(chat_id, '⛔ Access denied.')
        return
    if _is_admin_chat(uid) and data in admin_actions and not _is_logged_in(chat_id):
        _show_login_prompt(chat_id)
        return
    if _is_admin_chat(uid):
        if not _is_logged_in(chat_id):
            _show_login_prompt(chat_id)
            return
        if data == 'event_stats':
            _telegram_send_message(chat_id, _format_stats())
            return
        if data == 'event_users':
            _telegram_send_message(chat_id, _format_users())
            return
        if data == 'reward_codes':
            _telegram_send_message(chat_id, _format_reward_codes())
            return
        if data == 'claim_history':
            _telegram_send_message(chat_id, _format_claim_history())
            return
        if data == 'view_reward_stock':
            d=_load_event_data(); total=len(d.get('reward_items',[])); left=sum(1 for i in d.get('reward_items',[]) if not i.get('used'))
            _telegram_send_message(chat_id, f'📦 Reward Stock\nTersedia: {left}\nTotal: {total}', _admin_keyboard())
            return
        if data in ('event_lock', 'event_active'):
            new_status = _set_bounty_event_status('open' if data == 'event_active' else 'locked')
            prefix = '🟢 MII REWARD DRAW sekarang OPEN.' if new_status == 'open' else '🔒 MII REWARD DRAW sekarang LOCKED.'
            refresh_admin_panel(chat_id, user, prefix)
            return
        if data == 'draw_start':
            winner, result = _start_reward_draw()
            if result == 'locked':
                _telegram_send_message(chat_id, 'Event masih locked. Open event dulu sebelum start draw.', _admin_keyboard()); return
            if result == 'empty':
                _telegram_send_message(chat_id, 'Token peserta belum cukup untuk draw.', _admin_keyboard())
                return
            if result == 'no_stock':
                _telegram_send_message(chat_id, 'Reward stock masih kosong.', _admin_keyboard()); return
            text = (
                '🏆 PEMENANG MII REWARD DRAW\n\n'
                'Token:\n'
                f'{_md_code(winner.get("token", "-"))}\n\n'
                'Telegram ID:\n'
                f'{_md_code(winner.get("telegram_id", "-"))}\n\n'
                'Username:\n'
                f'@{winner.get("username") or "-"}\n\n'
                'Nama:\n'
                f'{winner.get("first_name") or "-"}\n\n'
                'Status:\n'
                'WINNER SELECTED'
            )
            _telegram_send_message(chat_id, text, _admin_keyboard(), parse_mode='Markdown')
            return
        if data == 'draw_status':
            payload = _draw_status_payload()
            winner = payload.get('winner') or {}
            text = (
                '📊 DRAW STATUS\n\n'
                f"Status: {payload['draw_status'].upper()}\n"
                f"Total Token: {payload['total_tokens']}\n"
                f"Winner: {winner.get('token') or 'Belum ada pemenang'}"
            )
            _telegram_send_message(chat_id, text, _admin_keyboard())
            return
        if data == 'list_token':
            d = _load_event_data()
            tokens = sorted(_valid_draw_tokens(d), key=lambda r: r.get('created_at', ''), reverse=True)[:20]
            lines = ['👥 LIST TOKEN']
            lines.extend(f"- {r.get('token')} | {r.get('telegram_id') or r.get('telegram_user_id')} | @{r.get('username','-')}" for r in tokens)
            _telegram_send_message(chat_id, '\n'.join(lines) if len(lines) > 1 else 'Belum ada token.', _admin_keyboard())
            return
        if data == 'winner_list':
            winner = (_draw_status_payload().get('winner') or {})
            msg = f"🏆 Winner List\n\n{winner.get('token')} | {winner.get('telegram_id')} | @{winner.get('username','-')}" if winner else 'Belum ada pemenang.'
            _telegram_send_message(chat_id, msg, _admin_keyboard())
            return
        if data == 'reset_draw':
            _reset_reward_draw()
            refresh_admin_panel(chat_id, user, '♻️ Draw direset ke LOCKED. Token existing tetap tersimpan.')
            return
        if data == 'event_settings':
            _set_bot_state(chat_id, 'set_event_settings', uid)
            _telegram_send_message(chat_id, '⚙️ Kirim Event Settings:\n\nNama Event: MII Reward Draw\nNama Hadiah: CloudMoon Pro 1 Bulan\nTanggal Event: 15 Juni 2026\nJam Mulai: 20:00 WIB\nJumlah Winner: 3\nCountdown Per Round: 10 detik\nAnnouncement: Event dimulai malam ini jam 20:00 WIB.', _claim_keyboard())
            return
        if data == 'reward_info':
            _set_bot_state(chat_id, 'set_reward_info', uid)
            _telegram_send_message(chat_id, '🎁 Kirim info hadiah event.\n\nContoh:\n`CloudMoon Pro 1 Bulan`', _claim_keyboard(), parse_mode='Markdown')
            return
        if data == 'reward_generate':
            _set_bot_state(chat_id, 'add_reward', uid)
            text = (
                '➕ Generate Reward Code\n\n'
                'Kirim format:\n\n'
                '`Nama Reward | type | max_claim | expired_date`\n\n'
                'Contoh:\n\n'
                '`Premium App Random | account | 3 | 2026-06-30`\n\n'
                'Sistem otomatis membuat kode:\n\n'
                '`MII-WIN-2026-XXXX`\n\n'
                'Jika ingin manual:\n\n'
                '`CODE | Nama Reward | type | max_claim | expired_date`\n\n'
                'Contoh manual:\n\n'
                '`MII-WIN-2026-ABCD | Premium App Random | account | 3 | 2026-06-30`'
            )
            _telegram_send_message(chat_id, text, _claim_keyboard(), parse_mode='Markdown')
            return
        if data == 'reward_stock':
            _set_bot_state(chat_id, 'add_stock', uid)
            text = (
                '📦 Tambah Stok Hadiah\n\n'
                'Kirim format:\n\n'
                '`CloudMoon Account\nemail1@gmail.com | pass123\nemail2@gmail.com | pass456`\n\n'
                'Atau:\n\n'
                '`Nama Reward: CloudMoon Account\nData:\nemail1@gmail.com | pass123`'
            )
            _telegram_send_message(chat_id, text, _claim_keyboard(), parse_mode='Markdown')
            return
        if data in ('maintenance_on', 'maintenance_off'):
            enabled = data == 'maintenance_on'
            set_maintenance_status(enabled)
            note = 'Maintenance website dihidupkan.' if enabled else 'Maintenance website dimatikan.'
            refresh_admin_panel(chat_id, user, note)
            return
        if state in ('add_reward', 'add_stock', 'set_reward_info', 'set_event_settings', 'set_community_link', 'set_telegram_channel'):
            _handle_admin_text(chat_id, raw_data)
            return
        if data == 'community_link':
            status = get_site_status()
            current_name = status.get('community_name', 'COMMUNITY')
            current_link = status.get('community_link', '(kosong)')
            current_btn = status.get('community_btn_label', 'GABUNG')
            _set_bot_state(chat_id, 'set_community_link', uid)
            _telegram_send_message(chat_id,
                f'🔗 Edit Community\n\nSaat ini:\nNama: *{current_name}*\nLink: `{current_link}`\nTombol: *{current_btn}*\n\nKirim format:\n`Nama | Link | Label Tombol`\n\nContoh:\n`GEMINI BOT | https://t.me/geminibot | BUKA`\n\nKosongkan link:\n`COMMUNITY | |`',
                _claim_keyboard(), parse_mode='Markdown')
            return
        if data == 'telegram_channel':
            status = get_site_status()
            current = status.get('telegram_channel_link', '(kosong)')
            _set_bot_state(chat_id, 'set_telegram_channel', uid)
            _telegram_send_message(chat_id,
                f'📢 Edit Telegram Channel\n\nSaat ini:\n`{current}`\n\nKirim link baru:',
                _claim_keyboard(), parse_mode='Markdown')
            return

    if state == 'awaiting_reward_code':
        if data == 'cancel':
            _clear_bot_state(chat_id, uid)
            if user.get('verified'):
                _telegram_send_message(chat_id, '❌ Claim reward dibatalkan.', _user_keyboard())
            else:
                show_unverified_start(chat_id, user)
            return
        if data == 'menu':
            _clear_bot_state(chat_id, uid)
            show_user_home(chat_id, user)
            return
        msg = _claim_reward(uid, raw_data)
        if msg.startswith('🎁 REWARD BERHASIL'):
            _clear_bot_state(chat_id, uid)
            _telegram_send_message(chat_id, msg, _user_keyboard(), parse_mode='Markdown')
        else:
            _telegram_send_message(chat_id, msg, _claim_keyboard())
        return

    if data == 'open_bounty':
        if user.get('verified'):
            _telegram_send_message(chat_id, '🌐 Buka halaman MII REWARD DRAW lewat tombol di bawah.', _inline_url_keyboard('Buka MII Reward Draw', 'https://makima.cloud/bounty'))
        else:
            show_unverified_start(chat_id, user)
        return
    if data == 'event_verify':
        callback_message_id = message.get('message_id') if callback else None
        if user.get('verified'):
            _clear_user_inline_join_buttons(chat_id, user, callback_message_id)
            _telegram_send_message(chat_id, _verified_menu_text(), _user_keyboard())
            return
        tg_status = _telegram_get_chat_member(uid)
        if tg_status == 'error':
            _telegram_send_message(chat_id, '⚠️ Sistem belum bisa mengecek channel.\nPastikan bot sudah menjadi admin channel dan TELEGRAM_CHANNEL_ID benar.')
            return
        if tg_status != 'joined':
            _telegram_send_message(chat_id, '❌ Kamu belum join Channel Telegram.\nJoin dulu, lalu tekan Verifikasi Join lagi.')
            return
        with _EVENT_LOCK:
            d = _load_event_data()
            u = d['users'][uid]
            u['telegram_join_verified'] = True
            u['verified'] = True
            u['last_action_at'] = _utc_timestamp()
            d['users'][uid] = u
            _save_event_data(d)
        _clear_user_inline_join_buttons(chat_id, u, callback_message_id)
        _telegram_send_message(chat_id, '✅ Verifikasi berhasil.\nMenu event sudah terbuka.', _user_keyboard())
        return
    if data == 'event_claim_token':
        if not user.get('verified'):
            show_unverified_start(chat_id, user)
            return
        _u, msg = _claim_or_get_token(uid)
        _telegram_send_message(chat_id, msg, _user_keyboard(), parse_mode='Markdown')
        return
    if data == 'event_claim_reward':
        if not user.get('verified'):
            _telegram_send_message(chat_id, '❌ Kamu belum verifikasi Channel Telegram.')
            return
        _set_bot_state(chat_id, 'awaiting_reward_code', uid)
        text = (
            'Kirim Winning Key kamu.\n\n'
            'Contoh:\n'
            '`MII-WIN-2026-ABCD`'
        )
        _telegram_send_message(chat_id, text, _claim_keyboard(), parse_mode='Markdown')
        return
    if data == 'event_myreward':
        d = _load_event_data()
        claims = [c for c in d['claims'] if c.get('telegram_user_id') == uid]
        lines = '\n'.join(f"- {c['reward_code']} pada {c['claimed_at']}" for c in claims) if claims else 'Belum ada reward.'
        _telegram_send_message(chat_id, '📦 Reward Saya\n' + lines, _user_keyboard())
        return
    admin_commands = {'/status', '/users', '/event_stats', '/reward_codes', '/claim_history', '/maintenance_on', '/maintenance_off'}
    if raw_data in admin_commands and not _is_admin_chat(uid):
        _telegram_send_message(chat_id, '⛔ Access denied.')
        return
    show_user_home(chat_id, user)

def _telegram_polling_loop():
    global _BOT_LAST_UPDATE_ID
    while True:
        url = _telegram_api_url('getUpdates')
        if not url: time.sleep(30); continue
        params = {'timeout': 25}
        if _BOT_LAST_UPDATE_ID is not None: params['offset'] = _BOT_LAST_UPDATE_ID + 1
        try:
            resp = requests_lib.get(url, params=params, timeout=35); data = resp.json() if resp.ok else {}
            for update in data.get('result', []): _BOT_LAST_UPDATE_ID = update.get('update_id', _BOT_LAST_UPDATE_ID); process_telegram_update(update)
        except Exception as exc: app.logger.warning('Telegram polling failed: %s', exc); time.sleep(5)


def start_telegram_bot():
    global _BOT_POLLING_STARTED
    if _BOT_POLLING_STARTED or not os.environ.get('TELEGRAM_BOT_TOKEN'): return
    _BOT_POLLING_STARTED = True; threading.Thread(target=_telegram_polling_loop, name='telegram-bot-polling', daemon=True).start()

_ensure_status_file()
start_telegram_bot()

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
# Maintenance request guard
# ---------------------------------------------------------------------------
_MAINTENANCE_ALLOWED_ENDPOINTS = {
    'telegram_webhook', 'telegram_status', 'event_draw_status', 'event_token_status',
    'event_join_draw', 'event_validate_token', 'event_start_draw', 'admin_panel',
    'admin_panel_event_status', 'admin_panel_reward_info', 'admin_panel_reward',
    'admin_panel_stock', 'static',
}


@app.before_request
def maintenance_guard():
    allowed_prefixes = ('/telegram/', '/admin-panel', '/admin', '/api/admin', '/internal/', '/webhook')
    if request.endpoint in _MAINTENANCE_ALLOWED_ENDPOINTS:
        return None
    if request.path.startswith('/static/') or request.path.startswith(allowed_prefixes):
        return None
    if get_site_status().get('maintenance'):
        return render_template('maintenance.html', status=get_site_status()), 503
    return None


@app.route('/telegram/webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    process_telegram_update(update)
    return jsonify({'ok': True})


@app.route('/api/site-status')
def telegram_status():
    return jsonify(get_site_status())


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    status = get_site_status()
    return render_template('index.html',
        community_name=status.get('community_name', 'COMMUNITY'),
        community_link=status.get('community_link', ''),
        community_btn_label=status.get('community_btn_label', 'GABUNG'),
        telegram_channel_link=status.get('telegram_channel_link', 'https://t.me/+L0mZsWxq30cxZmM1')
    )


@app.route('/ai')
def ai_view():
    status = get_site_status()
    return render_template('index.html',
        community_name=status.get('community_name', 'COMMUNITY'),
        community_link=status.get('community_link', ''),
        community_btn_label=status.get('community_btn_label', 'GABUNG'),
        telegram_channel_link=status.get('telegram_channel_link', 'https://t.me/+L0mZsWxq30cxZmM1')
    )



@app.route('/event')
@app.route('/bounty')
def event_page():
    data = _load_event_data()
    return render_template('event.html', event_status=_bounty_event_status(data), reward_info=_format_reward_info(data).replace('🎁 Info Hadiah\n', ''), maintenance=get_site_status().get('maintenance'))


@app.route('/api/event/draw-status')
def event_draw_status():
    return jsonify(_draw_status_payload())


@app.route('/api/event/token-status', methods=['POST'])
def event_token_status():
    token = (request.get_json(silent=True) or {}).get('token', '')
    with _EVENT_LOCK:
        data = _load_event_data()
        payload = _token_room_payload(token, data)
        if not payload:
            return jsonify({'valid': False, 'error': 'Token tidak valid atau belum terdaftar.'}), 404
        return jsonify({**payload, 'event': _draw_status_payload(data)})


@app.route('/api/event/join-draw', methods=['POST'])
def event_join_draw():
    token = (request.get_json(silent=True) or {}).get('token', '')
    payload, error, status = _run_web_draw(token)
    if error:
        return jsonify({'ok': False, 'error': error}), status
    with _EVENT_LOCK:
        data = _load_event_data()
        room = _token_room_payload(token, data) or {}
        return jsonify({'ok': True, **payload, **room, 'event': _draw_status_payload(data)})


@app.route('/api/event/validate-token', methods=['POST'])
def event_validate_token():
    token = (request.get_json(silent=True) or {}).get('token', '')
    ok, user, error = validate_event_token(token)
    if not ok:
        return jsonify({'valid': False, 'error': error or 'Token tidak valid atau belum terdaftar.'}), 400
    return jsonify({'valid': True, 'message': 'Token valid untuk MII REWARD DRAW.'})


@app.route('/api/event/start-draw', methods=['POST'])
def event_start_draw():
    token = (request.get_json(silent=True) or {}).get('token', '')
    payload, error, status = _run_web_draw(token)
    if error:
        return jsonify({'ok': False, 'error': error}), status
    return jsonify({'ok': True, **payload})


def _admin_web_authed():
    if session.get('mii_event_admin') is True:
        return True
    return checkAdminPassword(request.form.get('password', ''))


@app.route('/admin-panel', methods=['GET', 'POST'])
@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    authed = _admin_web_authed()
    resp = None
    if request.method == 'POST' and authed:
        session['mii_event_admin'] = True
        resp = app.make_response('', 302)
        resp.headers['Location'] = '/admin-panel'
        return resp
    data = _load_event_data()
    stats = json.dumps(_event_stats(data), ensure_ascii=False, indent=2)
    reward_codes = json.dumps(list(data['reward_codes'].values()), ensure_ascii=False, indent=2)
    claims = json.dumps(data['claims'][-50:], ensure_ascii=False, indent=2)
    return render_template('event_admin.html', authed=authed, stats=stats, reward_codes=reward_codes, claims=claims, event_status=_bounty_event_status(data), reward_info=_reward_info_text(data))


@app.route('/admin-panel/event-status', methods=['POST'])
def admin_panel_event_status():
    if not _admin_web_authed():
        return jsonify({'error': 'Forbidden'}), 403
    _set_bounty_event_status(request.form.get('status'))
    from flask import redirect
    return redirect('/admin-panel')


@app.route('/admin-panel/reward-info', methods=['POST'])
def admin_panel_reward_info():
    if not _admin_web_authed():
        return jsonify({'error': 'Forbidden'}), 403
    _set_reward_info(request.form.get('reward_info', ''))
    from flask import redirect
    return redirect('/admin-panel')


@app.route('/admin-panel/reward', methods=['POST'])
def admin_panel_reward():
    if not _admin_web_authed():
        return jsonify({'error': 'Forbidden'}), 403
    code = (request.form.get('code') or '').strip().upper()
    if not code:
        code = _generate_code('MII-WIN')
    with _EVENT_LOCK:
        data = _load_event_data()
        data['reward_codes'][code] = {'code': code, 'name': request.form.get('name',''), 'type': request.form.get('type',''), 'max_claim': int(request.form.get('max_claim') or 1), 'claimed_count': 0, 'is_active': True, 'expires_at': _normalize_reward_expires(request.form.get('expires_at','')), 'created_at': _utc_timestamp(), 'created_by': 'web-admin'}
        _save_event_data(data)
    from flask import redirect
    return redirect('/admin-panel')


@app.route('/admin-panel/stock', methods=['POST'])
def admin_panel_stock():
    if not _admin_web_authed():
        return jsonify({'error': 'Forbidden'}), 403
    code = (request.form.get('reward_code') or '').strip().upper()
    content = (request.form.get('content') or '').strip()
    with _EVENT_LOCK:
        data = _load_event_data()
        if code not in data['reward_codes']:
            return jsonify({'error': 'Reward code tidak ditemukan'}), 400
        data['reward_items'].append({'id': str(uuid.uuid4()), 'reward_code': code, 'content': content, 'used': False, 'used_by': '', 'used_at': '', 'created_at': _utc_timestamp()})
        _save_event_data(data)
    from flask import redirect
    return redirect('/admin-panel')

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
