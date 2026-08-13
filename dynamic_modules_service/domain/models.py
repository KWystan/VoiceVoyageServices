"""Domain model for the dynamic modules service — pure value objects.

Zero framework imports: this module must stay testable in isolation.
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
    pcc: Optional[float] = None


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
    target_sound: str
    position: str = ""
    phonemes: str = ""  # comma-separated; used to avoid other error sounds


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
