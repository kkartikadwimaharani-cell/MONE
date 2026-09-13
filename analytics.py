import sqlite3
import threading
import os

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.abspath(
    os.environ.get('MII_DATA_DIR')
    or os.environ.get('RAILWAY_VOLUME_MOUNT_PATH')
    or _MODULE_DIR
)
_DB_PATH = os.path.abspath(
    os.environ.get('MII_ANALYTICS_DB')
    or os.path.join(_DATA_DIR, 'analytics.db')
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
            CREATE TABLE IF NOT EXISTS analytics_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                ip_hash TEXT,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_visitor_ip
            ON analytics_events (event_type, ip_hash)
        ''')
        conn.commit()


def has_visitor(ip_hash):
    """Return True if a visitor event already exists for this ip_hash."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM analytics_events WHERE event_type = 'visitor' AND ip_hash = ? LIMIT 1",
        (ip_hash,)
    )
    return cur.fetchone() is not None


def record_event(event_type, ip_hash, user_agent):
    conn = _get_conn()
    with _write_lock:
        conn.execute(
            'INSERT INTO analytics_events (event_type, ip_hash, user_agent) VALUES (?, ?, ?)',
            (event_type, ip_hash, user_agent)
        )
        conn.commit()


def get_stats():
    conn = _get_conn()
    cur = conn.cursor()

    # Single GROUP BY query instead of 8 sequential COUNT queries
    cur.execute("SELECT event_type, COUNT(*) as count FROM analytics_events GROUP BY event_type")
    counts = {}
    for row in cur.fetchall():
        counts[row[0]] = row[1]

    # Unique visitors requires a distinct count
    cur.execute("SELECT COUNT(DISTINCT ip_hash) FROM analytics_events WHERE event_type = 'visitor'")
    total_visitors = cur.fetchone()[0]

    total_views = counts.get('page_view', 0)
    total_download_clicks = counts.get('download_click', 0)
    total_download_success = counts.get('download_success', 0)
    total_downloads = total_download_success

    instagram_clicks = counts.get('instagram_click', 0)
    telegram_clicks = counts.get('telegram_click', 0)
    whatsapp_clicks = counts.get('whatsapp_click', 0)
    lynkid_clicks = counts.get('lynkid_click', 0)
    total_social_clicks = instagram_clicks + telegram_clicks + whatsapp_clicks + lynkid_clicks

    return {
        'total_views': total_views,
        'total_visitors': total_visitors,
        'total_downloads': total_downloads,
        'total_download_clicks': total_download_clicks,
        'total_download_success': total_download_success,
        'total_social_clicks': total_social_clicks,
        'instagram_clicks': instagram_clicks,
        'telegram_clicks': telegram_clicks,
        'whatsapp_clicks': whatsapp_clicks,
        'lynkid_clicks': lynkid_clicks,
    }


def get_detailed_stats():
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT event_type, COUNT(*) as count FROM analytics_events GROUP BY event_type ORDER BY count DESC")
    rows = cur.fetchall()
    return [{'event_type': row[0], 'count': row[1]} for row in rows]
