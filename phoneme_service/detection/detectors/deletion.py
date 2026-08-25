"""Deletion detectors — consonants missing from the child's audio.

Three scanners with mutually exclusive scopes; word-relative positions
come from ``get_position`` (boundary ``#`` aware), so multi-word
phrases are handled naturally.
"""

from detection.utils import get_position, is_consonant
from .gates import has_consonant_neighbor, is_deletion


def _deleted_consonant_runs(breakdown: list[dict]) -> list[list[int]]:
    """Group indices of contiguously deleted consonants into runs.

    Adjacent deleted consonants (no vowel / ``#`` between them) form one
    run — clinically a single deletion event, whether it is read as
    cluster reduction (onset/coda partially kept) or final consonant
    deletion (whole coda gone).
    """
    runs: list[list[int]] = []
    run: list[int] = []
    for i, entry in enumerate(breakdown):
        deleted_consonant = (
            entry.get("expected") != "#"
            and is_deletion(entry)
            and is_consonant(entry.get("expected", ""))
        )
        if deleted_consonant and (not run or run[-1] == i - 1):
            run.append(i)
            continue
        if run:
            runs.append(run)
        run = [i] if deleted_consonant else []
    if run:
        runs.append(run)
    return runs


def detect_cluster_reduction(breakdown: list[dict]) -> list[dict]:
    """Detect cluster reduction: consonant(s) deleted in a consonant cluster.

    Strictly requires the deleted phonemes themselves to be consonants
    (deleted vowels may not trigger cluster reduction).  Word-boundary
    (#) tokens naturally block cross-word adjacency since
    ``is_consonant("#")`` returns ``False``.

    Contiguous deleted consonants merge into ONE clinical event:
    deleting a whole onset cluster ("stop" -> [ɑp]) is a single
    reduction of /st/, not two separate errors.  A merged event's
    ``_index`` is the full index list (the ASHA hierarchy understands
    list indices); singleton deletions keep the single-index shape and
    the original detail format.
    """
    processes: list[dict] = []
    for run in _deleted_consonant_runs(breakdown):
        if len(run) == 1:
            i = run[0]
            left, right = has_consonant_neighbor(breakdown, i)
            if not (left or right):
                continue  # singleton deletion — other detectors own it
            processes.append({
                "process": "Cluster Reduction",
                "position": get_position(i, breakdown),
                "detail": f"/{breakdown[i]['expected']}/ deleted (-> Ø) in cluster",
                "_index": i,
            })
        else:
            phonemes = ",".join(breakdown[i]["expected"] for i in run)
            processes.append({
                "process": "Cluster Reduction",
                "position": get_position(run[0], breakdown),
                "detail": f"/{phonemes}/ deleted in cluster",
                "_index": list(run),
            })
    return processes


def detect_final_consonant_deletion(breakdown: list[dict]) -> list[dict]:
    """Detect final consonant deletion: word-final consonant(s) deleted.

    Iterates over every entry and checks word-relative position via
    ``get_position(i, breakdown)``, making it correct for multi-word
    phrases where multiple word-final positions exist.  Contiguous
    deleted consonants merge into one event — a fully deleted coda
    cluster ("milk" -> [mɪ]) is one clinical deletion, not two.
    """
    processes = []
    for run in _deleted_consonant_runs(breakdown):
        if get_position(run[0], breakdown) != "Final":
            continue
        if len(run) == 1:
            i = run[0]
            processes.append({
                "process": "Final Consonant Deletion",
                "position": "Final",
                "detail": f"/{breakdown[i]['expected']}/ deleted (-> Ø) word-finally",
                "_index": i,
            })
        else:
            phonemes = ",".join(breakdown[i]["expected"] for i in run)
            processes.append({
                "process": "Final Consonant Deletion",
                "position": "Final",
                "detail": f"/{phonemes}/ deleted word-finally",
                "_index": list(run),
            })
    return processes


def detect_initial_consonant_deletion(breakdown: list[dict]) -> list[dict]:
    """Detect initial consonant deletion: word-initial singleton consonant
    omitted (not a cluster member, not final)."""
    processes = []
    for i, entry in enumerate(breakdown):
        if entry.get("expected") == "#":
            continue
        if not is_deletion(entry):
            continue
        if not is_consonant(entry.get("expected", "")):
            continue
        # Skip cluster deletions — handled by Cluster Reduction
        left, right = has_consonant_neighbor(breakdown, i)
        if left or right:
            continue
        # Skip word-final — handled by Final Consonant Deletion
        if get_position(i, breakdown) == "Final":
            continue
        if get_position(i, breakdown) != "Initial":
            continue
        processes.append({
            "process": "Initial Consonant Deletion",
            "position": "Initial",
            "detail": f"/{entry['expected']}/ deleted (-> Ø) word-initially",
            "_index": i,
        })
    return processes


def detect_medial_consonant_deletion(breakdown: list[dict]) -> list[dict]:
    """Detect medial consonant deletion: word-medial singleton consonant
    omitted between vowels (not a cluster member, not final)."""
    processes = []
    for i, entry in enumerate(breakdown):
        if entry.get("expected") == "#":
            continue
        if not is_deletion(entry):
            continue
        if not is_consonant(entry.get("expected", "")):
            continue
        # Skip cluster deletions — handled by Cluster Reduction
        left, right = has_consonant_neighbor(breakdown, i)
        if left or right:
            continue
        # Skip word-final — handled by Final Consonant Deletion
        if get_position(i, breakdown) == "Final":
            continue
        if get_position(i, breakdown) != "Medial":
            continue
        processes.append({
            "process": "Medial Consonant Deletion",
            "position": "Medial",
            "detail": f"/{entry['expected']}/ deleted (-> Ø) word-medially",
            "_index": i,
        })
    return processes


# Registry consumed by the orchestrator — adding a deletion detector here
# wires it into the pipeline (with skip_indices filtering) automatically.
DELETION_DETECTORS = (
    detect_cluster_reduction,
    detect_final_consonant_deletion,
    detect_initial_consonant_deletion,
    detect_medial_consonant_deletion,
)
