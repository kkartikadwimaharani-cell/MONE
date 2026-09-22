"""Shared, isolated primitives for MII PUBLISHER social providers.

This module intentionally contains no provider credentials or dependencies on
SOCIAL MEDIA, AI generation, Dropbox, or MCP. Provider adapters own their API
calls; this file owns validation, safe errors, idempotency, lightweight history,
and publish-job state.
"""

from __future__ import annotations

import fcntl
import ipaddress
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import urlparse


VIDEO_EXTENSIONS = {".mp4", ".mov"}
HEALTH_STATES = {
    "OPERATIONAL", "DEGRADED", "AUTHORIZATION REQUIRED",
    "CONFIGURATION ERROR", "API ERROR", "UNKNOWN",
}


def utc_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_text(value, limit=320, fallback="Request failed."):
    text = " ".join(str(value or "").split())
    text = re.sub(r"(?i)(access[_ -]?token|client[_ -]?secret|app[_ -]?secret)\s*[:=]\s*\S+", r"\1=[REDACTED]", text)
    return text[:limit] or fallback


class PublisherError(RuntimeError):
    status_code = 502
    error_code = "publisher_error"
    health_status = "API ERROR"
    recommended_action = "Try again."

    def __init__(self, message, *, correlation_id="", provider_code="", http_status=None):
        super().__init__(safe_text(message))
        self.correlation_id = safe_text(correlation_id, 80, "")
        self.provider_code = safe_text(provider_code, 80, "")
        self.http_status = int(http_status) if str(http_status or "").isdigit() else None

    def public_detail(self):
        return {
            "subsystem": "INSTAGRAM",
            "time": utc_iso(),
            "http_status": self.http_status,
            "code": self.provider_code or self.error_code,
            "message": str(self),
            "correlation_id": self.correlation_id,
            "recommended_action": self.recommended_action,
        }


class PublisherValidationError(PublisherError):
    status_code = 400
    error_code = "validation_error"
    health_status = "OPERATIONAL"
    recommended_action = "Review the highlighted publishing input."


class PublisherMediaError(PublisherValidationError):
    status_code = 422
    error_code = "unsupported_media"
    recommended_action = "Use a public direct MP4 or MOV video URL supported by Instagram Reels."


class PublisherConfigurationError(PublisherError):
    status_code = 503
    error_code = "configuration_error"
    health_status = "CONFIGURATION ERROR"
    recommended_action = "Complete the Instagram server environment configuration."


class PublisherAuthError(PublisherError):
    status_code = 409
    error_code = "authorization_required"
    health_status = "AUTHORIZATION REQUIRED"
    recommended_action = "Reconnect Instagram."


class PublisherPermissionError(PublisherAuthError):
    status_code = 403
    error_code = "permission_missing"
    recommended_action = "Reconnect Instagram and approve the required publishing permissions."


class PublisherRateLimitError(PublisherError):
    status_code = 429
    error_code = "rate_limit"
    health_status = "DEGRADED"
    recommended_action = "Wait before retrying the request."

    def __init__(self, message, *, retry_after=60, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = max(1, min(int(retry_after or 60), 3600))


class PublisherNetworkError(PublisherError):
    status_code = 503
    error_code = "network_failure"
    health_status = "DEGRADED"
    recommended_action = "Check the connection and retry without submitting duplicate content."


def validate_instagram_video_url(value):
    """Validate syntax only; media bytes are never fetched by the MII server."""
    value = str(value or "").strip()
    if not value or len(value) > 2048:
        raise PublisherMediaError("Enter a valid public video URL.")
    try:
        parsed = urlparse(value)
    except ValueError as exc:
        raise PublisherMediaError("The media URL is invalid.") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise PublisherMediaError("Instagram media must use a public HTTPS URL.")
    if parsed.username or parsed.password or parsed.fragment:
        raise PublisherMediaError("Credentials and URL fragments are not allowed.")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise PublisherMediaError("Local or private media URLs are not allowed.")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise PublisherMediaError("Local or private media URLs are not allowed.")
    except ValueError:
        pass
    if host == "dropbox.com" or host.endswith(".dropbox.com"):
        raise PublisherMediaError(
            "Dropbox preview pages are not direct video files. Use a stable public direct-download URL."
        )
    path = PurePosixPath(parsed.path)
    extension = path.suffix.lower()
    if extension not in VIDEO_EXTENSIONS:
        raise PublisherMediaError("Instagram Reel media must be a direct MP4 or MOV URL.")
    return {
        "url": value,
        "type": "video",
        "destination": "instagram_reels",
        "filename": path.name[:180] or f"instagram-reel{extension}",
        "host": host,
        "transport": "direct_remote_url",
        "warning": "The URL must remain publicly reachable while Instagram processes the Reel.",
    }


class PublisherStore:
    """Small cross-process-safe JSON store for Publisher activity and jobs."""

    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, "mii_publisher_instagram.json")
        self.lock_path = os.path.join(data_dir, "mii_publisher_instagram.lock")
        self._thread_lock = threading.Lock()
        os.makedirs(data_dir, exist_ok=True)

    @staticmethod
    def _empty():
        return {"activities": [], "jobs": {}, "submissions": {}, "health": {}}

    def _locked(self):
        handle = open(self.lock_path, "a+")
        fcntl.flock(handle, fcntl.LOCK_EX)
        return handle

    def _read(self):
        if not os.path.exists(self.path):
            return self._empty()
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            return {
                "activities": list(raw.get("activities") or []),
                "jobs": dict(raw.get("jobs") or {}),
                "submissions": dict(raw.get("submissions") or {}),
                "health": dict(raw.get("health") or {}),
            }
        except (OSError, ValueError, TypeError):
            return self._empty()

    def _write(self, data):
        temp_path = self.path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(temp_path, self.path)

    def _mutate(self, callback):
        with self._thread_lock:
            lock = self._locked()
            try:
                data = self._read()
                result = callback(data)
                self._write(data)
                return result
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
                lock.close()

    def read(self):
        with self._thread_lock:
            lock = self._locked()
            try:
                return self._read()
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
                lock.close()

    def add_activity(self, event, message, *, status="INFO", details=None):
        record = {
            "id": uuid.uuid4().hex,
            "created_at": utc_iso(),
            "event": safe_text(event, 80),
            "status": safe_text(status, 40),
            "message": safe_text(message, 320),
            "details": details if isinstance(details, dict) else {},
        }

        def update(data):
            data["activities"] = [record] + data["activities"][:99]
            return dict(record)

        return self._mutate(update)

    def activities(self, limit=60):
        return self.read()["activities"][:max(1, min(int(limit), 100))]

    def get_health(self):
        return self.read()["health"]

    def set_health(self, status, summary, *, detail=None):
        if status not in HEALTH_STATES:
            status = "UNKNOWN"
        value = {
            "status": status,
            "summary": safe_text(summary, 240),
            "checked_at": utc_iso(),
            "detail": detail if isinstance(detail, dict) else None,
        }

        def update(data):
            previous = dict(data.get("health") or {})
            data["health"] = value
            return previous

        return self._mutate(update)

    def begin_submission(self, key, request_hash):
        try:
            key = str(uuid.UUID(str(key or "")))
        except (ValueError, TypeError, AttributeError) as exc:
            raise PublisherValidationError("Invalid submission key. Refresh and try again.") from exc
        now = time.time()

        def update(data):
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
            return None, False

        return self._mutate(update)

    def complete_submission(self, key, request_hash, result):
        def update(data):
            data["submissions"][str(key)] = {
                "request_hash": request_hash,
                "state": "complete",
                "created_at": time.time(),
                "result": result,
            }
            data["submissions"] = dict(list(data["submissions"].items())[-200:])

        self._mutate(update)

    def create_job(self, job):
        value = dict(job)
        value.setdefault("id", uuid.uuid4().hex)
        value.setdefault("created_at", utc_iso())
        value.setdefault("updated_at", value["created_at"])

        def update(data):
            data["jobs"][value["id"]] = value
            if len(data["jobs"]) > 100:
                ordered = sorted(data["jobs"].values(), key=lambda item: item.get("created_at", ""), reverse=True)[:100]
                data["jobs"] = {item["id"]: item for item in ordered}
            return dict(value)

        return self._mutate(update)

    def get_job(self, job_id):
        return self.read()["jobs"].get(str(job_id or ""))

    def update_job(self, job_id, **changes):
        def update(data):
            current = data["jobs"].get(str(job_id or ""))
            if not current:
                return None
            current.update(changes)
            current["updated_at"] = utc_iso()
            return dict(current)

        return self._mutate(update)

    def claim_publish(self, job_id):
        def update(data):
            current = data["jobs"].get(str(job_id or ""))
            if not current or current.get("status") != "PROCESSING":
                return False, dict(current) if current else None
            current["status"] = "PUBLISHING"
            current["publishing_started_at"] = time.time()
            current["updated_at"] = utc_iso()
            return True, dict(current)

        return self._mutate(update)

    def jobs(self, limit=60):
        jobs = list(self.read()["jobs"].values())
        jobs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return jobs[:max(1, min(int(limit), 100))]
