"""Voicing-error detector — the one non-declarative substitution.

Voicing needs raw panphon features (not manner/place labels), so it
keeps a dedicated scanner.  The panphon table is lazy-loaded once at
import; if panphon is unavailable, voicing detection is disabled.
"""

import logging

from detection.utils import get_position, manner
from .gates import is_substitution

logger = logging.getLogger(__name__)

# ── Panphon (lazy-loaded at module level) ───────────────────────────
try:
    import panphon as _panphon  # type: ignore[import-untyped]
    PANPHON_FT: object = _panphon.FeatureTable()
    PANPHON_AVAILABLE: bool = True
except ImportError:
    PANPHON_AVAILABLE = False
    PANPHON_FT = None
    logger.warning("panphon not available; voicing detection disabled")


def detect_voicing_errors(breakdown: list[dict]) -> list[dict]:
    """Detect voicing-direction errors via panphon features.

    Uses module-level PANPHON_FT (lazy-loaded at import time) instead
    of importing panphon on each call.

    Voiceless→voiced substitutions are labelled:
      - "Prevocalic Voicing" when the next phoneme is a vowel
        (the classic developmental pattern)
      - "Voicing" everywhere else (e.g. "plane" -> [beɪn], where /p/
        is voiced before the cluster-mate /l/)

    Voiced→voiceless substitutions are labelled:
      - "Final Devoicing" when the phoneme is the last index in the word
      - "Devoicing" otherwise (Initial or Medial)

    NOTE: all four labels are mutually exclusive on the SAME phoneme
    index (voicing direction + position); each gets the same ``_index``
    value, and the hierarchy filter resolves any residual overlap.
    """
    processes = []
    if not PANPHON_AVAILABLE:
        return processes

    for i, entry in enumerate(breakdown):
        if entry.get("expected") == "#":
            continue
        if not is_substitution(entry):
            continue
        exp_p, det_p = entry["expected"], entry["predicted"]
        if manner(exp_p) == "Vowel" or manner(det_p) == "Vowel":
            continue
        try:
            seg_exp = PANPHON_FT.fts(exp_p)
            seg_det = PANPHON_FT.fts(det_p)
            if not hasattr(seg_exp, "numeric") or not hasattr(seg_det, "numeric"):
                continue
            ev = seg_exp.numeric()
            dv = seg_det.numeric()
        except Exception:
            continue
        # index 8 = [voi] (voicing)
        ev_voice, dv_voice = ev[8], dv[8]
        if ev_voice != dv_voice:
            if ev_voice == -1 and dv_voice == 1:
                follow_vowel = (
                    i < len(breakdown) - 1
                    and manner(breakdown[i + 1]["expected"]) == "Vowel"
                )
                if follow_vowel:
                    processes.append({
                        "process": "Prevocalic Voicing",
                        "position": get_position(i, breakdown),
                        "detail": f"/{exp_p}/ -> [{det_p}] (voiced before vowel)",
                        "_index": i,
                    })
                else:
                    processes.append({
                        "process": "Voicing",
                        "position": get_position(i, breakdown),
                        "detail": f"/{exp_p}/ -> [{det_p}] (voiced)",
                        "_index": i,
                    })
            elif ev_voice == 1 and dv_voice == -1:
                is_final = get_position(i, breakdown) == "Final"
                proc_name = "Final Devoicing" if is_final else "Devoicing"
                processes.append({
                    "process": proc_name,
                    "position": get_position(i, breakdown),
                    "detail": f"/{exp_p}/ -> [{det_p}] (devoiced)",
                    "_index": i,
                })
    return processes
