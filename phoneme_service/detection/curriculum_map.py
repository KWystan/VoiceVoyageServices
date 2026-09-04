"""Educational labels for detected speech-sound observations.

This adapter intentionally does not diagnose, assign a severity, or apply a
universal age cut-off. ASHA and the McLeod reviews describe variability across
languages, dialects, tasks, and speakers; those references are not a
Philippine diagnostic norm. Age is retained in the function signature for API
compatibility and for callers that use it to select learning content.

The legacy clinical_status key is retained for clients that already read it.
Its values are now bounded, descriptive labels rather than clinical
conclusions.
"""

import re


def _years_to_bracket(age_years: int) -> str:
    """Return a coarse educational age band for compatibility only."""

    if age_years <= 4:
        return "Age 4"
    if age_years == 5:
        return "Age 5"
    if age_years <= 7:
        return "Age 6-7"
    return "Age 8"


def _parse_detail(detail: str) -> tuple[str, str]:
    """Parse detector detail into expected and produced symbols."""

    match = re.match(r"/(.+?)/\s*->\s*\[(.+?)\]", detail or "")
    if match:
        return match.group(1), match.group(2)

    match = re.match(r"/(.+?)/\s*deleted", detail or "")
    if match:
        return match.group(1), "-"

    match = re.match(r"Syllables?\s+'(.+?)'\s+reduplicated", detail or "")
    if match:
        return match.group(1), "-"

    return "", ""


def _extract_syllable(detail: str) -> str:
    match = re.search(r"Syllable\s+'([^']+)'\s+deleted", detail or "")
    return match.group(1) if match else ""


def _display_label(process: dict, expected: str) -> str:
    """Normalize only presentation labels; preserve the detector process."""

    name = str(process.get("process", "")).strip()
    if name == "Fronting" and expected in {"ʃ", "ʒ"}:
        return "Palatal Fronting"
    if name == "Stopping" and expected in {
        "m",
        "n",
        "ŋ",
        "p",
        "b",
        "t",
        "d",
        "k",
        "g",
    }:
        return "Frication"
    return name


def _observation(
    *,
    process: dict,
    expected: str,
    predicted: str,
) -> dict:
    label = _display_label(process, expected)
    return {
        "target_sound": f"/{expected}/",
        "child_produced": f"[{predicted}]",
        "display_label": label,
        # Compatibility key; deliberately non-diagnostic.
        "clinical_status": "Practice observation",
        "position": process.get("position", "Unknown"),
    }


def get_curriculum_summary(
    processes: list[dict],
    age_years: int = 4,
) -> list[dict]:
    """Return all parseable observations for educational content selection.

    A process is not removed because of the child's age. Age-of-acquisition
    studies are used elsewhere to order optional practice difficulty, not as
    an automatic expected/delayed/atypical decision rule.
    """

    # Keep the argument part of the stable public API without treating age as
    # a diagnostic gate.
    _ = age_years
    observations: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()

    for process in processes:
        expected, predicted = _parse_detail(process.get("detail", ""))
        if not expected and process.get("process") == "Weak Syllable Deletion":
            expected = _extract_syllable(process.get("detail", "")) or "syllable"
            predicted = "-"
        if not expected:
            continue

        item = _observation(
            process=process,
            expected=expected,
            predicted=predicted,
        )
        key = (
            item["display_label"],
            item["target_sound"],
            item["child_produced"],
            item["position"],
        )
        if key not in seen:
            observations.append(item)
            seen.add(key)

    return observations
