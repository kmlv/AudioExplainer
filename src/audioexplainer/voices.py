"""Voice catalog: aliases, recommended voices, and dialogue pairings.

The engine reads from here so voice choices remain data rather than constants
scattered throughout the synthesis code.
"""

from __future__ import annotations

# Default ES voice: es-MX-DaliaNeural, a neutral Latin American female voice.
# es-CO-SalomeNeural remains available through the "colombia" alias.
DEFAULT_EDGE_VOICE_ES = "es-MX-DaliaNeural"
DEFAULT_EDGE_VOICE_EN = "en-US-AvaNeural"

# Friendly alias -> edge voice id.
VOICE_ALIASES = {
    "default": DEFAULT_EDGE_VOICE_ES,
    "neutral": "es-MX-DaliaNeural",
    "colombia": "es-CO-SalomeNeural",
    "spain": "es-ES-ElviraNeural",
    "spain-male": "es-ES-AlvaroNeural",
    "mexico": "es-MX-DaliaNeural",
    "mexico-male": "es-MX-JorgeNeural",
    "peru": "es-PE-CamilaNeural",
    "english": DEFAULT_EDGE_VOICE_EN,
    "english-male": "en-US-AndrewNeural",
}

RECOMMENDED = [
    "es-CO-SalomeNeural",
    "es-ES-AlvaroNeural",
    "es-ES-ElviraNeural",
    "es-MX-DaliaNeural",
    "es-MX-JorgeNeural",
    "es-PE-CamilaNeural",
    "en-US-AvaNeural",
    "en-US-AndrewNeural",
    "en-US-JennyNeural",
]

# Dialogue (voice_a, voice_b) — neutral LatAm female + male, complementary.
# es female updated to Dalia (2026-06-22) to match the new neutral default.
DIALOGUE_PAIRS = {
    "es": ("es-MX-DaliaNeural", "es-MX-JorgeNeural"),
    "en": ("en-US-AvaNeural", "en-US-AndrewNeural"),
}

# macOS `say` fallback voice by language (offline provider).
SAY_VOICE = {"es": "Paulina", "en": "Samantha"}


def resolve_voice(name: str | None) -> str:
    """Map an alias to a full edge voice id; pass through unknown ids."""
    if not name:
        return DEFAULT_EDGE_VOICE_ES
    return VOICE_ALIASES.get(name.strip().lower(), name.strip())


def dialogue_pair(lang: str) -> tuple[str, str]:
    return DIALOGUE_PAIRS.get(lang, DIALOGUE_PAIRS["es"])


def lang_of(voice: str) -> str:
    return "en" if voice.lower().startswith("en") else "es"
