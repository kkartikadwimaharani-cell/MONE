"""Backend-only BudgetPixel transport for Mii generation tasks.

Only fields in the supplied Phase 1 contract are emitted.  Reference media is
intentionally rejected until its provider request schema and Derabox upload
contract are known.
"""
import re
import time

import requests


BASE_URL = "https://api.budgetpixel.com/v1"

VIDEO_MODELS = {
    ("seedance", "MINI"): "/videos/seedance-2.0-mini",
    ("seedance", "FAST"): "/videos/seedance-2.0-fast",
    ("seedance", "PRO"): "/videos/seedance-2.0",
    ("seedance25", "STANDARD"): "/videos/seedance-2.5",
    ("wan30", "STANDARD"): "/videos/wan-3.0-video",
    ("wan30", "PRIME"): "/videos/wan-3.0-video-prime",
}

# Verified public request controls.  Keep this separate from endpoint routing so
# UI/request validation can share the contract without introducing new fields.
VIDEO_CAPABILITIES = {
    ("seedance25", "STANDARD"): {
        "aspect_ratios": ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9"),
        "resolutions": ("480p", "720p"),
        "duration": (4, 30),
        "generate_audio": True,
    },
}


def video_capabilities(family, variant="STANDARD"):
    """Return a copy of verified video controls for capability-driven callers."""
    return dict(VIDEO_CAPABILITIES.get((str(family).lower(), str(variant).upper()), {}))

IMAGE_MODELS = {
    ("flux2", "KLEIN"): "/images/flux-2-klein",
    ("flux2", "PRO"): "/images/flux-2-pro",
    ("flux2", "DEV"): "/images/flux-2-dev",
    ("qwenbp", "STANDARD"): "/images/qwen-image",
    ("seedream5", "LITE"): "/images/seedream-5.0-lite",
    ("seedream5", "PRO"): "/images/seedream-5.0-pro",
    ("klingimage", "V3"): "/images/kling-v3",
    ("klingimage", "OMNI"): "/images/kling-v3-omni",
    ("gptimage", "LOW"): "/images/gpt-image-2",
    ("gptimage", "STANDARD"): "/images/gpt-image-2",
    ("gptimage", "HIGH"): "/images/gpt-image-2",
}

# Public UI contract.  An empty list means that the provider contract in this
# repository does not publish that setting; callers must omit the control and
# the field rather than borrowing options from another model.
GPT_IMAGE_2_RATIOS = ("1:1", "4:3", "3:4", "5:4", "4:5", "16:9", "9:16",
                      "3:2", "2:3", "21:9", "9:21", "2:1", "1:2")
IMAGE_CAPABILITIES = {
    ("flux2", "KLEIN"): {},
    ("flux2", "PRO"): {},
    ("flux2", "DEV"): {},
    ("qwenbp", "STANDARD"): {},
    ("seedream5", "LITE"): {},
    ("seedream5", "PRO"): {"aspect_ratios": ("1:1", "3:4", "4:3", "9:16", "16:9"),
                               "resolutions": ("1K", "2K")},
    ("klingimage", "V3"): {},
    ("klingimage", "OMNI"): {},
    ("gptimage", "LOW"): {"aspect_ratios": GPT_IMAGE_2_RATIOS, "resolutions": ("1K", "2K", "4K"),
                              "qualities": ("low", "medium", "high"), "image_count": (1, 4),
                              "reference_images": 9, "formats": ("png", "jpeg")},
    ("gptimage", "STANDARD"): {"aspect_ratios": GPT_IMAGE_2_RATIOS, "resolutions": ("1K", "2K", "4K"),
                                   "qualities": ("low", "medium", "high"), "image_count": (1, 4),
                                   "reference_images": 9, "formats": ("png", "jpeg")},
    ("gptimage", "HIGH"): {"aspect_ratios": GPT_IMAGE_2_RATIOS, "resolutions": ("1K", "2K", "4K"),
                               "qualities": ("low", "medium", "high"), "image_count": (1, 4),
                               "reference_images": 9, "formats": ("png", "jpeg")},
}


def image_capabilities(family, variant="STANDARD"):
    """Return a copy so request/UI code cannot mutate the verified registry."""
    return dict(IMAGE_CAPABILITIES.get((str(family).lower(), str(variant).upper()), {}))


class ProviderError(RuntimeError):
    def __init__(self, code, public_message, internal=""):
        super().__init__(internal or public_message)
        self.code = code
        self.public_message = public_message


def _resolve(registry, family, variant):
    key = (str(family).lower(), str(variant or "STANDARD").upper())
    if key not in registry:
        raise ProviderError("MODEL_UNAVAILABLE", "Selected model is unavailable.", repr(key))
    return registry[key]


def resolve_video_model(family, variant="STANDARD"):
    return _resolve(VIDEO_MODELS, family, variant)


def resolve_image_model(family, variant="STANDARD"):
    return _resolve(IMAGE_MODELS, family, variant)


def _headers(api_key):
    if not api_key:
        raise ProviderError("MODEL_UNAVAILABLE", "Selected model is unavailable.", "missing API key")
    return {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}


def _json(response):
    try:
        data = response.json()
    except (TypeError, ValueError) as exc:
        raise ProviderError("GENERATION_FAILED", "Generation failed. Please try again.", str(exc))
    if not isinstance(data, dict):
        raise ProviderError("GENERATION_FAILED", "Generation failed. Please try again.", repr(data))
    return data


def _submit(endpoint, payload, api_key, session=requests, timeout=30):
    try:
        response = session.post(BASE_URL + endpoint, headers=_headers(api_key), json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise ProviderError("GENERATION_FAILED", "Generation failed. Please try again.", str(exc))
    if response.status_code >= 400:
        raise normalize_error(response)
    data = _json(response)
    job_id = data.get("job_id") or data.get("id")
    if not isinstance(job_id, (str, int)) or not str(job_id):
        raise ProviderError("GENERATION_FAILED", "Generation failed. Please try again.", repr(data))
    return {"job_id": str(job_id), "raw": data}


def submit_video(family, variant, payload, api_key, session=requests, timeout=30):
    return _submit(resolve_video_model(family, variant), payload, api_key, session, timeout)


def submit_image(family, variant, payload, api_key, session=requests, timeout=30):
    return _submit(resolve_image_model(family, variant), payload, api_key, session, timeout)


def _get_status(kind, job_id, api_key, session=requests, timeout=30):
    try:
        response = session.get("%s/%ss/%s" % (BASE_URL, kind, job_id), headers=_headers(api_key), timeout=timeout)
    except requests.RequestException as exc:
        raise ProviderError("GENERATION_FAILED", "Generation failed. Please try again.", str(exc))
    if response.status_code >= 400:
        raise normalize_error(response)
    return normalize_result(_json(response))


def get_video_status(job_id, api_key, session=requests, timeout=30):
    return _get_status("video", job_id, api_key, session, timeout)


def get_image_status(job_id, api_key, session=requests, timeout=30):
    return _get_status("image", job_id, api_key, session, timeout)


def normalize_result(data):
    raw_status = str(data.get("status") or data.get("state") or "").lower()
    statuses = {
        "pending": "queued", "starting": "processing", "processing": "processing",
        "completing": "processing", "succeeded": "completed", "failed": "failed",
        "timeout": "failed",
    }
    status = statuses.get(raw_status)
    if not status:
        raise ProviderError("GENERATION_FAILED", "Generation failed. Please try again.", repr(data))
    output = data.get("output") or data.get("result") or {}
    if isinstance(output, str):
        output = {"url": output}
    images = data.get("images") or output.get("images") or []
    normalized_images = []
    if isinstance(images, list):
        for item in images:
            candidate = item.get("url") if isinstance(item, dict) else item
            if isinstance(candidate, str) and candidate:
                normalized_images.append({"url": candidate})
    url = (output.get("url") or output.get("video_url") or output.get("image_url")
           or data.get("url") or data.get("video_url") or data.get("image_url"))
    if not url and normalized_images:
        url = normalized_images[0]["url"]
    return {"status": status, "url": url, "images": normalized_images,
            "raw_status": raw_status, "raw": data}


def normalize_error(response):
    if response.status_code == 429:
        code = "RATE_LIMITED"
    else:
        code = "MODEL_UNAVAILABLE" if response.status_code in (401, 403, 404) else "GENERATION_FAILED"
    detail = "HTTP %s" % response.status_code
    try:
        detail += ": " + str(response.json())[:1000]
    except (TypeError, ValueError):
        detail += ": " + str(getattr(response, "text", ""))[:1000]
    detail = re.sub(r'(?i)(authorization|api[_ -]?key|token|secret)(["\'\s:=]+)[^,}\s]+',
                    r'\1\2[REDACTED]', detail)
    return ProviderError(code, "Selected model is unavailable." if code == "MODEL_UNAVAILABLE" else "Generation failed. Please try again.", detail)


def poll(job_id, api_key, kind="video", session=requests, timeout_seconds=600, interval=2, sleep=time.sleep):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        getter = get_image_status if kind == "image" else get_video_status
        result = getter(job_id, api_key, session=session)
        if result["status"] in ("completed", "failed"):
            return result
        sleep(interval)
    raise ProviderError("GENERATION_TIMEOUT", "Generation timed out. Please try again.", "poll timeout")
