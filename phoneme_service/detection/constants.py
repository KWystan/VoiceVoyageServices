"""
Phoneme Classification Sets — SINGLE source of truth.

All manner and place sets used by detector.py and syllable.py are
defined here and imported elsewhere.  Do NOT duplicate these sets
in other files.

NOTE: Only ɡ (U+0261, IPA small letter script G) is used throughout.
The ASCII g (U+0067) is NOT in any phoneme set — use normalize_ipa()
to convert before lookup.
"""

# ── Manner Sets ──────────────────────────────────────────────

STOPS: set[str] = {'p', 'b', 't', 'd', 'k', 'ɡ'}

FRICATIVES: set[str] = {'f', 'v', 'θ', 'ð', 's', 'z', 'ʃ', 'ʒ', 'h'}

AFFRICATES: set[str] = {'tʃ', 'dʒ'}

NASALS: set[str] = {'m', 'n', 'ŋ'}

LIQUIDS: set[str] = {'l', 'r', 'ɹ'}

GLIDES: set[str] = {'w', 'j'}

VOWELS: set[str] = {
    'a', 'e', 'i', 'o', 'u', 'ə', 'ɔ', 'æ', 'ɑ', 'ʌ', 'ɛ', 'ɪ', 'ʊ',
    'aɪ', 'eɪ', 'oʊ', 'aʊ', 'ɔɪ',
    'ɚ', 'ɝ', 'əl',
}

# ── Place Sets ───────────────────────────────────────────────

VELARS: set[str] = {'k', 'ɡ', 'ŋ'}

PALATALS: set[str] = {'ʃ', 'ʒ', 'tʃ', 'dʒ'}

ALVEOLARS: set[str] = {'t', 'd', 's', 'z', 'n', 'l', 'r', 'ɹ'}

LABIALS: set[str] = {'p', 'b', 'f', 'v', 'm', 'w'}

# ── Convenience Lookups ─────────────────────────────────────

MANNER_MAP: dict[str, set[str]] = {
    "Stop": STOPS,
    "Fricative": FRICATIVES,
    "Affricate": AFFRICATES,
    "Nasal": NASALS,
    "Liquid": LIQUIDS,
    "Glide": GLIDES,
    "Vowel": VOWELS,
}

# ── Additional Place Sets ─────────────────────────────────────────────
# Used by place() in utils.py (DENTALS maps to "Alveolar" per ASHA;
# GLOTTALS maps to "Glottal").
DENTALS: set[str] = {'θ', 'ð'}
GLOTTALS: set[str] = {'h'}
