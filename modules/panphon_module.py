"""
Panphon phoneme scoring module.

Provides score_pair() for evaluating phoneme substitution severity
using panphon feature edit distance, with close-pair detection
for natural coarticulation.

This module is the SINGLE source of truth for close-pair and devoicing
boost tables used by the forced-alignment scoring pipeline.
"""

import panphon.distance
from functools import lru_cache

# Close phoneme pairs (natural coarticulation variants).
# Key is the expected phoneme, value is a set of detected variants
# that should receive a score BOOST because they are coarticulation
# artefacts rather than genuine errors.
_CLOSE_PAIRS: dict[str, set[str]] = {
    # ---- Vowel length / nasalisation ----
    "a":           {"aː", "ɑ", "æ", "ɑː"},
    "e":           {"eː", "ɛ", "ɛː", "ɪ"},
    "i":           {"iː", "ɨ", "ɪ"},
    "o":           {"oː", "ɔ", "ɔː", "ʊ"},
    "u":           {"uː", "ʉ", "ʊ"},
    "ə":           {"ɜ", "ɝ", "ʌ"},
    "ɛ":           {"e", "eː", "ɛː"},
    "ɔ":           {"o", "oː", "ɔː"},
    "æ":           {"a", "aː", "ɑ"},
    "ʌ":           {"ə", "ɜ"},
    "ɪ":           {"i", "iː", "ɨ"},
    "ʊ":           {"u", "uː"},
    # ---- Diphthong variants ----
    "aɪ":          {"aɪ̆", "ɔɪ"},
    "eɪ":          {"eɪ̆", "ɛɪ"},
    "oʊ":          {"oʊ̆", "ɔʊ"},
    "aʊ":          {"aʊ̆", "ɔʊ"},
    # ---- Consonant voicing (1-feature [voice]) ----
    "p":           {"b"},
    "b":           {"p"},
    "t":           {"d"},
    "d":           {"t"},
    "k":           {"ɡ"},      # IPA ɡ ONLY — fixed from duplicate-key bug
    "ɡ":           {"k"},      # NOTE: key is ɡ (U+0261), NOT g (U+0067)
    "f":           {"v"},
    "v":           {"f"},
    "s":           {"z"},
    "z":           {"s"},
    "ʃ":           {"ʒ"},
    "ʒ":           {"ʃ"},
    "θ":           {"ð"},
    "ð":           {"θ"},
    # ---- Consonant place (same manner) ----
    "m":           {"n"},
    "n":           {"m", "ŋ"},
    "ŋ":           {"n"},
    # ---- Liquid variation ----
    "l":           {"r", "ɹ", "ɫ"},
    "r":           {"l", "ɹ"},
    "ɹ":           {"l", "r"},
    # ---- Glide variation ----
    "w":           {"ʍ", "j"},
    "j":           {"w"},
}

# Devoicing map: detected phone paired with expected phone within 1 [voice]
# feature.  Key = expected, value = detected.  NOTE: use only ɡ (U+0261).
# FIXED: removed duplicate "k" key — only the IPA-correct ɡ variant is used.
_DEVOICE_PAIRS: dict[str, str] = {
    "b": "p", "d": "t", "ɡ": "k",
    "v": "f", "z": "s", "ʒ": "ʃ", "ð": "θ",
    "p": "b", "t": "d", "k": "ɡ",
    "f": "v", "s": "z", "ʃ": "ʒ", "θ": "ð",
}


@lru_cache(maxsize=1)
def get_distance() -> panphon.distance.Distance:
    """Lazy initializer for panphon Distance object."""
    return panphon.distance.Distance()


def score_pair(expected: str, detected: str) -> float:
    """Score a single expected-detected phoneme pair [0, 100].

    Returns 0 for deletions (detected == '-'), 100 for exact matches,
    and a scaled panphon feature edit distance for substitutions.
    """
    if detected == "-":
        return 0.0
    if expected == detected:
        return 100.0

    dst = get_distance()
    fed = dst.feature_edit_distance(expected, detected)
    score = max(0.0, (1.0 - fed) * 100.0)

    # Boost close pairs
    if expected in _CLOSE_PAIRS and detected in _CLOSE_PAIRS[expected]:
        score = min(100.0, score + 20.0)

    # Boost devoicing pairs (1-feature [voice] changes)
    if expected in _DEVOICE_PAIRS and detected == _DEVOICE_PAIRS[expected]:
        score = min(100.0, score + 15.0)

    return round(score, 2)


def lookup_boost(expected: str, detected: str) -> float:
    """Return the boost value (+20, +15, or 0) without computing full score.
    Used by the forced-alignment scoring pipeline to adjust confidence-derived scores.
    """
    if expected in _CLOSE_PAIRS and detected in _CLOSE_PAIRS[expected]:
        return 20.0
    if expected in _DEVOICE_PAIRS and detected == _DEVOICE_PAIRS[expected]:
        return 15.0
    return 0.0
