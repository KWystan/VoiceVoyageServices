"""Findings-to-module use case with one closed candidate-pool seam."""

import re
import uuid
from typing import Optional

try:
    from dynamic_modules_service.config import config as default_config
except ImportError:
    from config import config as default_config
from data import GradeDocuments, ModuleCatalog
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
    """No professional outline matches the findings."""


class NoContentError(Exception):
    """A matching outline exists but has no valid catalog content."""


class FindingsAnalyzer:
    """Turn detected processes into normalized, deduplicated focus sounds."""

    def focus_sounds(self, findings: AssessmentFindings) -> list[FocusSound]:
        seen: set[tuple[str, str]] = set()
        result: list[FocusSound] = []
        for process in findings.processes:
            sound = self._normalize_sound(
                process.target_sound or self._parse_target_sound(process.detail)
            )
            if not sound:
                continue
            position = (process.position or "").strip()
            key = (sound, position.lower())
            if key in seen:
                continue
            seen.add(key)
            result.append(
                FocusSound(
                    sound=sound,
                    position=position,
                    source_process=process.process,
                )
            )
        return result

    @staticmethod
    def _normalize_sound(sound: Optional[str]) -> Optional[str]:
        normalized = (sound or "").strip().strip("/[]").replace(" ", "")
        return normalized or None

    @staticmethod
    def _parse_target_sound(detail: str) -> Optional[str]:
        if not detail:
            return None
        match = _DETAIL_TARGET_RE.search(detail)
        if match:
            return match.group(1).replace(",", "").replace(" ", "").strip()
        fallback = re.search(
            r"(?:of\s+)?([a-zA-Zʃʒθðŋɡ]+)\s*->", detail
        )
        return fallback.group(1).strip() if fallback else None


class CandidatePoolBuilder:
    """Build grade-, outline-, and target-constrained item pools.

    This interface is shared by deterministic and LLM builders. An item that
    cannot enter this pool cannot enter a returned learning module.
    """

    def build(
        self,
        *,
        findings: AssessmentFindings,
        outlines: list[ModuleOutline],
    ) -> dict[str, dict[PracticeLevel, list[PracticeItem]]]:
        grade = GradeDocuments.parse_grade(
            findings.grade, default_age=findings.age
        )
        child_focus = FindingsAnalyzer().focus_sounds(findings)
        child_sounds = {focus.sound for focus in child_focus}
        candidates: dict[str, dict[PracticeLevel, list[PracticeItem]]] = {}

        for outline in outlines:
            other_error_sounds = child_sounds - set(outline.target_sounds)
            levels: dict[PracticeLevel, list[PracticeItem]] = {}
            for level in PracticeLevel:
                eligible = [
                    item
                    for item in outline.levels.get(level, ())
                    if grade in item.grades or (grade == 0 and 1 in item.grades)
                ]
                without_competing_errors = [
                    item
                    for item in eligible
                    if not self._has_error_sound(item, other_error_sounds)
                ]
                levels[level] = without_competing_errors or eligible
            candidates[outline.id] = levels
        return candidates

    @staticmethod
    def _has_error_sound(item: PracticeItem, sounds: set[str]) -> bool:
        if not item.phonemes or not sounds:
            return False
        item_sounds = {
            phoneme.strip()
            for phoneme in item.phonemes.split(",")
            if phoneme.strip()
        }
        return bool(item_sounds & sounds)


class RuleBasedModuleBuilder:
    """Deterministically select from the same closed pools used by the LLM."""

    def __init__(self, config=default_config):
        self._config = config

    def build(
        self,
        *,
        findings,
        outlines,
        bank,
        grade_document=None,
        process_documents=None,
        candidate_items=None,
    ) -> LearningModule:
        if not outlines:
            raise NoOutlineError("No outline matches the detected processes")
        candidate_items = candidate_items or CandidatePoolBuilder().build(
            findings=findings, outlines=outlines
        )
        outline = outlines[0]
        child_focus = FindingsAnalyzer().focus_sounds(findings)
        focus_sounds = [
            focus
            for focus in child_focus
            if focus.sound in outline.target_sounds
        ] or [
            FocusSound(sound, "Initial", outline.focus_process)
            for sound in outline.target_sounds
        ]

        levels = {
            level: self._pick(
                list(candidate_items[outline.id][level]), child_focus
            )
            for level in PracticeLevel
        }
        if not any(levels.values()):
            raise NoContentError(
                f"Outline '{outline.id}' has no valid practice items"
            )

        grade = GradeDocuments.parse_grade(
            findings.grade, default_age=findings.age
        )
        grade_text = GradeDocuments.format_grade(grade)
        atypical_processes = {
            "Initial Consonant Deletion",
            "Medial Consonant Deletion",
            "Backing",
            "Liquidization",
            "Frication",
            "Denasalization",
        }
        needs_follow_up = any(
            process.process in atypical_processes for process in findings.processes
        )
        follow_up = (
            " This educational pattern may warrant review by a qualified "
            "speech-language pathologist; the app does not diagnose."
            if needs_follow_up
            else ""
        )
        return LearningModule(
            module_id=f"mod-{uuid.uuid4().hex[:8]}",
            focus_sounds=focus_sounds,
            focus_processes=[outline.focus_process],
            outline_id=outline.id,
            outline_title=outline.title,
            levels=levels,
            rationale=(
                f"{grade_text} educational practice for "
                f"{outline.focus_process}, progressing from syllables to "
                f"connected text using familiar closed-catalog items.{follow_up}"
            ),
            generated_by="rule-based",
            grade=grade_text,
        )

    def _pick(
        self,
        pool: list[PracticeItem],
        focus_sounds: list[FocusSound],
    ) -> list[PracticeItem]:
        target_positions = {
            (focus.sound, focus.position.lower())
            for focus in focus_sounds
            if focus.position
        }
        exact = [
            item
            for item in pool
            if item.position
            and (item.target_sound, item.position.lower()) in target_positions
        ]
        remaining = [item for item in pool if item not in exact]
        return (exact + remaining)[: self._config.items_per_level]


class LLMModuleBuilder:
    """Ask the LLM to choose only among prevalidated candidate items."""

    def __init__(self, *, client, prompt_builder, parser, config=default_config):
        self._client = client
        self._prompt_builder = prompt_builder
        self._parser = parser
        self._config = config

    def build(
        self,
        *,
        findings,
        outlines,
        bank,
        grade_document,
        process_documents=None,
        candidate_items=None,
    ) -> LearningModule:
        if not outlines:
            raise NoOutlineError("No outline matches the detected processes")
        candidate_items = candidate_items or CandidatePoolBuilder().build(
            findings=findings, outlines=outlines
        )
        system, user = self._prompt_builder.build(
            findings=findings,
            outlines=outlines,
            candidate_items=candidate_items,
            curriculum_constraints=GradeDocuments.constraints_for(
                findings.age, findings.grade
            ),
            process_documents=process_documents,
        )
        raw = self._client.complete(system=system, user=user)
        selection = self._parser.parse(
            raw,
            allowed_items_by_outline={
                outline_id: {
                    level: {item.text for item in items}
                    for level, items in levels.items()
                }
                for outline_id, levels in candidate_items.items()
            },
            bank_lookup=bank.get,
        )
        chosen = next(
            outline
            for outline in outlines
            if outline.id == selection["outline_id"]
        )
        child_focus = FindingsAnalyzer().focus_sounds(findings)
        focus_sounds = [
            focus
            for focus in child_focus
            if focus.sound in chosen.target_sounds
        ] or [
            FocusSound(sound, "Initial", chosen.focus_process)
            for sound in chosen.target_sounds
        ]
        grade = GradeDocuments.parse_grade(
            findings.grade, default_age=findings.age
        )
        return LearningModule(
            module_id=f"mod-{uuid.uuid4().hex[:8]}",
            focus_sounds=focus_sounds,
            focus_processes=[chosen.focus_process],
            outline_id=chosen.id,
            outline_title=chosen.title,
            levels=selection["levels"],
            rationale=selection["rationale"],
            generated_by="llm",
            grade=GradeDocuments.format_grade(grade),
        )


class ModuleService:
    """Build personalized modules from assessment findings."""

    def __init__(
        self,
        *,
        outlines=None,
        bank=None,
        primary_builder=None,
        fallback_builder=None,
        grade_documents=None,
        module_catalog=None,
        config=default_config,
    ):
        self._outlines = outlines
        self._bank = bank
        self._config = config
        self._grade_documents = grade_documents or GradeDocuments()
        self._module_catalog = module_catalog or ModuleCatalog()
        self._fallback_builder = fallback_builder or RuleBasedModuleBuilder(config)
        self._candidate_pool_builder = CandidatePoolBuilder()
        self._llm_fallback_reason: Optional[str] = None
        self._primary_builder = (
            primary_builder
            if primary_builder is not None
            else self._make_primary_builder()
        )

    def _make_primary_builder(self):
        provider = self._config.llm_provider
        if provider in {"openrouter", "zen"}:
            try:
                from llm import (
                    LLMResponseParser,
                    OpenAICompatibleLLMClient,
                    PromptBuilder,
                )

                return LLMModuleBuilder(
                    client=OpenAICompatibleLLMClient(
                        model=self._config.llm_model,
                        base_url=self._config.llm_base_url,
                        api_key_env=self._config.llm_api_key_env,
                        timeout=self._config.request_timeout_sec,
                        max_retries=self._config.max_retries,
                    ),
                    prompt_builder=PromptBuilder(config=self._config),
                    parser=LLMResponseParser(config=self._config),
                    config=self._config,
                )
            except Exception as exc:
                self._llm_fallback_reason = (
                    f"{exc.__class__.__name__}: {exc}"
                )
        return self._fallback_builder

    def build_module(self, findings: AssessmentFindings) -> LearningModule:
        if self._outlines is None or self._bank is None:
            raise RuntimeError("ModuleService requires outlines and a word bank")

        focus_sounds = FindingsAnalyzer().focus_sounds(findings)
        grade = self._grade_documents.parse_grade(
            findings.grade, default_age=findings.age
        )
        matched: list[ModuleOutline] = []
        if focus_sounds:
            matched = self._outlines.outlines_for(focus_sounds)
        if not matched and findings.processes:
            matched = self._outlines.outlines_for_processes(
                [process.process for process in findings.processes]
            )

        if not findings.processes:
            return self._build_enrichment_module(grade)
        if not matched:
            raise NoOutlineError(
                "No professional outline matches the detected processes"
            )

        matched = [
            outline
            for outline in matched
            if grade in outline.grades or (grade == 0 and 1 in outline.grades)
        ][: self._config.max_candidate_outlines]
        candidate_items = self._candidate_pool_builder.build(
            findings=findings, outlines=matched
        )
        matched = [
            outline
            for outline in matched
            if any(
                candidate_items[outline.id][level]
                for level in PracticeLevel
            )
        ]
        candidate_items = {
            outline.id: candidate_items[outline.id] for outline in matched
        }
        if not matched:
            raise NoContentError(
                "No grade- and target-compatible practice items are available "
                "for the detected process"
            )

        grade_document = self._grade_documents.document_for_grade(grade)
        process_documents = self._module_catalog.get_documents_for_findings(
            findings
        )
        build_args = {
            "findings": findings,
            "outlines": matched,
            "bank": self._bank,
            "grade_document": grade_document,
            "process_documents": process_documents,
            "candidate_items": candidate_items,
        }
        try:
            module = self._primary_builder.build(**build_args)
        except Exception as exc:
            module = self._fallback_builder.build(**build_args)
            module.warning = (
                f"LLM selection was unavailable ({exc.__class__.__name__}); "
                "the same validated pool was selected deterministically."
            )
            return module

        if self._llm_fallback_reason and not module.warning:
            module.warning = (
                "LLM selection is not configured; the validated pool was "
                "selected deterministically."
            )
        return module

    def _build_enrichment_module(self, grade: int) -> LearningModule:
        grade_text = GradeDocuments.format_grade(grade)
        levels = {}
        for level in PracticeLevel:
            eligible = [
                item
                for item in self._bank.items_for(level)
                if grade in item.grades or (grade == 0 and 1 in item.grades)
            ]
            levels[level] = eligible[: self._config.items_per_level]
        return LearningModule(
            module_id=f"mod-{uuid.uuid4().hex[:8]}",
            focus_sounds=[],
            focus_processes=["Speech Intelligibility & Enrichment"],
            outline_id="speech-champion-enrichment",
            outline_title="Speech Champion: Fluency and Storytelling",
            levels=levels,
            rationale=(
                f"{grade_text} educational enrichment using familiar "
                "closed-catalog text."
            ),
            generated_by="rule-based",
            grade=grade_text,
        )
