"""Process-detection orchestrator for the forced-alignment pipeline.

The detector implementations live in ``detection/detectors/``:

    gates.py         shared entry gates (deletion / substitution / neighbours)
    substitution.py  declarative SUBSTITUTION_SPECS table + shared scanner
    deletion.py      cluster / final / singleton consonant deletions
    voicing.py       panphon-based voicing errors (sole non-declarative case)
    hierarchy.py     ASHA clinical-hierarchy filter

This module is only the composition root: it runs the detectors in a
fixed order and owns no classification logic itself.

Operates on the 1-to-1 output of PhonemeForcedAligner:
  - "Deletions"     → the model predicted blank/silence for the slot
  - "Substitutions" → the model's top-1 predicted token differs from target

Every detector injects an internal ``_index`` key on each process dict
so the ASHA hierarchy filter can group by phoneme index rather than
parsing human-readable detail strings.  Multi-phoneme processes (weak
syllable deletion) inject ``_index`` as a list of indices; the key is
stripped from the final returned list.
"""

import logging

from detection.detectors.assimilation import detect_consonant_harmony
from detection.detectors.deletion import DELETION_DETECTORS
from detection.detectors.hierarchy import apply_clinical_hierarchy
from detection.detectors.substitution import SUBSTITUTION_SPECS, scan_substitutions
from detection.detectors.voicing import detect_voicing_errors
from detection.syllable import detect_weak_syllable_deletion, detect_reduplication
from .detectors.gates import run_safely

logger = logging.getLogger(__name__)


def _detect_phoneme_processes(breakdown: list[dict]) -> list[dict]:
    """Run all process detectors in a carefully ordered sequence.

    Execution order:
      1. Substitution & Assimilation detectors — collect ``_index``-tagged
         processes, including consonant harmony and panphon-based voicing
      2. Weak syllable deletion            — capture ``skip_indices``
      3. Micro-level deletion detectors    — results filtered by ``skip_indices``,
                                             so phonemes absorbed by syllable
                                             deletion are not redundantly reported
      4. ASHA hierarchy filter             — resolve remaining ``_index`` overlaps
                                             (e.g. Stopping vs Fronting on /ʃ/),
                                             then strip ``_index`` from output
    """
    if not breakdown:
        return []

    all_processes: list[dict] = []

    # ── 1. Substitution & Assimilation detectors ─────────────────────
    for spec in SUBSTITUTION_SPECS:
        all_processes.extend(run_safely(scan_substitutions, breakdown, spec))
    all_processes.extend(run_safely(detect_consonant_harmony, breakdown))
    all_processes.extend(run_safely(detect_voicing_errors, breakdown))

    # ── 2. Weak syllable deletion (capture skip indices) ──────────
    skip_indices: set[int] = set()
    try:
        ws_proc, skip_indices = detect_weak_syllable_deletion(breakdown)
        all_processes.extend(ws_proc)
    except Exception as exc:
        logger.warning("Weak syllable detection failed: %s", exc)

    # ── 2b. Reduplication (syllable-level copying) ────────────────
    all_processes.extend(run_safely(detect_reduplication, breakdown))

    # ── 3. Deletion detectors, filtered by skip_indices ───────────
    for detector in DELETION_DETECTORS:
        for r in run_safely(detector, breakdown):
            idx = r.get("_index")
            if idx is not None:
                if isinstance(idx, list):
                    # Multi-phoneme: trim indices absorbed by Weak
                    # Syllable Deletion; keep the event if any of its
                    # phonemes were not part of the deleted syllable
                    trimmed = [i for i in idx if i not in skip_indices]
                    if trimmed:
                        r["_index"] = trimmed
                        all_processes.append(r)
                elif idx not in skip_indices:
                    all_processes.append(r)
            else:
                all_processes.append(r)

    # ── 4. Apply ASHA hierarchy filter (strips _index) ────────────
    return apply_clinical_hierarchy(all_processes)


class ProcessDetector:
    """Detects phonological processes from forced-alignment breakdowns.

    The input ``breakdown`` is the ``phoneme_breakdown`` list from the
    AssessResponse, where each entry has ``expected``, ``predicted``,
    ``score``, and optionally ``duration_sec`` / ``confidence``.
    """

    def detect(self, breakdown: list[dict]) -> list[dict]:
        """Run all phonological process detectors."""
        return _detect_phoneme_processes(breakdown)
