"""
Phonological process detection for the forced-alignment pipeline.

Operates on the 1-to-1 output of PhonemeForcedAligner:
  - "Deletions"   → phoneme duration < min_phoneme_duration_sec
  - "Substitutions" → low-confidence phonemes where the model's top-1
                         predicted token differs from the target token
  - Clinical boost logic reuses panphon_module.lookup_boost()

Every detector injects an internal ``_index`` key on each process dict
so the ASHA hierarchy filter can group by phoneme index rather than
parsing human-readable detail strings.  Multi-phoneme processes (weak
syllable deletion) inject ``_index`` as a list of indices.

The ``_index`` key is stripped from the final returned list.

Design: substitution detectors are DECLARATIVE — one shared scanner
(``_scan_substitutions``) driven by the ``_SUBSTITUTION_SPECS`` table of
(process name, pure predicate).  Adding a new process = one table row +
one predicate, no copy-pasted loop.  The voicing detector is the one
exception (panphon features + position-dependent naming), so it stays a
dedicated function.
"""

import logging
from dataclasses import dataclass
from typing import Callable

from detection.utils import manner, place, is_consonant, get_position, same_phoneme
from detection.syllable import detect_weak_syllable_deletion
from config import config

logger = logging.getLogger(__name__)

# ── Panphon for voicing detection (lazy-loaded at module level) ─────
try:
    import panphon as _panphon  # type: ignore[import-untyped]
    _PANPHON_FT: object = _panphon.FeatureTable()
    _PANPHON_AVAILABLE: bool = True
except ImportError:
    _PANPHON_AVAILABLE = False
    _PANPHON_FT = None
    logger.warning("panphon not available; voicing detection disabled")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_deletion(item: dict) -> bool:
    """A phoneme is 'deleted' if too short OR the model predicted blank/silence."""
    if item.get("duration_sec", 1.0) < config.forced_alignment.min_phoneme_duration_sec:
        return True
    if item.get("predicted", "-") in ("-", None, ""):
        return True
    return False


def _is_substitution(item: dict) -> bool:
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
    if _is_deletion(item):
        return False  # too short → deletion, not substitution
    predicted = item.get("predicted", "-")
    if predicted in ("-", None, ""):
        return False  # no prediction available
    if same_phoneme(predicted, item.get("expected", "")):
        return False  # same phoneme (after alphabet translation) → not a substitution
    return True


def _has_consonant_neighbor(breakdown: list[dict], idx: int) -> tuple[bool, bool]:
    """Return (left_is_consonant, right_is_consonant) around ``idx``.

    Word-boundary (#) tokens are not consonants, so this is automatically
    correct across word edges.
    """
    left = idx > 0 and is_consonant(breakdown[idx - 1].get("expected", ""))
    right = idx < len(breakdown) - 1 and is_consonant(breakdown[idx + 1].get("expected", ""))
    return left, right


def _run_safely(detector_fn: Callable, breakdown: list[dict], *args) -> list[dict]:
    """Run a detector, converting any exception into a logged warning."""
    try:
        return detector_fn(breakdown, *args)
    except Exception as exc:
        logger.warning(
            "Process detector %s failed: %s",
            getattr(detector_fn, "__name__", "?"), exc,
        )
        return []


# ---------------------------------------------------------------------------
# Substitution predicates (pure: entry -> bool)
# ---------------------------------------------------------------------------

def _is_stopping(entry: dict) -> bool:
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


def _is_frication(entry: dict) -> bool:
    """Stop/nasal → fricative (reverse of Stopping; atypical, Red Flag)."""
    return (manner(entry["expected"]) in ("Stop", "Nasal")
            and manner(entry["predicted"]) == "Fricative")


def _is_deaffrication(entry: dict) -> bool:
    """Affricate → stop or fricative."""
    return (manner(entry["expected"]) == "Affricate"
            and manner(entry["predicted"]) in ("Stop", "Fricative"))


def _is_denasalization(entry: dict) -> bool:
    """Nasal → stop."""
    return (manner(entry["expected"]) == "Nasal"
            and manner(entry["predicted"]) == "Stop")


def _is_fronting(entry: dict) -> bool:
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


def _is_backing(entry: dict) -> bool:
    """Alveolar/labial → velar/palatal.  /ŋ/ as predicted is excluded."""
    exp, det = entry["expected"], entry["predicted"]
    exp_m, det_m = manner(exp), manner(det)
    if exp_m == "Vowel" or det_m == "Vowel":
        return False
    if det == "ŋ":
        return False
    exp_p, det_p = place(exp), place(det)
    return exp_p in ("Alveolar", "Labial") and det_p in ("Velar", "Palatal")


def _is_gliding(entry: dict) -> bool:
    """Liquid → glide."""
    return (manner(entry["expected"]) == "Liquid"
            and manner(entry["predicted"]) == "Glide")


def _is_liquidization(entry: dict) -> bool:
    """Glide → liquid (reverse of Gliding)."""
    return (manner(entry["expected"]) == "Glide"
            and manner(entry["predicted"]) == "Liquid")


def _is_vowelization(entry: dict) -> bool:
    """Liquid → vowel."""
    return (manner(entry["expected"]) == "Liquid"
            and manner(entry["predicted"]) == "Vowel")


# ---------------------------------------------------------------------------
# Substitution registry (declarative table)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SubstitutionSpec:
    """One row of the substitution-detector table."""
    process: str
    matches: Callable[[dict], bool]


_SUBSTITUTION_SPECS: tuple[SubstitutionSpec, ...] = (
    SubstitutionSpec("Stopping", _is_stopping),
    SubstitutionSpec("Frication", _is_frication),
    SubstitutionSpec("Deaffrication", _is_deaffrication),
    SubstitutionSpec("Denasalization", _is_denasalization),
    SubstitutionSpec("Fronting", _is_fronting),
    SubstitutionSpec("Backing", _is_backing),
    SubstitutionSpec("Gliding", _is_gliding),
    SubstitutionSpec("Liquidization", _is_liquidization),
    SubstitutionSpec("Vowelization", _is_vowelization),
)


def _scan_substitutions(
    breakdown: list[dict],
    spec: SubstitutionSpec,
) -> list[dict]:
    """Run one substitution spec over the breakdown (shared scanner)."""
    processes = []
    for i, entry in enumerate(breakdown):
        if entry.get("expected") == "#":
            continue
        if not _is_substitution(entry):
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


# ---------------------------------------------------------------------------
# Voicing errors (special: panphon features + position-dependent naming)
# ---------------------------------------------------------------------------

def _detect_voicing_errors(breakdown: list[dict]) -> list[dict]:
    """Detect prevocalic voicing and devoicing via panphon features.

    Uses module-level _PANPHON_FT (lazy-loaded at import time) instead
    of importing panphon on each call.

    Voiced→voiceless substitutions are labelled:
      - "Final Devoicing" when the phoneme is the last index in the word
      - "Devoicing" otherwise (Initial or Medial)

    NOTE: Prevocalic Voicing and Devoicing are separate processes
    on the SAME phoneme index (mutually exclusive by voicing direction).
    Both get the same ``_index`` value, and the hierarchy filter resolves
    the overlap if somehow both fire.
    """
    processes = []
    if not _PANPHON_AVAILABLE:
        return processes

    for i, entry in enumerate(breakdown):
        if entry.get("expected") == "#":
            continue
        if not _is_substitution(entry):
            continue
        exp_p, det_p = entry["expected"], entry["predicted"]
        if manner(exp_p) == "Vowel" or manner(det_p) == "Vowel":
            continue
        try:
            seg_exp = _PANPHON_FT.fts(exp_p)
            seg_det = _PANPHON_FT.fts(det_p)
            if not hasattr(seg_exp, "numeric") or not hasattr(seg_det, "numeric"):
                continue
            ev = seg_exp.numeric()
            dv = seg_det.numeric()
        except Exception:
            continue
        # index 8 = [voi] (voicing)
        ev_voice, dv_voice = ev[8], dv[8]
        if ev_voice != dv_voice:
            follow_vowel = (
                i < len(breakdown) - 1
                and manner(breakdown[i + 1]["expected"]) == "Vowel"
            )
            if ev_voice == -1 and dv_voice == 1 and follow_vowel:
                processes.append({
                    "process": "Prevocalic Voicing",
                    "position": get_position(i, breakdown),
                    "detail": f"/{exp_p}/ -> [{det_p}] (voiced before vowel)",
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


# ---------------------------------------------------------------------------
# Deletion detectors (each injects ``_index`` = phoneme index)
# ---------------------------------------------------------------------------

def _detect_cluster_reduction(breakdown: list[dict]) -> list[dict]:
    """Detect cluster reduction: consonant deleted in a consonant cluster.

    Strictly requires the deleted phoneme itself to be a consonant
    (deleted vowels may not trigger cluster reduction).  Word-boundary
    (#) tokens naturally block cross-word adjacency since
    ``is_consonant("#")`` returns ``False``.
    """
    processes = []
    for i, entry in enumerate(breakdown):
        if entry.get("expected") == "#":
            continue
        if not _is_deletion(entry):
            continue
        # A deleted vowel is never cluster reduction
        if not is_consonant(entry.get("expected", "")):
            continue
        left, right = _has_consonant_neighbor(breakdown, i)
        if left or right:
            processes.append({
                "process": "Cluster Reduction",
                "position": get_position(i, breakdown),
                "detail": f"/{entry['expected']}/ deleted (-> Ø) in cluster",
                "_index": i,
            })
    return processes


def _detect_final_consonant_deletion(breakdown: list[dict]) -> list[dict]:
    """Detect final consonant deletion: word-final consonant deleted.

    Iterates over every entry and checks word-relative position via
    ``get_position(i, breakdown)``, making it correct for multi-word
    phrases where multiple word-final positions exist.
    """
    processes = []
    for i, entry in enumerate(breakdown):
        if entry.get("expected") == "#":
            continue
        if not _is_deletion(entry):
            continue
        if not is_consonant(entry.get("expected", "")):
            continue
        if get_position(i, breakdown) != "Final":
            continue
        processes.append({
            "process": "Final Consonant Deletion",
            "position": "Final",
            "detail": f"/{entry['expected']}/ deleted (-> Ø) word-finally",
            "_index": i,
        })
    return processes


def _detect_consonant_deletion(breakdown: list[dict]) -> list[dict]:
    """Detect singleton consonant deletion (not in cluster, not word-final)."""
    processes = []
    for i, entry in enumerate(breakdown):
        if entry.get("expected") == "#":
            continue
        if not _is_deletion(entry):
            continue
        if not is_consonant(entry.get("expected", "")):
            continue
        # Skip cluster deletions — handled by Cluster Reduction
        left, right = _has_consonant_neighbor(breakdown, i)
        if left or right:
            continue
        # Skip word-final — handled by Final Consonant Deletion
        if get_position(i, breakdown) == "Final":
            continue
        processes.append({
            "process": "Consonant Deletion",
            "position": get_position(i, breakdown),
            "detail": f"/{entry['expected']}/ deleted (-> Ø) singleton consonant",
            "_index": i,
        })
    return processes


# ---------------------------------------------------------------------------
# ASHA Clinical Hierarchy
# ---------------------------------------------------------------------------
# When multiple processes fire for the same phoneme index, only the most
# clinically significant one is retained.  Grouping is done by the
# ``_index`` key (set by every detector) instead of regex-parsing the
# human-readable ``detail`` string.
#
# Based on ASHA developmental norms:
#   manner changes > place changes > sonority changes > voicing > deletions
# Reference: https://www.asha.org/practice-portal/clinical-topics/
#            speech-sound-disorders-articulation-and-phonology/

_ASHA_HIERARCHY: dict[str, int] = {
    "Weak Syllable Deletion": 1,
    "Stopping": 2,
    "Frication": 3,
    "Deaffrication": 4,
    "Denasalization": 5,
    "Fronting": 6,
    "Backing": 7,
    "Gliding": 8,
    "Liquidization": 9,
    "Vowelization": 10,
    "Prevocalic Voicing": 11,
    "Devoicing": 12,
    "Final Devoicing": 12,
    "Cluster Reduction": 13,
    "Final Consonant Deletion": 14,
    "Consonant Deletion": 15,
}


def _apply_clinical_hierarchy(processes: list[dict]) -> list[dict]:
    """Filter overlapping processes using ASHA clinical hierarchy.

    Groups detected processes by their ``_index`` key (set by each
    detector at fire-time).  When multiple processes target the same
    phoneme index, only the highest-priority one (lowest number in
    ``_ASHA_HIERARCHY``) is retained.

    The internal ``_index`` key is stripped from all returned dicts
    so the API response schema stays clean.

    Args:
        processes: Raw list of process dicts from all detectors.

    Returns:
        Filtered list with at most one process per phoneme index.
    """
    if not processes:
        return []

    if len(processes) == 1:
        processes[0].pop("_index", None)
        return processes

    # Group by _index key.  List indices (from syllable-level processes)
    # are normalised to tuples for dict-key compatibility.
    by_index: dict[tuple | int | str, list[dict]] = {}
    for proc in processes:
        key = proc.get("_index")
        if key is None:
            key = "__none__"
        elif isinstance(key, list):
            key = tuple(key)
        by_index.setdefault(key, []).append(proc)

    filtered: list[dict] = []
    for _index_key, procs in by_index.items():
        if len(procs) == 1:
            filtered.append(procs[0])
        else:
            # Sort by ASHA priority (lower number = higher priority)
            procs.sort(key=lambda p: _ASHA_HIERARCHY.get(p["process"], 99))
            kept = procs[0]
            filtered.append(kept)

            for dropped in procs[1:]:
                logger.debug(
                    "Hierarchy filter: kept '%s' over '%s' for index=%s "
                    "(ASHA priority %d vs %d)",
                    kept["process"], dropped["process"], _index_key,
                    _ASHA_HIERARCHY.get(kept["process"], 99),
                    _ASHA_HIERARCHY.get(dropped["process"], 99),
                )

    # Strip internal _index key before returning
    for proc in filtered:
        proc.pop("_index", None)

    return filtered


# ---------------------------------------------------------------------------
# Master detection
# ---------------------------------------------------------------------------

def _detect_phoneme_processes(breakdown: list[dict]) -> list[dict]:
    """Run all process detectors in a carefully ordered sequence.

    Execution order:
      1. Substitution detectors (table-driven) — collect ``_index``-tagged
         processes, including the panphon-based voicing detector
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

    # ── 1. Substitution detectors (declarative table + voicing) ──────
    for spec in _SUBSTITUTION_SPECS:
        all_processes.extend(_run_safely(_scan_substitutions, breakdown, spec))
    all_processes.extend(_run_safely(_detect_voicing_errors, breakdown))

    # ── 2. Weak syllable deletion (capture skip indices) ──────────
    skip_indices: set[int] = set()
    try:
        ws_proc, skip_indices = detect_weak_syllable_deletion(breakdown)
        all_processes.extend(ws_proc)
    except Exception as exc:
        logger.warning("Weak syllable detection failed: %s", exc)

    # ── 3. Deletion detectors, filtered by skip_indices ───────────
    deletion_detectors = (
        _detect_cluster_reduction,
        _detect_final_consonant_deletion,
        _detect_consonant_deletion,
    )
    for detector in deletion_detectors:
        for r in _run_safely(detector, breakdown):
            idx = r.get("_index")
            if idx is not None:
                if isinstance(idx, list):
                    # Multi-phoneme: keep only if none of its indices
                    # overlap with skip_indices
                    if not any(i in skip_indices for i in idx):
                        all_processes.append(r)
                elif idx not in skip_indices:
                    all_processes.append(r)
            else:
                all_processes.append(r)

    # ── 4. Apply ASHA hierarchy filter (strips _index) ────────────
    all_processes = _apply_clinical_hierarchy(all_processes)

    return all_processes


class ProcessDetector:
    """Detects phonological processes from forced-alignment breakdowns.

    The input ``breakdown`` is the ``phoneme_breakdown`` list from the
    AssessResponse, where each entry has ``expected``, ``predicted``,
    ``score``, and optionally ``duration_sec`` / ``confidence``.
    """

    def detect(self, breakdown: list[dict]) -> list[dict]:
        """Run all phonological process detectors."""
        return _detect_phoneme_processes(breakdown)
