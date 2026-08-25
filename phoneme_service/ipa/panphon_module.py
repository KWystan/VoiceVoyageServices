"""
Panphon phoneme similarity module.

Provides get_phonetic_similarity() — continuous articulatory feature similarity
using Panphon feature edit distance across all consonants and vowels.
"""

from functools import lru_cache
import panphon.distance

from ipa.normalization import same_phoneme, clean

# Diphthong base extraction map: extracts the primary vowel nucleus
# so Panphon Levenshtein distance compares phonemes without sequence-length penalty.
_DIPHTHONG_BASES: dict[str, str] = {
    "eɪ": "e",
    "oʊ": "o",
    "aɪ": "a",
    "aʊ": "a",
    "ɔɪ": "ɔ",
}

# Affricate components: decomposing affricates (stop + fricative)
# allows comparing against each single component rather than incurring a 2-segment penalty.
_AFFRICATE_COMPONENTS: dict[str, tuple[str, str]] = {
    "tʃ": ("t", "ʃ"),
    "dʒ": ("d", "ʒ"),
    "ʧ": ("t", "ʃ"),
    "ʤ": ("d", "ʒ"),
}

# Gliding pairs: developmental liquid-to-glide substitutions (ASHA elimination age ~5;0)
# receive a dedicated developmental floor since Panphon major class distance for liquid->glide is wide.
_GLIDING_PAIRS: set[frozenset[str]] = {
    frozenset({"l", "w"}),
    frozenset({"r", "w"}),
    frozenset({"ɹ", "w"}),
    frozenset({"l", "j"}),
    frozenset({"r", "j"}),
    frozenset({"ɹ", "j"}),
}


@lru_cache(maxsize=1)
def get_distance() -> panphon.distance.Distance:
    """Lazy initializer for panphon Distance object."""
    return panphon.distance.Distance()


def get_phonetic_similarity(expected: str, detected: str) -> float:
    """Compute graded [0, 100] Panphon feature similarity between any two phonemes.

    Uses articulatory feature edit distance (place, manner, voice, height,
    backness, tenseness, etc.) so phonetically close substitutions (e.g.
    Stopping /v/ -> [b], /s/ -> [t], Voicing /b/ -> [p], Vowel reduction
    /ə/ -> [e], Tense-lax /ɪ/ -> [i]) receive appropriate partial credit
    rather than unfairly falling to 0.0.
    """
    if same_phoneme(detected, expected):
        return 100.0
    if not detected or detected in ("-", None, ""):
        return 0.0

    exp_c = clean(expected)
    det_c = clean(detected)

    if not exp_c or not det_c or exp_c == "-" or det_c == "-":
        return 0.0

    # 1. Diphthong base extraction
    exp_b = _DIPHTHONG_BASES.get(exp_c, exp_c)
    det_b = _DIPHTHONG_BASES.get(det_c, det_c)

    if same_phoneme(det_b, exp_b):
        return 95.0

    dst = get_distance()

    # 2. Affricate decomposition
    if exp_c in _AFFRICATE_COMPONENTS:
        c1, c2 = _AFFRICATE_COMPONENTS[exp_c]
        fed = min(dst.feature_edit_distance(c1, det_b), dst.feature_edit_distance(c2, det_b))
        sim = max(20.0, min(95.0, 100.0 * (1.0 - fed * 3.5)))
        return round(sim * 0.85, 2)
    if det_c in _AFFRICATE_COMPONENTS:
        c1, c2 = _AFFRICATE_COMPONENTS[det_c]
        fed = min(dst.feature_edit_distance(exp_b, c1), dst.feature_edit_distance(exp_b, c2))
        sim = max(20.0, min(95.0, 100.0 * (1.0 - fed * 3.5)))
        return round(sim * 0.85, 2)

    # 3. Liquid Gliding floor
    if frozenset({exp_c, det_c}) in _GLIDING_PAIRS:
        return 70.0

    # 4. Pure Panphon feature edit distance
    fed = dst.feature_edit_distance(exp_b, det_b)
    sim = max(0.0, min(95.0, 100.0 * (1.0 - fed * 3.5)))
    return round(sim, 2)
