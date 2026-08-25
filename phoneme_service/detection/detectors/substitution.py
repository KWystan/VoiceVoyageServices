"""Substitution detectors — declarative table of (process, predicate) rows.

Adding a new substitution process = one predicate + one row in
``SUBSTITUTION_SPECS``; the shared scanner and the orchestrator never
change (open/closed principle).
"""

from dataclasses import dataclass
from typing import Callable

from detection.utils import get_position, manner, place
from .gates import is_substitution


# ---------------------------------------------------------------------------
# Predicates (pure: entry -> bool)
# ---------------------------------------------------------------------------

def is_stopping(entry: dict) -> bool:
    """Fricative → stop.

    Affricate→Stop is intentionally NOT Stopping: ASHA defines
    deaffrication as an affricate produced as a stop or fricative
    ("chip" → "tip"), so affricate targets belong to Deaffrication
    alone.  Keeping the two detectors mutually exclusive by target
    manner prevents the hierarchy filter from masking Deaffrication
    whenever Stopping also fires.
    """
    return (manner(entry["expected"]) == "Fricative"
            and manner(entry["predicted"]) == "Stop")


def is_frication(entry: dict) -> bool:
    """Stop/nasal → fricative (reverse of Stopping; atypical, Red Flag)."""
    return (manner(entry["expected"]) in ("Stop", "Nasal")
            and manner(entry["predicted"]) == "Fricative")


def is_deaffrication(entry: dict) -> bool:
    """Affricate → stop or fricative."""
    return (manner(entry["expected"]) == "Affricate"
            and manner(entry["predicted"]) in ("Stop", "Fricative"))


def is_denasalization(entry: dict) -> bool:
    """Nasal → stop."""
    return (manner(entry["expected"]) == "Nasal"
            and manner(entry["predicted"]) == "Stop")


def is_fronting(entry: dict) -> bool:
    """Velar/palatal → alveolar/labial.

    /ŋ/ is excluded as an expected phoneme (not subject to fronting
    per ASHA norms).  Glides are excluded as expected phonemes: a glide
    produced as a liquid (/j/ → [l]) is Liquidization, and a liquid
    produced as a glide (/r/ → [w]) is Gliding — neither is a
    place-change fronting.
    """
    exp, det = entry["expected"], entry["predicted"]
    exp_m, det_m = manner(exp), manner(det)
    if exp_m in ("Vowel", "Glide") or det_m == "Vowel":
        return False
    if exp == "ŋ":
        return False
    exp_p, det_p = place(exp), place(det)
    return exp_p in ("Velar", "Palatal") and det_p in ("Alveolar", "Labial")


def is_backing(entry: dict) -> bool:
    """Alveolar/labial → velar/palatal.  /ŋ/ as predicted is excluded.

    A LIQUID target produced as a glide (/l/ → [j], /ɹ/ → [j]) is
    Gliding per ASHA ("a liquid is replaced with a glide /w/, /j/");
    the pair is ceded so the developmental classification wins instead
    of a Red-Flag Backing.
    """
    exp, det = entry["expected"], entry["predicted"]
    exp_m, det_m = manner(exp), manner(det)
    if exp_m == "Vowel" or det_m == "Vowel":
        return False
    if det == "ŋ":
        return False
    if exp_m == "Liquid" and det_m == "Glide":
        return False
    exp_p, det_p = place(exp), place(det)
    return exp_p in ("Alveolar", "Labial") and det_p in ("Velar", "Palatal")


def is_gliding(entry: dict) -> bool:
    """Liquid → glide."""
    return (manner(entry["expected"]) == "Liquid"
            and manner(entry["predicted"]) == "Glide")


def is_liquidization(entry: dict) -> bool:
    """Glide → liquid (reverse of Gliding)."""
    return (manner(entry["expected"]) == "Glide"
            and manner(entry["predicted"]) == "Liquid")


def is_vowelization(entry: dict) -> bool:
    """Liquid → vowel."""
    return (manner(entry["expected"]) == "Liquid"
            and manner(entry["predicted"]) == "Vowel")


# ---------------------------------------------------------------------------
# Registry (declarative table)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SubstitutionSpec:
    """One row of the substitution-detector table."""
    process: str
    matches: Callable[[dict], bool]


SUBSTITUTION_SPECS: tuple[SubstitutionSpec, ...] = (
    SubstitutionSpec("Stopping", is_stopping),
    SubstitutionSpec("Frication", is_frication),
    SubstitutionSpec("Deaffrication", is_deaffrication),
    SubstitutionSpec("Denasalization", is_denasalization),
    SubstitutionSpec("Fronting", is_fronting),
    SubstitutionSpec("Backing", is_backing),
    SubstitutionSpec("Gliding", is_gliding),
    SubstitutionSpec("Liquidization", is_liquidization),
    SubstitutionSpec("Vowelization", is_vowelization),
)


def scan_substitutions(
    breakdown: list[dict],
    spec: SubstitutionSpec,
) -> list[dict]:
    """Run one substitution spec over the breakdown (shared scanner)."""
    processes = []
    for i, entry in enumerate(breakdown):
        if entry.get("expected") == "#":
            continue
        if not is_substitution(entry):
            continue
        if not spec.matches(entry):
            continue
        processes.append({
            "process": spec.process,
            "position": get_position(i, breakdown),
            "detail": f"/{entry['expected']}/ -> [{entry['predicted']}]",
            "_index": i,
        })
    return processes
