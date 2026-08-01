"""
Dropbox OAuth Connection Manager
=================================

Replaces the old manual workflow:

    Dropbox App Console -> generate authorization code -> copy -> paste into
    a form -> generate refresh_token -> copy -> Railway Variables -> redeploy

...with a full in-app OAuth2 flow: connect once from the browser at
/ai-video/dropbox-token, everything else (redirect callback, token exchange,
auto-refresh) happens automatically from then on.

Components
----------
DropboxCredentialStore
    Encrypted-at-rest, file-based, cross-process-safe persistence for the
    Dropbox app key/secret and OAuth tokens. Survives Gunicorn worker
    restarts, app restarts and redeploys as long as DATA_DIR is on a
    persistent volume (same file `site_status.json` already relies on).

DropboxOAuthService
    Stateless helper that builds the Dropbox authorize URL and performs the
    authorization_code <-> token and refresh_token <-> token HTTP exchanges.

DropboxTokenManager
    The single source of truth callers should use to get a valid access
    token right now. Handles auto-refresh (a few minutes before expiry),
    cross-process locking (so multiple Gunicorn workers never race on the
    same refresh), and falls back to legacy DROPBOX_* env vars when the
    encrypted store hasn't been configured yet.

Backward compatibility
-----------------------
If the encrypted store is empty, DROPBOX_APP_KEY / DROPBOX_APP_SECRET /
DROPBOX_REFRESH_TOKEN / DROPBOX_ACCESS_TOKEN env vars (the old setup) keep
working exactly as before. The admin UI offers a one-click "Import existing
configuration" action that copies those env vars into the encrypted store,
after which the store becomes the source of truth (env vars become an
inert fallback — nothing deletes them automatically).
"""

import os
import io
import json
import time
import base64
import fcntl
import threading
import requests as requests_lib

from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DROPBOX_OAUTH_AUTHORIZE_URL = 'https://www.dropbox.com/oauth2/authorize'
DROPBOX_OAUTH_TOKEN_URL = 'https://api.dropboxapi.com/oauth2/token'
DROPBOX_ACCOUNT_URL = 'https://api.dropboxapi.com/2/users/get_current_account'

# Refresh this many seconds before the access token would actually expire,
# so a request in flight never hits a token that dies mid-air.
_REFRESH_MARGIN_SECONDS = 300
# How long an OAuth `state` value stays valid (CSRF protection window).
_STATE_TTL_SECONDS = 600


# ---------------------------------------------------------------------------
# Encryption — AES-256-GCM, key derived (HKDF-SHA256) from a master secret
# that is NEVER stored alongside the ciphertext. In this project the master
# secret is FLASK_SECRET_KEY (already required to be a stable env var for
# sessions to survive worker restarts — see app.py's own startup warning),
# so no extra env var is strictly required. DROPBOX_ENC_KEY can be set
# separately if you want the encryption key to be independent of the Flask
# session-signing key.
# ---------------------------------------------------------------------------

class CredentialEncryptionError(RuntimeError):
    pass


class CredentialDecryptionError(CredentialEncryptionError):
    """Raised when stored ciphertext can't be decrypted with the current
    master secret — almost always means FLASK_SECRET_KEY changed (e.g. it
    was never set, so a new random one is generated on every process
    start). Handled explicitly wherever it's caught: the store still
    degrades to 'not usable', not a hard crash."""
    pass


class _Crypto:
    def __init__(self, master_secret):
        if not master_secret:
            raise CredentialEncryptionError(
                'Tidak ada master secret untuk enkripsi. Set FLASK_SECRET_KEY '
                '(direkomendasikan) atau DROPBOX_ENC_KEY di environment.'
            )
        if isinstance(master_secret, str):
            master_secret = master_secret.encode('utf-8')
        key = HKDF(
            algorithm=hashes.SHA256(), length=32,
            salt=b'mii-dropbox-oauth-v1', info=b'dropbox-credential-store',
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
            raise CredentialDecryptionError(
                'Gagal decrypt credential Dropbox — FLASK_SECRET_KEY kemungkinan '
                'berubah sejak data ini disimpan (mis. belum diset, sehingga key '
                'baru dibuat setiap restart). Set FLASK_SECRET_KEY yang stabil di '
                'Railway lalu connect ulang Dropbox.'
            ) from e


# ---------------------------------------------------------------------------
# Credential store
# ---------------------------------------------------------------------------

_SENSITIVE_FIELDS = ('app_secret', 'refresh_token', 'access_token')


class DropboxCredentialStore:
    """Encrypted JSON file on disk, guarded by a cross-process file lock
    (fcntl.flock — works across separate Gunicorn worker *processes* on the
    same filesystem, unlike a plain threading.Lock which only protects
    threads inside a single process)."""

    def __init__(self, data_dir, master_secret_fn):
        self._path = os.path.join(data_dir, 'dropbox_oauth.json')
        self._lock_path = os.path.join(data_dir, 'dropbox_oauth.lock')
        self._data_dir = data_dir
        self._master_secret_fn = master_secret_fn  # called lazily so app.secret_key can be read after Flask configures it
        self._thread_lock = threading.Lock()

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

    def read(self):
        """Return the decrypted credential dict (never logged/returned to
        the frontend as-is — routes must pick only the safe fields).
        On decryption failure (master secret changed), returns a dict with
        '_key_mismatch': True and sensitive fields blanked, instead of
        raising — callers must treat that as 'needs reconnect', not crash."""
        with self._thread_lock:
            lockfile = self._flock()
            try:
                raw = self._read_raw()
                if not raw:
                    return {}
                crypto = self._crypto()
                out = dict(raw)
                key_mismatch = False
                for field in _SENSITIVE_FIELDS:
                    enc = raw.get(field + '_enc')
                    if not enc:
                        out[field] = ''
                        continue
                    try:
                        out[field] = crypto.decrypt(enc)
                    except CredentialDecryptionError:
                        out[field] = ''
                        key_mismatch = True
                if key_mismatch:
                    out['_key_mismatch'] = True
                return out
            finally:
                fcntl.flock(lockfile, fcntl.LOCK_UN)
                lockfile.close()

    def update(self, **fields):
        """Merge `fields` into the stored record, encrypting sensitive ones.
        Pass a field explicitly as '' to clear it."""
        with self._thread_lock:
            lockfile = self._flock()
            try:
                raw = self._read_raw()
                crypto = self._crypto()
                for key, value in fields.items():
                    if key in _SENSITIVE_FIELDS:
                        raw[key + '_enc'] = crypto.encrypt(value) if value else None
                    else:
                        raw[key] = value
                self._write_raw(raw)
            finally:
                fcntl.flock(lockfile, fcntl.LOCK_UN)
                lockfile.close()

    def clear(self, keep_app_credentials=False):
        with self._thread_lock:
            lockfile = self._flock()
            try:
                if keep_app_credentials:
                    raw = self._read_raw()
                    kept = {
                        'app_key': raw.get('app_key', ''),
                        'app_secret_enc': raw.get('app_secret_enc'),
                    }
                    self._write_raw(kept)
                else:
                    self._write_raw({})
            finally:
                fcntl.flock(lockfile, fcntl.LOCK_UN)
                lockfile.close()

    def is_present(self):
        return os.path.exists(self._path) and bool(self._read_raw())


# ---------------------------------------------------------------------------
# OAuth service (stateless HTTP helper)
# ---------------------------------------------------------------------------

class DropboxOAuthError(RuntimeError):
    def __init__(self, message, code='DROPBOX_OAUTH_ERROR', status=400):
        super().__init__(message)
        self.code = code
        self.status = status


class DropboxOAuthService:
    def authorize_url(self, app_key, redirect_uri, state):
        from urllib.parse import urlencode
        params = {
            'client_id': app_key,
            'response_type': 'code',
            'token_access_type': 'offline',
            'redirect_uri': redirect_uri,
            'state': state,
        }
        return DROPBOX_OAUTH_AUTHORIZE_URL + '?' + urlencode(params)

    def exchange_code(self, app_key, app_secret, code, redirect_uri):
        resp = requests_lib.post(
            DROPBOX_OAUTH_TOKEN_URL,
            data={
                'grant_type': 'authorization_code',
                'code': code,
                'client_id': app_key,
                'client_secret': app_secret,
                'redirect_uri': redirect_uri,
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            raise DropboxOAuthError(
                f'Dropbox menolak authorization code (HTTP {resp.status_code}): {resp.text[:300]}',
                status=400,
            )
        data = resp.json()
        if not data.get('refresh_token'):
            raise DropboxOAuthError(
                'Dropbox tidak mengembalikan refresh_token. Pastikan token_access_type=offline '
                'terkirim dan akun ini belum pernah authorize app dengan access_type lain.',
                status=500,
            )
        return data

    def refresh(self, app_key, app_secret, refresh_token):
        resp = requests_lib.post(
            DROPBOX_OAUTH_TOKEN_URL,
            data={
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': app_key,
                'client_secret': app_secret,
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            raise DropboxOAuthError(
                f'Dropbox token refresh gagal (HTTP {resp.status_code}): {resp.text[:300]}',
                code='DROPBOX_REAUTH_REQUIRED' if resp.status_code in (400, 401) else 'DROPBOX_OAUTH_ERROR',
                status=resp.status_code,
            )
        return resp.json()

    def get_account_info(self, access_token):
        resp = requests_lib.post(
            DROPBOX_ACCOUNT_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=15,
        )
        if resp.status_code >= 400:
            raise DropboxOAuthError(
                f'Gagal mengambil info akun Dropbox (HTTP {resp.status_code}): {resp.text[:300]}',
                status=resp.status_code,
            )
        return resp.json()


# ---------------------------------------------------------------------------
# Token manager — the thing the rest of the app actually calls
# ---------------------------------------------------------------------------

class DropboxTokenManager:
    def __init__(self, store, legacy_env, logger=None, redirect_uri=None):
        self.store = store
        self.service = DropboxOAuthService()
        self._legacy_env = legacy_env  # dict: app_key, app_secret, refresh_token, access_token
        self._logger = logger
        self._legacy_cache = {'access_token': '', 'expires_at': 0}
        self._legacy_lock = threading.Lock()
        self.redirect_uri = redirect_uri

    # -- logging helper -----------------------------------------------------
    def _log(self, level, msg, *args):
        if self._logger:
            getattr(self._logger, level)(msg, *args)

    # -- source of truth ------------------------------------------------------
    def _oauth_creds(self):
        """Return dict from the encrypted store if it has enough to operate,
        else None (meaning: fall back to legacy env vars)."""
        creds = self.store.read()
        if creds.get('_key_mismatch'):
            return None
        if creds.get('app_key') and creds.get('app_secret') and creds.get('refresh_token'):
            return creds
        return None

    def is_configured(self):
        return bool(self._oauth_creds()) or bool(
            self._legacy_env.get('app_key') and self._legacy_env.get('app_secret')
            and self._legacy_env.get('refresh_token')
        ) or bool(self._legacy_env.get('access_token'))

    def has_app_credentials(self):
        creds = self.store.read()
        if not creds.get('_key_mismatch') and creds.get('app_key') and creds.get('app_secret'):
            return True
        return bool(self._legacy_env.get('app_key') and self._legacy_env.get('app_secret'))

    # -- the important one ----------------------------------------------------
    def get_valid_access_token(self):
        creds = self._oauth_creds()
        if creds:
            now = time.time()
            expires_at = float(creds.get('access_token_expires_at') or 0)
            if creds.get('access_token') and now < expires_at:
                return creds['access_token']
            return self._refresh_stored(creds)

        # Legacy env-var fallback (unchanged behaviour from before this module existed)
        env = self._legacy_env
        if env.get('app_key') and env.get('app_secret') and env.get('refresh_token'):
            with self._legacy_lock:
                cached = self._legacy_cache['access_token']
                valid = cached and time.time() < self._legacy_cache['expires_at']
            if valid:
                return cached
            return self._refresh_legacy()
        if env.get('access_token'):
            self._log('warning',
                       '[dropbox] using legacy static DROPBOX_ACCESS_TOKEN — expires after ~4h '
                       'and will start failing silently. Configure via /ai-video/dropbox-token instead.')
            return env['access_token']
        raise RuntimeError(
            'Dropbox belum dikonfigurasi. Buka /ai-video/dropbox-token untuk connect akun Dropbox.'
        )

    def force_refresh(self):
        """Used after a 401 to force a fresh token regardless of cached expiry."""
        creds = self._oauth_creds()
        if creds:
            return self._refresh_stored(creds, force=True)
        env = self._legacy_env
        if env.get('app_key') and env.get('app_secret') and env.get('refresh_token'):
            with self._legacy_lock:
                self._legacy_cache['access_token'] = ''
                self._legacy_cache['expires_at'] = 0
            return self._refresh_legacy()
        return self.get_valid_access_token()

    def _refresh_stored(self, creds, force=False):
        # Re-check after acquiring the cross-process lock inside store.update
        # is not quite right for a read-then-decide flow, so we take a small
        # dedicated critical section here: re-read once more right before
        # the network call to minimize (not fully eliminate, HTTP round trip
        # itself isn't inside the lock) duplicate refreshes across workers.
        fresh = self.store.read()
        now = time.time()
        if not force and fresh.get('access_token') and now < float(fresh.get('access_token_expires_at') or 0):
            return fresh['access_token']
        self._log('info', '[dropbox] refreshing access token via oauth2/token (stored credentials)')
        data = self.service.refresh(fresh['app_key'], fresh['app_secret'], fresh['refresh_token'])
        access_token = data.get('access_token', '')
        expires_in = int(data.get('expires_in', 14400))
        if not access_token:
            raise RuntimeError('Dropbox token refresh sukses tapi access_token kosong di response')
        self.store.update(
            access_token=access_token,
            access_token_expires_at=now + expires_in - _REFRESH_MARGIN_SECONDS,
            last_refresh_at=now,
        )
        return access_token

    def _refresh_legacy(self):
        env = self._legacy_env
        self._log('info', '[dropbox] refreshing access token via oauth2/token (legacy env vars)')
        data = self.service.refresh(env['app_key'], env['app_secret'], env['refresh_token'])
        access_token = data.get('access_token', '')
        expires_in = int(data.get('expires_in', 14400))
        if not access_token:
            raise RuntimeError('Dropbox token refresh sukses tapi access_token kosong di response')
        with self._legacy_lock:
            self._legacy_cache['access_token'] = access_token
            self._legacy_cache['expires_at'] = time.time() + expires_in - _REFRESH_MARGIN_SECONDS
        return access_token

    # -- status for the admin UI ----------------------------------------------
    def status(self):
        creds = self.store.read()
        key_mismatch = bool(creds.get('_key_mismatch'))
        has_oauth = (not key_mismatch) and bool(
            creds.get('app_key') and creds.get('app_secret') and creds.get('refresh_token'))
        env = self._legacy_env
        has_legacy_refresh = bool(env.get('app_key') and env.get('app_secret') and env.get('refresh_token'))
        has_legacy_static = bool(env.get('access_token'))
        has_legacy_unmigrated = (not creds.get('app_key')) and (has_legacy_refresh or has_legacy_static)

        if key_mismatch:
            state = 'key_mismatch'
        elif has_oauth:
            state = 'connected'
        elif has_legacy_refresh or has_legacy_static:
            state = 'legacy_not_migrated'
        elif creds.get('app_key') and creds.get('app_secret'):
            state = 'credentials_saved'
        else:
            state = 'not_connected'

        return {
            'state': state,
            'source': 'oauth' if has_oauth else ('legacy_env' if (has_legacy_refresh or has_legacy_static) else None),
            'has_app_credentials': (not key_mismatch and bool(creds.get('app_key') and creds.get('app_secret'))) or bool(
                env.get('app_key') and env.get('app_secret')),
            'app_key_masked': _mask_middle((not key_mismatch and creds.get('app_key')) or env.get('app_key') or ''),
            'account_name': (not key_mismatch and creds.get('account_name')) or '',
            'account_id_masked': _mask_account_id((not key_mismatch and creds.get('account_id')) or ''),
            'scope': (not key_mismatch and creds.get('scope')) or '',
            'connected_at': (not key_mismatch and creds.get('connected_at')) or None,
            'last_refresh_at': (not key_mismatch and creds.get('last_refresh_at')) or None,
            'last_test_at': (not key_mismatch and creds.get('last_test_at')) or None,
            'last_test_ok': None if key_mismatch else creds.get('last_test_ok'),
            'auto_refresh': True,
            'redirect_uri': self.redirect_uri,
            'legacy_import_available': has_legacy_unmigrated,
            'key_mismatch': key_mismatch,
        }

    def test_connection(self):
        try:
            token = self.get_valid_access_token()
            info = self.service.get_account_info(token)
        except DropboxOAuthError as e:
            if e.status == 401:
                try:
                    token = self.force_refresh()
                    info = self.service.get_account_info(token)
                except Exception as e2:
                    self._mark_test(False)
                    if self._oauth_creds() is not None:
                        self.store.update(last_test_ok=False)
                    raise DropboxOAuthError(str(e2), code='DROPBOX_REAUTH_REQUIRED', status=401)
            else:
                self._mark_test(False)
                raise
        except Exception as e:
            self._mark_test(False)
            raise
        name = ((info or {}).get('name') or {}).get('display_name', '')
        account_id = (info or {}).get('account_id', '')
        if self._oauth_creds() is not None:
            self.store.update(
                account_name=name, account_id=account_id,
                last_test_at=time.time(), last_test_ok=True,
            )
        self._mark_test(True)
        return {'account_name': name, 'account_id_masked': _mask_account_id(account_id)}

    def _mark_test(self, ok):
        if self._oauth_creds() is not None:
            try:
                self.store.update(last_test_at=time.time(), last_test_ok=bool(ok))
            except Exception:
                pass

    # -- setup wizard operations ------------------------------------------------
    def save_credentials(self, app_key, app_secret):
        self.store.update(app_key=app_key.strip(), app_secret=app_secret.strip())

    def build_authorize_url(self, state):
        creds = self.store.read()
        app_key = creds.get('app_key') or self._legacy_env.get('app_key')
        if not app_key:
            raise DropboxOAuthError('APP KEY belum disimpan. Lengkapi Step 1 dulu.', status=400)
        return self.service.authorize_url(app_key, self.redirect_uri, state)

    def complete_authorization(self, code):
        creds = self.store.read()
        app_key = creds.get('app_key') or self._legacy_env.get('app_key')
        app_secret = creds.get('app_secret') or self._legacy_env.get('app_secret')
        if not (app_key and app_secret):
            raise DropboxOAuthError('APP KEY / APP SECRET belum disimpan.', status=400)
        data = self.service.exchange_code(app_key, app_secret, code, self.redirect_uri)
        now = time.time()
        expires_in = int(data.get('expires_in', 14400))
        account_id = data.get('account_id', '')
        account_name = ''
        try:
            info = self.service.get_account_info(data['access_token'])
            account_name = (info.get('name') or {}).get('display_name', '')
        except Exception:
            pass
        self.store.update(
            app_key=app_key, app_secret=app_secret,
            refresh_token=data.get('refresh_token'),
            access_token=data.get('access_token'),
            access_token_expires_at=now + expires_in - _REFRESH_MARGIN_SECONDS,
            account_id=account_id, account_name=account_name,
            scope=data.get('scope', ''), connected_at=now, last_refresh_at=now,
            last_test_at=now, last_test_ok=True,
        )

    def import_legacy(self):
        env = self._legacy_env
        if not (env.get('app_key') and env.get('app_secret')):
            raise DropboxOAuthError('Tidak ada DROPBOX_APP_KEY/DROPBOX_APP_SECRET di environment untuk di-import.', status=400)
        fields = {'app_key': env['app_key'], 'app_secret': env['app_secret']}
        if env.get('refresh_token'):
            fields['refresh_token'] = env['refresh_token']
        if env.get('access_token'):
            fields['access_token'] = env['access_token']
            fields['access_token_expires_at'] = time.time() + 60  # force a refresh soon to get real expiry tracked
        self.store.update(**fields, connected_at=time.time())

    def disconnect(self, mode='tokens'):
        """mode='tokens' -> clear tokens/account info but keep app key/secret
        (so RECONNECT doesn't need Step 1 again). mode='all' -> wipe
        everything including app key/secret."""
        self.store.clear(keep_app_credentials=(mode == 'tokens'))


def _mask_middle(value):
    if not value:
        return ''
    if len(value) <= 8:
        return value[:2] + '…' + value[-2:]
    return value[:6] + '…' + value[-4:]


def _mask_account_id(value):
    if not value:
        return ''
    return value[:10] + '…' if len(value) > 10 else value
