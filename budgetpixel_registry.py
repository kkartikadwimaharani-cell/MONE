"""Authoritative, server-side BudgetPixel model catalogue and capabilities.

The remote ``/v1/models`` response is discovery data, never an executable
endpoint.  Only entries with a reviewed local schema are generatable.  This
keeps a newly-published (or maliciously-shaped) catalogue entry from becoming
an arbitrary proxy while still making it visible as ``UNSUPPORTED``.
"""
from copy import deepcopy
from datetime import datetime, timezone
import threading
import time

import requests


BASE_URL = "https://api.budgetpixel.com/v1"
CACHE_TTL_SECONDS = 300

_lock = threading.Lock()
_cache = {"expires": 0.0, "models": None, "synced_at": None, "error": None}


def _fallback_models():
    # Reviewed contracts already exercised by budgetpixel_provider.  Keep the
    # schema here, and let all other layers consume it rather than duplicating
    # an endpoint/field allow-list in the browser or MCP server.
    from budgetpixel_provider import (IMAGE_CAPABILITIES, IMAGE_MODELS,
                                      VIDEO_CAPABILITIES, VIDEO_MODELS)
    rows = []
    for category, endpoints, capabilities in (
            ("image", IMAGE_MODELS, IMAGE_CAPABILITIES),
            ("video", VIDEO_MODELS, VIDEO_CAPABILITIES)):
        for (family, variant), endpoint in endpoints.items():
            caps = capabilities[(family, variant)]
            rows.append({
                "slug": endpoint.rsplit("/", 1)[-1], "name": endpoint.rsplit("/", 1)[-1],
                "category": category, "family": family, "variant": variant,
                "endpoint": "/v1" + endpoint, "status": "UNVERIFIED",
                "available": True, "handler": True, "modes": _modes(category, caps),
                "parameters": _json_safe(caps), "source": "fallback",
            })
    # Several UI tiers intentionally share one provider slug (GPT-Image-2).
    # Keep one authoritative catalogue row and expose its tiers as metadata
    # instead of returning duplicate models from list_models.
    unique_rows = []
    by_slug = {}
    for row in rows:
        current = by_slug.get(row["slug"])
        if current:
            current.setdefault("variants", [current["variant"]]).append(row["variant"])
            continue
        by_slug[row["slug"]] = row
        unique_rows.append(row)
    rows = unique_rows
    # Additive catalogue handlers. Existing provider rows above win on slug,
    # so their proven routing and payload builders are never replaced.
    from budgetpixel_video_catalog import registry_rows
    from budgetpixel_media_catalog import registry_rows as media_registry_rows
    existing = {(row["slug"], row["category"]) for row in rows}
    rows.extend(row for row in registry_rows()
                if (row["slug"], row["category"]) not in existing)
    existing = {(row["slug"], row["category"]) for row in rows}
    rows.extend(row for row in media_registry_rows()
                if (row["slug"], row["category"]) not in existing)
    return rows


def _json_safe(value):
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    return value


def _modes(category, caps):
    if category == "image":
        return ["text-to-image"] + (["image-editing"] if caps.get("reference_images") or caps.get("singular_image") else [])
    modes = ["text-to-video"]
    if caps.get("start_frame"): modes.append("image-to-video")
    if caps.get("end_frame"): modes.append("first-last-frame")
    if any(caps.get(k) for k in ("reference_images", "reference_videos", "reference_audios")):
        modes.append("reference-to-video")
    return modes


def _remote_rows(data):
    """Parse common catalogue envelopes without guessing generation schemas."""
    raw = data.get("data", data.get("models", data)) if isinstance(data, dict) else data
    if isinstance(raw, dict):
        expanded = []
        for category, values in raw.items():
            if isinstance(values, list):
                for item in values:
                    if isinstance(item, dict):
                        item = dict(item); item.setdefault("category", category)
                        expanded.append(item)
        raw = expanded
    if not isinstance(raw, list):
        raise ValueError("models response is not a list or grouped object")
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        # BudgetPixel's documented response uses `name` as the endpoint slug.
        slug = item.get("slug") or item.get("model") or item.get("name") or item.get("id")
        if not isinstance(slug, str) or not slug.strip():
            continue
        category = str(item.get("category") or item.get("type") or item.get("kind") or "unknown").lower()
        category = {"images":"image", "videos":"video", "audio":"audio", "audios":"audio",
                    "music":"audio", "speech":"audio", "voice":"audio", "tts":"audio",
                    "sound-effect":"audio", "sound_effect":"audio", "sfx":"audio"}.get(category, category)
        result.append({"slug": slug.strip(), "name": str(item.get("name") or slug),
                       "category": category, "remote": _public_remote(item)})
    return result


def _public_remote(item):
    # Retain useful, non-secret descriptive metadata only.
    allowed = ("description", "modes", "resolutions", "aspect_ratios", "durations", "status")
    return {key: _json_safe(item[key]) for key in allowed if key in item}


def _merge(remote, configured):
    local = {(row["slug"], row["category"]): row for row in _fallback_models()}
    merged = []
    for found in remote:
        reviewed = local.pop((found["slug"], found["category"]), None)
        if reviewed:
            reviewed.update(name=found["name"], source="catalog", catalog=True)
            reviewed["remote"] = found.get("remote", {})
            row = reviewed
        else:
            # Live video slugs are safe through the generic adapter: the
            # endpoint kind is fixed and unknown slugs are prompt-only.
            is_video = found.get("category") == "video"
            row = dict(found,
                       endpoint=("/v1/videos/" + found["slug"]) if is_video else None,
                       status="INTEGRATED" if is_video else "UNSUPPORTED",
                       available=is_video, handler=is_video,
                       family=("bpx-" + found["slug"]) if is_video else None,
                       variant="STANDARD" if is_video else None,
                       modes=found.get("remote", {}).get("modes", []),
                       parameters={}, source="catalog", catalog=True)
        row["configured"] = configured
        merged.append(row)
    # Reviewed local handlers remain usable when the remote directory is
    # partial or categorises an endpoint differently. They are fixed local
    # contracts, not arbitrary endpoints discovered from the remote response.
    for row in local.values():
        row["configured"] = configured
        merged.append(row)
    return sorted(merged, key=lambda r: (r["category"], r["name"].lower(), r["slug"]))


def get_registry(api_key="", session=requests, ttl=CACHE_TTL_SECONDS, now=time.monotonic, force=False):
    current = now()
    with _lock:
        if not force and _cache["models"] is not None and current < _cache["expires"]:
            return snapshot()
        error = None
        remote = []
        if api_key:
            try:
                response = session.get(BASE_URL + "/models", headers={"Authorization": "Bearer " + api_key}, timeout=15)
                response.raise_for_status()
                remote = _remote_rows(response.json())
            except Exception as exc:  # catalog outage must not break generation
                error = "%s: %s" % (type(exc).__name__, str(exc)[:300])
        else:
            error = "BUDGETPIXEL_API_KEY is not configured"
        models = _merge(remote, bool(api_key)) if remote else _merge([], bool(api_key))
        _cache.update(models=models, expires=current + max(1, ttl),
                      synced_at=datetime.now(timezone.utc).isoformat(), error=error)
        return snapshot()


def snapshot():
    return {"models": deepcopy(_cache["models"] or []), "synced_at": _cache["synced_at"],
            "sync_error": _cache["error"], "cache_ttl_seconds": CACHE_TTL_SECONDS}


def reset_cache():
    with _lock:
        _cache.update(expires=0.0, models=None, synced_at=None, error=None)


def model_by_slug(slug, registry, category=None):
    for model in registry.get("models", []):
        if model["slug"] == slug and (category is None or model.get("category") == category):
            return model
    return None
