"""Isolated Buffer integration for the protected MII PUBLISHER module.

This module deliberately has no dependency on the existing SOCIAL MEDIA or
AI-generation services. Buffer credentials remain server-side, media is
referenced by public HTTPS URL, and no media bytes are downloaded or proxied.
"""

from __future__ import annotations

import fcntl
import hashlib
import ipaddress
import json
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from urllib.parse import parse_qsl, urlencode, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests


BUFFER_GRAPHQL_URL = "https://api.buffer.com"
BUFFER_AUTHORIZE_URL = "https://auth.buffer.com/auth"
BUFFER_TOKEN_URL = "https://auth.buffer.com/token"
BUFFER_SCOPES = "account:read posts:read posts:write offline_access"
SUPPORTED_CHANNEL_SERVICES = {
    "bluesky", "facebook", "googlebusiness", "instagram", "linkedin",
    "mastodon", "pinterest", "threads", "twitter", "youtube",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}


class PublisherError(RuntimeError):
    status_code = 502


class PublisherValidationError(PublisherError):
    status_code = 400


class PublisherAuthError(PublisherError):
    status_code = 401


class PublisherRateLimitError(PublisherError):
    status_code = 429

    def __init__(self, message, retry_after=60):
        super().__init__(message)
        self.retry_after = max(1, min(int(retry_after or 60), 3600))


def _utc_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_error(value, limit=320):
    text = " ".join(str(value or "").split())
    return text[:limit] or "Buffer request failed."


def validate_media_url(value):
    """Validate a direct, public remote media URL without fetching it."""
    value = str(value or "").strip()
    if not value or len(value) > 2048:
        raise PublisherValidationError("Enter a valid media URL.")
    try:
        parsed = urlparse(value)
    except ValueError as exc:
        raise PublisherValidationError("The media URL is invalid.") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise PublisherValidationError("Media must use a public HTTPS URL.")
    if parsed.username or parsed.password or parsed.fragment:
        raise PublisherValidationError("Credentials and fragments are not allowed in media URLs.")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise PublisherValidationError("Local or private media URLs are not allowed.")
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise PublisherValidationError("Local or private media URLs are not allowed.")
    except ValueError:
        pass

    if host == "dropbox.com" or host.endswith(".dropbox.com"):
        raise PublisherValidationError(
            "Dropbox preview links are not direct media files. Use a stable public direct-download URL."
        )

    path = PurePosixPath(parsed.path)
    extension = path.suffix.lower()
    if extension in IMAGE_EXTENSIONS:
        media_type = "image"
    elif extension in VIDEO_EXTENSIONS:
        media_type = "video"
    else:
        raise PublisherValidationError(
            "The URL must point directly to a supported image or video file."
        )

    query_keys = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    expiring_keys = {
        "expires", "expiry", "signature", "sig", "token",
        "x-amz-expires", "x-amz-signature", "x-goog-expires", "x-goog-signature",
    }
    if query_keys & expiring_keys:
        raise PublisherValidationError(
            "Expiring or signed media URLs are unsafe for scheduled publishing. Use a stable public URL."
        )
    return {
        "url": value,
        "type": media_type,
        "filename": path.name[:180] or f"remote{extension}",
        "host": host,
        "transport": "direct_remote_url",
    }


def parse_schedule(date_value, time_value, timezone_name):
    date_value = str(date_value or "").strip()
    time_value = str(time_value or "").strip()
    timezone_name = str(timezone_name or "").strip()
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise PublisherValidationError("Select a valid timezone.") from exc
    try:
        local_dt = datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M").replace(tzinfo=zone)
    except ValueError as exc:
        raise PublisherValidationError("Enter a valid schedule date and time.") from exc
    utc_dt = local_dt.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if utc_dt < now + timedelta(minutes=2):
        raise PublisherValidationError("Scheduled time must be at least two minutes from now.")
    if utc_dt > now + timedelta(days=365):
        raise PublisherValidationError("Scheduled time cannot be more than one year ahead.")
    return utc_dt.isoformat().replace("+00:00", "Z")


class PublisherHistoryStore:
    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, "mii_publisher_history.json")
        self.lock_path = os.path.join(data_dir, "mii_publisher_history.lock")
        self._thread_lock = threading.Lock()
        os.makedirs(data_dir, exist_ok=True)

    def _locked(self):
        handle = open(self.lock_path, "a+")
        fcntl.flock(handle, fcntl.LOCK_EX)
        return handle

    def _read(self):
        if not os.path.exists(self.path):
            return {"history": [], "submissions": {}}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return {
                "history": list(data.get("history") or []),
                "submissions": dict(data.get("submissions") or {}),
            }
        except (OSError, ValueError, TypeError):
            return {"history": [], "submissions": {}}

    def _write(self, data):
        temp_path = self.path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(temp_path, self.path)

    def begin(self, key, request_hash):
        now = time.time()
        with self._thread_lock:
            lock = self._locked()
            try:
                data = self._read()
                prior = data["submissions"].get(key)
                if prior and prior.get("request_hash") != request_hash:
                    raise PublisherValidationError("This submission key was already used for different content.")
                if prior and prior.get("state") == "complete":
                    return prior.get("result"), True
                if prior and now - float(prior.get("created_at") or 0) < 300:
                    raise PublisherValidationError("This publishing request is already processing.")
                data["submissions"][key] = {
                    "request_hash": request_hash, "state": "processing", "created_at": now,
                }
                data["submissions"] = dict(list(data["submissions"].items())[-200:])
                self._write(data)
                return None, False
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
                lock.close()

    def complete(self, key, request_hash, result, records):
        with self._thread_lock:
            lock = self._locked()
            try:
                data = self._read()
                data["submissions"][key] = {
                    "request_hash": request_hash,
                    "state": "complete",
                    "created_at": time.time(),
                    "result": result,
                }
                data["history"] = (list(records) + data["history"])[:100]
                self._write(data)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
                lock.close()

    def fail(self, key, request_hash, records):
        result = {"ok": False, "records": records}
        self.complete(key, request_hash, result, records)

    def list(self):
        with self._thread_lock:
            lock = self._locked()
            try:
                return self._read()["history"][:100]
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
                lock.close()


class BufferPublisherService:
    TOKEN_KEYS = (
        "BUFFER_ACCESS_TOKEN", "BUFFER_REFRESH_TOKEN", "BUFFER_TOKEN_EXPIRES_AT",
        "BUFFER_TOKEN_SCOPE", "BUFFER_CONNECTION_DISABLED",
    )

    def __init__(self, data_dir, secret_store, get_secret, logger):
        self.data_dir = data_dir
        self.secret_store = secret_store
        self.get_secret = get_secret
        self.logger = logger
        self.history = PublisherHistoryStore(data_dir)
        self.refresh_lock_path = os.path.join(data_dir, "mii_publisher_buffer_refresh.lock")
        self._thread_lock = threading.Lock()

    def _secret(self, name):
        return str(self.get_secret(name, default="") or "")

    def oauth_configured(self):
        return all(self._secret(name) for name in ("BUFFER_CLIENT_ID", "BUFFER_CLIENT_SECRET", "BUFFER_REDIRECT_URI"))

    def _api_key(self):
        if self._secret("BUFFER_CONNECTION_DISABLED") == "1":
            return ""
        return self._secret("BUFFER_API_KEY")

    def connection_status(self):
        connected = bool(self._stored("BUFFER_ACCESS_TOKEN") or self._api_key())
        return {
            "connected": connected,
            "connection_type": "oauth" if self._stored("BUFFER_ACCESS_TOKEN") else ("api_key" if connected else None),
            "oauth_available": self.oauth_configured(),
            "connect_available": bool(self.oauth_configured() or self._secret("BUFFER_API_KEY")),
        }

    def _stored(self, key):
        try:
            return str(self.secret_store.get(key) or "")
        except Exception:
            return ""

    def _save_tokens(self, payload):
        access_token = str(payload.get("access_token") or "")
        if not access_token:
            raise PublisherAuthError("Buffer did not return an access token.")
        self.secret_store.set("BUFFER_ACCESS_TOKEN", access_token)
        if payload.get("refresh_token"):
            self.secret_store.set("BUFFER_REFRESH_TOKEN", str(payload["refresh_token"]))
        expires_in = max(0, int(payload.get("expires_in") or 0))
        self.secret_store.set("BUFFER_TOKEN_EXPIRES_AT", str(time.time() + expires_in) if expires_in else "")
        self.secret_store.set("BUFFER_TOKEN_SCOPE", str(payload.get("scope") or BUFFER_SCOPES))
        self.secret_store.delete("BUFFER_CONNECTION_DISABLED")

    def authorization_url(self, state, verifier):
        if not self.oauth_configured():
            if self._secret("BUFFER_API_KEY"):
                self.secret_store.delete("BUFFER_CONNECTION_DISABLED")
                return None
            raise PublisherValidationError("Buffer OAuth is not configured on the server.")
        challenge = hashlib.sha256(verifier.encode("ascii")).digest()
        import base64
        challenge = base64.urlsafe_b64encode(challenge).decode("ascii").rstrip("=")
        return BUFFER_AUTHORIZE_URL + "?" + urlencode({
            "response_type": "code",
            "client_id": self._secret("BUFFER_CLIENT_ID"),
            "redirect_uri": self._secret("BUFFER_REDIRECT_URI"),
            "scope": BUFFER_SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })

    def exchange_code(self, code, verifier):
        try:
            response = requests.post(BUFFER_TOKEN_URL, data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._secret("BUFFER_REDIRECT_URI"),
                "client_id": self._secret("BUFFER_CLIENT_ID"),
                "client_secret": self._secret("BUFFER_CLIENT_SECRET"),
                "code_verifier": verifier,
            }, timeout=(5, 20))
        except requests.RequestException as exc:
            raise PublisherError("Buffer connection timed out. Try again.") from exc
        if response.status_code >= 400:
            raise PublisherAuthError("Buffer rejected the connection request.")
        self._save_tokens(response.json())

    def disconnect(self):
        for key in self.TOKEN_KEYS:
            self.secret_store.delete(key)
        self.secret_store.set("BUFFER_CONNECTION_DISABLED", "1")

    def _access_token(self):
        stored = self._stored("BUFFER_ACCESS_TOKEN")
        if stored:
            expires_at = float(self._stored("BUFFER_TOKEN_EXPIRES_AT") or 0)
            if expires_at and expires_at <= time.time() + 60:
                return self._refresh_access_token()
            return stored
        api_key = self._api_key()
        if api_key:
            return api_key
        raise PublisherAuthError("Connect Buffer before publishing.")

    def _refresh_access_token(self):
        with self._thread_lock:
            lock = open(self.refresh_lock_path, "a+")
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                expires_at = float(self._stored("BUFFER_TOKEN_EXPIRES_AT") or 0)
                if expires_at > time.time() + 60 and self._stored("BUFFER_ACCESS_TOKEN"):
                    return self._stored("BUFFER_ACCESS_TOKEN")
                refresh_token = self._stored("BUFFER_REFRESH_TOKEN")
                if not refresh_token:
                    raise PublisherAuthError("Buffer connection expired. Reconnect Buffer.")
                try:
                    response = requests.post(BUFFER_TOKEN_URL, data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": self._secret("BUFFER_CLIENT_ID"),
                        "client_secret": self._secret("BUFFER_CLIENT_SECRET"),
                    }, timeout=(5, 20))
                except requests.RequestException as exc:
                    raise PublisherError("Buffer token refresh timed out.") from exc
                if response.status_code >= 400:
                    raise PublisherAuthError("Buffer connection expired. Reconnect Buffer.")
                self._save_tokens(response.json())
                return self._stored("BUFFER_ACCESS_TOKEN")
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
                lock.close()

    def _graphql(self, query, variables=None, retry_auth=True):
        token = self._access_token()
        try:
            response = requests.post(
                BUFFER_GRAPHQL_URL,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"query": query, "variables": variables or {}},
                timeout=(5, 25),
            )
        except requests.RequestException as exc:
            raise PublisherError("Buffer API timed out. No media was uploaded through MII.") from exc
        if response.status_code == 401 and retry_auth and self._stored("BUFFER_REFRESH_TOKEN"):
            self.secret_store.set("BUFFER_TOKEN_EXPIRES_AT", "1")
            self._refresh_access_token()
            return self._graphql(query, variables, retry_auth=False)
        if response.status_code == 429:
            raise PublisherRateLimitError("Buffer rate limit reached. Try again later.", response.headers.get("Retry-After", 60))
        if response.status_code in (401, 403):
            raise PublisherAuthError("Buffer authorization failed. Reconnect Buffer.")
        if response.status_code >= 500:
            raise PublisherError("Buffer is temporarily unavailable.")
        try:
            body = response.json()
        except ValueError as exc:
            raise PublisherError("Buffer returned an invalid response.") from exc
        if response.status_code >= 400:
            raise PublisherError("Buffer rejected the request.")
        errors = body.get("errors") or []
        if errors:
            message = _safe_error(errors[0].get("message") if isinstance(errors[0], dict) else errors[0])
            raise PublisherError(message)
        return body.get("data") or {}

    def accounts_and_channels(self):
        account_data = self._graphql("query MiiPublisherOrganizations { account { organizations { id name } } }")
        organizations = ((account_data.get("account") or {}).get("organizations") or [])
        safe_orgs = []
        safe_channels = []
        query = """query MiiPublisherChannels($input: ChannelsInput!) {
          channels(input: $input) { id name displayName service avatar isQueuePaused }
        }"""
        for org in organizations[:20]:
            org_id = str(org.get("id") or "")
            if not org_id:
                continue
            safe_orgs.append({"id": org_id, "name": str(org.get("name") or "Buffer Organization")[:120]})
            data = self._graphql(query, {"input": {"organizationId": org_id}})
            for channel in (data.get("channels") or [])[:100]:
                service = str(channel.get("service") or "").lower()
                if service not in SUPPORTED_CHANNEL_SERVICES:
                    continue
                safe_channels.append({
                    "id": str(channel.get("id") or ""),
                    "name": str(channel.get("displayName") or channel.get("name") or service.title())[:160],
                    "platform": service,
                    "avatar": str(channel.get("avatar") or "")[:2048],
                    "connected": True,
                    "queue_paused": bool(channel.get("isQueuePaused")),
                    "organization_id": org_id,
                })
        return {"organizations": safe_orgs, "channels": [item for item in safe_channels if item["id"]]}

    def publish(self, payload):
        if not isinstance(payload, dict) or payload.get("confirmed") is not True:
            raise PublisherValidationError("Explicit publishing confirmation is required.")
        caption = str(payload.get("caption") or "").strip()
        if len(caption) > 5000:
            raise PublisherValidationError("Caption cannot exceed 5,000 characters.")
        media = validate_media_url(payload.get("media_url"))
        channel_ids = list(dict.fromkeys(str(value) for value in (payload.get("channel_ids") or []) if value))
        if not channel_ids or len(channel_ids) > 10:
            raise PublisherValidationError("Select between one and ten connected channels.")
        mode = str(payload.get("mode") or "now")
        if mode not in {"now", "schedule"}:
            raise PublisherValidationError("Select a valid publishing mode.")
        due_at = None
        if mode == "schedule":
            due_at = parse_schedule(payload.get("date"), payload.get("time"), payload.get("timezone"))
        key = str(payload.get("idempotency_key") or "")
        try:
            key = str(__import__("uuid").UUID(key))
        except (ValueError, TypeError, AttributeError) as exc:
            raise PublisherValidationError("Invalid submission key. Refresh and try again.") from exc

        available = self.accounts_and_channels()["channels"]
        channel_map = {item["id"]: item for item in available}
        if any(channel_id not in channel_map for channel_id in channel_ids):
            raise PublisherValidationError("One or more selected channels are unavailable.")

        canonical = json.dumps({
            "caption": caption, "media_url": media["url"], "channel_ids": channel_ids,
            "mode": mode, "due_at": due_at,
        }, sort_keys=True, separators=(",", ":"))
        request_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        prior, duplicate = self.history.begin(key, request_hash)
        if duplicate:
            result = dict(prior or {})
            result["duplicate_prevented"] = True
            return result

        records = []
        mutation = """mutation MiiPublisherCreatePost($input: CreatePostInput!) {
          createPost(input: $input) {
            ... on PostActionSuccess { post { id status dueAt } }
            ... on MutationError { message }
          }
        }"""
        try:
            for channel_id in channel_ids:
                channel = channel_map[channel_id]
                asset = {media["type"]: {"url": media["url"]}}
                input_data = {
                    "text": caption,
                    "channelId": channel_id,
                    "schedulingType": "automatic",
                    "mode": "customScheduled" if mode == "schedule" else "shareNow",
                    "assets": [asset],
                }
                if due_at:
                    input_data["dueAt"] = due_at
                data = self._graphql(mutation, {"input": input_data})
                action = data.get("createPost") or {}
                if action.get("message"):
                    raise PublisherError(_safe_error(action.get("message")))
                post = action.get("post") or {}
                raw_status = str(post.get("status") or "").lower()
                status = {
                    "scheduled": "SCHEDULED", "sent": "PUBLISHED", "error": "FAILED",
                }.get(raw_status, "SCHEDULED" if mode == "schedule" else "PUBLISHING")
                records.append({
                    "id": secrets.token_urlsafe(12),
                    "buffer_post_id": str(post.get("id") or ""),
                    "created_at": _utc_iso(),
                    "media_url": media["url"],
                    "media_type": media["type"],
                    "caption": caption,
                    "channel_id": channel_id,
                    "channel_name": channel["name"],
                    "platform": channel["platform"],
                    "scheduled_at": str(post.get("dueAt") or due_at or ""),
                    "status": status,
                    "error": "",
                })
        except PublisherError as exc:
            for channel_id in channel_ids[len(records):]:
                channel = channel_map[channel_id]
                records.append({
                    "id": secrets.token_urlsafe(12), "buffer_post_id": "", "created_at": _utc_iso(),
                    "media_url": media["url"], "media_type": media["type"], "caption": caption,
                    "channel_id": channel_id, "channel_name": channel["name"],
                    "platform": channel["platform"], "scheduled_at": due_at or "",
                    "status": "FAILED", "error": _safe_error(exc),
                })
            self.history.fail(key, request_hash, records)
            raise

        result = {"ok": True, "records": records, "duplicate_prevented": False}
        self.history.complete(key, request_hash, result, records)
        return result
