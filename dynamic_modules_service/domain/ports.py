"""Ports (interfaces) for the dynamic modules service.

Defined in the domain so the dependency rule points inward:
application/infrastructure implement these, domain never imports them back.
"""

from typing import Optional, Protocol

from domain.models import (
    AssessmentFindings,
    FocusSound,
    LearningModule,
    ModuleOutline,
    PracticeItem,
    PracticeLevel,
)


class Outlines(Protocol):
    """Source of professional module outlines."""

    def outlines_for(self, focus_sounds: list[FocusSound]) -> list[ModuleOutline]:
        """Outlines relevant to the child's focus sounds, best match first."""
        ...

    def by_id(self, outline_id: str) -> Optional[ModuleOutline]:
        ...


class WordBank(Protocol):
    """Source of practice items (syllables/words/phrases/sentences)."""

    def items_for(self, level: PracticeLevel, target_sound: str) -> list[PracticeItem]:
        ...


class LLMClient(Protocol):
    """A chat-completions client (OpenCode Zen, OpenAI, Anthropic...)."""

    def complete(self, *, system: str, user: str) -> str:
        ...


class ModuleBuilder(Protocol):
    """Builds a LearningModule from findings + outlines + bank."""

    def build(
        self,
        *,
        findings: AssessmentFindings,
        outlines: list[ModuleOutline],
        bank: WordBank,
    ) -> LearningModule:
        ...
