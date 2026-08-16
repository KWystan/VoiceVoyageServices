from .utils import clean, manner
from config import config


def _fix_coda_onsets(syllables, alignment):
    """Post-process syllable boundaries to fix coda/onset splits.

    Two rules:
    1. If a syllable is just a single consonant with no vowel (trailing
       coda), merge it into the previous syllable.
    2. If a syllable is JUST a single vowel, and the next syllable starts
       with 2+ consonants, move the first consonant of the next syllable
       as coda so the weak syllable detector catches the full coda.
    """
    if len(syllables) < 2:
        return syllables

    fixed = [list(syllables[0])]
    for i in range(1, len(syllables)):
        prev = fixed[-1]
        curr = list(syllables[i])

        # Rule 1: trailing coda (single consonant, no vowel)
        if (len(curr) == 1
            and manner(alignment[curr[0]]["expected"]) not in ("Vowel", None)):
            prev.extend(curr)
            continue

        # Rule 2: single-vowel prev + multi-cons curr -> move first as coda
        if (len(prev) == 1
            and len(curr) >= 2
            and manner(alignment[prev[0]]["expected"]) == "Vowel"
            and manner(alignment[curr[0]]["expected"]) not in ("Vowel", None)):
            prev.append(curr.pop(0))

        fixed.append(curr)

    return fixed


def find_syllables(alignment):
    """Group alignment into syllables by vowel nuclei.

    First pass: each vowel nucleus (and everything before it) forms a
    syllable. After the last vowel, trailing consonants are appended as
    coda to the final syllable.

    Second pass (_fix_coda_onsets): corrects coda/onset boundary splits.

    Returns:
        list of index lists - each sublist contains indices belonging to
        one syllable.
    """
    syllables = []
    current = []

    for i, entry in enumerate(alignment):
        # Hard break on word boundaries — # is silent, not a spoken phoneme
        if entry.get("expected") == "#":
            if current:
                syllables.append(current)
                current = []
            continue
        current.append(i)
        if manner(entry["expected"]) == "Vowel":
            syllables.append(current)
            current = []

    if current:
        if syllables:
            syllables[-1].extend(current)
        else:
            syllables.append(current)

    return _fix_coda_onsets(syllables, alignment)


def detect_weak_syllable_deletion(alignment):
    """Detect weak syllable deletion.

    Returns:
        (processes, skip_indices) - list of process dicts and set of indices to skip.
    """
    processes = []
    skip_indices = set()
    syllables = find_syllables(alignment)

    # Weak Syllable Deletion requires a multisyllabic word — a single
    # syllable cannot be "weak" relative to another.  Guard so e.g. a
    # fully-deleted "dog" is not reported as Weak Syllable Deletion.
    if len(syllables) < 2:
        return processes, skip_indices

    for i, indices in enumerate(syllables):
        vowel_deleted = False
        syllable_parts = []

        for idx in indices:
            entry = alignment[idx]
            ph = clean(entry["expected"])
            if ph == "-":
                continue
            syllable_parts.append(ph)

            if manner(entry["expected"]) == "Vowel":
                if entry.get("duration_sec", 1.0) < config.forced_alignment.min_phoneme_duration_sec or entry.get("predicted") in ("-", None, ""):
                    vowel_deleted = True

        # Syllable deleted only if the vowel nucleus is gone
        if vowel_deleted:
            pos = "Initial" if i == 0 else "Final" if i == len(syllables) - 1 else "Medial"
            processes.append({
                "process": "Weak Syllable Deletion",
                "position": pos,
                "detail": f"Syllable '{''.join(syllable_parts)}' deleted",
                "_index": list(indices),
            })
            for idx in indices:
                skip_indices.add(idx)

    return processes, skip_indices