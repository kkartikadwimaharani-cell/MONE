"""Additive BudgetPixel video catalogue used by the web UI and MII MCP.

The existing family handlers in :mod:`budgetpixel_provider` stay untouched.
This module provides a deliberately small, provider-native adapter for every
video slug advertised by BudgetPixel.  Optional controls are emitted only
when the local capability table explicitly allows them; an unknown model
discovered from ``GET /v1/models`` therefore remains usable as prompt-only
text-to-video instead of becoming an unrestricted proxy.
"""
import re

from budgetpixel_provider import ProviderError


RATIOS = ("16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3")


def _spec(slug, name, modes=("t2v",), durations=(), resolutions=(), ratios=(),
          audio=False, first=False, last=False, refs=(0, 0, 0), description=""):
    return {"slug": slug, "name": name, "modes": tuple(modes),
            "durations": tuple(durations), "resolutions": tuple(resolutions),
            "aspect_ratios": tuple(ratios), "generate_audio": bool(audio),
            "first_frame": bool(first), "end_frame": bool(last),
            "reference_images": refs[0], "reference_videos": refs[1],
            "reference_audios": refs[2], "description": description}


# Slugs mirror the public model catalogue / endpoint path.  Conservative
# capability rows intentionally omit controls that are not documented for a
# model; prompt-only submission remains available for those rows.
_ROWS = [
    _spec("grok-imagine-video-1.5", "GROK IMAGINE VIDEO 1.5", ("t2v", "i2v"),
          range(1, 16), ("480p", "720p", "1080p"), RATIOS, True, True),
    _spec("wan-3.0-video-prime", "WAN 3.0 PRIME", ("t2v", "i2v", "reference"),
          range(2, 31), ("480p", "720p", "1080p"), ("adaptive",) + RATIOS,
          True, True, True, (10, 5, 5)),
    _spec("wan-3.0-video", "WAN 3.0", ("t2v", "i2v", "reference"),
          range(2, 31), ("480p", "720p", "1080p"), ("adaptive",) + RATIOS,
          True, True, True, (10, 5, 5)),
    _spec("seedance-2.5", "SEEDANCE 2.5", ("t2v", "i2v", "reference"),
          range(4, 31), ("480p", "720p", "1080p"), RATIOS, True, True, True, (15, 5, 5)),
    _spec("minimax-h3", "MINIMAX H3", ("t2v", "i2v", "reference"),
          range(5, 16), ("2K",), ("adaptive",) + RATIOS, True, True, True, (9, 3, 3)),
    _spec("seedance-2.0-mini", "SEEDANCE 2.0 MINI", ("t2v", "i2v", "reference", "v2v"),
          range(4, 16), ("480p", "720p"), RATIOS, True, True, True, (9, 1, 1)),
    _spec("happyhorse-1.1", "HAPPYHORSE 1.1", ("t2v", "i2v"), range(3, 16),
          ("720p", "1080p"), RATIOS[:5], True, True),
    _spec("kling-3.0-turbo", "KLING 3.0 TURBO", ("t2v", "i2v"), range(3, 16),
          ("720p", "1080p"), RATIOS, True, True),
    _spec("pixverse-c1", "PIXVERSE C1", ("t2v", "i2v"), first=True),
    _spec("kling-v3-omni-video", "KLING V3 OMNI", ("t2v", "i2v", "reference", "v2v"),
          range(3, 16), (), RATIOS, True, False, False, (9, 1, 0)),
    _spec("kling-v3.0-4k", "KLING 3.0 4K", ("t2v", "i2v"), range(3, 16),
          ("4K",), RATIOS, True, True, True),
    _spec("kling-v3.0-pro", "KLING 3.0 PRO", ("t2v", "i2v"), range(3, 16),
          ("1080p",), RATIOS, True, True, True),
    _spec("kling-v3.0-standard", "KLING 3.0 STANDARD", ("t2v", "i2v"), range(3, 16),
          ("720p",), RATIOS, True, True, True),
    _spec("seedance-2.0-fast", "SEEDANCE 2.0 FAST", ("t2v", "i2v", "reference", "v2v"),
          range(4, 16), ("480p", "720p"), RATIOS, True, True, True, (9, 1, 1)),
    _spec("seedance-2.0", "SEEDANCE 2.0 PRO", ("t2v", "i2v", "reference", "v2v"),
          range(4, 16), ("480p", "720p", "1080p", "4K"), RATIOS, True, True, True, (9, 1, 1)),
    _spec("pixverse-v6", "PIXVERSE V6", ("t2v", "i2v"), (5, 8, 10, 15),
          ("720p", "1080p"), RATIOS, False, True),
    _spec("wan-2.7-video", "WAN 2.7", ("t2v", "i2v", "v2v"), (5, 10, 15),
          ("720p", "1080p"), RATIOS, True, True, True, (4, 1, 0)),
    _spec("wan-2.2-animate-move", "WAN 2.2 ANIMATE MOVE", ("v2v",), first=True, refs=(1, 1, 0)),
    _spec("wan-2.2-animate-replace", "WAN 2.2 ANIMATE REPLACE", ("v2v",), first=True, refs=(1, 1, 0)),
    _spec("vidu-q3-pro", "VIDU Q3 PRO", ("t2v", "i2v"), first=True),
    _spec("p-video", "P-VIDEO", ("t2v", "i2v", "audio"), (5, 10),
          ("720p", "1080p"), RATIOS, True, True, True, (0, 0, 1)),
    _spec("wan-2.6-i2v-flash", "WAN 2.6 I2V FLASH", ("i2v",), (5, 10),
          ("720p", "1080p"), (), True, True),
    _spec("seedance-1.5-pro", "SEEDANCE 1.5 PRO", ("t2v", "i2v"), (5, 10),
          ("480p", "720p", "1080p"), RATIOS, True, True),
    _spec("wan-2.6", "WAN 2.6", ("t2v",), (5, 10), ("720p", "1080p"), RATIOS, True),
    _spec("kling-v2.6-pro", "KLING V2.6 PRO", ("t2v", "i2v"), (5, 10),
          ("1080p",), RATIOS, True, True),
    _spec("wan-2.5", "WAN 2.5", ("t2v",), (5, 10), ("720p", "1080p"), RATIOS, True),
    _spec("hailuo-2.3-fast", "MINIMAX HAILUO 2.3 FAST", ("i2v",), (6, 10),
          ("768p", "1080p"), (), False, True),
    _spec("hailuo-2.3", "MINIMAX HAILUO 2.3", ("t2v", "i2v"), (6, 10),
          ("768p", "1080p"), RATIOS, False, True),
    _spec("ltx-2-fast", "LTX-2 FAST", ("t2v", "i2v"), (),
          ("1080p", "2K", "4K"), ("16:9",), True, True),
    _spec("wan-2.5-fast-i2v", "WAN 2.5 I2V FAST", ("i2v",), (5, 10),
          ("720p", "1080p"), (), True, True),
    _spec("wan-2.5-fast-t2v", "WAN 2.5 T2V FAST", ("t2v",), (5, 10),
          ("720p", "1080p"), RATIOS, True),
    _spec("veo-3.1-fast", "VEO 3.1 FAST", ("t2v", "i2v"), (4, 6, 8),
          ("720p", "1080p"), RATIOS, True, True),
    _spec("veo-3.1", "VEO 3.1", ("t2v", "i2v"), (4, 6, 8),
          ("1080p",), RATIOS, True, True),
    _spec("seedance-1-lite", "SEEDANCE 1 LITE", ("t2v", "i2v"), (5, 10),
          ("480p", "720p"), RATIOS, False, True),
    _spec("hailuo-02", "HAILUO 02", ("t2v", "i2v"), (6, 10),
          ("768p", "1080p"), RATIOS, False, True),
    _spec("wan-2.2-i2v-a14b", "WAN 2.2 I2V A14B", ("i2v",), (5,), ("720p",), (), False, True),
    _spec("wan-2.2-i2v-fast", "WAN 2.2 I2V FAST", ("i2v",), (5,), ("720p",), (), False, True),
    _spec("wan-2.2-t2v-fast", "WAN 2.2 T2V FAST", ("t2v",), (5,), ("720p",), RATIOS),
    _spec("veo-3-fast", "VEO 3 FAST", ("t2v", "i2v"), (5, 6, 8), ("720p", "1080p"), RATIOS, True, True),
    _spec("seedance-1-pro-1080p", "SEEDANCE 1 PRO 1080P", ("t2v", "i2v"), (5, 10), ("1080p",), RATIOS, False, True),
    _spec("seedance-1-pro-480p", "SEEDANCE 1 PRO 480P", ("t2v", "i2v"), (5, 10), ("480p",), RATIOS, False, True),
    _spec("veo-3", "VEO 3", ("t2v", "i2v"), (5, 6, 8), ("1080p",), RATIOS, True, True),
    _spec("happyhorse-1.0", "HAPPYHORSE 1.0", ("t2v", "i2v"), range(3, 16),
          ("720p", "1080p"), RATIOS[:5], True, True),
]

VIDEO_CATALOG = {row["slug"]: row for row in _ROWS}
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,79}$")


def capabilities(slug):
    return dict(VIDEO_CATALOG.get(str(slug).lower(), {}))


def allow_live_slug(slug):
    """Return true only for a syntactically safe video-catalog slug."""
    return bool(_SLUG_RE.fullmatch(str(slug or "")))


def build_payload(slug, incoming, prompt, reference_images=None,
                  reference_videos=None, reference_audios=None,
                  first_frame="", last_frame="", generate_audio=True):
    caps = capabilities(slug)
    if not caps:
        # Forward-compatible live-catalog entries are prompt-only.  They do
        # not inherit arbitrary client fields.
        if not allow_live_slug(slug):
            raise ProviderError("MODEL_UNAVAILABLE", "Selected model is unavailable.")
        return {"prompt": prompt}

    images = [u for u in (reference_images or []) if u]
    videos = [u for u in (reference_videos or []) if u]
    audios = [u for u in (reference_audios or []) if u]
    modes = caps["modes"]
    if last_frame and not first_frame:
        raise ProviderError("INVALID_INPUT", "Last frame requires a first frame.")
    if first_frame and not caps.get("first_frame"):
        raise ProviderError("INVALID_INPUT", "This model does not accept a start image.")
    if last_frame and not caps.get("end_frame"):
        raise ProviderError("INVALID_INPUT", "This model does not accept an end image.")
    if "t2v" not in modes and not (first_frame or images or videos or audios):
        raise ProviderError("INVALID_INPUT", "This model requires reference media.")
    for values, field in ((images, "reference_images"), (videos, "reference_videos"), (audios, "reference_audios")):
        if len(values) > int(caps.get(field, 0)):
            raise ProviderError("INVALID_INPUT", "Reference settings exceed model limits.")
    if (first_frame or last_frame) and (images or videos or audios):
        raise ProviderError("INVALID_INPUT", "Elements and Frames cannot be used together.")

    body = {"prompt": prompt}
    allowed_durations = caps.get("durations", ())
    if allowed_durations:
        try:
            duration = int(incoming.get("duration", allowed_durations[0]))
        except (TypeError, ValueError):
            duration = allowed_durations[0]
        if duration not in allowed_durations:
            raise ProviderError("INVALID_INPUT", "Duration is not supported by this model.")
        body["length_seconds"] = duration
    resolutions = caps.get("resolutions", ())
    if resolutions:
        resolution = str(incoming.get("resolution") or resolutions[0])
        if resolution not in resolutions:
            raise ProviderError("INVALID_INPUT", "Resolution is not supported by this model.")
        body["resolution"] = resolution
    ratios = caps.get("aspect_ratios", ())
    if ratios and not first_frame:
        ratio = str(incoming.get("aspect_ratio") or ratios[0])
        if ratio not in ratios:
            raise ProviderError("INVALID_INPUT", "Aspect ratio is not supported by this model.")
        body["aspect_ratio"] = ratio
    if first_frame:
        body["image"] = first_frame
    if last_frame:
        body["end_image"] = last_frame
    if images:
        if caps.get("reference_images", 0) == 1 and "reference" not in modes:
            body["image"] = images[0]
        else:
            body["reference_images"] = images
    if videos:
        body["video" if caps.get("reference_videos") == 1 and "reference" not in modes else "reference_videos"] = videos[0] if caps.get("reference_videos") == 1 and "reference" not in modes else videos
    if audios:
        body["audio" if caps.get("reference_audios") == 1 and "reference" not in modes else "reference_audios"] = audios[0] if caps.get("reference_audios") == 1 and "reference" not in modes else audios
    if caps.get("generate_audio"):
        body["generate_audio"] = bool(generate_audio)
    return body


def registry_rows():
    rows = []
    for item in _ROWS:
        caps = {key: value for key, value in item.items()
                if key not in ("slug", "name", "description")}
        rows.append({"slug": item["slug"], "name": item["name"], "category": "video",
                     "family": "bpx-" + item["slug"], "variant": "STANDARD",
                     "endpoint": "/v1/videos/" + item["slug"], "status": "INTEGRATED",
                     "available": True, "handler": True,
                     "modes": list(item["modes"]), "parameters": _json_safe(caps),
                     "source": "mii-video-catalog"})
    return rows


def public_ui_families(exclude=(), registry=None):
    excluded = set(exclude)
    families = []
    rows = list(_ROWS)
    if registry and not registry.get("sync_error"):
        live_slugs = [row["slug"] for row in registry.get("models", [])
                      if row.get("category") == "video" and row.get("handler")]
        known = VIDEO_CATALOG
        rows = [known.get(slug) or _spec(slug, slug.replace("-", " ").upper())
                for slug in live_slugs]
    for item in rows:
        if item["slug"] in excluded:
            continue
        durations = item["durations"]
        contiguous_duration = bool(durations) and tuple(range(min(durations), max(durations) + 1)) == tuple(durations)
        caps = {
            "supportsT2V": "t2v" in item["modes"],
            "supportsI2V": "i2v" in item["modes"],
            "supportsVideoEdit": "v2v" in item["modes"],
            "supportsElements": any(item[k] for k in ("reference_images", "reference_videos", "reference_audios")),
            "supportsFirstFrame": item["first_frame"], "supportsEndFrame": item["end_frame"],
            "maxReferenceImages": item["reference_images"], "maxReferenceVideos": item["reference_videos"],
            "maxReferenceAudios": item["reference_audios"], "resolutions": list(item["resolutions"]),
            "aspectRatios": list(item["aspect_ratios"]), "supportsAudioGeneration": item["generate_audio"],
            "supportsDuration": bool(durations), "durationMode": "range" if contiguous_duration else "discrete",
        }
        if durations:
            caps.update(durationMin=min(durations), durationMax=max(durations), durationStep=1,
                        durations=list(durations), durationOptions=list(durations))
        families.append({"key": "bpx-" + item["slug"], "brand": "BUDGETPIXEL",
                         "name": item["name"], "featured": True,
                         "desc": item["description"] or "BudgetPixel video model.",
                         "caps": caps, "qualities": [{"id": item["slug"], "label": "STANDARD"}]})
    return families


def _json_safe(value):
    if isinstance(value, tuple):
        return list(value)
    return value
