"""ASHA clinical hierarchy — resolves overlapping process detections.

When several processes fire for the same phoneme index, only the most
clinically significant one is retained:

    manner changes > place changes > sonority changes > voicing > deletions

Reference: https://www.asha.org/practice-portal/clinical-topics/
           speech-sound-disorders-articulation-and-phonology/
"""

import logging

logger = logging.getLogger(__name__)

ASHA_HIERARCHY: dict[str, int] = {
    "Weak Syllable Deletion": 1,
    "Reduplication": 1,
    "Stopping": 2,
    "Frication": 3,
    "Deaffrication": 4,
    "Denasalization": 5,
    "Fronting": 6,
    "Consonant Harmony": 7,
    "Backing": 8,
    "Gliding": 9,
    "Liquidization": 10,
    "Vowelization": 11,
    "Prevocalic Voicing": 12,
    "Voicing": 13,
    "Devoicing": 13,
    "Final Devoicing": 13,
    "Cluster Reduction": 14,
    "Final Consonant Deletion": 15,
    "Initial Consonant Deletion": 16,
    "Medial Consonant Deletion": 16,
}


def apply_clinical_hierarchy(processes: list[dict]) -> list[dict]:
    """Filter overlapping processes using ASHA clinical hierarchy.

    Groups detected processes by their ``_index`` key (set by each
    detector at fire-time).  When multiple processes target the same
    phoneme index, only the highest-priority one (lowest number in
    ``ASHA_HIERARCHY``) is retained.

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
            procs.sort(key=lambda p: ASHA_HIERARCHY.get(p["process"], 99))
            kept = procs[0]
            filtered.append(kept)

            for dropped in procs[1:]:
                logger.debug(
                    "Hierarchy filter: kept '%s' over '%s' for index=%s "
                    "(ASHA priority %d vs %d)",
                    kept["process"], dropped["process"], _index_key,
                    ASHA_HIERARCHY.get(kept["process"], 99),
                    ASHA_HIERARCHY.get(dropped["process"], 99),
                )

    # Strip internal _index key before returning
    for proc in filtered:
        proc.pop("_index", None)

    return filtered
