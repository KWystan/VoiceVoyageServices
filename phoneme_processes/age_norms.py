"""
Age-of-acquisition norms for English phonemes.

Provides age-normative context for pronunciation assessment: given a
child's age in months, which phonemes are expected to be mastered and
which are developmentally appropriate to still be in error?

Primary reference
-----------------
McLeod, S., & Crowe, K. (2020). Children's consonant acquisition in
27 languages: A cross-linguistic review. *American Journal of
Speech-Language Pathology*, 27(4), 1546–1571.
https://doi.org/10.1044/2020_AJSLP-19-00153
https://pubs.asha.org/doi/10.1044/2018_AJSLP-17-0100

This cross-linguistic meta-analysis synthesised data from 27 languages
and > 27 000 children aged 2;0–5;11.  The age bands below reflect the
**90% criterion** (mastery level) for US English.

Supplementary reference (vowels)
---------------------------------
Stoel-Gammon, C., & Herrington, P. B. (1990). Vowel systems of normally
developing and phonologically disordered children. *Clinical Linguistics
& Phonetics*, 4(2), 145–160.

Usage
-----
    >>> from phoneme_processes.age_norms import get_expected_phonemes
    >>> expected = get_expected_phonemes(48)   # child aged 4;0
    >>> expected["consonants"]
    {'p', 'b', 'm', 'n', 'w', 'd', 'h', 't', 'k', 'ɡ', 'f', 'v', 'ŋ',
     'j', 'l', 'ʃ', 'tʃ', 'dʒ', 's', 'z'}
"""

import logging
from typing import Optional

from .utils import is_consonant, manner, clean

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# Age-of-acquisition data (90% criterion, US English)
# -----------------------------------------------------------------------
# Each entry: (upper_age_months, acquired_set)
# A child at age_months is expected to have acquired all consonants
# in bands where upper_age_months <= age_months.

_CONSONANT_BANDS: list[tuple[int, set[str]]] = [
    # By 24 months (2;0)
    (24, {'p', 'b', 'm', 'n', 'w', 'd', 'h'}),
    # By 36 months (3;0)
    (36, {'t', 'k', 'ɡ', 'f', 'v', 'ŋ', 'j'}),
    # By 48 months (4;0)
    (48, {'l', 'ʃ', 'tʃ', 'dʒ', 's', 'z'}),
    # By 60 months (5;0)
    (60, {'r', 'ʒ', 'θ', 'ð'}),
    # By 72 months (6;0)
    (72, {'ɹ'}),
    # Beyond 72 months (6;0+) — marginal / still developing
    (120, set()),
]

# All consonants listed in the band system (for completeness)
_ALL_CONSONANTS: set[str] = {
    'p', 'b', 't', 'd', 'k', 'ɡ',           # stops
    'f', 'v', 'θ', 'ð', 's', 'z', 'ʃ', 'ʒ',  # fricatives
    'tʃ', 'dʒ',                               # affricates
    'm', 'n', 'ŋ',                             # nasals
    'l', 'r', 'ɹ',                             # liquids
    'w', 'j',                                  # glides
    'h',                                       # glottal
}

# Vowels — most are acquired by 36 months (Stoel-Gammon & Herrington 1990)
_VOWEL_BANDS: list[tuple[int, set[str]]] = [
    # Core monophthongs — by 24 months
    (24, {'a', 'e', 'i', 'o', 'u', 'ə', 'æ', 'ɑ', 'ʌ', 'ɛ', 'ɪ', 'ʊ'}),
    # Diphthongs + rhotic vowels — by 36 months
    (36, {'aɪ', 'eɪ', 'oʊ', 'aʊ', 'ɔɪ', 'ɚ', 'ɝ'}),
    # Marginal — still developing
    (72, set()),
]

_ALL_VOWELS: set[str] = {
    'a', 'e', 'i', 'o', 'u', 'ə', 'ɔ', 'æ',
    'ɑ', 'ʌ', 'ɛ', 'ɪ', 'ʊ',
    'aɪ', 'eɪ', 'oʊ', 'aʊ', 'ɔɪ',
    'ɚ', 'ɝ',
}


def _collect_bands(bands: list[tuple[int, set[str]]], age_months: int) -> set[str]:
    """Collect all phonemes from bands whose upper age ≤ age_months."""
    result: set[str] = set()
    for upper, ph_set in bands:
        if age_months >= upper:
            result.update(ph_set)
        else:
            break
    return result


# -----------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------

def get_expected_consonants(age_months: int) -> set[str]:
    """Return the set of English consonants expected to be mastered
    by a child of the given age (in months).

    Uses the 90% criterion from McLeod & Crowe (2020).
    """
    return _collect_bands(_CONSONANT_BANDS, age_months)


def get_expected_vowels(age_months: int) -> set[str]:
    """Return the set of English vowels expected to be mastered
    by a child of the given age (in months).

    Uses Stoel-Gammon & Herrington (1990) supplemented by clinical
    consensus on typical vowel development.
    """
    return _collect_bands(_VOWEL_BANDS, age_months)


def get_expected_phonemes(age_months: int) -> dict:
    """Return all phonemes (consonants + vowels) expected to be mastered
    by a child of the given age.

    Parameters
    ----------
    age_months : int
        Child's age in months (e.g., 60 for 5;0).

    Returns
    -------
    dict with keys:
        - ``age_months`` : int
        - ``age_label`` : str (e.g., "5;0")
        - ``consonants`` : set[str]
        - ``vowels`` : set[str]
        - ``all`` : set[str] — union of consonants and vowels
    """
    years = age_months // 12
    months = age_months % 12
    cons = get_expected_consonants(age_months)
    vows = get_expected_vowels(age_months)
    return {
        "age_months": age_months,
        "age_label": f"{years};{months}",
        "consonants": cons,
        "vowels": vows,
        "all": cons | vows,
    }


def get_not_yet_expected(
    breakdown: list[dict],
    age_months: int,
) -> list[dict]:
    """Identify phonemes in the breakdown that are not yet expected
    to be mastered at the child's age.

    This flags phonemes that a normally developing child of this age
    might still be expected to produce incorrectly — useful for
    determining whether an error is clinically significant or
    age-appropriate.

    Parameters
    ----------
    breakdown : list[dict]
        Phoneme breakdown from forced alignment.
    age_months : int
        Child's age in months.

    Returns
    -------
    list[dict]
        Each entry has ``index``, ``expected``, ``predicted``, ``score``,
        ``age_label`` (the age band by which this phoneme is expected).
    """
    expected_cons = get_expected_consonants(age_months)
    expected_vows = get_expected_vowels(age_months)

    not_yet: list[dict] = []

    for idx, entry in enumerate(breakdown):
        exp = clean(entry.get("expected", ""))
        if not exp or exp == "-":
            continue

        pred = entry.get("predicted", "")

        # Is this phoneme expected?
        if is_consonant(exp):
            if exp in expected_cons:
                continue
        elif manner(exp) == "Vowel":
            if exp in expected_vows:
                continue
        else:
            continue  # can't classify — skip

        # Find the age band where this phoneme IS expected
        age_band: Optional[str] = None
        if is_consonant(exp):
            for upper, ph_set in _CONSONANT_BANDS:
                if exp in ph_set:
                    y = upper // 12
                    m = upper % 12
                    age_band = f"{y};{m}"
                    break
        if not age_band and manner(exp) == "Vowel":
            for upper, ph_set in _VOWEL_BANDS:
                if exp in ph_set:
                    y = upper // 12
                    m = upper % 12
                    age_band = f"{y};{m}"
                    break

        not_yet.append({
            "index": idx,
            "expected": exp,
            "predicted": pred,
            "score": entry.get("score", 0.0),
            "manner": manner(exp),
            "expected_by": age_band or "72+",
        })

    return not_yet


def get_age_norm_summary(breakdown: list[dict], age_months: int) -> dict:
    """Produce a clinical summary of age-normative context.

    Returns ONLY the errors relevant to the current word, grouped by
    developmental expectation.  The full phoneme inventory is NOT
    included (it would bloat every API response with 40+ items the
    app cannot use).

    Parameters
    ----------
    breakdown : list[dict]
        Forced-alignment phoneme breakdown.
    age_months : int
        Child's age in months.

    Returns
    -------
    dict with keys:
        - ``age_months`` : int
        - ``age_label`` : str (e.g. "5;0")
        - ``developmentally_normal_errors`` : list[dict] — errors on
          phonemes NOT yet expected to be mastered at this age
        - ``clinically_significant_errors`` : list[dict] — errors on
          phonemes that ARE expected to be mastered at this age
    """
    not_yet = get_not_yet_expected(breakdown, age_months)
    not_yet_indices = {item["index"] for item in not_yet}

    clinically_significant: list[dict] = []
    for idx, entry in enumerate(breakdown):
        if idx in not_yet_indices:
            continue
        pred = entry.get("predicted", "")
        exp = entry.get("expected", "")
        if pred != exp and pred not in ("-", None, ""):
            clinically_significant.append({
                "index": idx,
                "expected": exp,
                "predicted": pred,
                "score": entry.get("score", 0.0),
                "confidence": entry.get("confidence", 0.0),
            })

    years = age_months // 12
    months = age_months % 12

    return {
        "age_months": age_months,
        "age_label": f"{years};{months}",
        "developmentally_normal_errors": not_yet,
        "clinically_significant_errors": clinically_significant,
    }
