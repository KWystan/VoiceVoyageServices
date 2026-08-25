"""Assimilation detectors — context-dependent sound changes.

Covers two clinical patterns:
1. Consonant Harmony (Place/Manner assimilation across words)
2. Reduplication (Whole-syllable copying)

Reference:
- ASHA Practice Portal: Selected Phonological Patterns (Assimilation)
- McLeod & Crowe (2018) / Crowe & McLeod (2020)
"""

from detection.syllable import detect_reduplication  # noqa: F401 (re-exported for modularity)
from detection.utils import (
    canonicalize,
    clean,
    get_position,
    is_consonant,
    manner,
    place,
    same_phoneme,
)
from .gates import is_substitution


def _split_word_indices(breakdown: list[dict]) -> list[list[int]]:
    """Split breakdown indices by '#' boundary tokens."""
    words: list[list[int]] = []
    current: list[int] = []
    for i, entry in enumerate(breakdown):
        if entry.get("expected") == "#":
            if current:
                words.append(current)
                current = []
            continue
        current.append(i)
    if current:
        words.append(current)
    return words


def detect_consonant_harmony(breakdown: list[dict]) -> list[dict]:
    """Detect consonant harmony / contextual assimilation.

    Fires when an obstruent or nasal consonant substitution is triggered by
    the presence of another consonant in the same word sharing the produced
    place or manner:

    1. Velar Assimilation:    "duck"  /d ʌ k/     -> [ɡ ʌ k]  (due to /k/)
                              "dog"   /d ɔ ɡ/     -> [ɡ ɔ ɡ]  (due to /ɡ/)
                              "take"  /t eɪ k/    -> [k eɪ k] (due to /k/)
    2. Labial Assimilation:   "tub"   /t ʌ b/     -> [b ʌ b]  (due to /b/)
                              "cap"   /k æ p/     -> [p æ p]  (due to /p/)
    3. Nasal Assimilation:    "candy" /k æ n d i/ -> [n æ n i] (due to /n/)
                              "sun"   /s ʌ n/     -> [n ʌ n]  (due to /n/)
    4. Complete Harmony:      "cookie" /k ʊ k i/  -> [k u k i] (exact consonant match)

    Exclusions:
    - Glides and liquids are excluded from Place/Manner assimilation
      (gliding / liquidization / vowelization take precedence).
    - Voicing-only changes on the same place/manner are excluded (devoicing/voicing).
    """
    processes = []

    for word_idxs in _split_word_indices(breakdown):
        if len(word_idxs) < 2:
            continue

        # Collect all expected obstruent and nasal consonants in the word as potential triggers
        word_consonants = []
        for i in word_idxs:
            ph_raw = breakdown[i].get("expected", "")
            if is_consonant(ph_raw):
                ph = clean(ph_raw)
                m = manner(ph)
                if m in ("Stop", "Fricative", "Affricate", "Nasal"):
                    word_consonants.append((i, ph, place(ph), m))

        if len(word_consonants) < 2:
            continue

        for i in word_idxs:
            entry = breakdown[i]
            if not is_substitution(entry):
                continue

            exp_raw = entry.get("expected", "")
            det_raw = entry.get("predicted", "")
            if not (is_consonant(exp_raw) and is_consonant(det_raw)):
                continue

            exp = clean(exp_raw)
            det = clean(det_raw)

            exp_p, det_p = place(exp), place(det)
            exp_m, det_m = manner(exp), manner(det)

            # Glides, liquids, and vowels are not subject to consonant harmony
            if exp_m in ("Liquid", "Glide", "Vowel") or det_m in ("Liquid", "Glide", "Vowel"):
                continue

            # Pure voicing changes on the exact same place and manner are not assimilation
            if exp_p == det_p and exp_m == det_m:
                continue

            # Look for another consonant in the same word that acts as the assimilation trigger
            for other_idx, other_exp, other_p, other_m in word_consonants:
                if other_idx == i:
                    continue

                is_harmony = False

                # 1. Velar Assimilation: non-velar becomes velar due to a velar target (/k, ɡ, ŋ/)
                if exp_p != "Velar" and det_p == "Velar" and det in ("k", "ɡ") and other_p == "Velar":
                    is_harmony = True

                # 2. Labial Assimilation: non-labial becomes labial due to a labial target (/p, b, m, f, v/)
                elif exp_p != "Labial" and det_p == "Labial" and det in ("p", "b", "m", "f", "v") and other_p == "Labial":
                    is_harmony = True

                # 3. Nasal Assimilation: non-nasal becomes nasal due to a nasal target (/m, n, ŋ/)
                elif exp_m != "Nasal" and det_m == "Nasal" and det in ("m", "n", "ŋ") and other_m == "Nasal":
                    is_harmony = True

                # 4. Complete Harmony: identical consonant copied from another target consonant across distinct places
                elif exp_p != det_p and (same_phoneme(det, other_exp) or canonicalize(det) == canonicalize(other_exp)):
                    is_harmony = True

                if is_harmony:
                    processes.append({
                        "process": "Consonant Harmony",
                        "position": get_position(i, breakdown),
                        "detail": f"/{exp}/ -> [{det}]",
                        "_index": i,
                    })
                    break  # One harmony flag per substituted phoneme index

    return processes
