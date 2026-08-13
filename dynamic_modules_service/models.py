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


@dataclass(frozen=True)
class FocusSound:
    """A phoneme the child needs to practice, with its position."""
    sound: str
    position: str
    source_process: str


@dataclass(frozen=True)
class PracticeItem:
    """A single practice unit (syllable, word, phrase, or sentence)."""
    text: str
    level: PracticeLevel
    target_sound: str = ""
    position: str = ""
    phonemes: str = ""  # comma-separated; used to avoid other error sounds
    theme: str = "general"  # "ocean" | "general" — matches the app's theme


@dataclass(frozen=True)
class ModuleOutline:
    """A professional-authored practice template with planned material."""
    id: str
    title: str
    focus_process: str
    target_sounds: tuple[str, ...]
    levels: dict[PracticeLevel, tuple[PracticeItem, ...]]


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
    warning: Optional[str] = None


@dataclass(frozen=True)
class AshaGroup:
    """One phoneme/process group from the ASHA word list, by position."""
    phonemes: str
    initial: tuple[str, ...] = ()
    medial: tuple[str, ...] = ()
    final: tuple[str, ...] = ()


@dataclass(frozen=True)
class AshaErrorPattern:
    """'If they say X -> display label Y' row from the ASHA lists."""
    word_group: str
    words: tuple[str, ...]
    if_they_say: str
    display_label: str


@dataclass(frozen=True)
class AshaBracket:
    """The ASHA word list + process context for one age bracket."""
    name: str
    focus: str
    groups: tuple[AshaGroup, ...] = ()
    error_patterns: tuple[AshaErrorPattern, ...] = ()
