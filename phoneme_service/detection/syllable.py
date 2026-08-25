from .utils import clean, manner, canonicalize, same_phoneme, get_position


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
                # Deleted nucleus = the model heard silence there.  A short
                # segment with a resolved token is a real (fast) production,
                # not a swallowed syllable.
                if entry.get("predicted") in ("-", None, ""):
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


def _split_words(alignment):
    """Split alignment index lists on '#' boundary tokens."""
    words, current = [], []
    for i, entry in enumerate(alignment):
        if entry.get("expected") == "#":
            if current:
                words.append(current)
                current = []
            continue
        current.append(i)
    if current:
        words.append(current)
    return words


def detect_reduplication(alignment):
    """Detect total reduplication (syllable-level copying).

    Fires when a multisyllabic target is produced as two or more
    IDENTICAL syllables that are NOT already identical in the target,
    with at least one target slot simplified, substituted, or deleted:

        water  /w ɔ t ə r/   -> [w ɑ w ɑ]
        blanket /b l æ ŋ k ɪ t/ -> [b æ b æ]
        cookie /k ʊ k i/     -> [k u k u]

    Suppression age is ~3;0, so any detection at screening ages is
    persistent by definition; the curriculum layer labels it
    "Clinically Significant (Delayed)".

    Returns a list of process dicts whose ``_index`` is the list of
    changed target slots.
    """
    processes = []
    for idxs in _split_words(alignment):
        if len(idxs) < 2:
            continue

        # 1. target must be multisyllabic
        tsylls = find_syllables([{"expected": alignment[i]["expected"]} for i in idxs])
        if len(tsylls) < 2:
            continue

        # predicted production, blanks dropped
        pred = [alignment[i].get("predicted") for i in idxs]
        pred_toks = [p for p in pred if p not in ("-", None, "")]
        if len(pred_toks) < 2:
            continue

        # 2. predicted production = identical repeated syllables
        psylls = find_syllables([{"expected": p} for p in pred_toks])
        if len(psylls) < 2:
            continue
        sigs = {tuple(canonicalize(pred_toks[j]) for j in s) for s in psylls}
        if len(sigs) != 1:
            continue

        # 3. repetition must NOT already be present in the target
        esigs = {tuple(canonicalize(alignment[idxs[j]]["expected"]) for j in s)
                 for s in tsylls}
        if len(esigs) == 1:
            continue

        # 4. at least one slot simplified / substituted / deleted
        changed = [i for k, i in enumerate(idxs)
                   if pred[k] in ("-", None, "")
                   or not same_phoneme(pred[k], alignment[i]["expected"])]
        if not changed:
            continue

        syl_text = "".join(pred_toks[j] for s in psylls for j in s)
        processes.append({
            "process": "Reduplication",
            "position": get_position(changed[0], alignment),
            "detail": f"Syllables '{syl_text}' reduplicated",
            "_index": changed,
        })
    return processes