"""Deterministic, bilingual prompt direction for MII video requests.

This module intentionally performs no network or model calls.  It preserves the
user's scene text and adds only compact, context-dependent production guidance.
"""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ModelProfile:
    """Wording limits which never alter provider parameters."""

    name: str
    detail: int
    max_chars: int = 1800


MODEL_PROFILES = {
    "seedance": ModelProfile("seedance", 2, 1800),
    "seedance25": ModelProfile("seedance25", 4, 2200),
    "wan30": ModelProfile("wan", 1, 1500),
    "kling": ModelProfile("kling", 2, 1800),
    "default": ModelProfile("other", 1, 1600),
}

_CONCEPTS = {
    "camera": r"\b(camera|kamera|shot|bidikan|adegan|pov|handheld|tracking|follow|mengikuti|dolly|push[- ]in|pull[- ]back|pan|tilt|zoom|orbit|locked|static|statis|angle|sudut)\b",
    "shot": r"\b(establishing|wide|full[- ]body|medium(?: close[- ]up)?|mcu|close[- ]up|extreme close[- ]up|insert|detail shot|over[- ]the[- ]shoulder|ots|reaction shot|cutaway)\b",
    "lighting": r"\b(light(?:ing)?|cahaya|pencahayaan|daylight|sunlight|moonlight|shadow|bayangan|exposure|practical lighting|lampu praktis|low[- ]key)\b",
    "grade": r"\b(color|colour|warna|grade|grading|gradasi|palette|palet|saturation|saturasi|contrast|kontras|filmic|monochrome|teal[- ]orange)\b",
    "focus": r"\b(lens|lensa|focus|fokus|depth of field|bokeh|motion blur|focal length|rack focus)\b",
    "dialogue": r"\b(dialogue|dialog|says?|berkata|speaks?|berbicara|whispers?|berbisik|shouts?|berteriak)\b",
}

_PERSON = re.compile(
    r"\b(man|woman|boy|girl|person|character|couple|child|actor|actress|pria|wanita|lelaki|perempuan|anak|orang|karakter|pasangan|aktor|aktris|he|she|they|dia|mereka)\b",
    re.I,
)
_NAMED_PERSON = re.compile(
    r"\b(?:named|bernama|mr\.?|mrs\.?|ms\.?|pak|bu|dr\.?)\s+[A-Z][a-z]{1,}\b"
)
_PROPER_PERSON_ACTION = re.compile(
    r"\b[A-Z][a-z]{1,}\s+(?:walks?|runs?|turns?|looks?|opens?|closes?|sits?|stands?|speaks?|says?|smiles?|enters?|leaves?)\b"
)
_ACTION = re.compile(
    r"\b(walks?|walking|berjalan|runs?|running|berlari|turns?|menoleh|looks?|looking|melihat|reaches?|meraih|touches?|menyentuh|opens?|opening|membuka|closes?|closing|menutup|sits?|sitting|duduk|stands?|standing|berdiri|speaks?|speaking|berbicara|says?|berkata|smiles?|smiling|tersenyum|cries?|menangis|jumps?|melompat|drives?|mengemudi|enters?|masuk|leaves?|exits?|keluar|moves?|bergerak)\b",
    re.I,
)
_SEQUENCE = re.compile(
    r"\b(then|lalu|kemudian|next|after|setelah|before|sebelum|finally|akhirnya|while|sementara|followed by)\b",
    re.I,
)
_REACTION = re.compile(r"\b(reacts?|reaction|hesitates?|pauses?|surprised|shocked|responds?|bereaksi|ragu|berhenti sejenak|terkejut|menanggapi)\b", re.I)
_TIME = {
    "morning": (r"\b(morning|pagi|sunrise)\b", "soft warm morning daylight"),
    "day": (r"\b(daylight|midday|afternoon|siang)\b", "natural daylight"),
    "golden": (r"\b(golden hour|sunset|senja|sore)\b", "soft golden-hour light"),
    "night": (r"\b(night|malam|midnight)\b", "motivated low-light exposure"),
    "neon": (r"\b(neon|city lights?|lampu kota)\b", "motivated neon and practical light"),
    "overcast": (r"\b(overcast|mendung)\b", "soft overcast daylight"),
    "interior": (r"\b(interior|inside|indoors|room|kamar|ruangan|dalam rumah)\b", "motivated practical and environmental bounce light"),
}


def normalize_prompt(prompt):
    """Normalize whitespace and remove exact repeated sentences, not ideas."""
    text = re.sub(r"[\t\r\n ]+", " ", str(prompt or "")).strip()
    parts = re.split(r"(?<=[.!?])\s+", text) if text else []
    unique, seen = [], set()
    for part in parts:
        key = re.sub(r"\W+", " ", part, flags=re.UNICODE).strip().casefold()
        if key and key not in seen:
            unique.append(part.strip())
            seen.add(key)
    return " ".join(unique)


def analyze_prompt_context(prompt, duration=None, references=None):
    lowered = prompt.casefold()
    try:
        seconds = int(duration) if duration is not None else None
    except (TypeError, ValueError):
        seconds = None
    actions = len(_ACTION.findall(prompt))
    sequence = len(_SEQUENCE.findall(prompt))
    clauses = len([p for p in re.split(r"[.!?;]+", prompt) if p.strip()])
    refs = references or {}
    lighting_hint = next((wording for pattern, wording in _TIME.values() if re.search(pattern, lowered)), None)
    return {
        "duration": seconds, "actions": actions, "stages": max(sequence + 1, clauses),
        "has_sequence": sequence > 0, "has_reaction": bool(_REACTION.search(prompt)),
        "has_character": bool(_PERSON.search(prompt) or _NAMED_PERSON.search(prompt) or _PROPER_PERSON_ACTION.search(prompt)),
        "has_reference": any(bool(value) for value in refs.values()),
        "character_reference": bool(refs.get("character") or refs.get("character_images")),
        "lighting_hint": lighting_hint,
        **{f"has_{name}": bool(re.search(pattern, lowered, re.I)) for name, pattern in _CONCEPTS.items()},
    }


def _duration_budget(seconds):
    if seconds is None:
        return 2
    if seconds <= 6:
        return 0
    if seconds <= 10:
        return 1
    if seconds <= 15:
        return 2
    if seconds <= 20:
        return 3
    return 4


def apply_scene_rules(context):
    additions = []
    budget = _duration_budget(context["duration"])
    if context["has_sequence"] or context["stages"] > 1 or context["actions"] >= 3:
        additions.append("Preserve the opening, development, interaction, reaction, and ending in their implied chronological order; complete each action before the next beat.")
    if budget == 0 and (context["actions"] > 1 or context["stages"] > 1):
        additions.append("For this short duration, keep only the essential readable action and reaction; do not add transitions or new beats.")
    elif budget >= 3 and context["actions"] >= 2:
        additions.append("Use the available duration for readable pauses and reactions between the described beats, without inventing story events.")
    return additions


def apply_character_rules(context):
    if not context["has_character"]:
        return []
    return ["Ground the performance in context-appropriate eye direction, micro-expression, gesture, posture, pauses, and reaction timing; do not change personality or add major actions."]


def apply_camera_and_shot_rules(context):
    if context["has_camera"] or context["has_shot"]:
        return []
    budget = _duration_budget(context["duration"])
    if context["has_character"] and context["actions"] >= 2 and budget >= 2:
        return ["Plan only useful coverage: establish spatial context, hold readable medium interaction, then use a closer reaction if earned; vary framing logically without rear-follow repetition or random camera jumps."]
    if context["actions"] >= 2:
        return ["Use a clear medium or wide view with restrained tracking or natural reframing only as needed to follow the action."]
    return ["Use a stable, readable composition with relevant environmental context."]


def apply_lighting_and_grade_rules(context):
    additions = []
    if not context["has_lighting"]:
        source = context["lighting_hint"] or "motivated environmental light"
        additions.append(f"Use {source}, believable exposure, coherent shadows, controlled highlights, and natural skin exposure where applicable.")
    if not context["has_grade"]:
        if context["lighting_hint"] == "motivated low-light exposure":
            grade = "a restrained cool-nocturnal grade"
        elif context["lighting_hint"] in ("soft warm morning daylight", "soft golden-hour light"):
            grade = "a soft warm, natural cinematic grade"
        else:
            grade = "a natural cinematic grade"
        additions.append(f"Use {grade} with neutral skin tones, balanced contrast, restrained saturation, and soft highlight rolloff.")
    return additions


def apply_motion_and_continuity_rules(context):
    additions = []
    if context["actions"]:
        additions.append("Show believable body weight, anticipation, inertia, action completion, and resulting reaction, with natural cloth, hair, and environmental response where relevant.")
    if context["has_character"] or context["actions"] >= 2:
        additions.append("Maintain identity, face, hair, outfit, accessories, props, environment, screen direction, blocking, and lighting across beats; preserve entrances, exits, and physical causality with no teleportation, pose resets, duplication, or disappearing props.")
    if context["has_reference"]:
        wording = ("Preserve the explicitly identified character reference attributes and continuity."
                   if context["character_reference"] else
                   "Preserve relevant supplied visual reference attributes and maintain consistency with supplied references.")
        additions.append(wording)
    return additions


def resolve_conflicts(prompt):
    """Preserve user wording; cross-beat camera changes are not conflicts."""
    return prompt


def apply_model_profile(additions, family, context=None):
    profile = MODEL_PROFILES.get(str(family or "").lower(), MODEL_PROFILES["default"])
    budget = _duration_budget((context or {}).get("duration"))
    # Duration and model profile affect compactness, not the user's content.
    limit = max(2, min(len(additions), profile.detail + budget))
    priorities = ("short duration", "chronological", "explicitly identified character reference",
                  "supplied visual reference", "performance", "body weight", "available duration",
                  "maintain identity", "camera", "light", "grade")
    ranked = sorted(enumerate(additions), key=lambda pair: (next((i for i, key in enumerate(priorities) if key in pair[1].casefold()), len(priorities)), pair[0]))
    chosen = {index for index, _ in ranked[:limit]}
    return [value for index, value in enumerate(additions) if index in chosen], profile


def compress_final_prompt(prompt, additions, profile, max_chars=None):
    sections = {"CHARACTER": [], "CAMERA": [], "LIGHTING/COLOR": [], "CONTINUITY": []}
    seen = set()
    for item in additions:
        key = re.sub(r"\W+", " ", item).casefold()
        if key in seen:
            continue
        seen.add(key)
        low = item.casefold()
        section = "CONTINUITY" if ("maintain" in low or "reference" in low or "chronological" in low or "duration" in low) else "LIGHTING/COLOR" if ("light" in low or "grade" in low) else "CAMERA" if ("camera" in low or "framing" in low or "coverage" in low or "view" in low) else "CHARACTER"
        sections[section].append(item)
    result = "SCENE:\n" + prompt
    ceiling = max(1, int(max_chars or profile.max_chars))
    for heading, items in sections.items():
        if not items:
            continue
        candidate = result + f"\n\n{heading}:\n" + " ".join(items)
        if len(candidate) <= ceiling:
            result = candidate
    return result if len(result) <= ceiling else prompt[:ceiling].rstrip()


def build_final_prompt(original_prompt, *, family="default", duration=None, references=None, max_chars=None):
    """Build a compact model-facing prompt, failing safely at the caller."""
    prompt = normalize_prompt(original_prompt)
    if not prompt:
        return prompt
    # Reference media URLs are transport data, never model-facing prose.
    prompt = re.sub(r"https?://\S+", "", prompt).strip()
    context = analyze_prompt_context(prompt, duration=duration, references=references)
    additions = (apply_scene_rules(context) + apply_character_rules(context) +
                 apply_camera_and_shot_rules(context) + apply_lighting_and_grade_rules(context) +
                 apply_motion_and_continuity_rules(context))
    additions, profile = apply_model_profile(additions, family, context)
    return compress_final_prompt(resolve_conflicts(prompt), additions, profile, max_chars=max_chars)
