"""Reusable catalog for all Remotion graphics templates."""

from __future__ import annotations


# ============================================================
# Template IDs
# ============================================================

# Internal Python IDs.
# Root.tsx converts:
#   audio_visualizer -> audio-visualizer
#   person_card      -> person-card
#   ken_burns        -> ken-burns
#
# Keep these IDs consistent with registry.ts.

TEMPLATE_COMPOSITION_IDS: dict[str, str] = {
    "poem": "poem",
    "hadith": "hadith",
    "quran": "quran",
    "quote": "quote",
    "battle": "battle",
    "map": "map",
    "audio_visualizer": "audio-visualizer",
    "person_card": "person-card",
    "ken_burns": "ken-burns",
    "counter": "counter",
    "karaoke": "karaoke",
}


# Templates which are completely self-contained.
# They don't require an external image/audio asset.
SELF_CONTAINED_TEMPLATES = {
    "poem",
    "hadith",
    "quran",
    "quote",
    "battle",
    "map",
    "person_card",
    "counter",
    "karaoke",
}


# Resource-backed templates.
RESOURCE_TEMPLATES = {
    "audio_visualizer",
    "ken_burns",
}


# Text templates where reading duration is controlled by:
#   totalReadingSeconds
TEXT_READING_TEMPLATES = {
    "poem",
    "hadith",
    "quran",
    "quote",
}


# Karaoke uses its own field.
KARAOKE_TEMPLATE = "karaoke"


ALLOWED_TEMPLATES = set(TEMPLATE_COMPOSITION_IDS)


# LLM sometimes returns README-style names.
TEMPLATE_ALIASES = {
    "islamic_map": "map",
    "islamic-map": "map",
    "map": "map",

    "audio-visualizer": "audio_visualizer",
    "audio_visualizer": "audio_visualizer",

    "person-card": "person_card",
    "person_card": "person_card",

    "ken-burns": "ken_burns",
    "ken_burns": "ken_burns",

    "caption": "karaoke",
    "karaoke": "karaoke",

    "poem": "poem",
    "hadith": "hadith",
    "quran": "quran",
    "quote": "quote",
    "battle": "battle",
    "counter": "counter",
}


def normalize_template_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    key = value.strip().lower()
    return TEMPLATE_ALIASES.get(key)


def composition_id(template: str) -> str:
    """Convert internal template ID to the actual Remotion Composition ID."""
    normalized = normalize_template_id(template)

    if normalized is None:
        raise ValueError(f"Unknown graphic template: {template!r}")

    return TEMPLATE_COMPOSITION_IDS[normalized]


# ============================================================
# Islamic Map catalog
# ============================================================

CITY_CATALOG = {
    "cordoba": (
        "قُرْطُبَة",
        3.3,
        35.6,
        "star",
    ),
    "seville": (
        "إِشْبِيلِيَة",
        3.8,
        40.5,
        "city",
    ),
    "fez": (
        "فَاس",
        11.5,
        31.5,
        "city",
    ),
    "marrakesh": (
        "مَرَّاكُش",
        7.0,
        39.0,
        "star",
    ),
    "kairouan": (
        "القَيْرَوَان",
        30.0,
        42.0,
        "mosque",
    ),
    "alexandria": (
        "الإِسْكَنْدَرِيَّة",
        40.5,
        47.0,
        "city",
    ),
    "cairo": (
        "القَاهِرَة",
        44.0,
        52.0,
        "star",
    ),
    "tripoli": (
        "طَرَابُلُس الغَرْب",
        26.0,
        48.4,
        "city",
    ),
    "aleppo": (
        "حَلَب",
        58.0,
        38.0,
        "city",
    ),
    "damascus": (
        "دِمَشْق",
        57.0,
        43.6,
        "star",
    ),
    "jerusalem": (
        "بَيْتُ المَقْدِس",
        54.8,
        50.2,
        "mosque",
    ),
    "mosul": (
        "المَوْصِل",
        63.5,
        37.5,
        "city",
    ),
    "baghdad": (
        "بَغْدَاد",
        68.3,
        41.1,
        "star",
    ),
    "kufa": (
        "الكُوفَة",
        66.5,
        45.5,
        "city",
    ),
    "basra": (
        "البَصْرَة",
        70.0,
        52.0,
        "city",
    ),
    "isfahan": (
        "أَصْبَهَان",
        76.5,
        40.0,
        "city",
    ),
    "nishapur": (
        "نَيْسَابُور",
        81.5,
        27.0,
        "city",
    ),
    "bukhara": (
        "بُخَارَى",
        85.5,
        22.0,
        "mosque",
    ),
    "samarkand": (
        "سَمَرْقَنْد",
        88.5,
        25.5,
        "star",
    ),
    "medina": (
        "المَدِينَةُ المُنَوَّرَة",
        61.9,
        67.7,
        "mosque",
    ),
    "mecca": (
        "مَكَّة المُكَرَّمَة",
        64.5,
        77.5,
        "kaaba",
    ),
    "sanaa": (
        "صَنْعَاء",
        67.5,
        80.0,
        "city",
    ),
    "poitiers": (
        "بُوَاطِيَة",
        8.5,
        11.2,
        "battle",
    ),
    "constantinople": (
        "القُسْطَنْطِينِيَّة",
        49.5,
        22.0,
        "star",
    ),
}


YEAR_HINTS = {
    "cordoba": "٩٢هـ",
    "fez": "١٩٣هـ",
    "marrakesh": "٤٦٣هـ",
    "kairouan": "٥٠هـ",
    "cairo": "٣٥٨هـ",
    "tripoli": "٢٣هـ",
    "damascus": "١٤هـ",
    "jerusalem": "١٧هـ",
    "baghdad": "١٤٥هـ",
    "kufa": "١٧هـ",
    "basra": "١٤هـ",
    "bukhara": "٢٣٦هـ",
    "poitiers": "١١٤هـ",
    "constantinople": "٨٥٧هـ",
}


def build_cities(ids: list[str]) -> list[dict]:
    out: list[dict] = []

    for cid in ids:
        if cid not in CITY_CATALOG:
            continue

        name, x, y, icon = CITY_CATALOG[cid]

        city = {
            "id": cid,
            "name": name,
            "x": x,
            "y": y,
            "icon": icon,
        }

        if cid in YEAR_HINTS:
            city["year"] = YEAR_HINTS[cid]

        out.append(city)

    return out


def catalog_for_prompt() -> str:
    return "\n".join(
        f"  {cid:16s} — {name} ({icon})"
        for cid, (name, _x, _y, icon) in CITY_CATALOG.items()
    )