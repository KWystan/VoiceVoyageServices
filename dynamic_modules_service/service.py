"""ModuleService — the use case: findings -> personalized practice module.

Orchestrates: analyze findings -> match outlines -> build via the primary
builder (LLM when configured, rule-based otherwise) -> graceful fallback
to rule-based on any LLM failure.

The LLM path feeds the child's age bracket + detected processes + the
grade-level gameplay Markdown documents + the metadata-rich word bank, and
follows the grade progression guidance in those documents.  All module
content is text-only (the Flutter client has no per-word assets yet).
"""

import re
import uuid
from typing import Optional

from config import config as default_config
from data import GradeDocuments
from models import (
    AssessmentFindings,
    FocusSound,
    LearningModule,
    ModuleOutline,
    PracticeItem,
    PracticeLevel,
)

_DETAIL_TARGET_RE = re.compile(r"/([^/]+)/")


class NoFindingsError(Exception):
    """No focus sounds could be extracted from the findings."""


class NoOutlineError(Exception):
    """No professional outline exists for the child's focus sounds."""


class FindingsAnalyzer:
    """Turns detected processes into practice focus sounds (deduplicated)."""

    def focus_sounds(self, findings: AssessmentFindings) -> list[FocusSound]:
        seen: set[tuple[str, str]] = set()
        result: list[FocusSound] = []
        for proc in findings.processes:
            sound = proc.target_sound or self._parse_target_sound(proc.detail)
            if not sound:
                continue
            key = (sound, proc.position or "")
            if key in seen:
                continue
            seen.add(key)
            result.append(FocusSound(sound=sound, position=proc.position or "",
                                     source_process=proc.process))
        return result

    @staticmethod
    def _parse_target_sound(detail: str) -> Optional[str]:
        match = _DETAIL_TARGET_RE.search(detail or "")
        return match.group(1) if match else None


class OutlineSelector:
    """Picks the most relevant outline for the child's focus sounds."""

    def best(self, outlines: list[ModuleOutline],
             focus_sounds: list[FocusSound]) -> Optional[ModuleOutline]:
        if not outlines:
            return None
        focus = {s.sound for s in focus_sounds}
        return max(outlines, key=lambda o: len(focus & set(o.target_sounds)))


class RuleBasedModuleBuilder:
    """Deterministic builder: fills each level from the outline pools,
    filtered to the child's grade and free of the child's OTHER error
    sounds.  Items carry their bank metadata (target sound, position,
    gameplay level)."""

    def __init__(self, config=default_config):
        self._config = config

    def build(self, *, findings, outlines, bank,
              grade_document=None) -> LearningModule:
        if not outlines:
            raise NoOutlineError("No outline matches the detected processes")
        outline = outlines[0]
        grade = GradeDocuments().grade_for_age(findings.age)
        child_focus = FindingsAnalyzer().focus_sounds(findings)
        focus_sounds = [fs for fs in child_focus
                        if fs.sound in outline.target_sounds] or [
            FocusSound(s, "Initial", outline.focus_process)
            for s in outline.target_sounds]
        # only the child's OTHER error sounds are excluded from items —
        # the outline's own target sounds are expected inside the items
        child_sounds = {s.sound for s in child_focus}
        error_sounds = child_sounds - set(outline.target_sounds)

        levels = {}
        for level in self._config.levels_order:
            pool = [it for it in outline.levels.get(
                PracticeLevel.from_value(level), ())
                if grade in it.grades]
            levels[PracticeLevel.from_value(level)] = self._pick(
                pool, error_sounds, child_focus)

        return LearningModule(
            module_id=f"mod-{uuid.uuid4().hex[:8]}",
            focus_sounds=focus_sounds,
            focus_processes=[outline.focus_process],
            outline_id=outline.id,
            outline_title=outline.title,
            levels=levels,
            rationale=(
                f"Grade {grade} practice plan for {outline.focus_process} "
                f"(target {', '.join(outline.target_sounds)}), following the "
                f"'{outline.gameplay_level or outline.title}' gameplay "
                f"guidance: progress from syllables to words to phrases to "
                f"sentences."
            ),
            generated_by="rule-based",
        )

    def _pick(self, pool: list[PracticeItem], error_sounds: set[str],
              focus_sounds: list[FocusSound]) -> list[PracticeItem]:
        """Pick up to items_per_level, preferring items that match the
        child's error pattern (target sound AND position), then excluding
        items containing the child's other error sounds."""
        wanted = {(fs.sound, fs.position.lower()) for fs in focus_sounds}
        wanted_sounds = {fs.sound for fs in focus_sounds}
        wanted_positions = {fs.position.lower() for fs in focus_sounds}

        def rank(it: PracticeItem) -> int:
            if (it.target_sound, it.position.lower()) in wanted:
                return 2
            if it.target_sound in wanted_sounds or it.position.lower() in wanted_positions:
                return 1
            return 0

        ordered = sorted(pool, key=lambda it: (-rank(it), it.text))
        items = []
        for item in ordered:
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

    def __init__(self, *, client, prompt_builder, parser, config=default_config):
        self._client = client
        self._prompt_builder = prompt_builder
        self._parser = parser
        self._config = config

    def build(self, *, findings, outlines, bank, grade_document) -> LearningModule:
        if not outlines:
            raise NoOutlineError("No outline matches the detected processes")
        outline = outlines[0]

        bank_items = {
            PracticeLevel.from_value(level): [
                {"text": it.text, "phonemes": it.phonemes,
                 "syllable_complexity": it.syllable_complexity,
                 "target_sound": it.target_sound, "position": it.position,
                 "processes": list(it.processes), "grades": list(it.grades),
                 "gameplay_level": it.gameplay_level}
                for it in bank.items_for(PracticeLevel.from_value(level))
            ]
            for level in self._config.levels_order
        }
        system, user = self._prompt_builder.build(
            findings=findings, outlines=outlines, bank_items=bank_items,
            grade_document=grade_document)
        raw = self._client.complete(system=system, user=user)

        selection = self._parser.parse(
            raw,
            allowed_outline_ids={o.id for o in outlines},
            bank_lookup=bank.get,
        )
        chosen = next(o for o in outlines if o.id == selection["outline_id"])

        return LearningModule(
            module_id=f"mod-{uuid.uuid4().hex[:8]}",
            focus_sounds=[FocusSound(s, "Initial", chosen.focus_process)
                          for s in chosen.target_sounds],
            focus_processes=[chosen.focus_process],
            outline_id=chosen.id,
            outline_title=chosen.title,
            levels=selection["levels"],
            rationale=selection["rationale"],
            generated_by="llm",
        )


class ModuleService:
    """Builds personalized practice modules from assessment findings."""

    def __init__(self, *, outlines=None, bank=None,
                 primary_builder=None, fallback_builder=None,
                 grade_documents=None, config=default_config):
        self._outlines = outlines
        self._bank = bank
        self._config = config
        self._grade_documents = grade_documents or GradeDocuments()
        self._fallback_builder = fallback_builder or RuleBasedModuleBuilder(config)
        self._primary_builder = primary_builder if primary_builder is not None \
            else self._make_primary_builder()

    def _make_primary_builder(self):
        if self._config.llm_provider == "zen":
            try:
                from llm import LLMResponseParser, PromptBuilder, ZenLLMClient
                return LLMModuleBuilder(
                    client=ZenLLMClient(
                        model=self._config.llm_model,
                        base_url=self._config.zen_base_url,
                        api_key_env=self._config.api_key_env,
                        timeout=self._config.request_timeout_sec,
                        max_retries=self._config.max_retries,
                    ),
                    prompt_builder=PromptBuilder(config=self._config),
                    parser=LLMResponseParser(config=self._config),
                    config=self._config,
                )
            except Exception:
                # Missing API key or provider error -> rule-based fallback
                return self._fallback_builder
        return self._fallback_builder

    def build_module(self, findings: AssessmentFindings) -> LearningModule:
        focus_sounds = FindingsAnalyzer().focus_sounds(findings)
        grade = self._grade_documents.grade_for_age(findings.age)
        if focus_sounds:
            outlines = self._outlines.outlines_for(focus_sounds)
            outline = OutlineSelector().best(outlines, focus_sounds)
        else:
            if not findings.processes:
                raise NoFindingsError(
                    "No focus sounds could be extracted from the detected processes")
            # e.g. Weak Syllable Deletion: no phoneme in the detail string —
            # match by process name, preferring grade-appropriate outlines.
            outlines = self._outlines.outlines_for_processes(
                {p.process for p in findings.processes})
            outlines.sort(key=lambda o: (grade not in o.grades,
                                         -len(o.target_sounds)))
            outline = outlines[0] if outlines else None
        if outline is None:
            raise NoOutlineError(
                "No professional outline matches the detected processes")
        matched = [outline]

        grade_document = self._grade_documents.document_for_age(findings.age)

        try:
            return self._primary_builder.build(
                findings=findings, outlines=matched, bank=self._bank,
                grade_document=grade_document)
        except Exception as exc:
            module = self._fallback_builder.build(
                findings=findings, outlines=matched, bank=self._bank)
            module.warning = (
                f"LLM builder unavailable ({exc.__class__.__name__}); "
                f"generated with the rule-based builder instead."
            )
            return module
