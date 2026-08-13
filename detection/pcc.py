"""
Percentage of Consonants Correct (PCC) and related severity metrics.

Clinical reference
------------------
Shriberg, L. D., & Kwiatkowski, J. (1982). Phonological disorders III:
A procedure for assessing severity of involvement.
*Journal of Speech and Hearing Disorders*, 47(3), 256–270.

Shriberg, L. D., Austin, D., Lewis, B. A., McSweeny, J. L., & Wilson,
D. L. (1997). The Percentage of Consonants Correct (PCC) metric:
Extensions and reliability data. *Journal of Speech, Language, and
Hearing Research*, 40(4), 708–722.

Primary metrics
---------------
- **PCC**  — Percentage of Consonants Correct (total consonants correct / total)
- **PVC**  — Percentage of Vowels Correct (vowels only)
- **PCC-R** — Percentage of Consonants Correct — Revised (excludes common
  clinical substitutes from the "correct" count)

Severity cut-offs (Shriberg & Kwiatkowski 1982):
  ≥ 85%  — Mild
  65–84% — Mild–Moderate
  50–64% — Moderate–Severe
  < 50%  — Severe
"""

import logging

from .utils import is_consonant, manner, same_phoneme

logger = logging.getLogger(__name__)

# ── Severity thresholds (Shriberg & Kwiatkowski 1982) ────────────────

_PCC_SEVERITY_BANDS: list[tuple[float, float, str, str]] = [
    (85.0, 100.0, "Mild", "Within or near age-appropriate expectations"),
    (65.0, 84.99, "Mild-Moderate", "Mild to moderate involvement"),
    (50.0, 64.99, "Moderate-Severe", "Moderate to severe involvement"),
    (0.0,  49.99, "Severe", "Severe involvement; likely needs intervention"),
]

# ── Common clinical substitutes excluded from PCC-R count ────────────
# These are developmentally common substitutions that Shriberg et al.
# (1997) recommend treating as "correct" for PCC-R scoring because they
# reflect typical phonological processes rather than disordered speech.

_PCC_R_ALLOWED: dict[str, set[str]] = {
    # Fronting
    "k": {"t", "ɡ"}, "ɡ": {"d", "k"}, "ŋ": {"n"},
    # Stopping
    "f": {"p", "v"}, "v": {"b", "f"}, "s": {"t", "z"}, "z": {"d", "s"},
    "ʃ": {"t", "ʒ"}, "ʒ": {"d", "ʃ"}, "θ": {"t", "ð"}, "ð": {"d", "θ"},
    # Gliding
    "l": {"w", "j"}, "r": {"w", "j"},
    # Devoicing / Voicing
    "b": {"p"}, "d": {"t"}, "p": {"b"}, "t": {"d"},
}
# NOTE: keys must NOT overlap with conflicting values — earlier duplicate
# keys (e.g. "k" under Fronting) were silently overwritten by later entries
# (e.g. "k" under Voicing), dropping fronting/stopping from the allowed set.


# -----------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------

def _is_correct_consonant(entry: dict) -> bool:
    """A consonant is correct if predicted matches expected (via alphabet
    translation — aspirated/syllabic/rhotic allophonic spellings of the
    same phoneme count as correct)."""
    return same_phoneme(entry.get("predicted", "-"), entry.get("expected", ""))


def _is_consonant_entry(entry: dict) -> bool:
    """Check if the *expected* phoneme in this entry is a consonant."""
    return is_consonant(entry.get("expected", ""))


def _is_correct_vowel(entry: dict) -> bool:
    """A vowel is correct if predicted matches expected (same translation)."""
    return same_phoneme(entry.get("predicted", "-"), entry.get("expected", ""))


def _is_vowel_entry(entry: dict) -> bool:
    """Check if the *expected* phoneme in this entry is a vowel."""
    return manner(entry.get("expected", "")) == "Vowel"


def _severity_label(pct: float) -> str:
    """Return the Shriberg & Kwiatkowski severity label for a PCC score."""
    for lo, hi, label, _ in _PCC_SEVERITY_BANDS:
        if lo <= pct <= hi:
            return label
    return "Unknown"


def _severity_description(pct: float) -> str:
    """Return the clinical description for a PCC score."""
    for lo, hi, _, desc in _PCC_SEVERITY_BANDS:
        if lo <= pct <= hi:
            return desc
    return ""


# -----------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------

def compute_pcc(breakdown: list[dict]) -> dict:
    """Compute Percentage of Consonants Correct (PCC).

    Parameters
    ----------
    breakdown : list[dict]
        The phoneme breakdown from forced alignment. Each entry must
        have ``expected`` and ``predicted`` keys.

    Returns
    -------
    dict with keys:
        - ``pcc`` : float — PCC score [0, 100]
        - ``total_consonants`` : int
        - ``correct_consonants`` : int
        - ``error_consonants`` : int
        - ``severity`` : str — "Mild", "Mild-Moderate", etc.
        - ``severity_description`` : str — clinical description
        - ``error_list`` : list[dict] — each has ``expected``,
          ``predicted``, ``score``
    """
    total = 0
    correct = 0
    errors: list[dict] = []

    for entry in breakdown:
        if not _is_consonant_entry(entry):
            continue
        total += 1
        if _is_correct_consonant(entry):
            correct += 1
        else:
            errors.append({
                "expected": entry.get("expected", ""),
                "predicted": entry.get("predicted", ""),
                "score": entry.get("score", 0.0),
            })

    if total == 0:
        return {
            "pcc": 0.0,
            "total_consonants": 0,
            "correct_consonants": 0,
            "error_consonants": 0,
            "severity": "N/A",
            "severity_description": "No consonants in target word",
            "error_list": [],
        }

    pct = round(correct / total * 100.0, 2)

    return {
        "pcc": pct,
        "total_consonants": total,
        "correct_consonants": correct,
        "error_consonants": total - correct,
        "severity": _severity_label(pct),
        "severity_description": _severity_description(pct),
        "error_list": errors,
    }


def compute_pcc_r(breakdown: list[dict]) -> dict:
    """Compute Percentage of Consonants Correct — Revised (PCC-R).

    PCC-R excludes common clinical substitutes (fronting, stopping,
    gliding, voicing errors) from the error count — only consonants
    that are deleted or substituted with a non-common error count
    as incorrect.

    Returns
    -------
    dict with keys:
        - ``pcc_r`` : float — PCC-R score [0, 100]
        - ``total_consonants`` : int
        - ``correct_or_common_substitute`` : int
        - ``severe_errors`` : int
        - ``error_list`` : list[dict] — only severe (non-common) errors
    """
    total = 0
    ok = 0
    severe_errors: list[dict] = []

    for entry in breakdown:
        if not _is_consonant_entry(entry):
            continue
        total += 1
        exp = entry.get("expected", "")
        pred = entry.get("predicted", "")

        # Exact match → correct
        if pred == exp:
            ok += 1
            continue

        # Common clinical substitute → still counts as "ok" for PCC-R
        if exp in _PCC_R_ALLOWED and pred in _PCC_R_ALLOWED[exp]:
            ok += 1
            continue

        # Severe error
        severe_errors.append({
            "expected": exp,
            "predicted": pred,
            "score": entry.get("score", 0.0),
        })

    if total == 0:
        return {
            "pcc_r": 0.0,
            "total_consonants": 0,
            "correct_or_common_substitute": 0,
            "severe_errors": 0,
            "error_list": [],
        }

    pct = round(ok / total * 100.0, 2)

    return {
        "pcc_r": pct,
        "total_consonants": total,
        "correct_or_common_substitute": ok,
        "severe_errors": total - ok,
        "error_list": severe_errors,
    }


def compute_pvc(breakdown: list[dict]) -> dict:
    """Compute Percentage of Vowels Correct (PVC).

    Parameters
    ----------
    breakdown : list[dict]
        The phoneme breakdown from forced alignment.

    Returns
    -------
    dict with keys:
        - ``pvc`` : float — PVC score [0, 100]
        - ``total_vowels`` : int
        - ``correct_vowels`` : int
        - ``error_vowels`` : int
        - ``error_list`` : list[dict]
    """
    total = 0
    correct = 0
    errors: list[dict] = []

    for entry in breakdown:
        if not _is_vowel_entry(entry):
            continue
        total += 1
        if _is_correct_vowel(entry):
            correct += 1
        else:
            errors.append({
                "expected": entry.get("expected", ""),
                "predicted": entry.get("predicted", ""),
                "score": entry.get("score", 0.0),
            })

    if total == 0:
        return {
            "pvc": 0.0,
            "total_vowels": 0,
            "correct_vowels": 0,
            "error_vowels": 0,
            "error_list": [],
        }

    pct = round(correct / total * 100.0, 2)

    return {
        "pvc": pct,
        "total_vowels": total,
        "correct_vowels": correct,
        "error_vowels": total - correct,
        "error_list": errors,
    }


def compute_all(breakdown: list[dict]) -> dict:
    """Compute PCC, PCC-R, and PVC in a single pass.

    Convenience function for API integration.

    Returns
    -------
    dict with keys ``pcc``, ``pcc_r``, ``pvc``, each containing the
    full result dict from the corresponding function above.
    """
    return {
        "pcc": compute_pcc(breakdown),
        "pcc_r": compute_pcc_r(breakdown),
        "pvc": compute_pvc(breakdown),
    }


def compute_overall_score(
    pcc_score: float,
    fa_average: float,
    total_consonants: int,
    min_consonants: int,
) -> float:
    """Combine PCC with the forced-alignment average into the overall score.

    Strategy (mirrors the /assess contract):
    - zero consonants (vowel-only word)  -> forced-alignment average
    - fewer than ``min_consonants``      -> blended by consonant ratio,
      so 1-2 wrong consonants in short words don't produce the
      "80% PCC wall" (0%/50%/100% extremes)
    - otherwise                          -> PCC as-is
    """
    if total_consonants == 0:
        return fa_average
    if total_consonants < min_consonants:
        pcc_weight = total_consonants / min_consonants
        return round(pcc_score * pcc_weight + fa_average * (1 - pcc_weight), 2)
    return pcc_score
