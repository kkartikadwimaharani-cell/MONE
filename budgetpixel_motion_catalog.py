"""Reviewed motion-control models exposed by the MII catalogue."""

from budgetpixel_provider import ProviderError

ROWS = (
    {"slug": "kling-3-motion-control-std", "name": "KLING 3 STANDARD"},
    {"slug": "dreamactor-m2.0", "name": "DREAMACTOR M2.0"},
)
MOTION_CATALOG = {row["slug"]: row for row in ROWS}


def registry_rows():
    return [{"slug": row["slug"], "name": row["name"], "category": "motion",
             "family": "bpx-motion-control", "variant": row["slug"],
             "endpoint": "/v1/motion-control/" + row["slug"], "status": "INTEGRATED",
             "available": True, "handler": True, "modes": ["motion-control"],
             "parameters": {"reference_images": 1, "reference_videos": 1},
             "source": "mii-motion-catalog"} for row in ROWS]


def public_ui_families():
    caps = {"supportsT2V": False, "supportsI2V": False, "supportsElements": True,
            "maxReferenceImages": 1, "maxReferenceVideos": 1,
            "requiresImage": True, "requiresVideo": True,
            "supportsDuration": False, "resolutions": [], "aspectRatios": []}
    return [{"key": "bpx-motion-control", "brand": "MIIAIVIDEO", "name": "MOTION CONTROL",
             "featured": True, "desc": "Animate a character image from a reference video.",
             "caps": caps, "qualities": [
                 {"id": row["slug"], "label": row["name"], "route": "catalog",
                  "outputKind": "motion", "caps": caps} for row in ROWS]}]


def build_payload(slug, prompt, image_urls, video_urls, mute_audio=False,
                  character_orientation="video", trim_intro=True):
    images = [url for url in (image_urls or []) if url]
    videos = [url for url in (video_urls or []) if url]
    if slug not in MOTION_CATALOG:
        raise ProviderError("MODEL_UNAVAILABLE", "Selected model is unavailable.")
    if len(images) != 1 or len(videos) != 1:
        raise ProviderError("INVALID_INPUT", "Motion Control requires exactly one image and one video.")
    body = {"image": images[0], "video": videos[0]}
    if prompt:
        body["prompt"] = prompt
    if slug == "kling-3-motion-control-std":
        orientation = str(character_orientation or "video").lower()
        if orientation not in ("video", "image"):
            raise ProviderError("INVALID_INPUT", "Character orientation must be video or image.")
        body.update(character_orientation=orientation, keep_original_sound=not mute_audio)
    else:
        body["trim_intro"] = bool(trim_intro)
    return body
