"""Reviewed BudgetPixel image and audio catalogue adapters.

The UI groups endpoints by product line, while every quality keeps the exact
BudgetPixel slug used for submission.  New catalogue entries remain visible
through ``GET /v1/models`` but only the contracts in this module are runnable.
"""
import re

from budgetpixel_provider import (
    IMAGE_CAPABILITIES as CORE_IMAGE_CAPABILITIES,
    ProviderError,
    build_image_payload as build_core_image_payload,
)


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,79}$")


def _image(slug, name, group, label="STANDARD", references=0,
           singular=False, required=False, description=""):
    return {"slug": slug, "name": name, "category": "image", "group": group,
            "label": label, "reference_images": references,
            "singular_image": singular, "requires_image": required,
            "description": description}


IMAGE_ROWS = [
    _image("seedream-5.0-pro", "SEEDREAM 5.0 PRO", "SEEDREAM 5", "PRO", 9),
    _image("seedream-5.0-lite", "SEEDREAM 5.0 LITE", "SEEDREAM 5", "LITE", 9),
    _image("kling-v3", "KLING V3", "KLING IMAGE", "V3", 1, True),
    _image("kling-v3-omni", "KLING V3 OMNI", "KLING IMAGE", "OMNI", 9),
    _image("gpt-image-2", "GPT-IMAGE-2", "GPT IMAGE 2", "STANDARD", 9),
    _image("gpt-image-2.5-flare", "GPT IMAGE 2.5 FLARE", "GPT IMAGE 2.5", "FLARE", 9,
           description="Fast image generation and targeted editing with up to nine references."),
    _image("gpt-image-2.5-sunburst", "GPT IMAGE 2.5 SUNBURST", "GPT IMAGE 2.5", "SUNBURST", 9,
           description="Precision image generation and editing with up to nine references."),
    _image("flux-2-klein", "FLUX 2 KLEIN", "FLUX 2", "KLEIN", 3),
    _image("flux-2-pro", "FLUX 2 PRO", "FLUX 2", "PRO", 1, True),
    _image("flux-2-dev", "FLUX 2 DEV", "FLUX 2", "DEV", 4),
    _image("nano-banana-pro", "NANO BANANA PRO", "NANO BANANA", "PRO", 14),
    _image("qwen-image", "QWEN IMAGE", "QWEN IMAGE", "STANDARD"),
    _image("flux-dev", "FLUX DEV", "FLUX", "DEV"),
    _image("muse-image-1.0", "MUSE IMAGE 1.0", "MUSE IMAGE"),
    _image("grok-imagine-image-2", "GROK IMAGINE 2.0", "GROK IMAGINE", "2.0"),
    _image("grok-imagine-image-quality", "GROK IMAGINE QUALITY", "GROK IMAGINE", "QUALITY"),
    _image("grok-imagine-image", "GROK IMAGINE", "GROK IMAGINE", "STANDARD"),
    _image("qwen-image-3.0", "QWEN IMAGE 3.0", "QWEN IMAGE 3", "STANDARD"),
    _image("qwen-image-3.0-pro", "QWEN IMAGE 3.0 PRO", "QWEN IMAGE 3", "PRO"),
    _image("qwen-image-2.0", "QWEN IMAGE 2.0", "QWEN IMAGE 2", "STANDARD"),
    _image("qwen-image-2.0-pro", "QWEN IMAGE 2.0 PRO", "QWEN IMAGE 2", "PRO"),
    _image("qwen-image-edit-plus", "QWEN IMAGE EDIT PLUS", "QWEN IMAGE EDIT", "PLUS", 1, True, True),
    _image("qwen-image-edit", "QWEN IMAGE EDIT", "QWEN IMAGE EDIT", "STANDARD", 1, True, True),
    _image("nano-banana-2", "NANO BANANA 2", "NANO BANANA 2", "STANDARD", 14),
    _image("nano-banana-2-lite", "NANO BANANA 2 LITE", "NANO BANANA 2", "LITE", 14),
    _image("nano-banana", "NANO BANANA", "NANO BANANA", "STANDARD", 4),
    _image("ideogram-v4", "IDEOGRAM V4", "IDEOGRAM", "V4"),
    _image("ideogram-v3-balanced", "IDEOGRAM V3 BALANCED", "IDEOGRAM", "V3 BALANCED"),
    _image("ideogram-v3-quality", "IDEOGRAM V3 QUALITY", "IDEOGRAM", "V3 QUALITY"),
    _image("ideogram-v3-turbo", "IDEOGRAM V3 TURBO", "IDEOGRAM", "V3 TURBO"),
    _image("krea-2-large", "KREA 2 LARGE", "KREA 2", "LARGE"),
    _image("krea-2-medium", "KREA 2 MEDIUM", "KREA 2", "MEDIUM"),
    _image("imagineart-2.0", "IMAGINEART 2.0", "IMAGINEART", "2.0"),
    _image("imagineart-1.5-pro", "IMAGINEART 1.5 PRO", "IMAGINEART", "1.5 PRO"),
    _image("imagineart-1.5", "IMAGINEART 1.5", "IMAGINEART", "1.5"),
    _image("recraft-v4", "RECRAFT V4", "RECRAFT V4", "STANDARD", 10),
    _image("recraft-v4-pro", "RECRAFT V4 PRO", "RECRAFT V4", "PRO", 10),
    _image("midjourney-v7", "MIDJOURNEY V7", "MIDJOURNEY", "V7",
           description="V7 for polished cinematic/editorial images; Niji 7 for anime and illustration."),
    _image("midjourney-niji-7", "MIDJOURNEY NIJI 7", "MIDJOURNEY", "NIJI 7",
           description="Anime-focused imagery with clean line work and expressive character detail."),
    _image("wan-2.7", "WAN 2.7", "WAN IMAGE", "2.7"),
    _image("wan-2.7-pro", "WAN 2.7 PRO", "WAN IMAGE", "2.7 PRO"),
    _image("wan-2.6", "WAN 2.6", "WAN IMAGE", "2.6"),
    _image("wan-2.5", "WAN 2.5", "WAN IMAGE", "2.5"),
    _image("wan-2.2-image", "WAN 2.2 IMAGE", "WAN IMAGE", "2.2"),
    _image("hunyuan-image-3-instruct", "HUNYUAN IMAGE 3 INSTRUCT", "HUNYUAN IMAGE"),
    _image("seedream-4.5", "SEEDREAM 4.5", "SEEDREAM 4", "4.5", 9),
    _image("seedream-4", "SEEDREAM 4", "SEEDREAM 4", "4.0", 6),
    _image("p-image", "P-IMAGE", "P-IMAGE", "GENERATE"),
    _image("p-image-edit", "P-IMAGE EDIT", "P-IMAGE", "EDIT", 1, True, True),
    _image("z-image-turbo", "Z-IMAGE TURBO", "Z-IMAGE"),
    _image("flux-2-max", "FLUX 2 MAX", "FLUX 2 EXTENDED", "MAX"),
    _image("flux-2-flex", "FLUX 2 FLEX", "FLUX 2 EXTENDED", "FLEX"),
    _image("flux-1.1-pro", "FLUX 1.1 PRO", "FLUX 1.1", "PRO"),
    _image("flux-1.1-pro-ultra", "FLUX 1.1 PRO ULTRA", "FLUX 1.1", "ULTRA"),
    _image("flux-schnell-ultra", "FLUX SCHNELL ULTRA", "FLUX SPECIAL", "SCHNELL ULTRA"),
    _image("flux-krea-dev", "FLUX KREA DEV", "FLUX SPECIAL", "KREA DEV"),
    _image("flux-kontext-max", "FLUX KONTEXT MAX", "FLUX KONTEXT", "MAX", 1, True, True),
    _image("flux-kontext-pro", "FLUX KONTEXT PRO", "FLUX KONTEXT", "PRO", 1, True, True),
    _image("imagen-4-ultra", "IMAGEN 4 ULTRA", "IMAGEN 4", "ULTRA"),
    _image("gen4-image", "GEN-4 IMAGE", "RUNWAY GEN-4"),
    _image("minimax-image-01", "MINIMAX IMAGE-01", "MINIMAX IMAGE"),
    _image("lucid-origin-standard", "LUCID ORIGIN STANDARD", "LUCID ORIGIN", "STANDARD"),
    _image("lucid-origin-ultra", "LUCID ORIGIN ULTRA", "LUCID ORIGIN", "ULTRA"),
]


def _audio(slug, name, group, label="STANDARD", subtype="music", duration=(),
           images=0, videos=0, formats=("mp3",), lyrics=False,
           instrumental=False, vocal_genders=(), description=""):
    return {"slug": slug, "name": name, "category": "audio", "subtype": subtype,
            "group": group, "label": label, "durations": tuple(duration),
            "reference_images": images, "reference_videos": videos,
            "formats": tuple(formats), "supports_lyrics": bool(lyrics),
            "supports_instrumental": bool(instrumental),
            "vocal_genders": tuple(vocal_genders), "description": description}


AUDIO_ROWS = [
    _audio("lyria-3", "LYRIA 3", "LYRIA", images=10, lyrics=True,
           description="Music from a text prompt, optionally guided by images."),
    _audio("mureka-v9", "MUREKA V9", "MUREKA", lyrics=True,
           instrumental=True, vocal_genders=("auto", "female", "male"),
           description="Instrumental music from a style prompt."),
    _audio("music-3.0", "MUSIC 3.0", "MINIMAX MUSIC", "3.0", formats=("wav", "mp3"),
           lyrics=True, instrumental=True),
    _audio("music-2.6", "MUSIC 2.6", "MINIMAX MUSIC", "2.6", formats=("wav", "mp3"),
           lyrics=True, instrumental=True),
    _audio("sonilo-music", "SONILO MUSIC", "SONILO MUSIC", "TEXT", "music",
           range(5, 361), formats=("mp3", "wav")),
    _audio("sonilo-video-music", "SONILO VIDEO MUSIC", "SONILO MUSIC", "VIDEO", videos=1, formats=("mp3", "wav")),
    _audio("sonilo-sfx", "SONILO SFX", "SONILO SFX", "TEXT", "sfx", range(1, 181), formats=("mp3", "wav")),
    _audio("sonilo-video-sfx", "SONILO VIDEO SFX", "SONILO SFX", "VIDEO", "sfx", videos=1, formats=("mp3", "wav")),
]


IMAGE_CATALOG = {row["slug"]: row for row in IMAGE_ROWS}
AUDIO_CATALOG = {row["slug"]: row for row in AUDIO_ROWS}


def audio_fields(item):
    """Return only request fields accepted by this audio model contract."""
    fields = []
    if len(item.get("formats", ())) > 1:
        fields.append("audio_format")
    if item.get("durations"):
        fields.append("duration")
    if item.get("supports_lyrics"):
        fields.append("lyrics")
    if item.get("supports_instrumental"):
        fields.append("instrumental")
    if item.get("vocal_genders"):
        fields.append("vocal_gender")
    if item.get("reference_images"):
        fields.append("image_urls")
    if item.get("reference_videos"):
        fields.append("video_urls")
    return fields

# Catalogue slugs that share the already-reviewed image request contracts in
# budgetpixel_provider. Keeping one contract source prevents the original app
# and the read-only demo from drifting apart as controls are added.
_CORE_IMAGE_ROUTE = {
    "seedream-5.0-pro": ("seedream5", "PRO"),
    "seedream-5.0-lite": ("seedream5", "LITE"),
    "kling-v3": ("klingimage", "V3"),
    "kling-v3-omni": ("klingimage", "OMNI"),
    "gpt-image-2": ("gptimage", "STANDARD"),
    "gpt-image-2.5-flare": ("gptimage25", "FLARE"),
    "gpt-image-2.5-sunburst": ("gptimage25", "SUNBURST"),
    "flux-2-klein": ("flux2", "KLEIN"),
    "flux-2-pro": ("flux2", "PRO"),
    "flux-2-dev": ("flux2", "DEV"),
    "qwen-image": ("qwenbp", "STANDARD"),
}

# Shared image-workshop baseline.  BudgetPixel's image endpoints use the same
# public names for these controls (aspect_ratio, size and num_images).  Exact
# model overrides live below; the baseline keeps every catalogue card usable
# instead of rendering controls that disappear when the user changes model.
_COMMON_IMAGE_RATIOS = ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9")
_WIDE_IMAGE_RATIOS = _COMMON_IMAGE_RATIOS + ("5:4", "4:5")
_IMAGE_CONTRACT_OVERRIDES = {
    "nano-banana-2": {
        "aspect_ratios": ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
                          "9:16", "16:9", "21:9", "1:4", "4:1", "1:8", "8:1"),
        "sizes": ("0.5K", "1K", "2K", "4K"), "default_size": "1K",
        "image_count": (1, 4), "reference_images": 9,
    },
    "nano-banana-2-lite": {
        "aspect_ratios": ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
                          "9:16", "16:9", "21:9", "1:4", "4:1"),
        "sizes": ("0.5K", "1K", "2K"), "default_size": "1K",
        "image_count": (1, 4), "reference_images": 9,
    },
    "qwen-image-3.0": {
        "aspect_ratios": _COMMON_IMAGE_RATIOS + ("match_input_image",),
        "sizes": ("1K", "2K"), "default_size": "1K", "image_count": (1, 4),
        "reference_images": 3, "seed": True, "negative_prompt": True,
    },
    "qwen-image-3.0-pro": {
        "aspect_ratios": _COMMON_IMAGE_RATIOS + ("match_input_image",),
        "sizes": ("1K", "2K"), "default_size": "1K", "image_count": (1, 4),
        "reference_images": 3, "seed": True, "negative_prompt": True,
    },
    "qwen-image-2.0": {
        "aspect_ratios": _COMMON_IMAGE_RATIOS + ("match_input_image",),
        "sizes": ("1K", "1.5K", "2K"), "default_size": "1.5K",
        "image_count": (1, 4), "reference_images": 3,
        "seed": True, "negative_prompt": True,
    },
    "qwen-image-2.0-pro": {
        "aspect_ratios": _COMMON_IMAGE_RATIOS + ("match_input_image",),
        "sizes": ("1K", "1.5K", "2K"), "default_size": "1.5K",
        "image_count": (1, 4), "reference_images": 3,
        "seed": True, "negative_prompt": True,
    },
    "wan-2.7": {
        "aspect_ratios": _COMMON_IMAGE_RATIOS + ("match_input_image",),
        "sizes": ("1K", "2K"), "default_size": "2K", "image_count": (1, 4),
        "reference_images": 9, "seed": True,
    },
    "wan-2.7-pro": {
        "aspect_ratios": _COMMON_IMAGE_RATIOS + ("match_input_image",),
        "sizes": ("1K", "2K"), "default_size": "2K", "image_count": (1, 4),
        "reference_images": 9, "seed": True,
    },
    "seedream-4.5": {
        "aspect_ratios": _COMMON_IMAGE_RATIOS, "sizes": ("2K", "4K"),
        "default_size": "2K", "image_count": (1, 4), "reference_images": 9,
        "sequential_modes": ("disabled", "auto"), "max_images": (1, 15),
    },
}


def _catalog_image_contract(item):
    """Return the normalized request contract for a catalogue-only model."""
    override = _IMAGE_CONTRACT_OVERRIDES.get(item["slug"])
    if override:
        contract = dict(override)
    else:
        # The catalogue image workshop exposes these normalized request fields
        # across its remaining image endpoints. Keep the conservative common
        # 1K/2K range here; documented 4K/MP models are explicit overrides.
        contract = {
            "aspect_ratios": _WIDE_IMAGE_RATIOS,
            "default_aspect_ratio": "1:1",
            "sizes": ("1K", "2K"),
            "default_size": "1K",
            "image_count": (1, 4),
        }
    contract.setdefault("default_aspect_ratio", "1:1")
    if item.get("reference_images"):
        contract.setdefault("reference_images", item["reference_images"])
    if item.get("singular_image"):
        contract["singular_image"] = True
    return contract


def image_contract(slug):
    """Return a copy of the shared UI/backend/tool contract for one image slug."""
    route = _CORE_IMAGE_ROUTE.get(slug)
    if route:
        contract = dict(CORE_IMAGE_CAPABILITIES.get(route, {}))
        # These endpoints publish aspect/count controls but no selectable
        # output-size request field. Expose their honest native-output state
        # in UI/tools without sending an unsupported resolution parameter.
        if slug in ("flux-2-dev", "qwen-image"):
            contract["native_resolution"] = True
        return contract
    item = IMAGE_CATALOG.get(str(slug).lower())
    return _catalog_image_contract(item) if item else {}


def _image_ui_caps(item):
    """Translate the request contract into the capability names used by UI."""
    contract = image_contract(item["slug"])
    image_limit = 1 if item["singular_image"] else int(contract.get("reference_images", item["reference_images"]))
    caps = {
        "image": image_limit,
        "video": 0,
        "audio": 0,
        "frames": False,
        "elements": bool(image_limit),
        "ratio": bool(contract.get("aspect_ratios")),
        "resolution": bool(contract.get("resolutions")),
        "requiresImage": item["requires_image"],
        "supportsAspectRatio": bool(contract.get("aspect_ratios")),
        "aspectRatios": list(contract.get("aspect_ratios", ())),
        "defaultAspectRatio": contract.get("default_aspect_ratio", "1:1"),
        "supportsResolution": bool(contract.get("resolutions") or contract.get("native_resolution")),
        "resolutions": list(contract.get("resolutions", ())) or
                       (["NATIVE"] if contract.get("native_resolution") else []),
        "defaultResolution": contract.get("default_resolution") or
                             ((contract.get("resolutions") or
                               (("NATIVE",) if contract.get("native_resolution") else (None,)))[0]),
        "supportsSize": bool(contract.get("sizes")),
        "sizes": list(contract.get("sizes", ())),
        "defaultSize": contract.get("default_size"),
        "supportsMegapixel": bool(contract.get("megapixels")),
        "megapixels": list(contract.get("megapixels", ())),
        "defaultMegapixel": contract.get("default_megapixel"),
        "supportsQuality": bool(contract.get("qualities")),
        "qualities": list(contract.get("qualities", ())),
        "defaultQuality": contract.get("default_quality") or
                          ("medium" if item["slug"] == "gpt-image-2" else
                           ((contract.get("qualities") or (None,))[0])),
        "supportsImageCount": bool(contract.get("image_count")),
        "minImages": contract.get("image_count", (1, 1))[0],
        "maxImages": contract.get("image_count", (1, 1))[1],
        "supportsOutputFormat": bool(contract.get("formats")),
        "formats": list(contract.get("formats", ())),
        "seed": bool(contract.get("seed")),
        "negativePrompt": bool(contract.get("negative_prompt")),
        "sequentialModes": list(contract.get("sequential_modes", ())),
        "maxImagesRange": list(contract.get("max_images", ())),
        "singularImage": bool(contract.get("singular_image") or item["singular_image"]),
    }
    return caps


def registry_rows():
    rows = []
    for item in IMAGE_ROWS + AUDIO_ROWS:
        kind = item["category"]
        params = {k: list(v) if isinstance(v, tuple) else v for k, v in item.items()
                  if k not in ("slug", "name", "group", "label", "description", "category")}
        if kind == "image":
            params.update({key: list(value) if isinstance(value, tuple) else value
                           for key, value in image_contract(item["slug"]).items()})
        rows.append({"slug": item["slug"], "name": item["name"], "category": kind,
                     "family": "bpx-" + item["slug"], "variant": "STANDARD",
                     "endpoint": "/v1/%ss/%s" % (kind, item["slug"]),
                     "status": "INTEGRATED", "available": True, "handler": True,
                     "modes": ["text-to-image"] if kind == "image" else [item.get("subtype", "audio")],
                     "parameters": params, "source": "mii-media-catalog"})
    return rows


def build_image_payload(slug, incoming, prompt, reference_images=None):
    item = IMAGE_CATALOG.get(str(slug).lower())
    if not item or not _SLUG_RE.fullmatch(str(slug or "")):
        raise ProviderError("MODEL_UNAVAILABLE", "Selected image model is unavailable.")
    refs = [url for url in (reference_images or []) if url]
    contract = image_contract(item["slug"])
    limit = 1 if item["singular_image"] else int(contract.get("reference_images", item["reference_images"]))
    if item["requires_image"] and not refs:
        raise ProviderError("INVALID_INPUT", "This image-edit model requires one source image.")
    if len(refs) > limit:
        raise ProviderError("INVALID_INPUT", "Reference image settings exceed model limits.")
    core_route = _CORE_IMAGE_ROUTE.get(item["slug"])
    if core_route:
        # The catalogue endpoint differs, but the accepted body is identical.
        # Reuse the strict validator so aspect ratio, size/resolution, quality,
        # count and format selected in either UI are never silently discarded.
        return build_core_image_payload(
            core_route[0], core_route[1], incoming, prompt,
            reference_images=refs,
        )
    body = {"prompt": prompt}
    ratios = contract.get("aspect_ratios", ())
    ratio = str(incoming.get("aspect_ratio") or contract.get("default_aspect_ratio") or ratios[0])
    if ratio not in ratios:
        raise ProviderError("INVALID_INPUT", "Aspect ratio is not supported by this model.")
    if ratio == "match_input_image" and not refs:
        raise ProviderError("INVALID_INPUT", "match_input_image requires a reference image.")
    body["aspect_ratio"] = ratio
    sizes = contract.get("sizes", ())
    size = str(incoming.get("size") or contract.get("default_size") or sizes[0]).upper()
    if size not in sizes:
        raise ProviderError("INVALID_INPUT", "Size is not supported by this model.")
    body["size"] = size
    count_range = contract.get("image_count", (1, 1))
    try:
        count = int(incoming.get("num_images", 1))
    except (TypeError, ValueError):
        count = 0
    if not count_range[0] <= count <= count_range[1]:
        raise ProviderError("INVALID_INPUT", "Image count is outside model limits.")
    body["num_images"] = count
    if contract.get("seed") and incoming.get("seed") not in (None, ""):
        try:
            body["seed"] = int(incoming["seed"])
        except (TypeError, ValueError):
            raise ProviderError("INVALID_INPUT", "Seed must be an integer.")
    if contract.get("negative_prompt") and incoming.get("negative_prompt") not in (None, ""):
        body["negative_prompt"] = str(incoming["negative_prompt"])
    if contract.get("sequential_modes"):
        mode = str(incoming.get("sequential_image_generation") or "disabled").lower()
        if mode not in contract["sequential_modes"]:
            raise ProviderError("INVALID_INPUT", "Sequential generation mode is invalid.")
        body["sequential_image_generation"] = mode
        if mode == "auto":
            try:
                maximum = int(incoming.get("max_images", contract["max_images"][0]))
            except (TypeError, ValueError):
                maximum = 0
            if not contract["max_images"][0] <= maximum <= contract["max_images"][1]:
                raise ProviderError("INVALID_INPUT", "Max images is outside model limits.")
            body["max_images"] = maximum
    if refs:
        body["image" if item["singular_image"] else "reference_images"] = refs[0] if item["singular_image"] else refs
    return body


def build_audio_payload(slug, incoming, prompt, reference_images=None, reference_videos=None):
    item = AUDIO_CATALOG.get(str(slug).lower())
    if not item:
        raise ProviderError("MODEL_UNAVAILABLE", "Selected audio model is unavailable.")
    images = [url for url in (reference_images or []) if url]
    videos = [url for url in (reference_videos or []) if url]
    if len(images) > item["reference_images"] or len(videos) > item["reference_videos"]:
        raise ProviderError("INVALID_INPUT", "Reference media settings exceed model limits.")
    if item["reference_videos"] and item["label"] == "VIDEO" and not videos:
        raise ProviderError("INVALID_INPUT", "This audio model requires one source video.")
    fmt = str(incoming.get("audio_format") or item["formats"][0]).lower()
    if len(item["formats"]) > 1 and fmt not in item["formats"]:
        raise ProviderError("INVALID_INPUT", "Audio format is not supported by this model.")
    body = {"prompt": prompt}
    lyrics = str(incoming.get("lyrics") or "").strip() if item["supports_lyrics"] else ""
    instrumental = bool(incoming.get("instrumental", not lyrics)) if item["supports_instrumental"] else False
    if slug in ("music-3.0", "music-2.6"):
        body.update(format=fmt, instrumental=instrumental,
                    lyrics_optimizer=not instrumental and not lyrics)
        if lyrics: body["lyrics"] = lyrics[:3500]
    elif slug == "mureka-v9":
        gender = str(incoming.get("vocal_gender") or "auto").lower()
        if gender not in ("auto", "female", "male"): gender = "auto"
        body.update(instrumental=instrumental, vocal_gender=gender)
        if lyrics: body["lyrics"] = lyrics[:5000]
    elif slug == "lyria-3":
        if images: body["images"] = images
        if lyrics: body["lyrics"] = lyrics[:3000]
    elif slug in ("sonilo-music", "sonilo-sfx"):
        try: duration = int(incoming.get("duration", item["durations"][0]))
        except (TypeError, ValueError): duration = item["durations"][0]
        if duration not in item["durations"]:
            raise ProviderError("INVALID_INPUT", "Duration is not supported by this audio model.")
        body.update(duration=duration, format=fmt)
    elif slug in ("sonilo-video-music", "sonilo-video-sfx"):
        body.update(video=videos[0], format=fmt)
    return body


def _audio_caps(item):
    durations = item["durations"]
    contiguous = bool(durations) and tuple(range(min(durations), max(durations) + 1)) == tuple(durations)
    caps = {"supportsT2V": False, "supportsI2V": False,
            "supportsElements": bool(item["reference_images"] or item["reference_videos"]),
            "maxReferenceImages": item["reference_images"],
            "maxReferenceVideos": item["reference_videos"], "maxReferenceAudios": 0,
            "supportsFirstFrame": False, "supportsEndFrame": False,
            "supportsDuration": bool(durations), "audioFormats": list(item["formats"]),
            "supportsAudioFormatSelection": len(item["formats"]) > 1,
            "supportsLyrics": item["supports_lyrics"],
            "supportsInstrumental": item["supports_instrumental"],
            "vocalGenders": list(item["vocal_genders"]),
            "requiresVideo": bool(item["reference_videos"] and item["label"] == "VIDEO")}
    if durations:
        caps.update(durationMode="range" if contiguous else "discrete", durationMin=min(durations),
                    durationMax=max(durations), durationStep=1,
                    durationOptions=list(durations), defaultDuration=min(durations))
    return caps


def public_ui_bundle(registry=None):
    images = list(IMAGE_ROWS)
    audios = list(AUDIO_ROWS)
    # These rows are the reviewed executable catalogue, not speculative cards.
    # Keep them visible even when /v1/models is partial or uses a different
    # category spelling. The generation route still validates every slug and
    # uses only the fixed local endpoint/payload handlers below.

    def grouped(rows, kind):
        result = {}
        for item in rows:
            key = re.sub(r"[^a-z0-9]+", "-", item["group"].lower()).strip("-")
            family = result.setdefault(key, {"key": "bpx-" + key, "brand": "MIIAIVIDEO",
                "name": item["group"], "featured": True,
                "desc": item["description"] or ("MII image model." if kind == "image" else "MII audio model."),
                "caps": {}, "qualities": []})
            quality = {"id": item["slug"], "label": item["label"],
                       "route": "catalog", "outputKind": kind}
            if kind == "image":
                quality["caps"] = _image_ui_caps(item)
            else:
                quality["caps"] = _audio_caps(item)
            family["qualities"].append(quality)
        return list(result.values())

    return {"image_families": grouped(images, "image"),
            "audio_families": grouped(audios, "audio")}
