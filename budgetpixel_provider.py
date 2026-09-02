"""Backend-only BudgetPixel transport for Mii generation tasks.

Only fields in the supplied Phase 1 contract are emitted.  Reference media is
intentionally rejected until its provider request schema and Derabox upload
contract are known.
"""
import time

import requests


BASE_URL = "https://api.budgetpixel.com/v1"
STATUS_PATH = "/jobs/{job_id}"

VIDEO_MODELS = {
    ("seedance", "MINI"): "/videos/seedance-2.0-mini",
    ("seedance", "FAST"): "/videos/seedance-2.0-fast",
    ("seedance", "PRO"): "/videos/seedance-2.0",
    ("seedance25", "STANDARD"): "/videos/seedance-2.5",
    ("wan30", "STANDARD"): "/videos/wan-3.0-video",
    ("wan30", "PRIME"): "/videos/wan-3.0-video-prime",
}

IMAGE_MODELS = {
    ("flux2", "KLEIN"): "/images/flux-2-klein",
    ("flux2", "PRO"): "/images/flux-2-pro",
    ("flux2", "DEV"): "/images/flux-2-dev",
    ("qwenbp", "STANDARD"): "/images/qwen-image",
    ("seedream5", "LITE"): "/images/seedream-5.0-lite",
    ("seedream5", "PRO"): "/images/seedream-5.0-pro",
    ("klingimage", "V3"): "/images/kling-v3",
    ("klingimage", "OMNI"): "/images/kling-v3-omni",
}


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
        raise ProviderError("MALFORMED_RESPONSE", "Generation failed. Please try again.", str(exc))
    if not isinstance(data, dict):
        raise ProviderError("MALFORMED_RESPONSE", "Generation failed. Please try again.", repr(data))
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
        raise ProviderError("MALFORMED_RESPONSE", "Generation failed. Please try again.", repr(data))
    return {"job_id": str(job_id), "raw": data}


def submit_video(family, variant, payload, api_key, session=requests, timeout=30):
    return _submit(resolve_video_model(family, variant), payload, api_key, session, timeout)


def submit_image(family, variant, payload, api_key, session=requests, timeout=30):
    return _submit(resolve_image_model(family, variant), payload, api_key, session, timeout)


def get_status(job_id, api_key, session=requests, timeout=30):
    try:
        response = session.get(BASE_URL + STATUS_PATH.format(job_id=job_id), headers=_headers(api_key), timeout=timeout)
    except requests.RequestException as exc:
        raise ProviderError("GENERATION_FAILED", "Generation failed. Please try again.", str(exc))
    if response.status_code >= 400:
        raise normalize_error(response)
    return normalize_result(_json(response))


def normalize_result(data):
    raw_status = str(data.get("status") or data.get("state") or "").lower()
    statuses = {
        "pending": "queued", "starting": "processing", "processing": "processing",
        "completing": "processing", "succeeded": "completed", "failed": "failed",
        "timeout": "failed",
    }
    status = statuses.get(raw_status)
    if not status:
        raise ProviderError("MALFORMED_RESPONSE", "Generation failed. Please try again.", repr(data))
    output = data.get("output") or data.get("result") or {}
    if isinstance(output, str):
        output = {"url": output}
    url = (output.get("url") or output.get("video_url") or output.get("image_url")
           or data.get("url") or data.get("video_url") or data.get("image_url"))
    return {"status": status, "url": url, "raw_status": raw_status, "raw": data}


def normalize_error(response):
    code = "MODEL_UNAVAILABLE" if response.status_code in (401, 403, 404) else "GENERATION_FAILED"
    detail = "HTTP %s" % response.status_code
    try:
        detail += ": " + str(response.json())[:1000]
    except (TypeError, ValueError):
        detail += ": " + str(getattr(response, "text", ""))[:1000]
    return ProviderError(code, "Selected model is unavailable." if code == "MODEL_UNAVAILABLE" else "Generation failed. Please try again.", detail)


def poll(job_id, api_key, session=requests, timeout_seconds=600, interval=2, sleep=time.sleep):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = get_status(job_id, api_key, session=session)
        if result["status"] in ("completed", "failed"):
            return result
        sleep(interval)
    raise ProviderError("GENERATION_FAILED", "Generation failed. Please try again.", "poll timeout")
