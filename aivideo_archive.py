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

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aivideo_archive.db')
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
        conn.commit()


def upsert_archive(rec):
    """rec: dict with at least 'id'. video_url/image_url MUST already be
    Dropbox URLs by the time they get here (the API route is responsible
    for uploading to Dropbox first if needed)."""
    conn = _get_conn()
    with _write_lock:
        conn.execute('''
            INSERT INTO aivideo_archive
                (id, media_type, video_url, image_url, thumb, prompt, model, quality,
                 duration, ratio, created_at_label, created_at_ts, ref_images, ref_videos,
                 model_key, model_tier, archived)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                media_type=excluded.media_type, video_url=excluded.video_url,
                image_url=excluded.image_url, thumb=excluded.thumb, prompt=excluded.prompt,
                model=excluded.model, quality=excluded.quality, duration=excluded.duration,
                ratio=excluded.ratio, created_at_label=excluded.created_at_label,
                created_at_ts=excluded.created_at_ts, ref_images=excluded.ref_images,
                ref_videos=excluded.ref_videos, model_key=excluded.model_key,
                model_tier=excluded.model_tier, archived=excluded.archived
        ''', (
            rec.get('id'),
            rec.get('media_type') or ('video' if rec.get('videoUrl') else 'image'),
            rec.get('videoUrl') or '',
            rec.get('imageUrl') or '',
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
        d['refImages'] = json.loads(d.pop('ref_images') or '[]')
        d['refVideos'] = json.loads(d.pop('ref_videos') or '[]')
        d['videoUrl'] = d.pop('video_url')
        d['imageUrl'] = d.pop('image_url')
        d['createdAtLabel'] = d.pop('created_at_label')
        d['createdAtTs'] = d.pop('created_at_ts')
        d['modelKey'] = d.pop('model_key')
        d['modelTier'] = d.pop('model_tier')
        d['archived'] = bool(d.get('archived'))
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
