"""Persistent storage for the MII AI Video "Archive" feature.

Previously Archive lived only in the browser's localStorage, so it
disappeared if the browser data was cleared, and never existed on any
other device. This module gives it a real, server-side, database-backed
home (same lightweight sqlite pattern as analytics.py) so archived
generations survive browser clears and server restarts, and are looked up
from the database rather than from the session.

The actual media file itself is expected to already live on Dropbox (or
gets uploaded there by the caller before calling upsert_archive) — this
module only stores the metadata + the Dropbox URL, never raw file bytes.
"""
import sqlite3
import threading
import os
import json

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.abspath(
    os.environ.get('MII_DATA_DIR')
    or os.environ.get('RAILWAY_VOLUME_MOUNT_PATH')
    or _MODULE_DIR
)
_DB_PATH = os.path.abspath(
    os.environ.get('MII_AIVIDEO_DB')
    or os.path.join(_DATA_DIR, 'aivideo_archive.db')
)
os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
_write_lock = threading.Lock()
_conn = None


def _get_conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def init_db():
    conn = _get_conn()
    with _write_lock:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS aivideo_archive (
                id TEXT PRIMARY KEY,
                media_type TEXT,
                video_url TEXT,
                image_url TEXT,
                thumb TEXT,
                prompt TEXT,
                model TEXT,
                quality TEXT,
                duration TEXT,
                ratio TEXT,
                created_at_label TEXT,
                created_at_ts INTEGER,
                ref_images TEXT,
                ref_videos TEXT,
                model_key TEXT,
                model_tier TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # This table used to hold ONLY explicitly-archived items. It now
        # backs every generation (server-side History), with `archived`
        # distinguishing the two — existing rows predate the column and are
        # real archived items, so they default to 1 (archived) on upgrade,
        # which is the correct historical value for anything already there.
        existing_cols = [r[1] for r in conn.execute('PRAGMA table_info(aivideo_archive)').fetchall()]
        if 'archived' not in existing_cols:
            conn.execute('ALTER TABLE aivideo_archive ADD COLUMN archived INTEGER DEFAULT 1')
        # Mode Audio (Seed Audio 1.0): hasil audio disimpan di kolomnya sendiri.
        if 'audio_url' not in existing_cols:
            conn.execute("ALTER TABLE aivideo_archive ADD COLUMN audio_url TEXT DEFAULT ''")
        for column, declaration in (
            ('resolution', "TEXT DEFAULT ''"), ('image_quality', "TEXT DEFAULT ''"),
            ('image_count', 'INTEGER DEFAULT 1'), ('output_format', "TEXT DEFAULT ''"),
            ('generation_status', "TEXT DEFAULT 'COMPLETED'"), ('image_urls', "TEXT DEFAULT '[]'"),
            ('ref_audios', "TEXT DEFAULT '[]'"), ('elapsed_ms', 'INTEGER DEFAULT 0'),
            ('size_bytes', 'INTEGER DEFAULT 0'), ('audio_enabled', 'INTEGER'),
            ('reference_counts', "TEXT DEFAULT '{}'"), ('final_prompt', "TEXT DEFAULT ''"),
            ('bitrate', "TEXT DEFAULT ''"), ('source_task_id', "TEXT DEFAULT ''")):
            if column not in existing_cols:
                conn.execute('ALTER TABLE aivideo_archive ADD COLUMN %s %s' % (column, declaration))
        _ensure_security_table(conn)
        conn.commit()


def _ensure_security_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS aivideo_security_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_ts INTEGER NOT NULL,
            kind TEXT NOT NULL,
            route TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            socket_ip TEXT NOT NULL,
            ip_source TEXT NOT NULL,
            device TEXT NOT NULL,
            http_status INTEGER NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_aivideo_security_created "
        "ON aivideo_security_events (created_ts DESC)"
    )


def record_security_event(kind, route, ip_address, socket_ip, ip_source, device, http_status):
    """Only blocked security events, never request bodies or credentials.

    Duplicate events are collapsed for one minute. Retain at most 30 days
    and 2000 records so a denied-request flood cannot grow this table forever.
    """
    import time as _time
    now = int(_time.time())
    with _write_lock:
        conn = _get_conn()
        _ensure_security_table(conn)
        conn.execute("DELETE FROM aivideo_security_events WHERE created_ts < ?", (now - 30 * 86400,))
        last = conn.execute(
            "SELECT created_ts FROM aivideo_security_events "
            "WHERE kind=? AND route=? AND ip_address=? ORDER BY id DESC LIMIT 1",
            (kind, route, ip_address),
        ).fetchone()
        if last is not None and now - last[0] < 60:
            conn.commit()
            return False
        conn.execute(
            "INSERT INTO aivideo_security_events "
            "(created_ts,kind,route,ip_address,socket_ip,ip_source,device,http_status) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (now, kind[:48], route[:96], ip_address[:64], socket_ip[:64],
             ip_source[:32], device[:180], int(http_status)),
        )
        threshold = conn.execute(
            "SELECT id FROM aivideo_security_events ORDER BY id DESC LIMIT 1 OFFSET 1999"
        ).fetchone()
        if threshold is not None:
            conn.execute("DELETE FROM aivideo_security_events WHERE id < ?", (threshold[0],))
        conn.commit()
        return True


def list_security_events(limit=60):
    """Read-only bounded history for the password-authenticated Debug page."""
    import time as _time
    with _write_lock:
        conn = _get_conn()
        _ensure_security_table(conn)
        cutoff = int(_time.time()) - 30 * 86400
        count = conn.execute(
            "SELECT COUNT(*) FROM aivideo_security_events WHERE created_ts >= ?", (cutoff,)
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT created_ts,kind,route,ip_address,socket_ip,ip_source,device,http_status "
            "FROM aivideo_security_events WHERE created_ts >= ? "
            "ORDER BY id DESC LIMIT ?",
            (cutoff, max(1, min(int(limit), 100))),
        ).fetchall()
    return {'count': count, 'retention_days': 30, 'events': [dict(row) for row in rows]}


def _ensure_tasks_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS aivideo_tasks (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            status TEXT DEFAULT '',
            updated_ts INTEGER DEFAULT 0
        )
    """)


def save_task(task_id, data):
    """Simpan/refresh snapshot task generate. Dipanggil app.py di setiap
    perubahan status penting — supaya hasil generate selamat kalau proses
    server mati/redeploy di tengah jalan."""
    import json as _json, time as _time
    with _write_lock:
        conn = _get_conn()
        _ensure_tasks_table(conn)
        conn.execute(
            'INSERT INTO aivideo_tasks (id, data, status, updated_ts) VALUES (?, ?, ?, ?) '
            'ON CONFLICT(id) DO UPDATE SET data=excluded.data, status=excluded.status, updated_ts=excluded.updated_ts',
            (task_id, _json.dumps(data, default=str), str(data.get('status') or ''), int(_time.time())))
        conn.commit()


def get_task(task_id):
    import json as _json
    with _write_lock:
        conn = _get_conn()
        _ensure_tasks_table(conn)
        cur = conn.cursor()
        cur.execute('SELECT data FROM aivideo_tasks WHERE id = ?', (task_id,))
        row = cur.fetchone()
    if not row:
        return None
    try:
        return _json.loads(row[0])
    except Exception:
        return None


def list_recent_tasks(limit=20):
    """Return recent task snapshots for diagnostics/history reconstruction."""
    with _write_lock:
        conn = _get_conn()
        _ensure_tasks_table(conn)
        rows = conn.execute(
            'SELECT id, data FROM aivideo_tasks ORDER BY updated_ts DESC LIMIT ?',
            (max(1, min(int(limit), 50)),),
        ).fetchall()
    out = []
    for task_id, raw in rows:
        try:
            item = json.loads(raw)
        except (TypeError, ValueError):
            continue
        item.setdefault('id', task_id)
        out.append(item)
    return out


def mark_interrupted_tasks(error_message):
    """Dipanggil sekali saat boot: task yang masih 'pending'/'processing'
    dari kehidupan server sebelumnya tidak mungkin selesai (thread-nya
    ikut mati) — tandai failed dengan pesan yang jelas, bukan hilang."""
    import json as _json, time as _time
    with _write_lock:
        conn = _get_conn()
        _ensure_tasks_table(conn)
        cur = conn.cursor()
        cur.execute("SELECT id, data FROM aivideo_tasks WHERE status NOT IN ('completed','failed')")
        rows = cur.fetchall()
        for task_id, raw in rows:
            try:
                d = _json.loads(raw)
            except Exception:
                d = {}
            d['status'] = 'failed'
            d['error'] = error_message
            conn.execute('UPDATE aivideo_tasks SET data=?, status=?, updated_ts=? WHERE id=?',
                         (_json.dumps(d, default=str), 'failed', int(_time.time()), task_id))
        conn.commit()
    return len(rows)


def prune_tasks(max_age_seconds):
    import time as _time
    with _write_lock:
        conn = _get_conn()
        _ensure_tasks_table(conn)
        cur = conn.cursor()
        cur.execute('DELETE FROM aivideo_tasks WHERE updated_ts < ?', (int(_time.time()) - int(max_age_seconds),))
        conn.commit()
        return cur.rowcount


def upsert_archive(rec):
    """rec: dict with at least 'id'. video_url/image_url MUST already be
    Dropbox URLs by the time they get here (the API route is responsible
    for uploading to Dropbox first if needed)."""
    conn = _get_conn()
    with _write_lock:
        conn.execute('''
            INSERT INTO aivideo_archive
                (id, media_type, video_url, image_url, audio_url, thumb, prompt, model, quality,
                 duration, ratio, created_at_label, created_at_ts, ref_images, ref_videos,
                 model_key, model_tier, archived, resolution, image_quality, image_count,
                 output_format, generation_status, image_urls, ref_audios, elapsed_ms, size_bytes, audio_enabled, reference_counts, final_prompt, bitrate, source_task_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                media_type=excluded.media_type, video_url=excluded.video_url,
                image_url=excluded.image_url, audio_url=excluded.audio_url,
                thumb=excluded.thumb, prompt=excluded.prompt,
                model=excluded.model, quality=excluded.quality, duration=excluded.duration,
                ratio=excluded.ratio, created_at_label=excluded.created_at_label,
                created_at_ts=excluded.created_at_ts, ref_images=excluded.ref_images,
                ref_videos=excluded.ref_videos, model_key=excluded.model_key,
                model_tier=excluded.model_tier, archived=excluded.archived,
                resolution=excluded.resolution, image_quality=excluded.image_quality,
                image_count=excluded.image_count, output_format=excluded.output_format,
                generation_status=excluded.generation_status, image_urls=excluded.image_urls,
                ref_audios=excluded.ref_audios, elapsed_ms=excluded.elapsed_ms,
                size_bytes=excluded.size_bytes, audio_enabled=excluded.audio_enabled,
                reference_counts=excluded.reference_counts, final_prompt=excluded.final_prompt,
                bitrate=excluded.bitrate, source_task_id=excluded.source_task_id
        ''', (
            rec.get('id'),
            rec.get('media_type') or ('video' if rec.get('videoUrl') else ('audio' if rec.get('audioUrl') else 'image')),
            rec.get('videoUrl') or '',
            rec.get('imageUrl') or '',
            rec.get('audioUrl') or '',
            rec.get('thumb') or '',
            rec.get('prompt') or '',
            rec.get('model') or '',
            rec.get('quality') or '',
            rec.get('duration') or '',
            rec.get('ratio') or '',
            rec.get('createdAtLabel') or '',
            int(rec.get('createdAtTs') or 0),
            json.dumps(rec.get('refImages') or []),
            json.dumps(rec.get('refVideos') or []),
            rec.get('modelKey') or '',
            rec.get('modelTier') or '',
            1 if rec.get('archived', True) else 0,
            rec.get('resolution') or '', rec.get('imageQuality') or '',
            int(rec.get('imageCount') or 1), rec.get('outputFormat') or '',
            rec.get('status') or 'COMPLETED', json.dumps(rec.get('imageUrls') or []),
            json.dumps(rec.get('refAudios') or []), int(rec.get('elapsedMs') or 0),
            int(rec.get('sizeBytes') or 0), None if rec.get('audioEnabled') is None else (1 if rec.get('audioEnabled') else 0),
            json.dumps(rec.get('referenceCounts') or {}), rec.get('finalPrompt') or '', rec.get('bitrate') or '',
            rec.get('sourceTaskId') or '',
        ))
        conn.commit()


def list_archive(archived=None):
    """archived=True -> only archived items (existing Archive-page
    behavior). archived=False -> only non-archived. archived=None -> every
    row (used to hydrate the History page, which then splits by the flag
    itself)."""
    conn = _get_conn()
    cur = conn.cursor()
    if archived is None:
        cur.execute('SELECT * FROM aivideo_archive ORDER BY created_at_ts DESC, created_at DESC')
    else:
        cur.execute(
            'SELECT * FROM aivideo_archive WHERE archived = ? ORDER BY created_at_ts DESC, created_at DESC',
            (1 if archived else 0,)
        )
    out = []
    for row in cur.fetchall():
        d = dict(row)
        d['mediaType'] = d.pop('media_type', '') or ''
        d['refImages'] = json.loads(d.pop('ref_images') or '[]')
        d['refVideos'] = json.loads(d.pop('ref_videos') or '[]')
        d['refAudios'] = json.loads(d.pop('ref_audios', '[]') or '[]')
        d['imageUrls'] = json.loads(d.pop('image_urls', '[]') or '[]')
        d['videoUrl'] = d.pop('video_url')
        d['imageUrl'] = d.pop('image_url')
        d['audioUrl'] = d.pop('audio_url', '') or ''
        d['createdAtLabel'] = d.pop('created_at_label')
        d['createdAtTs'] = d.pop('created_at_ts')
        d['modelKey'] = d.pop('model_key')
        d['modelTier'] = d.pop('model_tier')
        d['archived'] = bool(d.get('archived'))
        d['imageQuality'] = d.pop('image_quality', '') or ''
        d['imageCount'] = d.pop('image_count', 1) or 1
        d['outputFormat'] = d.pop('output_format', '') or ''
        d['status'] = d.pop('generation_status', '') or 'COMPLETED'
        d['elapsedMs'] = d.pop('elapsed_ms', 0) or 0
        d['sizeBytes'] = d.pop('size_bytes', 0) or 0
        raw_audio_enabled = d.pop('audio_enabled', None)
        d['audioEnabled'] = None if raw_audio_enabled is None else bool(raw_audio_enabled)
        d['referenceCounts'] = json.loads(d.pop('reference_counts', '{}') or '{}')
        d['finalPrompt'] = d.pop('final_prompt', '') or ''
        d['sourceTaskId'] = d.pop('source_task_id', '') or ''
        out.append(d)
    return out


def get_archive(archive_id):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute('SELECT * FROM aivideo_archive WHERE id = ?', (archive_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def delete_archive(archive_id):
    conn = _get_conn()
    with _write_lock:
        conn.execute('DELETE FROM aivideo_archive WHERE id = ?', (archive_id,))
        conn.commit()


def _ensure_visits_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS aivideo_lock_visits (
            device_id TEXT PRIMARY KEY,
            first_seen_ts INTEGER,
            last_seen_ts INTEGER,
            visit_count INTEGER DEFAULT 1
        )
    """)


def record_lock_visit(device_id):
    """Catat satu device sebagai 'pernah lihat halaman lock'. device_id
    dikirim dari localStorage sisi browser (persist lintas refresh/reopen),
    dan menjadi PRIMARY KEY di sini — jadi device yang sama refresh 100x
    tetap cuma 1 baris (visit_count-nya yang naik, bukan total device-nya).
    Device baru (device_id belum pernah tercatat) -> total unique bertambah 1.
    Return total unique device SETELAH update."""
    import time as _time
    if not device_id or not isinstance(device_id, str) or len(device_id) > 128:
        return get_lock_visit_total()
    conn = _get_conn()
    with _write_lock:
        _ensure_visits_table(conn)
        now = int(_time.time())
        conn.execute('''
            INSERT INTO aivideo_lock_visits (device_id, first_seen_ts, last_seen_ts, visit_count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(device_id) DO UPDATE SET
                last_seen_ts=excluded.last_seen_ts,
                visit_count=aivideo_lock_visits.visit_count + 1
        ''', (device_id, now, now))
        conn.commit()
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM aivideo_lock_visits')
        return cur.fetchone()[0]


def get_lock_visit_total():
    conn = _get_conn()
    with _write_lock:
        _ensure_visits_table(conn)
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM aivideo_lock_visits')
        return cur.fetchone()[0]


def _ensure_lock_stats_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS aivideo_lock_stats (
            key TEXT PRIMARY KEY,
            value INTEGER DEFAULT 0
        )
    """)
    conn.execute("INSERT OR IGNORE INTO aivideo_lock_stats (key, value) VALUES ('total_attempts', 0)")
    conn.execute("INSERT OR IGNORE INTO aivideo_lock_stats (key, value) VALUES ('total_failed', 0)")


def record_unlock_attempt(success):
    """Hitungan GLOBAL, lintas semua orang & device, seumur hidup server —
    beda dari _AIVIDEO_UNLOCK_ATTEMPTS di app.py yang cuma per-IP dan reset
    tiap kali lockout selesai. Ini murni statistik ('sudah berapa kali
    password dicoba, berapa yang salah'), tidak memengaruhi logika lockout
    sama sekali. Return (total_attempts, total_failed) setelah update."""
    conn = _get_conn()
    with _write_lock:
        _ensure_lock_stats_table(conn)
        conn.execute("UPDATE aivideo_lock_stats SET value = value + 1 WHERE key = 'total_attempts'")
        if not success:
            conn.execute("UPDATE aivideo_lock_stats SET value = value + 1 WHERE key = 'total_failed'")
        conn.commit()
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM aivideo_lock_stats WHERE key IN ('total_attempts','total_failed')")
        rows = dict(cur.fetchall())
    return rows.get('total_attempts', 0), rows.get('total_failed', 0)


def get_lock_stats():
    conn = _get_conn()
    with _write_lock:
        _ensure_lock_stats_table(conn)
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM aivideo_lock_stats WHERE key IN ('total_attempts','total_failed')")
        rows = dict(cur.fetchall())
    return rows.get('total_attempts', 0), rows.get('total_failed', 0)
