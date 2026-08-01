"""
Generic Application Secrets Store
==================================

Same idea as dropbox_oauth.py's credential store, generalized to any simple
key/value secret (API keys, passwords, chat IDs, bot tokens) so they can be
configured once from the browser at /ai-video/app-secrets and survive:

  - GitHub repo swaps / redeploys
  - Railway restarts
  - container replacement

...without having to re-enter them in Railway Variables every time.

Encrypted at rest (AES-256-GCM, key derived via HKDF-SHA256 from
FLASK_SECRET_KEY — same approach as dropbox_oauth.py, kept as a separate,
self-contained implementation here on purpose so the two stores don't share
mutable state or a coupled failure mode). Cross-process safe via
fcntl.flock, same reasoning as the Dropbox store: Gunicorn runs multiple
worker *processes*, so a plain threading.Lock would not protect against a
second worker reading/writing at the same time.

Every secret still falls back to its original os.environ.get(...) value
when the encrypted store has nothing for it — nothing already deployed via
Railway Variables breaks by adding this.
"""

import os
import json
import time
import base64
import fcntl
import threading

from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecretStoreError(RuntimeError):
    pass


class SecretDecryptionError(SecretStoreError):
    """Master secret (FLASK_SECRET_KEY) changed since these values were
    saved. Handled explicitly wherever raised — degrade to 'value
    unavailable', never crash the caller."""
    pass


class _Crypto:
    def __init__(self, master_secret):
        if not master_secret:
            raise SecretStoreError(
                'Tidak ada master secret untuk enkripsi. Set FLASK_SECRET_KEY di environment.'
            )
        if isinstance(master_secret, str):
            master_secret = master_secret.encode('utf-8')
        key = HKDF(
            algorithm=hashes.SHA256(), length=32,
            salt=b'mii-app-secrets-v1', info=b'app-secrets-store',
        ).derive(master_secret)
        self._aead = AESGCM(key)

    def encrypt(self, plaintext):
        if plaintext is None:
            return None
        nonce = os.urandom(12)
        ct = self._aead.encrypt(nonce, plaintext.encode('utf-8'), None)
        return base64.urlsafe_b64encode(nonce + ct).decode('ascii')

    def decrypt(self, token):
        if not token:
            return ''
        try:
            raw = base64.urlsafe_b64decode(token.encode('ascii'))
            nonce, ct = raw[:12], raw[12:]
            return self._aead.decrypt(nonce, ct, None).decode('utf-8')
        except Exception as e:
            raise SecretDecryptionError(
                'Gagal decrypt — FLASK_SECRET_KEY kemungkinan berubah sejak nilai ini disimpan.'
            ) from e


class SecretsStore:
    """One encrypted JSON file: { "<KEY>": {"v": "<enc>", "updated_at": ts}, ... } """

    def __init__(self, data_dir, master_secret_fn):
        self._path = os.path.join(data_dir, 'app_secrets.json')
        self._lock_path = os.path.join(data_dir, 'app_secrets.lock')
        self._data_dir = data_dir
        self._master_secret_fn = master_secret_fn
        self._thread_lock = threading.Lock()
        # Small in-process cache so every request handler doesn't re-open +
        # re-decrypt the file on every single call site (Gemini key alone
        # is read on every chat message). Invalidated on any write, and
        # naturally re-read if another worker process changes the file
        # (each worker keeps its own cache — fine, these change rarely and
        # a few seconds of staleness across workers is a non-issue here).
        self._cache = None
        self._cache_at = 0
        self._cache_ttl = 5.0

    def _crypto(self):
        return _Crypto(self._master_secret_fn())

    def _flock(self):
        os.makedirs(self._data_dir, exist_ok=True)
        f = open(self._lock_path, 'a+')
        fcntl.flock(f, fcntl.LOCK_EX)
        return f

    def _read_raw(self):
        if not os.path.exists(self._path):
            return {}
        try:
            with open(self._path, 'r', encoding='utf-8') as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _write_raw(self, data):
        tmp_path = self._path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self._path)

    def _decrypt_all(self, raw):
        crypto = self._crypto()
        out = {}
        for key, entry in raw.items():
            enc = (entry or {}).get('v')
            if not enc:
                continue
            try:
                out[key] = {'value': crypto.decrypt(enc), 'updated_at': entry.get('updated_at')}
            except SecretDecryptionError:
                out[key] = {'value': '', 'updated_at': entry.get('updated_at'), 'key_mismatch': True}
        return out

    def _load(self, force=False):
        now = time.time()
        if not force and self._cache is not None and (now - self._cache_at) < self._cache_ttl:
            return self._cache
        with self._thread_lock:
            lockfile = self._flock()
            try:
                raw = self._read_raw()
                decrypted = self._decrypt_all(raw)
                self._cache = decrypted
                self._cache_at = time.time()
                return decrypted
            finally:
                fcntl.flock(lockfile, fcntl.LOCK_UN)
                lockfile.close()

    def get(self, key, default=''):
        """Decrypted value for `key`, or `default` if unset / undecryptable."""
        entry = self._load().get(key)
        if not entry or entry.get('key_mismatch'):
            return default
        return entry.get('value') or default

    def get_all_meta(self):
        """{key: {'has_value': bool, 'updated_at': ts, 'key_mismatch': bool}} —
        never includes the actual decrypted value (for the admin list view)."""
        data = self._load()
        return {
            k: {
                'has_value': bool(v.get('value')) and not v.get('key_mismatch'),
                'updated_at': v.get('updated_at'),
                'key_mismatch': bool(v.get('key_mismatch')),
            }
            for k, v in data.items()
        }

    def set(self, key, value):
        with self._thread_lock:
            lockfile = self._flock()
            try:
                raw = self._read_raw()
                crypto = self._crypto()
                if value:
                    raw[key] = {'v': crypto.encrypt(value), 'updated_at': time.time()}
                else:
                    raw.pop(key, None)
                self._write_raw(raw)
            finally:
                fcntl.flock(lockfile, fcntl.LOCK_UN)
                lockfile.close()
        self._cache = None  # invalidate

    def delete(self, key):
        self.set(key, '')

    def has_any_key_mismatch(self):
        return any(v.get('key_mismatch') for v in self._load().values())
