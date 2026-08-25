"""Shared entry-classification gates for process detectors.

Every detector asks the same two questions before applying its own
predicate: was this phoneme deleted, or substituted?  Those gates live
here so all detector modules stay consistent by construction.
"""

import logging
from typing import Callable

from detection.utils import is_consonant, same_phoneme

logger = logging.getLogger(__name__)


def is_deletion(item: dict) -> bool:
    """A phoneme is 'deleted' iff the model heard silence (blank prediction).

    Design decision (real-data driven): a segment with a resolved token
    is a PRODUCTION at any duration.  An earlier rule treated
    sub-threshold (<0.03 s) mismatched stop/affricate fragments as
    deletion artifacts, but premade error recordings showed that real
    fast stop→stop substitutions — cup→[tʌp] (Fronting), ten→[kɛn]
    (Backing), bee→[pi] (Voicing) — collapse into false Consonant
    Deletions that way.  Genuine omissions produce blank predictions
    (noise floor + unfilled CTC slots), which this gate still catches.
    Short segments are penalised in scoring instead.
    """
    return item.get("predicted", "-") in ("-", None, "")


def is_substitution(item: dict) -> bool:
    """True if entry is a genuine phoneme substitution (not deletion, not match).

    No confidence gate: a substitution is detected whenever the model's
    predicted (argmax) phoneme differs from the target.  If the argmax
    differs from ``expected``, the target's mean softmax probability is
    necessarily below 0.5 — so a "high-confidence" wrong prediction
    (confidence 0.4–0.5) is still a real substitution and must be
    reported, not silently hidden (previously the 0.4 ``_low_confidence``
    gate suppressed exactly this band).  Both sides are translated via
    ``same_phoneme()`` so aspirated/lengthened/syllabic allophones
    (e.g. ``tʰ`` vs ``t``, ``l̩`` vs ``əl``) do not count as substitutions.
    """
    if is_deletion(item):
        return False  # too short → deletion, not substitution
    predicted = item.get("predicted", "-")
    if predicted in ("-", None, ""):
        return False  # no prediction available
    if same_phoneme(predicted, item.get("expected", "")):
        return False  # same phoneme (after alphabet translation) → not a substitution
    return True


def has_consonant_neighbor(breakdown: list[dict], idx: int) -> tuple[bool, bool]:
    """Return (left_is_consonant, right_is_consonant) around ``idx``.

    Word-boundary (#) tokens are not consonants, so this is automatically
    correct across word edges.
    """
    left = idx > 0 and is_consonant(breakdown[idx - 1].get("expected", ""))
    right = idx < len(breakdown) - 1 and is_consonant(breakdown[idx + 1].get("expected", ""))
    return left, right


def run_safely(detector_fn: Callable, breakdown: list[dict], *args) -> list[dict]:
    """Run a detector, converting any exception into a logged warning."""
    try:
        return detector_fn(breakdown, *args)
    except Exception as exc:
        logger.warning(
            "Process detector %s failed: %s",
            getattr(detector_fn, "__name__", "?"), exc,
        )
        return []
