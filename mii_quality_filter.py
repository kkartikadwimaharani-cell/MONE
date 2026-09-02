"""Deterministic prompt preprocessing for MII BudgetPixel video requests.

The filter deliberately uses only local text rules.  It adds restrained direction
where the user was silent and leaves explicit creative choices in control.
"""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ModelProfile:
    """Wording limits that can be tuned without changing provider contracts."""

    name: str
    max_additions: int = 4
    max_chars: int = 1800


MODEL_PROFILES = {
    "seedance": ModelProfile("seedance", max_additions=4),
    "seedance25": ModelProfile("seedance", max_additions=4),
    "wan30": ModelProfile("wan", max_additions=3),
    "kling": ModelProfile("kling", max_additions=4),
    "default": ModelProfile("other", max_additions=3),
}


_CONCEPTS = {
    "camera": r"\b(camera|shot|pov|handheld|tracking|follow|dolly|push[- ]in|pull[- ]back|pan|tilt|zoom|orbit|locked|static|angle)\b",
    "shot": r"\b(wide|full[- ]body|medium|close[- ]up|extreme close|insert|detail shot|over[- ]the[- ]shoulder|reaction shot|cutaway|establishing)\b",
    "lighting": r"\b(light(?:ing)?|daylight|sunlight|moonlight|sunset|sunrise|morning|midday|midnight|night|overcast|neon|shadow|exposure)\b",
    "grade": r"\b(color|colour|grade|grading|palette|saturation|contrast|filmic|monochrome|black and white|teal[- ]orange)\b",
    "focus": r"\b(lens|focus|depth of field|bokeh|motion blur|focal length|rack focus)\b",
    "style": r"\b(style|anime|documentary|cinematic|commercial|realistic|surreal|stop[- ]motion|noir|vintage)\b",
    "audio": r"\b(audio|sound|music|silent|mute|dialogue|dialog|says|whispers|shouts|voice)\b",
}

_CHARACTER_WORDS = re.compile(
    r"\b(man|woman|boy|girl|person|character|couple|child|actor|actress|he|she|they|[A-Z][a-z]{2,})\b"
)
_ACTION_WORDS = re.compile(
    r"\b(walks?|runs?|turns?|looks?|reaches?|touches?|opens?|closes?|sits?|stands?|speaks?|says|smiles?|cries|jumps?|drives?|enters?|leaves?|moves?)\b",
    re.I,
)
_SEQUENCE_WORDS = re.compile(r"\b(then|next|after|before|finally|while|as soon as|followed by)\b", re.I)


def normalize_prompt(prompt):
    """Normalize formatting and remove exact repeated beats without paraphrasing."""
    text = re.sub(r"[\t\r\n ]+", " ", str(prompt or "")).strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    unique, seen = [], set()
    for part in parts:
        key = re.sub(r"\W+", " ", part).strip().casefold()
        if key and key not in seen:
            unique.append(part.strip())
            seen.add(key)
    return " ".join(unique)


def analyze_prompt_context(prompt, duration=None, references=None):
    """Return conservative signals; absence of a signal permits an enhancement."""
    lowered = prompt.casefold()
    try:
        seconds = int(duration) if duration is not None else None
    except (TypeError, ValueError):
        seconds = None
    actions = len(_ACTION_WORDS.findall(prompt))
    stages = len(_SEQUENCE_WORDS.findall(prompt)) + max(0, len(re.findall(r"[.!?]", prompt)) - 1)
    refs = references or {}
    return {
        "duration": seconds,
        "actions": actions,
        "stages": stages,
        "has_character": bool(_CHARACTER_WORDS.search(prompt)),
        "has_sequence": bool(_SEQUENCE_WORDS.search(prompt)),
        "has_reference": any(bool(value) for value in refs.values()),
        **{f"has_{name}": bool(re.search(pattern, lowered, re.I)) for name, pattern in _CONCEPTS.items()},
    }


def apply_scene_rules(context):
    additions = []
    if context["stages"] > 0 or context["actions"] >= 3:
        additions.append("Keep the implied beats in chronological order; complete each action before its reaction and the next beat.")
    if context["duration"] and context["duration"] <= 6 and context["actions"] >= 4:
        additions.append("Prioritize the essential readable beats within the short duration rather than adding transitions or extra actions.")
    return additions


def apply_character_rules(context):
    if not context["has_character"]:
        return []
    return ["Use natural posture, eye movement, small gestures, and reactions appropriate to the described action, without adding new character actions."]


def apply_camera_and_shot_rules(context):
    additions = []
    if not context["has_camera"] and not context["has_shot"]:
        if context["actions"] >= 2:
            additions.append("Frame the action clearly in a contextual medium or wide shot with subtle natural reframing; avoid robotic movement or unnecessary orbiting.")
        else:
            additions.append("Use a stable, readable composition that keeps the main subject and relevant environment clear.")
    if not context["has_focus"] and context["has_character"]:
        additions.append("Keep focus naturally on the acting subject, with believable depth and restrained motion blur.")
    return additions


def apply_lighting_and_grade_rules(context):
    additions = []
    if not context["has_lighting"]:
        additions.append("Use motivated environmental light with believable exposure, coherent shadows, and natural skin exposure.")
    if not context["has_grade"]:
        additions.append("Keep the color grade natural and restrained, with balanced contrast and soft highlight rolloff.")
    return additions


def apply_motion_and_continuity_rules(context):
    additions = []
    if context["actions"]:
        additions.append("Motion has realistic body weight, anticipation, completion, and an appropriate reaction.")
    if context["has_character"]:
        continuity = "Maintain the same identity, appearance, outfit, and coherent screen position; no unexplained duplication, teleportation, or pose reset."
        if context["has_reference"]:
            continuity = "Preserve the referenced character identity and appearance; maintain coherent screen position with no unexplained duplication, teleportation, or pose reset."
        additions.append(continuity)
    return additions


def resolve_conflicts(prompt):
    """Resolve only unmistakable opposing camera directives; latest wins."""
    clauses = re.split(r"(?<=[,;])\s+|\s+but\s+|\s+then\s+", prompt, flags=re.I)
    camera_modes = []
    for index, clause in enumerate(clauses):
        if re.search(r"\b(static|locked)\b", clause, re.I):
            camera_modes.append((index, "static"))
        if re.search(r"\b(orbit|circl\w* around|tracking|dolly|pan|tilt|push[- ]in|pull[- ]back)\b", clause, re.I):
            camera_modes.append((index, "moving"))
    if len({mode for _, mode in camera_modes}) < 2:
        return prompt
    last_index, last_mode = camera_modes[-1]
    kept = []
    for index, clause in enumerate(clauses):
        opposing = (last_mode == "static" and re.search(r"\b(orbit|circl\w* around|tracking|dolly|pan|tilt|push[- ]in|pull[- ]back)\b", clause, re.I))
        opposing = opposing or (last_mode == "moving" and re.search(r"\b(static|locked)\b", clause, re.I))
        if index == last_index or not opposing:
            kept.append(clause.strip())
    return ", ".join(filter(None, kept))


def apply_model_profile(additions, family):
    profile = MODEL_PROFILES.get(str(family or "").lower(), MODEL_PROFILES["default"])
    # Continuity and temporal readability carry more value than decorative
    # direction when a terse model profile requires us to choose.
    def priority(item):
        lowered = item.casefold()
        if "same identity" in lowered or "referenced character identity" in lowered:
            return 0
        if "short duration" in lowered:
            return 1
        return 2

    ranked = sorted(enumerate(additions), key=lambda item: (priority(item[1]), item[0]))
    selected_indexes = {index for index, _ in ranked[:profile.max_additions]}
    return [item for index, item in enumerate(additions) if index in selected_indexes], profile


def compress_final_prompt(prompt, additions, profile):
    """Deduplicate directions and enforce a profile-level verbosity ceiling."""
    compact, seen = [], set()
    for addition in additions:
        key = re.sub(r"\W+", " ", addition).casefold()
        if key not in seen and key not in prompt.casefold():
            compact.append(addition)
            seen.add(key)
    result = prompt
    for addition in compact:
        candidate = f"{result} Direction: {addition}"
        if len(candidate) > profile.max_chars:
            break
        result = candidate
    return result


def build_final_prompt(original_prompt, *, family="default", duration=None, references=None):
    """Run the MII Quality Filter and return the model-facing video prompt."""
    prompt = normalize_prompt(original_prompt)
    if not prompt:
        return prompt
    context = analyze_prompt_context(prompt, duration=duration, references=references)
    additions = []
    additions.extend(apply_scene_rules(context))
    additions.extend(apply_character_rules(context))
    additions.extend(apply_camera_and_shot_rules(context))
    additions.extend(apply_lighting_and_grade_rules(context))
    additions.extend(apply_motion_and_continuity_rules(context))
    prompt = resolve_conflicts(prompt)
    additions, profile = apply_model_profile(additions, family)
    return compress_final_prompt(prompt, additions, profile)
