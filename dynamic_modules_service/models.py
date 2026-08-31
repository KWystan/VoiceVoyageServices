"""Domain data for the dynamic modules service — plain dataclasses.

Zero framework imports: these stay testable in isolation.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PracticeLevel(str, Enum):
    """The four practice levels of a module, in clinical progression order."""
    SYLLABLE = "syllable"
    WORD = "word"
    PHRASE = "phrase"
    SENTENCE = "sentence"

    @classmethod
    def from_value(cls, value: str) -> "PracticeLevel":
        try:
            return cls(value)
        except ValueError:
            raise ValueError(
                f"Unknown practice level '{value}'; "
                f"expected one of {[lvl.value for lvl in cls]}"
            ) from None


@dataclass(frozen=True)
class DetectedProcess:
    """One phonological process detected by the phoneme service."""
    process: str
    position: str
    detail: str = ""
    target_sound: Optional[str] = None


@dataclass(frozen=True)
class AssessmentFindings:
    """The child's assessment results — the input to module building."""
    age: int
    processes: tuple[DetectedProcess, ...] = ()
    grade: Optional[str] = None


@dataclass(frozen=True)
class FocusSound:
    """A phoneme the child needs to practice, with its position."""
    sound: str
    position: str
    source_process: str


@dataclass(frozen=True)
class PracticeItem:
    """A single practice unit (syllable, word, phrase, or sentence).

    Text-only by design: the Flutter client has no per-word image/audio
    assets yet, so items carry their display text plus the phoneme-level
    metadata the LLM needs to make age- and finding-appropriate choices.
    """

    text: str
    level: PracticeLevel
    # Primary sound(s) this item practices (e.g. "s", "st", "θ") and where
    # it occurs (initial | medial | final | na).
    target_sound: str = ""
    position: str = ""
    # Comma-separated IPA (Wav2Vec2-validated spelling); used to avoid
    # items containing OTHER error sounds.
    phonemes: str = ""
    # Structural complexity: CV pattern / syllable count for words,
    # word count for phrases and sentences (e.g. "CVC", "2 syllables").
    syllable_complexity: str = ""
    # Related phonological processes this item targets (phoneme-service
    # process names, e.g. "Gliding", "Cluster Reduction").
    processes: tuple[str, ...] = ()
    # Grade levels the item suits (1 = ages 5-6, 2 = ages 6-7, 3 = age 8).
    grades: tuple[int, ...] = (1,)
    # Gameplay island/level reference from the grade-level docs.
    gameplay_level: str = ""


@dataclass(frozen=True)
class ModuleOutline:
    """A professional-authored practice template with planned material.

    ``levels`` pools are resolved from the word bank at load time; the
    rule-based builder further filters them by the child's grade and by
    other error sounds.
    """

    id: str
    title: str
    focus_process: str
    target_sounds: tuple[str, ...]
    grades: tuple[int, ...] = (1, 2, 3)
    gameplay_level: str = ""
    levels: dict[PracticeLevel, tuple[PracticeItem, ...]] = field(
        default_factory=dict)


@dataclass
class LearningModule:
    """The personalized practice module returned to the app."""
    module_id: str
    focus_sounds: list[FocusSound]
    focus_processes: list[str]
    outline_id: str
    outline_title: str
    levels: dict[PracticeLevel, list[PracticeItem]]
    rationale: str
    generated_by: str  # "llm" | "rule-based"
    grade: str = "Kinder"
    warning: Optional[str] = None
