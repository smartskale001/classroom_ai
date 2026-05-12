from typing import Literal

OutputLanguage = Literal[
    "english",
    "hindi",
    "roman_hindi",
    "telugu",
    "tamil",
    "gujarati",
    "marathi",
    "bengali",
    "kannada",
    "malayalam",
    "punjabi",
    "urdu",
]

OUTPUT_LANGUAGE_ALIASES: dict[str, OutputLanguage] = {
    # English
    "english": "english",
    "en": "english",
    # Hindi (Devanagari)
    "hindi": "hindi",
    "hi": "hindi",
    "devanagari": "hindi",
    # Roman Hindi
    "roman_hindi": "roman_hindi",
    "roman": "roman_hindi",
    "hinglish": "roman_hindi",
    "latin_hindi": "roman_hindi",
    # Telugu
    "telugu": "telugu",
    "te": "telugu",
    "telgu": "telugu",          # common typo
    # Tamil
    "tamil": "tamil",
    "ta": "tamil",
    "tamizh": "tamil",
    # Gujarati
    "gujarati": "gujarati",
    "gu": "gujarati",
    "gujrati": "gujarati",      # common typo
    "gujurati": "gujarati",     # common typo
    # Marathi
    "marathi": "marathi",
    "mr": "marathi",
    "marathi_devanagari": "marathi",
    # Bengali
    "bengali": "bengali",
    "bn": "bengali",
    "bangla": "bengali",
    "bengali_bangla": "bengali",
    # Kannada
    "kannada": "kannada",
    "kn": "kannada",
    "kanada": "kannada",        # common typo
    # Malayalam
    "malayalam": "malayalam",
    "ml": "malayalam",
    "malayalm": "malayalam",    # common typo
    # Punjabi
    "punjabi": "punjabi",
    "pa": "punjabi",
    "panjabi": "punjabi",
    "gurmukhi": "punjabi",
    # Urdu
    "urdu": "urdu",
    "ur": "urdu",
}


def normalize_output_language(raw: str | None) -> OutputLanguage:
    if raw is None or not str(raw).strip():
        return "english"
    key = str(raw).lower().strip().replace("-", "_")
    return OUTPUT_LANGUAGE_ALIASES.get(key, "english")