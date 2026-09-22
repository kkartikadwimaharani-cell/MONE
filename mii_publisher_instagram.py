"""Official Instagram/Meta provider for the isolated MII PUBLISHER module.

Only Instagram professional accounts and Reel/video publishing are implemented.
Credentials and tokens never leave the backend. Remote media is passed by URL
to Instagram; MII does not download, proxy, or persist the media bytes.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from urllib.parse import urlencode

import requests

import mii_publisher


INSTAGRAM_AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
INSTAGRAM_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
INSTAGRAM_GRAPH_HOST = "https://graph.instagram.com"
INSTAGRAM_SCOPES = (
    "instagram_business_basic",
    "instagram_business_content_publish",
)
REQUIRED_ENV = (
    "INSTAGRAM_APP_ID",
    "INSTAGRAM_APP_SECRET",
    "INSTAGRAM_REDIRECT_URI",
)
DEFAULT_GRAPH_VERSION = "v26.0"
TOKEN_KEYS = (
    "INSTAGRAM_ACCESS_TOKEN",
    "INSTAGRAM_TOKEN_EXPIRES_AT",
    "INSTAGRAM_USER_ID",
    "INSTAGRAM_USERNAME",
    "INSTAGRAM_ACCOUNT_TYPE",
)


class InstagramPublisherService:
    provider = "instagram"

    def __init__(self, data_dir, secret_store, get_secret, logger, http=None):
        self.secret_store = secret_store
        self.get_secret = get_secret
        self.logger = logger
        self.http = http or requests
        self.store = mii_publisher.PublisherStore(data_dir)

    def _secret(self, name):
        return str(self.get_secret(name, default="") or "").strip()

    def _stored(self, name):
        try:
            return str(self.secret_store.get(name) or "")
        except Exception:
            return ""

    def _configuration(self, *, require=True):
        values = {name: self._secret(name) for name in REQUIRED_ENV}
        values["INSTAGRAM_GRAPH_VERSION"] = self._secret("INSTAGRAM_GRAPH_VERSION") or DEFAULT_GRAPH_VERSION
        missing = [name for name, value in values.items() if not value]
        version = values["INSTAGRAM_GRAPH_VERSION"]
        if version and not re.fullmatch(r"v\d+\.\d+", version):
            missing.append("INSTAGRAM_GRAPH_VERSION (FORMAT vNN.N)")
        if missing and require:
            raise mii_publisher.PublisherConfigurationError(
                "Instagram server configuration is incomplete.",
                provider_code="missing_configuration",
            )
        return values, missing

    def _correlation_id(self):
        return secrets.token_urlsafe(9)

    @staticmethod
    def _response_json(response):
        try:
            body = response.json()
            return body if isinstance(body, dict) else {}
        except (ValueError, TypeError):
            return {}

    def _record_error_health(self, error):
        detail = error.public_detail()
        self.store.set_health(error.health_status, str(error), detail=detail)
        event = {
            "rate_limit": "Rate limit",
            "unsupported_media": "Media rejected",
            "authorization_required": "Authentication failed",
            "permission_missing": "Authentication failed",
        }.get(error.error_code, "Instagram API error")
        self.store.add_activity(event, str(error), status="FAILED", details=detail)

    def _operational(self, summary="Instagram API connection is healthy."):
        previous = self.store.set_health("OPERATIONAL", summary)
        if previous and previous.get("status") not in (None, "OPERATIONAL"):
            self.store.add_activity("Integration restored", summary, status="OPERATIONAL")

    def _provider_error(self, response, correlation_id, fallback="Instagram rejected the request."):
        body = self._response_json(response)
        raw = body.get("error") if isinstance(body.get("error"), dict) else {}
        message = mii_publisher.safe_text(raw.get("message") or fallback)
        provider_code = str(raw.get("code") or response.status_code or "instagram_api_error")
        http_status = int(response.status_code or 0) or None
        kwargs = {
            "correlation_id": correlation_id,
            "provider_code": provider_code,
            "http_status": http_status,
        }
        numeric_code = int(raw.get("code") or 0) if str(raw.get("code") or "").isdigit() else 0
        if http_status == 429 or numeric_code in {4, 17, 32, 613}:
            return mii_publisher.PublisherRateLimitError(
                "Instagram rate limit reached. Try again later.",
                retry_after=response.headers.get("Retry-After", 60),
                **kwargs,
            )
        if numeric_code == 190 or http_status == 401:
            return mii_publisher.PublisherAuthError(
                "Instagram authorization is invalid or expired.", **kwargs,
            )
        if numeric_code in {10, 200} or http_status == 403:
            return mii_publisher.PublisherPermissionError(
                "Instagram publishing permission is missing or was revoked.", **kwargs,
            )
        return mii_publisher.PublisherError(message, **kwargs)

    def _request(self, method, url, *, correlation_id=None, timeout=(5, 25), **kwargs):
        correlation_id = correlation_id or self._correlation_id()
        try:
            response = self.http.request(method, url, timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            error = mii_publisher.PublisherNetworkError(
                "Instagram API could not be reached.", correlation_id=correlation_id,
            )
            self.logger.warning(
                "[mii-publisher][instagram] network failure correlation_id=%s type=%s",
                correlation_id, type(exc).__name__,
            )
            raise error from exc
        if response.status_code >= 400:
            error = self._provider_error(response, correlation_id)
            self.logger.warning(
                "[mii-publisher][instagram] provider error correlation_id=%s http=%s code=%s",
                correlation_id, response.status_code, error.provider_code,
            )
            raise error
        body = self._response_json(response)
        if not body:
            raise mii_publisher.PublisherError(
                "Instagram returned an invalid response.",
                correlation_id=correlation_id,
                http_status=response.status_code,
                provider_code="invalid_response",
            )
        return body

    def _graph_url(self, path):
        config, _ = self._configuration()
        return f"{INSTAGRAM_GRAPH_HOST}/{config['INSTAGRAM_GRAPH_VERSION']}/{str(path).lstrip('/')}"

    def _graph_request(self, method, path, *, token=None, correlation_id=None, **kwargs):
        access_token = token or self._access_token()
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Authorization"] = f"Bearer {access_token}"
        headers["Accept"] = "application/json"
        return self._request(
            method, self._graph_url(path), headers=headers,
            correlation_id=correlation_id, **kwargs,
        )

    def authorization_url(self, state, reconnect=False):
        config, _ = self._configuration()
        query = {
            "client_id": config["INSTAGRAM_APP_ID"],
            "redirect_uri": config["INSTAGRAM_REDIRECT_URI"],
            "response_type": "code",
            "scope": ",".join(INSTAGRAM_SCOPES),
            "state": state,
            "enable_fb_login": "0",
            "force_authentication": "1" if reconnect else "0",
        }
        return f"{INSTAGRAM_AUTHORIZE_URL}?{urlencode(query)}"

    def exchange_code(self, code):
        config, _ = self._configuration()
        correlation_id = self._correlation_id()
        short = self._request(
            "POST", INSTAGRAM_TOKEN_URL,
            data={
                "client_id": config["INSTAGRAM_APP_ID"],
                "client_secret": config["INSTAGRAM_APP_SECRET"],
                "grant_type": "authorization_code",
                "redirect_uri": config["INSTAGRAM_REDIRECT_URI"],
                "code": str(code or ""),
            },
            correlation_id=correlation_id,
            timeout=(5, 20),
        )
        short_token = str(short.get("access_token") or "")
        user_id = str(short.get("user_id") or "")
        if not short_token:
            raise mii_publisher.PublisherAuthError(
                "Instagram did not return an access token.",
                correlation_id=correlation_id,
                provider_code="missing_access_token",
            )
        long_lived = self._request(
            "GET", f"{INSTAGRAM_GRAPH_HOST}/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": config["INSTAGRAM_APP_SECRET"],
                "access_token": short_token,
            },
            correlation_id=correlation_id,
            timeout=(5, 20),
        )
        access_token = str(long_lived.get("access_token") or "")
        if not access_token:
            raise mii_publisher.PublisherAuthError(
                "Instagram long-lived authorization could not be created.",
                correlation_id=correlation_id,
                provider_code="long_lived_token_missing",
            )
        expires_in = max(0, int(long_lived.get("expires_in") or 0))
        profile = self._profile(access_token, fallback_user_id=user_id, correlation_id=correlation_id)
        account_type = str(profile.get("account_type") or "").upper()
        if account_type and account_type not in {"BUSINESS", "MEDIA_CREATOR"}:
            raise mii_publisher.PublisherPermissionError(
                "Instagram publishing requires a professional Business or Creator account.",
                correlation_id=correlation_id,
                provider_code="professional_account_required",
            )
        self.secret_store.set("INSTAGRAM_ACCESS_TOKEN", access_token)
        self.secret_store.set(
            "INSTAGRAM_TOKEN_EXPIRES_AT",
            str(time.time() + expires_in) if expires_in else "",
        )
        self.secret_store.set("INSTAGRAM_USER_ID", profile["id"])
        self.secret_store.set("INSTAGRAM_USERNAME", profile.get("username") or "")
        self.secret_store.set("INSTAGRAM_ACCOUNT_TYPE", account_type)
        self.store.add_activity(
            "Instagram connected",
            f"@{profile.get('username') or 'instagram'} connected.",
            status="CONNECTED",
        )
        self._operational("Instagram authorization and profile access are valid.")
        return profile

    def _profile(self, token, *, fallback_user_id="", correlation_id=None):
        data = self._graph_request(
            "GET", "me", token=token,
            params={"fields": "user_id,username,account_type,media_count"},
            correlation_id=correlation_id,
        )
        user_id = str(data.get("user_id") or data.get("id") or fallback_user_id or "")
        if not user_id:
            raise mii_publisher.PublisherAuthError(
                "Instagram account identity could not be verified.",
                correlation_id=correlation_id or self._correlation_id(),
                provider_code="missing_user_id",
            )
        return {
            "id": user_id,
            "username": mii_publisher.safe_text(data.get("username"), 120, "instagram"),
            "account_type": mii_publisher.safe_text(data.get("account_type"), 40, "PROFESSIONAL"),
            "media_count": int(data.get("media_count") or 0),
        }

    def _refresh_token(self, access_token):
        correlation_id = self._correlation_id()
        data = self._request(
            "GET", f"{INSTAGRAM_GRAPH_HOST}/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": access_token},
            correlation_id=correlation_id,
            timeout=(5, 20),
        )
        fresh = str(data.get("access_token") or "")
        if not fresh:
            raise mii_publisher.PublisherAuthError(
                "Instagram token renewal failed.",
                correlation_id=correlation_id,
                provider_code="token_renewal_failed",
            )
        expires_in = max(0, int(data.get("expires_in") or 0))
        self.secret_store.set("INSTAGRAM_ACCESS_TOKEN", fresh)
        self.secret_store.set(
            "INSTAGRAM_TOKEN_EXPIRES_AT",
            str(time.time() + expires_in) if expires_in else "",
        )
        self.store.add_activity("Token renewed", "Instagram authorization token renewed.", status="CONNECTED")
        return fresh

    def _access_token(self):
        token = self._stored("INSTAGRAM_ACCESS_TOKEN")
        if not token:
            raise mii_publisher.PublisherAuthError("Connect Instagram before publishing.")
        try:
            expires_at = float(self._stored("INSTAGRAM_TOKEN_EXPIRES_AT") or 0)
        except ValueError:
            expires_at = 0
        if expires_at and expires_at <= time.time() + (7 * 24 * 60 * 60):
            return self._refresh_token(token)
        return token

    def connection_status(self, *, live_check=True):
        _, missing = self._configuration(require=False)
        if missing:
            summary = "Instagram server configuration is incomplete."
            health = {
                "status": "CONFIGURATION ERROR",
                "summary": summary,
                "checked_at": mii_publisher.utc_iso(),
                "detail": {
                    "subsystem": "INSTAGRAM",
                    "code": "missing_configuration",
                    "message": summary,
                    "recommended_action": "Add the required Instagram environment variables.",
                },
            }
            self.store.set_health(health["status"], health["summary"], detail=health["detail"])
            return {
                "provider": self.provider,
                "configured": False,
                "missing_configuration": missing,
                "connected": False,
                "account": None,
                "health": health,
            }
        token = self._stored("INSTAGRAM_ACCESS_TOKEN")
        if not token:
            health = {
                "status": "AUTHORIZATION REQUIRED",
                "summary": "Instagram is not connected.",
                "checked_at": mii_publisher.utc_iso(),
                "detail": None,
            }
            self.store.set_health(health["status"], health["summary"])
            return {
                "provider": self.provider, "configured": True, "connected": False,
                "account": None, "health": health,
            }
        account = {
            "id": self._stored("INSTAGRAM_USER_ID"),
            "username": self._stored("INSTAGRAM_USERNAME"),
            "account_type": self._stored("INSTAGRAM_ACCOUNT_TYPE"),
        }
        if live_check:
            try:
                account = self._profile(self._access_token(), fallback_user_id=account["id"])
                self.secret_store.set("INSTAGRAM_USER_ID", account["id"])
                self.secret_store.set("INSTAGRAM_USERNAME", account.get("username") or "")
                self.secret_store.set("INSTAGRAM_ACCOUNT_TYPE", account.get("account_type") or "")
                self._operational()
            except mii_publisher.PublisherError as exc:
                self._record_error_health(exc)
                return {
                    "provider": self.provider,
                    "configured": True,
                    "connected": not isinstance(exc, mii_publisher.PublisherAuthError),
                    "account": account if account.get("id") else None,
                    "health": self.store.get_health(),
                }
        health = self.store.get_health() or {
            "status": "OPERATIONAL", "summary": "Instagram is connected.",
            "checked_at": mii_publisher.utc_iso(), "detail": None,
        }
        return {
            "provider": self.provider, "configured": True, "connected": True,
            "account": account, "health": health,
        }

    def disconnect(self):
        for key in TOKEN_KEYS:
            try:
                self.secret_store.delete(key)
            except Exception:
                pass
        self.store.add_activity("Instagram disconnected", "Instagram authorization removed from MII PUBLISHER.", status="DISCONNECTED")
        self.store.set_health("AUTHORIZATION REQUIRED", "Instagram is not connected.")

    def validate_media(self, value):
        return mii_publisher.validate_instagram_video_url(value)

    def _account_for_publish(self):
        token = self._access_token()
        account = self._profile(token, fallback_user_id=self._stored("INSTAGRAM_USER_ID"))
        self._operational()
        return token, account

    def create_reel(self, payload):
        if not isinstance(payload, dict) or payload.get("confirmed") is not True:
            raise mii_publisher.PublisherValidationError("Explicit publishing confirmation is required.")
        caption = str(payload.get("caption") or "").strip()
        if len(caption) > 2200:
            raise mii_publisher.PublisherValidationError("Instagram captions cannot exceed 2,200 characters.")
        media = self.validate_media(payload.get("media_url"))
        key = str(payload.get("idempotency_key") or "")
        canonical = json.dumps(
            {"caption": caption, "media_url": media["url"], "destination": "instagram_reels"},
            sort_keys=True, separators=(",", ":"),
        )
        request_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        prior, duplicate = self.store.begin_submission(key, request_hash)
        if duplicate:
            result = dict(prior or {})
            result["duplicate_prevented"] = True
            return result

        job = self.store.create_job({
            "status": "VALIDATING",
            "provider": "instagram",
            "destination": "INSTAGRAM REELS",
            "media_url": media["url"],
            "media_type": "video",
            "caption": caption,
            "container_id": "",
            "provider_media_id": "",
            "error": "",
            "detail": None,
        })
        correlation_id = job["id"]
        try:
            token, account = self._account_for_publish()
            created = self._graph_request(
                "POST", f"{account['id']}/media", token=token,
                data={
                    "media_type": "REELS",
                    "video_url": media["url"],
                    "caption": caption,
                    "share_to_feed": "true",
                },
                correlation_id=correlation_id,
            )
            container_id = str(created.get("id") or "")
            if not container_id:
                raise mii_publisher.PublisherError(
                    "Instagram did not return a media container.",
                    correlation_id=correlation_id,
                    provider_code="missing_container_id",
                )
            job = self.store.update_job(
                job["id"], status="PROCESSING", container_id=container_id,
                account_username=account.get("username") or "instagram",
            )
            result = {"ok": True, "job": job, "duplicate_prevented": False}
            self.store.complete_submission(key, request_hash, result)
            self.store.add_activity(
                "Publish processing",
                "Instagram accepted the Reel media container for processing.",
                status="PROCESSING",
                details={"correlation_id": correlation_id},
            )
            self._operational("Instagram accepted the Reel for processing.")
            return result
        except mii_publisher.PublisherError as exc:
            if not exc.correlation_id:
                exc.correlation_id = correlation_id
            failed = self.store.update_job(
                job["id"], status="FAILED", error=str(exc), detail=exc.public_detail(),
            )
            result = {"ok": False, "job": failed, "duplicate_prevented": False}
            self.store.complete_submission(key, request_hash, result)
            self._record_error_health(exc)
            raise

    def refresh_publish_status(self, job_id):
        job = self.store.get_job(job_id)
        if not job:
            raise mii_publisher.PublisherValidationError("Publishing job was not found.")
        if job.get("status") in {"PUBLISHED", "FAILED"}:
            return job
        container_id = str(job.get("container_id") or "")
        if not container_id:
            return self.store.update_job(
                job["id"], status="FAILED", error="Instagram media container is missing.",
            )
        correlation_id = job["id"]
        try:
            token, account = self._account_for_publish()
            provider_state = self._graph_request(
                "GET", container_id, token=token,
                params={"fields": "status_code,status"},
                correlation_id=correlation_id,
            )
            status_code = str(provider_state.get("status_code") or "").upper()
            if status_code in {"ERROR", "EXPIRED"}:
                error = mii_publisher.PublisherMediaError(
                    "Instagram could not process this video.",
                    correlation_id=correlation_id,
                    provider_code=f"container_{status_code.lower()}",
                )
                failed = self.store.update_job(
                    job["id"], status="FAILED", error=str(error), detail=error.public_detail(),
                    provider_status=status_code,
                )
                self.store.add_activity("Media rejected", str(error), status="FAILED", details=error.public_detail())
                return failed
            if status_code == "PUBLISHED":
                published = self.store.update_job(job["id"], status="PUBLISHED", error="", provider_status=status_code)
                self.store.add_activity("Publish succeeded", "Instagram confirmed the Reel is published.", status="PUBLISHED")
                self._operational("Instagram publishing is operational.")
                return published
            if status_code != "FINISHED":
                return self.store.update_job(job["id"], status="PROCESSING", provider_status=status_code or "IN_PROGRESS")

            claimed, claimed_job = self.store.claim_publish(job["id"])
            if not claimed:
                return claimed_job or job
            try:
                published_data = self._graph_request(
                    "POST", f"{account['id']}/media_publish", token=token,
                    data={"creation_id": container_id},
                    correlation_id=correlation_id,
                )
            except mii_publisher.PublisherNetworkError as exc:
                self._record_error_health(exc)
                return self.store.update_job(
                    job["id"], status="PUBLISHING",
                    error="Publish confirmation is pending after a network interruption.",
                    detail=exc.public_detail(), provider_status="FINISHED",
                )
            media_id = str(published_data.get("id") or "")
            if not media_id:
                raise mii_publisher.PublisherError(
                    "Instagram did not confirm the published media ID.",
                    correlation_id=correlation_id,
                    provider_code="missing_published_media_id",
                )
            published = self.store.update_job(
                job["id"], status="PUBLISHED", provider_media_id=media_id,
                provider_status="PUBLISHED", error="", detail=None,
            )
            self.store.add_activity("Publish succeeded", "Instagram confirmed the Reel is published.", status="PUBLISHED")
            self._operational("Instagram publishing is operational.")
            return published
        except mii_publisher.PublisherError as exc:
            if not exc.correlation_id:
                exc.correlation_id = correlation_id
            failed = self.store.update_job(
                job["id"], status="FAILED", error=str(exc), detail=exc.public_detail(),
            )
            self.store.add_activity("Publish failed", str(exc), status="FAILED", details=exc.public_detail())
            self._record_error_health(exc)
            return failed

    def history(self):
        return {
            "activities": self.store.activities(),
            "jobs": self.store.jobs(),
        }
