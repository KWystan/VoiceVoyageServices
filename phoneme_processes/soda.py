"""
SODA Error Typology Classifier.

Classifies each phoneme in the forced-alignment breakdown into one of
four error types plus Correct:

    S = Substitution   — phoneme replaced with a different STANDARD phoneme
                          (e.g., /k/ -> [t] — Fronting)
    O = Omission       — phoneme deleted entirely (no acoustic evidence)
                          (e.g., /l/ -> null in "blue" -> "bue")
    D = Distortion     — phoneme attempted but produced with a NON-STANDARD
                          variant (e.g., dentalised /s/, lateral lisp, or
                          any output that is not a recognisable English
                          phoneme)
    A = Addition       — extra phoneme inserted that is not in the target
                          (e.g., schwa in "blue" -> [b@lu:])

Clinical reference
------------------
Bauman-Waengler, J. A. (2016). *Articulation and Phonology in Speech
Sound Disorders: A Clinical Focus* (6th ed.). Pearson.

Distortion definition
---------------------
In Speech-Language Pathology a **distortion** is the production of a
sound that does not clearly become another phoneme — the child makes
an identifiable attempt but the articulation is imprecise (dentalised
/s/, lateral /s/, derhotacised /r/, etc.).

By contrast, when the child produces a CLEAR, RECOGNISABLE English
phoneme that is NOT the target (e.g., /k/ -> [t]), it is always a
**substitution**, even if the two phonemes are articulatorily close
in feature space.  /k/ -> [t] = Fronting (Substitution), not Distortion.

Detection rules
---------------
O (Omission):      predicted = "-" or duration < min_phoneme_duration_sec
C (Correct):       predicted == expected
S (Substitution):  predicted != expected AND predicted IS a standard phoneme
                   (has a known manner of articulation)
D (Distortion):    predicted != expected AND predicted is NOT a standard
                   phoneme (manner() returns None) — the child produced
                   something the ASR cannot map to a clean phoneme
A (Addition):      Duration- or prediction-based heuristics for epenthesis
"""

import logging
from typing import Optional

from config import config
from .utils import is_consonant, manner, place, same_phoneme
from modules.panphon_module import get_distance

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────

# Maximum feature edit distance for a non-standard output to count as
# a distortion rather than an unknown/uncategorised error.
_DISTORTION_MAX_FEATURE_DIST: float = 0.35

# Duration thresholds for addition heuristics (seconds)
_CONSONANT_ADDITION_DURATION_S: float = 0.35
_VOWEL_ADDITION_DURATION_S: float = 0.70

# Error-type labels
_SODA_LABELS = {
    "S": "Substitution",
    "O": "Omission",
    "D": "Distortion",
    "A": "Addition",
    "C": "Correct",
}


# -----------------------------------------------------------------------
# Per-phoneme classification
# -----------------------------------------------------------------------

def _is_omission(entry: dict) -> bool:
    """Check if this phoneme is omitted."""
    cfg = config.forced_alignment
    if entry.get("duration_sec", 1.0) < cfg.min_phoneme_duration_sec:
        return True
    if entry.get("predicted", "-") in ("-", None, ""):
        return True
    return False


def _is_standard_phoneme(phoneme: str) -> bool:
    """Check whether a phoneme string represents a standard English phoneme.

    A phoneme is "standard" if it has a known manner of articulation
    (our ``manner()`` helper returns a non-None value for it).  This
    covers all phonemes in our hardcoded sets plus any that panphon
    can classify.

    Phoneme strings that fail this check are either diacritic-bearing
    variants (e.g. /s_0/, /n_d/ in X-SAMPA; /s[U+0326]/ in IPA) or
    unknown symbols — these are candidates for distortion.
    """
    return manner(phoneme) is not None


def _is_distortion(entry: dict) -> bool:
    """Check if this phoneme is a distortion (non-standard variant).

    Clinical criterion:
    1. Not an omission
    2. Predicted != expected
    3. The predicted phoneme is NOT a standard English phoneme
       (manner() returns None — it's a diacritic variant or unknown)
    4. Small panphon feature edit distance from the target confirms
       it's a close attempt, not a different sound entirely

    NOTE: If ``predicted`` IS a standard phoneme (e.g., /t/ when /k/
    was expected), this returns False — the entry will be classified
    as Substitution, which is the correct clinical label (Fronting).
    """
    if _is_omission(entry):
        return False
    exp = entry.get("expected", "")
    pred = entry.get("predicted", "")
    if pred == exp:
        return False
    if pred in ("-", None, ""):
        return False

    # If the predicted phoneme IS a standard English phoneme, it's a
    # SUBSTITUTION, not a distortion — regardless of feature distance.
    if _is_standard_phoneme(pred):
        return False

    # Non-standard predicted phoneme — check feature distance to see
    # whether it's close enough to count as a "distorted" attempt
    try:
        dst = get_distance()
        fed = dst.feature_edit_distance(exp, pred)
    except Exception:
        fed = 999.0

    return fed <= _DISTORTION_MAX_FEATURE_DIST


def _detect_additions_at_index(
    entry: dict,
    idx: int,
    breakdown: list[dict],
) -> Optional[dict]:
    """Detect potential phoneme addition at a single index.

    Returns a dict describing the suspected addition, or None.

    Heuristics used (see module docstring for limitations):
    1. **Duration anomaly**: consonant > 0.35s may have absorbed a vowel.
    2. **Predicted-vowel-on-consonant**: model predicts a vowel-like sound
       where the target is a consonant.
    """
    exp = entry.get("expected", "")
    pred = entry.get("predicted", "")
    dur = entry.get("duration_sec", 0.0)

    if dur <= 0.0 or pred in ("-", None, ""):
        return None

    exp_m = manner(exp)
    pred_m = manner(pred)

    # ---- Heuristic 1: Abnormally long consonant ──────────
    if exp_m and exp_m != "Vowel" and dur >= _CONSONANT_ADDITION_DURATION_S:
        # A consonant this long may have absorbed an epenthetic vowel
        detail = f"Segment unusually long ({dur:.2f}s)"
        if pred_m == "Vowel" and exp_m != "Vowel":
            detail += f"; vowel-like prediction [{pred}] suggests vowel insertion"
        elif exp_m == "Stop" and dur > 0.25:
            detail += f"; stop released into possible schwa"
        return {
            "index": idx,
            "expected": exp,
            "predicted": pred,
            "duration_sec": dur,
            "type": "A",
            "detail": detail,
        }

    # ---- Heuristic 2: Predicted vowel on consonant slot ──
    if exp_m and exp_m != "Vowel" and pred_m == "Vowel":
        return {
            "index": idx,
            "expected": exp,
            "predicted": pred,
            "duration_sec": dur,
            "type": "A",
            "detail": f"Vowel [{pred}] inserted where [{exp}] expected",
        }

    # ---- Heuristic 3: Abnormally long vowel ──────────────
    if exp_m == "Vowel" and dur >= _VOWEL_ADDITION_DURATION_S:
        return {
            "index": idx,
            "expected": exp,
            "predicted": pred,
            "duration_sec": dur,
            "type": "A",
            "detail": f"Vowel segment unusually long ({dur:.2f}s); may reflect paraphasia",
        }

    return None


def _classify_single(entry: dict, idx: int = 0) -> str:
    """Classify a single phoneme entry into a SODA error type.

    Returns one of ``"S"``, ``"O"``, ``"D"``, ``"A"``, or ``"C"``.

    Decision order (first match wins):
        1. Omission (O)  — no acoustic evidence for this phoneme
        2. Correct (C)   — exact match
        3. Distortion (D) — non-standard variant (diacritic, unknown)
        4. Addition (A)  — epenthesis heuristic
        5. Substitution (S) — default: wrong but recognisable phoneme
    """
    # Omission gate
    if _is_omission(entry):
        return "O"

    exp = entry.get("expected", "")
    pred = entry.get("predicted", "")

    # Correct (via alphabet translation — allophonic spellings match)
    if same_phoneme(pred, exp):
        return "C"

    # Distortion gate — catches non-standard variants first
    if _is_distortion(entry):
        return "D"

    # Addition gate (duration-based heuristic)
    if _detect_additions_at_index(entry, idx, []):
        return "A"

    # Default: substitution (predicted is a standard but wrong phoneme)
    return "S"


# -----------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------

def classify_all(breakdown: list[dict]) -> dict:
    """Run full SODA classification on a phoneme breakdown.

    Parameters
    ----------
    breakdown : list[dict]
        List of phoneme breakdown entries from forced alignment.
        Each must have ``expected``, ``predicted``, ``confidence``,
        ``duration_sec``.

    Returns
    -------
    dict with keys:
        - ``per_phoneme`` : list[dict] — detailed per-phoneme labels
        - ``soda_summary`` : dict[str, int] — count per type
          e.g. ``{"S": 1, "O": 0, "D": 0, "A": 0, "C": 2}``
    """
    per_phoneme: list[dict] = []
    additions: list[dict] = []
    summary: dict[str, int] = {"S": 0, "O": 0, "D": 0, "A": 0, "C": 0}

    for idx, entry in enumerate(breakdown):
        add_result = _detect_additions_at_index(entry, idx, breakdown)

        soda_type = _classify_single(entry, idx)

        # Addition detection overrides if triggered
        if add_result is not None:
            soda_type = "A"
            additions.append(add_result)

        per_phoneme.append({
            "index": idx,
            "expected": entry.get("expected", ""),
            "predicted": entry.get("predicted", ""),
            "type": soda_type,
            "label": _SODA_LABELS.get(soda_type, "Unknown"),
            "score": entry.get("score", 0.0),
            "confidence": entry.get("confidence", 0.0),
            "duration_sec": entry.get("duration_sec", 0.0),
        })
        summary[soda_type] = summary.get(soda_type, 0) + 1

    return {
        "per_phoneme": per_phoneme,
        "soda_summary": summary,
        "additions": additions,
    }
