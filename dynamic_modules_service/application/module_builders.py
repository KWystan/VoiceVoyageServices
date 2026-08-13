"""Module builders — implementations of the ModuleBuilder port.

RuleBasedModuleBuilder: deterministic fallback (no LLM needed).
LLMModuleBuilder: sends findings + outline pools to the LLM and uses its
humanlike selection (validated against the word bank).
"""

import uuid
from typing import Optional

from domain.models import (
    AssessmentFindings,
    FocusSound,
    LearningModule,
    ModuleOutline,
    PracticeItem,
    PracticeLevel,
)
from domain.ports import LLMClient, WordBank
from config import config


class NoOutlineError(Exception):
    """No professional outline exists for the child's focus sounds."""


class RuleBasedModuleBuilder:
    """Deterministic builder: fills each level from the outline pools."""

    def __init__(self, config=config):
        self._config = config

    def build(
        self,
        *,
        findings: AssessmentFindings,
        outlines: list[ModuleOutline],
        bank: WordBank,
    ) -> LearningModule:
        if not outlines:
            raise NoOutlineError("No outline matches the detected processes")
        outline = outlines[0]
        focus_sounds = [FocusSound(s, "Initial", outline.focus_process)
                        for s in outline.target_sounds]
        # only the child's OTHER error sounds are excluded from items —
        # the outline's own target sounds are expected inside the items
        from domain.findings import FindingsAnalyzer
        child_sounds = {s.sound for s in FindingsAnalyzer().focus_sounds(findings)}
        error_sounds = child_sounds - set(outline.target_sounds)

        levels = {}
        for level in self._config.levels_order:
            practice_level = PracticeLevel.from_value(level)
            pool = outline.levels.get(practice_level, ())
            picked = self._pick(pool, error_sounds)
            levels[practice_level] = picked

        return LearningModule(
            module_id=f"mod-{uuid.uuid4().hex[:8]}",
            focus_sounds=focus_sounds,
            focus_processes=[outline.focus_process],
            outline_id=outline.id,
            outline_title=outline.title,
            levels=levels,
            rationale=f"Practice /{', '.join(outline.target_sounds)}/ "
                      f"({outline.focus_process}) from syllables to sentences.",
            generated_by="rule-based",
        )

    def _pick(self, pool: tuple[PracticeItem, ...],
              error_sounds: set[str]) -> list[PracticeItem]:
        items = []
        for item in pool:
            if len(items) >= self._config.items_per_level:
                break
            if self._contains_other_error_sound(item, error_sounds):
                continue
            items.append(item)
        return items

    @staticmethod
    def _contains_other_error_sound(item: PracticeItem,
                                    error_sounds: set[str]) -> bool:
        if not item.phonemes or not error_sounds:
            return False
        sounds = {p.strip() for p in item.phonemes.split(",") if p.strip()}
        return bool(sounds & error_sounds)


class LLMModuleBuilder:
    """Builds the module from the LLM's humanlike selection."""

    def __init__(
        self,
        *,
        client: LLMClient,
        prompt_builder,
        parser,
        config=config,
    ):
        self._client = client
        self._prompt_builder = prompt_builder
        self._parser = parser
        self._config = config

    def build(
        self,
        *,
        findings: AssessmentFindings,
        outlines: list[ModuleOutline],
        bank: WordBank,
    ) -> LearningModule:
        if not outlines:
            raise NoOutlineError("No outline matches the detected processes")

        bank_items = {
            PracticeLevel.from_value(level): [
                {"text": it.text, "target_sound": it.target_sound,
                 "position": it.position, "phonemes": it.phonemes}
                for it in bank.items_for(PracticeLevel.from_value(level),
                                         outlines[0].target_sounds[0])
            ]
            for level in self._config.levels_order
        }
        system, user = self._prompt_builder.build(
            findings=findings, outlines=outlines, bank_items=bank_items)
        raw = self._client.complete(system=system, user=user)

        selection = self._parser.parse(
            raw,
            allowed_outline_ids={o.id for o in outlines},
            bank_lookup=bank.get,
        )
        outline = next(o for o in outlines if o.id == selection["outline_id"])
        focus_sounds = [FocusSound(s, "Initial", outline.focus_process)
                        for s in outline.target_sounds]

        return LearningModule(
            module_id=f"mod-{uuid.uuid4().hex[:8]}",
            focus_sounds=focus_sounds,
            focus_processes=[outline.focus_process],
            outline_id=outline.id,
            outline_title=outline.title,
            levels=selection["levels"],
            rationale=selection["rationale"],
            generated_by="llm",
        )
