"""
Curriculum Map — Translates raw ASHA phonological processes into
parent-friendly display labels, filtered by the child's developmental
age bracket.

This module is the bridge between the clinical analysis (detectors, PCC,
age norms) and the parent-facing mobile interface (Voice Voyage).
Raw process names like "Fronting" and "Stopping" are mapped to
developmentally contextualised display labels with clinical status flags.

Functions
---------
get_curriculum_summary(processes, age_months)
    Filter processes to age-applicable display labels.
"""

import re
import logging
from typing import Callable

from .utils import manner, place

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Age bracket definitions
# ---------------------------------------------------------------------------

_BRACKET_RANGES: list[tuple[int, int, str]] = [
    (2, 4, "Age 4"),
    (5, 6, "Age 5"),
    (7, 7, "Age 6-7"),
    (8, 99, "Age 8"),
]

# Display labels retired at the oldest bracket — developmentally expected
# to be resolved by age 8. Weak Syllable Deletion is relabelled
# "Syllable Reduction" (supplied by the Age 8 bracket map), so the raw
# label must not linger in the Age 8 applicable set.
_AGE8_RETIRED_LABELS: set[str] = {"Backing", "Weak Syllable Deletion"}

# Process display_labels applicable per age bracket (cumulative).
# Values are the "display_label" outputs from _translate_error().
_AGE_PROCESS_MAP: dict[str, set[str]] = {
    "Age 4": {
        "Initial Consonant Deletion",
        "Medial Consonant Deletion",
        "Final Consonant Deletion",
        "Frication",
        "Backing",
        "Fronting",
        "Stopping",
        "Liquidization",
        "Weak Syllable Deletion",
    },
    "Age 5": {
        "Gliding",
        "Palatal Fronting",
        "Cluster Reduction",
    },
    "Age 6-7": {
        "Deaffrication",
    },
    "Age 8": {
        "Syllable Reduction",
    },
}


def _years_to_bracket(age_years: int) -> str:
    """Map age in years to a developmental bracket label.

    NOTE: The returned labels (e.g. "Age 4") refer to the developmental
    stage when the corresponding patterns are expected to be mastered,
    NOT the child's actual age.  A 6-year-old who is in the
    "Age 4" bracket is working toward the skills typically mastered by
    age 4.  This follows the clinical convention in the Voice Voyage
    README.

    Parameters
    ----------
    age_years : int
        Child's age in years (e.g. 5).

    Returns
    -------
    str
        One of "Age 4", "Age 5", "Age 6-7", "Age 8".
        Falls back to "Age 4" if the given age is outside all ranges.
    """
    for min_y, max_y, label in _BRACKET_RANGES:
        if min_y <= age_years <= max_y:
            return label
    return "Age 4"


def _get_applicable_labels(bracket: str) -> set[str]:
    result: set[str] = set()
    for _, _, label in _BRACKET_RANGES:
        result |= _AGE_PROCESS_MAP.get(label, set())
        if label == bracket:
            break
    else:
        # Unknown bracket label -> nothing is applicable.
        return set()
    if bracket == "Age 8":
        result -= _AGE8_RETIRED_LABELS
    return result


def _parse_detail(detail: str) -> tuple[str, str]:
    """Parse a detector detail string into (expected, predicted) phonemes.

    Handles three formats:

    **Standard substitution** (e.g. ``/k/ -> [t]``)
        Returns ``("k", "t")``.

    **Deletion** (e.g. ``/l/ deleted (-> Ø) in cluster``,
    ``/t/ deleted (-> Ø) word-finally``,
    ``/b/ deleted (-> Ø) singleton consonant``)
        Returns ``("l", "-")`` — predicted is ``"-"`` to represent omission.

    **Syllable deletion** (e.g. ``Syllable 'nana' deleted``)
        Returns ``("", "")`` — these span multiple phonemes and are
        handled by ``_translate_error`` using the process name alone.

    Parameters
    ----------
    detail : str
        The ``detail`` field from a process dict.

    Returns
    -------
    tuple[str, str]
        ``(expected, predicted)``.  Empty strings when parsing fails.
    """
    # Standard substitution: /k/ -> [t]
    match = re.match(r'/(.+?)/\s*->\s*\[(.+?)\]', detail)
    if match:
        return match.group(1), match.group(2)

    # Deletion: /l/ deleted (-> Ø) in cluster
    match = re.match(r'/(.+?)/\s*deleted', detail)
    if match:
        return match.group(1), "-"

    # Syllable deletion ("Syllable 'nana' deleted") or unparseable
    return "", ""


def _extract_syllable(detail: str) -> str:
    """Extract the deleted syllable from a Weak Syllable Deletion detail.

    e.g. ``Syllable 'nana' deleted`` -> ``"nana"``.  Returns ``""`` when
    the detail does not follow the detector's syllable format.
    """
    match = re.search(r"Syllable '([^']+)' deleted", detail)
    return match.group(1) if match else ""


def _translate_error(
    process: dict,
    expected: str,
    predicted: str,
) -> dict:
    """Map a raw ASHA process to a parent-friendly display label and status.

    Lookup is table-driven (``_TRANSLATORS`` keyed by process name);
    conditional rules (manner/place/position) live in small per-process
    translator functions.  Unrecognised processes fall through to
    ``("Needs Review", "Needs Review")``.

    Parameters
    ----------
    process : dict
        A single process dict from the detector, must have a ``"process"`` key.
    expected : str
        The target phoneme (from ``_parse_detail``).
    predicted : str
        The child's produced phoneme (from ``_parse_detail``).

    Returns
    -------
    dict with keys ``display_label`` (str) and ``clinical_status`` (str).
    """
    proc_name = process.get("process", "")
    translator = _TRANSLATORS.get(proc_name)
    if translator:
        return translator(process, expected, predicted)
    return {"display_label": proc_name, "clinical_status": "Needs Review"}


# ---------------------------------------------------------------------------
# Per-process translators (conditional rules keyed by manner/place/position)
# ---------------------------------------------------------------------------

def _tl_fronting(process: dict, expected: str, predicted: str) -> dict:
    # Palatal Fronting: /ʃ/ → [s] — the only palatal with a distinct
    # parent-facing label.  Check before the general Palatal rule.
    if expected == 'ʃ':
        return {"display_label": "Palatal Fronting", "clinical_status": "Expected Error"}
    if place(expected) in ("Velar", "Palatal"):
        return {"display_label": "Fronting", "clinical_status": "Expected Error"}
    return {"display_label": "Fronting", "clinical_status": "Needs Review"}


def _tl_backing(process: dict, expected: str, predicted: str) -> dict:
    if place(expected) in ("Alveolar", "Labial"):
        return {"display_label": "Backing", "clinical_status": "Red Flag"}
    return {"display_label": "Backing", "clinical_status": "Needs Review"}


def _tl_stopping(process: dict, expected: str, predicted: str) -> dict:
    # Stopping a fricative → developmentally expected
    if manner(expected) == "Fricative":
        return {"display_label": "Stopping", "clinical_status": "Expected Error"}
    # Stopping a stop or nasal → Frication (reverse pattern).
    # NOTE: with the current Stopping detector (expects fricative targets)
    # this branch is unreachable, but kept for forward-compatibility.
    if manner(expected) in ("Nasal", "Stop"):
        return {"display_label": "Frication", "clinical_status": "Red Flag"}
    return {"display_label": "Stopping", "clinical_status": "Needs Review"}


def _tl_gliding(process: dict, expected: str, predicted: str) -> dict:
    if manner(expected) == "Liquid":
        return {"display_label": "Gliding", "clinical_status": "Expected Error"}
    return {"display_label": "Gliding", "clinical_status": "Needs Review"}


def _tl_liquidization(process: dict, expected: str, predicted: str) -> dict:
    if manner(expected) == "Glide":
        return {"display_label": "Liquidization", "clinical_status": "Red Flag"}
    return {"display_label": "Liquidization", "clinical_status": "Needs Review"}


def _tl_deaffrication(process: dict, expected: str, predicted: str) -> dict:
    if manner(expected) == "Affricate":
        return {"display_label": "Deaffrication", "clinical_status": "Expected Error"}
    return {"display_label": "Deaffrication", "clinical_status": "Needs Review"}


def _tl_voicing(process: dict, expected: str, predicted: str) -> dict:
    proc_name = process.get("process", "")
    return {"display_label": proc_name, "clinical_status": "Expected Error"}


def _tl_consonant_deletion(process: dict, expected: str, predicted: str) -> dict:
    position = process.get("position", "")
    if position == "Medial":
        return {"display_label": "Medial Consonant Deletion", "clinical_status": "Red Flag"}
    if position == "Final":
        return {"display_label": "Final Consonant Deletion", "clinical_status": "Red Flag"}
    return {"display_label": "Initial Consonant Deletion", "clinical_status": "Red Flag"}


_FIXED_LABELS: dict[str, tuple[str, str]] = {
    "Frication": ("Frication", "Red Flag"),
    "Denasalization": ("Denasalization", "Red Flag"),
    "Vowelization": ("Vowelization", "Red Flag"),
    "Cluster Reduction": ("Cluster Reduction", "Expected Error"),
    "Weak Syllable Deletion": ("Weak Syllable Deletion", "Expected Error"),
    "Final Consonant Deletion": ("Final Consonant Deletion", "Red Flag"),
}


def _tl_fixed(process: dict, expected: str, predicted: str) -> dict:
    """Fixed label+status processes (no conditional logic)."""
    label, status = _FIXED_LABELS[process.get("process", "")]
    return {"display_label": label, "clinical_status": status}


_TRANSLATORS: dict[str, Callable[[dict, str, str], dict]] = {
    "Fronting": _tl_fronting,
    "Backing": _tl_backing,
    "Stopping": _tl_stopping,
    "Gliding": _tl_gliding,
    "Liquidization": _tl_liquidization,
    "Deaffrication": _tl_deaffrication,
    "Prevocalic Voicing": _tl_voicing,
    "Devoicing": _tl_voicing,
    "Final Devoicing": _tl_voicing,
    "Consonant Deletion": _tl_consonant_deletion,
    "Frication": _tl_fixed,
    "Denasalization": _tl_fixed,
    "Vowelization": _tl_fixed,
    "Cluster Reduction": _tl_fixed,
    "Weak Syllable Deletion": _tl_fixed,
    "Final Consonant Deletion": _tl_fixed,
}


def get_curriculum_summary(
    processes: list[dict],
    age_years: int = 4,
) -> list[dict]:
    """Filter detected processes to those applicable for the child's age."""
    bracket = _years_to_bracket(age_years)
    applicable_labels = _get_applicable_labels(bracket)

    applicable_errors: list[dict] = []

    for proc in processes:
        detail = proc.get("detail", "")
        expected_ph, predicted_ph = _parse_detail(detail)

        if not expected_ph:
            # Weak Syllable Deletion spans a whole syllable — its detail
            # (e.g. "Syllable 'nana' deleted") has no single phoneme, so
            # the process is handled by name alone.
            if proc.get("process") == "Weak Syllable Deletion":
                expected_ph = _extract_syllable(detail) or "σ"
                predicted_ph = "-"
            else:
                logger.debug(
                    "Skipping process with unparseable detail: %s — %s",
                    proc.get("process"), detail,
                )
                continue

        translated = _translate_error(proc, expected_ph, predicted_ph)
        display_label = translated["display_label"]
        clinical_status = translated["clinical_status"]

        if display_label == "Weak Syllable Deletion" and bracket == "Age 8":
            display_label = "Syllable Reduction"

        if display_label not in applicable_labels:
            logger.debug(
                "Skipping %s (display_label=%s) — not applicable at %s",
                proc.get("process"), display_label, bracket,
            )
            continue

        applicable_errors.append({
            "target_sound": f"/{expected_ph}/",
            "child_produced": f"[{predicted_ph}]",
            "display_label": display_label,
            "clinical_status": clinical_status,
            "position": proc.get("position", "Unknown"),
        })

    return applicable_errors
