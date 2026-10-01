"""LLM graphic planner for the Remotion template library."""

from __future__ import annotations

import json
import re
from typing import Any

from config import GRAPHIC_FPS, GRAPHIC_MAX_DURATION
from models.types import Scene
from pipeline.graphic_catalog import (
    ALLOWED_TEMPLATES,
    CITY_CATALOG,
    KARAOKE_TEMPLATE,
    RESOURCE_TEMPLATES,
    SELF_CONTAINED_TEMPLATES,
    TEXT_READING_TEMPLATES,
    build_cities,
    catalog_for_prompt,
    normalize_template_id,
)
from config import MODEL_ORCHESTRATOR
from utils.llm_client import chat
from utils.logger import log


# ============================================================
# LLM prompt
# ============================================================

_SYSTEM = r"""
You are the graphic designer for an Arabic historical / Islamic documentary.

Your job is NOT to rewrite the narration.

Your job:
1. Pick the best Remotion template.
2. Fill only the props that belong to that template.
3. Preserve source Arabic exactly whenever the scene contains quoted,
   Quranic, hadith, poetic, or speaker text.
4. Never invent historical facts.
5. Never invent dates, locations, people, sources, or battle outcomes.
6. When a fact is unknown, use an empty string or null.

AVAILABLE TEMPLATES

1. poem
   Classical Arabic poetry.
   Best for شعر, بيت شعر, two hemistichs.

   Props:
   poemLines: [{text1, text2}]
   footerLabel: string

2. hadith
   Hadith with isnad + matn.

   Props:
   topLabel: string
   isnad: string
   matnPlain: string
   source: string
   wrapInGuillemets: boolean

3. quran
   Quran ayahs.

   Props:
   basmala: string
   surahName: string
   verses: [{text, number}]

   IMPORTANT:
   Do not invent ayah numbers.
   Only use verse numbering supplied by the scene/context.

4. quote
   Scholar / historical figure quote.

   Props:
   topLabel: string
   speaker: string
   quotePlain: string
   source: string

5. battle
   Battle / war / conquest graphic.

   Props:
   hijriDate: string
   miladiDate: string
   battleName: string
   side1: {name, detail}
   side2: {name, detail}
   outcome: string
   source: string

6. map
   Islamic geography / journey / city / campaign route.

   Props:
   title: string
   subtitle: string
   footer: string
   cities: [catalog_id, ...]
   spotlight:
     {cityId, label} | null
   journey:
     {path, label} | null

   Only use city IDs from the catalog below.

7. person_card
   Historical person introduction.

   Props:
   portraitSrc: string | null
   name: string
   honorific: string
   title: string
   birthYear: string
   deathYear: string
   birthPlace: string
   deathPlace: string
   footerLabel: string

   Never invent a portrait.

8. counter
   Statistics / explicit numerical facts.

   Props:
   value: number
   prefix: string
   suffix: string
   label: string
   subLabel: string
   topLabel: string | null
   numberFormat: "arabic" | "western"
   thousandsSeparator: "," | "٬" | ""

   Only use this when a clear numerical fact exists.

9. karaoke
   Word-by-word Arabic captions.

   Props:
   background: string | null
   theme: "parchment" | "crimson" | "andalusian" | "night"
   style: "underline" | "rise" | "pop" | "blurFocus" | "dualTone" | "wave"
   text: string
   header: string | null

   Use auto timing.
   Do not create manual timestamps.

10. audio_visualizer
    Audio-reactive bars / waveform.

    ONLY select when AUDIO_SRC_AVAILABLE is true.

    Props:
    audioSrc: string
    background: string
    mode: "spectrum" | "waveform"
    title: {speaker, subtitle} | null

11. ken_burns
    Slow cinematic motion over a still image.

    ONLY select when IMAGE_SRC_AVAILABLE is true.

    Props:
    imageSrc: string
    motion:
      zoom-in | zoom-out |
      pan-left | pan-right | pan-up | pan-down |
      diagonal-tl | diagonal-tr | diagonal-bl | diagonal-br

    caption: {line1, line2?} | null
    source: string | null


TEMPLATE SELECTION RULES

Use quran when content_type == "quran".

Use hadith when content_type == "hadith".

Use poem when content_type == "poetry" and the text is clearly poetic.

Use karaoke for dua or short spoken Arabic where word-by-word emphasis
is useful and the scene is not better represented by hadith/quran/poetry.

Use battle when the scene clearly describes a named battle,
war, conquest, army clash, or military campaign.

Use map when geography is the visual subject:
cities, journeys, routes, migration, campaigns across regions,
territorial spread, locating a historical event.

Use person_card when the scene primarily introduces ONE historical person.

Use counter when a concrete number is the visual point:
population, years, number of books, number of hadith, distance, casualties,
army size, etc.

Use quote when a scholar / ruler / historical figure is directly quoted.

Use audio_visualizer only when AUDIO_SRC_AVAILABLE == true.

Use ken_burns only when IMAGE_SRC_AVAILABLE == true.

When multiple templates could work, prefer the template that communicates
the scene's actual information most directly.

Do not use a graphic just because the scene contains Arabic.
Generic narrative / descriptive scenes should remain image scenes.

OUTPUT JSON ONLY:

{
  "template": "template_id",
  "props": {}
}
"""


# ============================================================
# Public API
# ============================================================

def plan_graphic(
    scene: Scene,
    context: dict | None = None,
    *,
    image_src: str | None = None,
    audio_src: str | None = None,
) -> dict | None:
    """
    Plan one graphic scene.

    Duration ALWAYS comes from scene.start/end.
    The LLM never controls the duration.
    """

    duration = scene.end - scene.start

    if duration <= 0:
        log.warn(
            f"Scene {scene.id}: invalid duration {duration}"
        )
        return None

    if duration > GRAPHIC_MAX_DURATION:
        log.warn(
            f"Scene {scene.id}: graphic duration "
            f"{duration:.2f}s exceeds "
            f"GRAPHIC_MAX_DURATION={GRAPHIC_MAX_DURATION:.2f}s"
        )
        return None

    user = _build_user_prompt(
        scene,
        context,
        image_src=image_src,
        audio_src=audio_src,
        duration=duration,
    )

    try:
        result = chat(
            MODEL_ORCHESTRATOR,
            [
                {
                    "role": "system",
                    "content": _SYSTEM,
                },
                {
                    "role": "user",
                    "content": user,
                },
            ],
            label=f"Graphic Planner [Scene {scene.id}]",
        )

        raw = result.get(
            "message",
            {},
        ).get(
            "content",
            "",
        )

        plan = _parse_and_validate(
            raw,
            scene,
            duration=duration,
            image_src=image_src,
            audio_src=audio_src,
        )

        if plan:
            log.ok(
                f"Scene {scene.id}: "
                f"graphic → {plan['template']} "
                f"({duration:.2f}s / "
                f"{round(duration * GRAPHIC_FPS)}f)"
            )
            return plan

    except Exception as exc:
        log.warn(
            f"Scene {scene.id}: "
            f"graphic planner failed ({exc})"
        )

    fallback = _fallback_plan(
        scene,
        duration=duration,
        image_src=image_src,
        audio_src=audio_src,
    )

    if fallback:
        log.ok(
            f"Scene {scene.id}: "
            f"graphic fallback → "
            f"{fallback['template']}"
        )

    return fallback

# ============================================================
# Prompt builder
# ============================================================

def _build_user_prompt(
    scene: Scene,
    context: dict | None,
    *,
    image_src: str | None,
    audio_src: str | None,
    duration: float,
) -> str:

    parts = [
        f"SCENE ID: {scene.id}",
        f"SCENE DURATION: {duration:.3f} seconds",
        "",
        f"CONTENT TYPE: {scene.content_type}",
        f"TRANSCRIPT (VERBATIM): {scene.text}",
        f"ARABIC SEARCH QUERY: {scene.arabic_query}",
        f"ENGLISH SEARCH QUERY: {scene.english_query}",
        "",
        f"IMAGE_SRC_AVAILABLE: {'true' if image_src else 'false'}",
        f"AUDIO_SRC_AVAILABLE: {'true' if audio_src else 'false'}",
    ]

    if context:
        parts.extend(
            [
                "",
                "GLOBAL CONTEXT:",
                json.dumps(
                    context,
                    ensure_ascii=False,
                    indent=2,
                ),
            ]
        )

    parts.extend(
        [
            "",
            "CITY CATALOG:",
            catalog_for_prompt(),
            "",
            "Return JSON only.",
        ]
    )

    return "\n".join(parts)


# ============================================================
# Validation
# ============================================================

def _parse_and_validate(
    raw: Any,
    scene: Scene,
    *,
    duration: float,
    image_src: str | None,
    audio_src: str | None,
) -> dict | None:

    if isinstance(raw, str):
        raw = _extract_json(raw)

    if not isinstance(raw, dict):
        return None

    template = normalize_template_id(raw.get("template"))

    if template not in ALLOWED_TEMPLATES:
        return None

    # Respect resource requirements.
    if template == "audio_visualizer" and not audio_src:
        return None

    if template == "ken_burns" and not image_src:
        return None

    props = raw.get("props")

    if not isinstance(props, dict):
        props = {}

    clean = _normalize_props(
        template,
        props,
        scene=scene,
        duration=duration,
        image_src=image_src,
        audio_src=audio_src,
    )

    if clean is None:
        return None

    return {
        "template": template,
        "props": clean,
        "duration_seconds": round(duration, 3),
        "duration_frames": max(1, round(duration * GRAPHIC_FPS)),
    }


# ============================================================
# Template-specific prop normalization
# ============================================================

def _normalize_props(
    template: str,
    props: dict,
    *,
    scene: Scene,
    duration: float,
    image_src: str | None,
    audio_src: str | None,
) -> dict | None:

    duration_frames = max(1, round(duration * GRAPHIC_FPS))

    # --------------------------------------------------------
    # POEM
    # --------------------------------------------------------
    if template == "poem":
        lines = _normalize_poem_lines(
            props.get("poemLines"),
            fallback_text=scene.text,
        )

        if not lines:
            return None

        return {
            "poemLines": lines,
            "footerLabel": _safe_str(props.get("footerLabel")),
            "totalReadingSeconds": duration,
            "fps": GRAPHIC_FPS,
        }

    # --------------------------------------------------------
    # HADITH
    # --------------------------------------------------------
    if template == "hadith":
        matn = _safe_str(props.get("matnPlain")) or scene.text

        if not matn:
            return None

        isnad = _safe_str(props.get("isnad"))

        return {
            "topLabel": _safe_str(props.get("topLabel")) or "حَـدِيـث",
            "isnad": isnad,
            "matnPlain": matn,
            "source": _safe_str(props.get("source")),
            "wrapInGuillemets": True,
            "fps": GRAPHIC_FPS,
            "totalReadingSeconds": duration,
            "isnadDuration": min(60, max(20, round(duration_frames * 0.18))),
        }

    # --------------------------------------------------------
    # QURAN
    # --------------------------------------------------------
    if template == "quran":
        verses = _normalize_verses(props.get("verses"))

        if not verses:
            return None

        return {
            "basmala": (
                _safe_str(props.get("basmala"))
                or "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"
            ),
            "surahName": _safe_str(props.get("surahName")),
            "verses": verses,
            "fps": GRAPHIC_FPS,
            "totalReadingSeconds": duration,
        }

    # --------------------------------------------------------
    # QUOTE
    # --------------------------------------------------------
    if template == "quote":
        quote = _safe_str(props.get("quotePlain")) or scene.text

        if not quote:
            return None

        return {
            "topLabel": _safe_str(props.get("topLabel")) or "اقْـتِـبَـاس",
            "speaker": _safe_str(props.get("speaker")),
            "quotePlain": quote,
            "source": _safe_str(props.get("source")),
            "fps": GRAPHIC_FPS,
            "totalReadingSeconds": duration,
            "speakerDuration": min(
                55,
                max(20, round(duration_frames * 0.18)),
            ),
        }

    # --------------------------------------------------------
    # BATTLE
    # --------------------------------------------------------
    if template == "battle":
        return {
            "hijriDate": _safe_str(props.get("hijriDate")),
            "miladiDate": _safe_str(props.get("miladiDate")),
            "battleName": (
                _safe_str(props.get("battleName"))
                or _safe_str(scene.arabic_query)
                or "مَعْرَكَة"
            ),
            "side1": {
                "name": _safe_nested_str(
                    props.get("side1"),
                    "name",
                ),
                "detail": _safe_nested_str(
                    props.get("side1"),
                    "detail",
                ),
            },
            "side2": {
                "name": _safe_nested_str(
                    props.get("side2"),
                    "name",
                ),
                "detail": _safe_nested_str(
                    props.get("side2"),
                    "detail",
                ),
            },
            "outcome": _safe_str(props.get("outcome")),
            "source": _safe_str(props.get("source")),
        }

    # --------------------------------------------------------
    # MAP
    # --------------------------------------------------------
    if template == "map":
        city_ids = _valid_city_ids(props.get("cities"))

        if not city_ids:
            city_ids = _cities_from_scene(scene)

        if not city_ids:
            return None

        city_ids = list(dict.fromkeys(city_ids))[:12]

        out: dict[str, Any] = {
            "title": (
                _safe_str(props.get("title"))
                or "دِيَارُ الإِسْلَام"
            ),
            "subtitle": _safe_str(props.get("subtitle")),
            "footer": _safe_str(props.get("footer")),
            "cities": build_cities(city_ids),
        }

        spotlight = props.get("spotlight")

        if isinstance(spotlight, dict):
            city_id = spotlight.get("cityId")

            if city_id in city_ids:
                out["spotlight"] = {
                    "cityId": city_id,
                    "startFrame": min(
                        60,
                        max(20, round(duration_frames * 0.20)),
                    ),
                    "label": (
                        _safe_str(spotlight.get("label"))
                        or "هُنَا"
                    ),
                }
            else:
                out["spotlight"] = None
        else:
            out["spotlight"] = None

        journey = props.get("journey")

        if isinstance(journey, dict):
            path = [
                cid
                for cid in journey.get("path", [])
                if cid in city_ids
            ]

            if len(path) >= 2:
                start_frame = min(
                    60,
                    max(20, round(duration_frames * 0.20)),
                )

                remaining = max(30, duration_frames - start_frame - 15)

                out["journey"] = {
                    "path": path,
                    "startFrame": start_frame,
                    "drawDuration": min(120, remaining),
                    "color": (
                        _safe_str(journey.get("color"))
                        or "rgba(232,200,116,0.9)"
                    ),
                    "label": (
                        _safe_str(journey.get("label"))
                        or None
                    ),
                }
            else:
                out["journey"] = None
        else:
            out["journey"] = None

        return out

    # --------------------------------------------------------
    # PERSON CARD
    # --------------------------------------------------------
    if template == "person_card":
        name = _safe_str(props.get("name"))

        if not name:
            return None

        return {
            "portraitSrc": None,
            "name": name,
            "honorific": _safe_str(props.get("honorific")),
            "title": _safe_str(props.get("title")),
            "birthYear": _safe_str(props.get("birthYear")),
            "deathYear": _safe_str(props.get("deathYear")),
            "birthPlace": _safe_str(props.get("birthPlace")),
            "deathPlace": _safe_str(props.get("deathPlace")),
            "footerLabel": _safe_str(props.get("footerLabel")),
        }

    # --------------------------------------------------------
    # COUNTER
    # --------------------------------------------------------
    if template == "counter":
        value = _extract_number(props.get("value"))

        if value is None:
            value = _extract_number(scene.text)

        if value is None:
            return None

        count_duration = max(
            30,
            round(duration_frames * 0.55),
        )

        reveal_start = min(
            40,
            max(0, round(duration_frames * 0.12)),
        )

        return {
            "value": value,
            "prefix": _safe_str(props.get("prefix")),
            "suffix": _safe_str(props.get("suffix")),
            "label": _safe_str(props.get("label")),
            "subLabel": _safe_str(props.get("subLabel")),
            "numberFormat": (
                props.get("numberFormat")
                if props.get("numberFormat")
                in {"arabic", "western"}
                else "arabic"
            ),
            "thousandsSeparator": (
                props.get("thousandsSeparator")
                if props.get("thousandsSeparator")
                in {",", "٬", ""}
                else "٬"
            ),
            "topLabel": (
                _safe_str(props.get("topLabel"))
                if props.get("topLabel") is not None
                else None
            ),
            "curve": (
                props.get("curve")
                if props.get("curve")
                in {"linear", "easeOut", "easeInOut"}
                else "easeOut"
            ),
            "revealStart": reveal_start,
            "countDuration": min(
                count_duration,
                max(1, duration_frames - reveal_start - 1),
            ),
            "labelDelay": min(
                duration_frames - 1,
                reveal_start + count_duration + 10,
            ),
            "subLabelDelay": min(
                duration_frames - 1,
                reveal_start + count_duration + 30,
            ),
            "fps": GRAPHIC_FPS,
        }

    # --------------------------------------------------------
    # KARAOKE
    # --------------------------------------------------------
    if template == KARAOKE_TEMPLATE:
        text = _safe_str(props.get("text")) or scene.text

        if not text:
            return None

        return {
            "background": (
                props.get("background")
                if props.get("background") is not None
                else "poem-bg.jpeg"
            ),
            "theme": (
                props.get("theme")
                if props.get("theme")
                in {"parchment", "crimson", "andalusian", "night"}
                else "parchment"
            ),
            "style": (
                props.get("style")
                if props.get("style")
                in {
                    "underline",
                    "rise",
                    "pop",
                    "blurFocus",
                    "dualTone",
                    "wave",
                }
                else "pop"
            ),
            "text": text,
            "timing": "auto",
            "readingSeconds": duration,
            "activeDurationSeconds": max(
                0.2,
                min(
                    0.8,
                    duration / max(1, len(text.split())) * 1.25,
                ),
            ),
            "header": (
                _safe_str(props.get("header"))
                if props.get("header") is not None
                else None
            ),
        }

    # --------------------------------------------------------
    # AUDIO VISUALIZER
    # --------------------------------------------------------
    if template == "audio_visualizer":
        if not audio_src:
            return None

        title = props.get("title")

        clean_title = None

        if isinstance(title, dict):
            clean_title = {
                "speaker": _safe_str(title.get("speaker")),
                "subtitle": _safe_str(title.get("subtitle")),
            }

        return {
            "audioSrc": audio_src,
            "background": (
                _safe_str(props.get("background"))
                or "poem-bg.jpeg"
            ),
            "mode": (
                props.get("mode")
                if props.get("mode")
                in {"spectrum", "waveform"}
                else "waveform"
            ),
            "title": clean_title,
        }

    # --------------------------------------------------------
    # KEN BURNS
    # --------------------------------------------------------
    if template == "ken_burns":
        if not image_src:
            return None

        motion = props.get("motion")

        valid_motions = {
            "zoom-in",
            "zoom-out",
            "pan-left",
            "pan-right",
            "pan-up",
            "pan-down",
            "diagonal-tl",
            "diagonal-tr",
            "diagonal-bl",
            "diagonal-br",
        }

        if motion not in valid_motions:
            motion = "zoom-in"

        caption = props.get("caption")

        clean_caption = None

        if isinstance(caption, dict):
            line1 = _safe_str(caption.get("line1"))

            if line1:
                clean_caption = {
                    "line1": line1,
                    "line2": _safe_str(caption.get("line2")),
                }

        return {
            "imageSrc": image_src,
            "motion": motion,
            "startScale": 1.0,
            "endScale": 1.18,
            "panAmount": 4,
            "caption": clean_caption,
            "source": (
                _safe_str(props.get("source"))
                if props.get("source") is not None
                else None
            ),
        }

    return None


# ============================================================
# Fallback planner
# ============================================================

def _fallback_plan(
    scene: Scene,
    *,
    duration: float,
    image_src: str | None,
    audio_src: str | None,
) -> dict | None:

    content_type = (
        (scene.content_type or "narration")
        .strip()
        .lower()
    )

    if content_type == "hadith":
        return {
            "template": "hadith",
            "props": {
                "topLabel": "حَـدِيـث",
                "isnad": "",
                "matnPlain": scene.text,
                "source": "",
                "wrapInGuillemets": True,
                "fps": GRAPHIC_FPS,
                "totalReadingSeconds": duration,
                "isnadDuration": min(
                    60,
                    max(
                        20,
                        round(duration * GRAPHIC_FPS * 0.18),
                    ),
                ),
            },
            "duration_seconds": duration,
            "duration_frames": round(duration * GRAPHIC_FPS),
        }

    if content_type == "poetry":
        lines = _normalize_poem_lines(
            None,
            fallback_text=scene.text,
        )

        if lines:
            return {
                "template": "poem",
                "props": {
                    "poemLines": lines,
                    "footerLabel": "",
                    "fps": GRAPHIC_FPS,
                    "totalReadingSeconds": duration,
                },
                "duration_seconds": duration,
                "duration_frames": round(duration * GRAPHIC_FPS),
            }

    if content_type == "quran":
        verses = _normalize_verses(None)

        # Only use a fallback Quran scene when the planner can safely
        # treat the entire scene as one verse. Do not invent numbering.
        if scene.text and len(scene.text.split()) <= 18:
            verses = [{"text": scene.text.strip(), "number": 1}]

        if verses:
            return {
                "template": "quran",
                "props": {
                    "basmala": "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
                    "surahName": "",
                    "verses": verses,
                    "fps": GRAPHIC_FPS,
                    "totalReadingSeconds": duration,
                },
                "duration_seconds": duration,
                "duration_frames": round(duration * GRAPHIC_FPS),
            }

    if content_type == "dua":
        return {
            "template": "karaoke",
            "props": {
                "background": "poem-bg.jpeg",
                "theme": "night",
                "style": "wave",
                "text": scene.text,
                "timing": "auto",
                "readingSeconds": duration,
                "activeDurationSeconds": 0.45,
                "header": None,
            },
            "duration_seconds": duration,
            "duration_frames": round(duration * GRAPHIC_FPS),
        }

    # Geography fallback.
    city_ids = _cities_from_scene(scene)

    if city_ids:
        return {
            "template": "map",
            "props": {
                "title": scene.arabic_query[:40] or "دِيَارُ الإِسْلَام",
                "subtitle": "",
                "footer": "",
                "cities": build_cities(city_ids),
                "spotlight": (
                    {
                        "cityId": city_ids[0],
                        "startFrame": 45,
                        "label": "هُنَا",
                    }
                    if len(city_ids) == 1
                    else None
                ),
                "journey": None,
            },
            "duration_seconds": duration,
            "duration_frames": round(duration * GRAPHIC_FPS),
        }

    # Explicit number fallback.
    number = _extract_number(scene.text)

    if number is not None:
        return {
            "template": "counter",
            "props": {
                "value": number,
                "prefix": "",
                "suffix": "",
                "label": scene.arabic_query[:60] or "",
                "subLabel": "",
                "numberFormat": "arabic",
                "thousandsSeparator": "٬",
                "topLabel": None,
                "curve": "easeOut",
                "revealStart": 20,
                "countDuration": min(
                    round(duration * GRAPHIC_FPS * 0.55),
                    round(duration * GRAPHIC_FPS) - 21,
                ),
                "fps": GRAPHIC_FPS,
            },
            "duration_seconds": duration,
            "duration_frames": round(duration * GRAPHIC_FPS),
        }

    # Generic quote fallback.
    if scene.text:
        return {
            "template": "quote",
            "props": {
                "topLabel": "اقْـتِـبَـاس",
                "speaker": "",
                "quotePlain": scene.text,
                "source": "",
                "fps": GRAPHIC_FPS,
                "totalReadingSeconds": duration,
                "speakerDuration": min(
                    55,
                    max(
                        20,
                        round(duration * GRAPHIC_FPS * 0.18),
                    ),
                ),
            },
            "duration_seconds": duration,
            "duration_frames": round(duration * GRAPHIC_FPS),
        }

    return None


# ============================================================
# Helpers
# ============================================================

def _safe_str(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _safe_nested_str(value: object, key: str) -> str:
    if not isinstance(value, dict):
        return ""
    return _safe_str(value.get(key))


def _extract_json(value: str) -> dict | None:
    text = value.strip()

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(
        r"\{.*\}",
        text,
        flags=re.DOTALL,
    )

    if not match:
        return None

    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _valid_city_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    result = []

    for item in value:
        if isinstance(item, str) and item in CITY_CATALOG:
            result.append(item)

    return list(dict.fromkeys(result))


def _cities_from_scene(scene: Scene) -> list[str]:
    text = " ".join(
        [
            scene.text or "",
            scene.arabic_query or "",
            scene.english_query or "",
        ]
    ).lower()

    keyword_map = {
        "بغداد": "baghdad",
        "baghdad": "baghdad",

        "دمشق": "damascus",
        "damascus": "damascus",

        "مكة": "mecca",
        "mecca": "mecca",

        "المدينة": "medina",
        "medina": "medina",

        "القاهرة": "cairo",
        "cairo": "cairo",

        "قرطبة": "cordoba",
        "cordoba": "cordoba",

        "الأندلس": "cordoba",
        "andalus": "cordoba",

        "فاس": "fez",
        "fez": "fez",

        "بخارى": "bukhara",
        "bukhara": "bukhara",

        "سمرقند": "samarkand",
        "samarkand": "samarkand",

        "القدس": "jerusalem",
        "بيت المقدس": "jerusalem",
        "jerusalem": "jerusalem",

        "حلب": "aleppo",
        "aleppo": "aleppo",

        "القسطنطينية": "constantinople",
        "constantinople": "constantinople",

        "بلاط الشهداء": "poitiers",
        "poitiers": "poitiers",
    }

    hits = []

    for keyword, city in keyword_map.items():
        if keyword in text:
            hits.append(city)

    return list(dict.fromkeys(hits))[:12]


def _normalize_poem_lines(
    value: object,
    *,
    fallback_text: str,
) -> list[dict]:
    if isinstance(value, list):
        clean = []

        for item in value:
            if not isinstance(item, dict):
                continue

            text1 = _safe_str(item.get("text1"))
            text2 = _safe_str(item.get("text2"))

            if text1 and text2:
                clean.append(
                    {
                        "text1": text1,
                        "text2": text2,
                    }
                )

        if clean:
            return clean

    lines = [
        line.strip()
        for line in fallback_text.splitlines()
        if line.strip()
    ]

    # Strip timestamp prefixes if the scene text retained them.
    lines = [
        re.sub(
            r"^\[\d+\.?\d*–\d+\.?\d*\]\s*",
            "",
            line,
        )
        for line in lines
    ]

    result = []

    for line in lines:
        if "|" in line:
            left, right = line.split("|", 1)

            if left.strip() and right.strip():
                result.append(
                    {
                        "text1": left.strip(),
                        "text2": right.strip(),
                    }
                )

    if result:
        return result

    # Sequential lines can represent hemistich pairs.
    if len(lines) >= 2 and len(lines) % 2 == 0:
        for i in range(0, len(lines), 2):
            result.append(
                {
                    "text1": lines[i],
                    "text2": lines[i + 1],
                }
            )

    return result


def _normalize_verses(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []

    clean = []

    for item in value:
        if not isinstance(item, dict):
            continue

        text = _safe_str(item.get("text"))
        number = item.get("number")

        if not text:
            continue

        if isinstance(number, bool):
            continue

        try:
            number = int(number)
        except (TypeError, ValueError):
            continue

        if number <= 0:
            continue

        clean.append(
            {
                "text": text,
                "number": number,
            }
        )

    return clean


def _extract_number(value: object) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return int(value)

    if not isinstance(value, str):
        return None

    text = value.strip()

    # Eastern Arabic digits → Western.
    translation = str.maketrans(
        "٠١٢٣٤٥٦٧٨٩",
        "0123456789",
    )
    text = text.translate(translation)

    # Arabic thousands separator / commas.
    text = (
        text
        .replace("٬", "")
        .replace(",", "")
        .replace("_", "")
        .replace(" ", "")
    )

    match = re.search(r"-?\d+", text)

    if not match:
        return None

    try:
        return int(match.group(0))
    except ValueError:
        return None