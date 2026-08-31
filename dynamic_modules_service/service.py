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
        if not detail:
            return None
        match = _DETAIL_TARGET_RE.search(detail)
        if match:
            raw = match.group(1).replace(",", "").replace(" ", "").strip()
            return raw or None
        # Fallback: parse "of X -> Y" or "X -> Y"
        match2 = re.search(r'(?:of\s+)?([a-zA-Zʃʒθðŋɡ]+)\s*->', detail)
        if match2:
            return match2.group(1).strip()
        return None


class OutlineSelector:
    """Picks the most relevant outline for the child's focus sounds."""

    def best(self, outlines: list[ModuleOutline],
             focus_sounds: list[FocusSound]) -> Optional[ModuleOutline]:
        if not outlines:
            return None
        # MockOutlines.outlines_for already clinically ranks and scores the outlines
        return outlines[0]


class RuleBasedModuleBuilder:
    """Deterministic builder: fills each level from the outline pools,
    filtered to the child's grade and free of the child's OTHER error
    sounds.  Items carry their bank metadata (target sound, position,
    gameplay level)."""

    def __init__(self, config=default_config):
        self._config = config

    def build(self, *, findings, outlines, bank,
              grade_document=None, process_documents=None) -> LearningModule:
        if not outlines:
            raise NoOutlineError("No outline matches the detected processes")
        outline = outlines[0]
        grade = GradeDocuments.parse_grade(findings.grade, default_age=findings.age)
        grade_text = GradeDocuments.format_grade(grade)
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
            lvl_enum = PracticeLevel.from_value(level)
            lvl_pool = outline.levels.get(lvl_enum, ())
            pool = [it for it in lvl_pool if grade in it.grades or (grade == 0 and 1 in it.grades)]
            if len(pool) < self._config.items_per_level and lvl_pool:
                for it in lvl_pool:
                    if it not in pool:
                        pool.append(it)
            if len(pool) < self._config.items_per_level and bank:
                bank_pool = bank.items_for(lvl_enum)
                for it in bank_pool:
                    if it not in pool:
                        pool.append(it)

            levels[lvl_enum] = self._pick(pool, error_sounds, child_focus)

        grade_label = "Kindergarten" if grade == 0 else f"Grade {grade}"
        atypical_procs = {"Initial Consonant Deletion", "Medial Consonant Deletion", "Backing", "Liquidization", "Frication", "Denasalization"}
        is_atypical = any(p.process in atypical_procs for p in findings.processes)
        clinical_note = " [CLINICAL ADVISORY: Non-developmental speech error pattern detected. Clinical SLP consultation advised.]" if is_atypical else ""

        return LearningModule(
            module_id=f"mod-{uuid.uuid4().hex[:8]}",
            focus_sounds=focus_sounds,
            focus_processes=[outline.focus_process],
            outline_id=outline.id,
            outline_title=outline.title,
            levels=levels,
            rationale=(
                f"{grade_label} practice plan for {outline.focus_process} "
                f"(target {', '.join(outline.target_sounds)}), following the "
                f"'{outline.gameplay_level or outline.title}' gameplay "
                f"guidance: progress from syllables to words to phrases to "
                f"sentences.{clinical_note}"
            ),
            generated_by="rule-based",
            grade=grade_text,
        )

    def _pick(self, pool: list[PracticeItem], error_sounds: set[str],
              focus_sounds: list[FocusSound]) -> list[PracticeItem]:
        """Pick up to items_per_level, preferring items that match the
        child's error pattern (target sound AND position), then excluding
        items containing the child's other error sounds."""
        if not pool:
            return []

        # Tier 1: matches child's specific sound + position error, no other errors
        # Tier 2: general outline item, no other error sounds
        # Tier 3: any outline item (even with other error sounds, if pool is tiny)
        t1, t2, t3 = [], [], []
        target_positions = {(fs.sound, fs.position.lower()) for fs in focus_sounds}

        for it in pool:
            has_error = self._has_error_sound(it, error_sounds)
            matches_pattern = (
                (it.target_sound, it.position.lower()) in target_positions
                if it.position else False
            )
            if matches_pattern and not has_error:
                t1.append(it)
            elif not has_error:
                t2.append(it)
            else:
                t3.append(it)

        picked: list[PracticeItem] = []
        for tier in (t1, t2, t3):
            for it in tier:
                if it not in picked:
                    picked.append(it)
                if len(picked) >= self._config.items_per_level:
                    return picked
        return picked

    def _has_error_sound(self, item: PracticeItem, error_sounds: set[str]) -> bool:
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

    def build(self, *, findings, outlines, bank, grade_document, process_documents=None) -> LearningModule:
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
            grade_document=grade_document, process_documents=process_documents)
        raw = self._client.complete(system=system, user=user)

        selection = self._parser.parse(
            raw,
            allowed_outline_ids={o.id for o in outlines},
            bank_lookup=bank.get,
        )
        chosen = next(o for o in outlines if o.id == selection["outline_id"])

        child_focus = FindingsAnalyzer().focus_sounds(findings)
        focus_sounds = [fs for fs in child_focus
                        if fs.sound in chosen.target_sounds] or [
            FocusSound(s, "Initial", chosen.focus_process)
            for s in chosen.target_sounds]

        grade = GradeDocuments.parse_grade(findings.grade, default_age=findings.age)
        grade_text = GradeDocuments.format_grade(grade)
        return LearningModule(
            module_id=f"mod-{uuid.uuid4().hex[:8]}",
            focus_sounds=focus_sounds,
            focus_processes=[chosen.focus_process],
            outline_id=chosen.id,
            outline_title=chosen.title,
            levels=selection["levels"],
            rationale=selection["rationale"],
            generated_by="llm",
            grade=grade_text,
        )


class ModuleService:
    """Builds personalized practice modules from assessment findings."""

    def __init__(self, *, outlines=None, bank=None,
                 primary_builder=None, fallback_builder=None,
                 grade_documents=None, module_catalog=None, config=default_config):
        self._outlines = outlines
        self._bank = bank
        self._config = config
        self._grade_documents = grade_documents or GradeDocuments()
        self._module_catalog = module_catalog or ModuleCatalog()
        self._fallback_builder = fallback_builder or RuleBasedModuleBuilder(config)
        self._llm_fallback_reason: Optional[str] = None
        self._primary_builder = primary_builder if primary_builder is not None \
            else self._make_primary_builder()

    def _make_primary_builder(self):
        provider = self._config.llm_provider
        if provider in ("openrouter", "zen"):
            try:
                from llm import LLMResponseParser, PromptBuilder, OpenAICompatibleLLMClient
                base_url = (
                    self._config.openrouter_base_url
                    if provider == "openrouter"
                    else self._config.zen_base_url
                )
                api_key_env = (
                    "OPENROUTER_API_KEY"
                    if provider == "openrouter"
                    else self._config.api_key_env
                )
                return LLMModuleBuilder(
                    client=OpenAICompatibleLLMClient(
                        model=self._config.llm_model,
                        base_url=base_url,
                        api_key_env=api_key_env,
                        timeout=self._config.request_timeout_sec,
                        max_retries=self._config.max_retries,
                    ),
                    prompt_builder=PromptBuilder(config=self._config),
                    parser=LLMResponseParser(config=self._config),
                    config=self._config,
                )
            except Exception as exc:
                # Missing API key or provider error -> rule-based fallback,
                # but remember WHY so the response can surface a warning.
                self._llm_fallback_reason = f"{exc.__class__.__name__}: {exc}"
                return self._fallback_builder
        return self._fallback_builder

    def build_module(self, findings: AssessmentFindings) -> LearningModule:
        focus_sounds = FindingsAnalyzer().focus_sounds(findings)
        grade = self._grade_documents.parse_grade(findings.grade, default_age=findings.age)
        outline = None
        outlines = []

        if focus_sounds:
            outlines = self._outlines.outlines_for(focus_sounds)
            outline = OutlineSelector().best(outlines, focus_sounds)

        # Smooth fallback: if sound matching didn't yield an outline, match by detected process names
        if outline is None and findings.processes:
            proc_outlines = self._outlines.outlines_for_processes(
                {p.process for p in findings.processes})
            proc_outlines.sort(key=lambda o: (grade not in o.grades,
                                             -len(o.target_sounds)))
            if proc_outlines:
                outline = proc_outlines[0]
                outlines = proc_outlines

        if outline is None and findings.processes:
            all_outlines = self._outlines.all()
            if all_outlines:
                outline = all_outlines[0]
                outlines = [outline]

        if outline is None:
            if not findings.processes:
                grade_text = GradeDocuments.format_grade(grade)
                levels = {}
                if self._bank:
                    for lvl in PracticeLevel:
                        items = [it for it in self._bank.items_for(lvl) if grade in it.grades or (grade == 0 and 1 in it.grades)]
                        if len(items) < 4:
                            for it in self._bank.items_for(lvl):
                                if it not in items:
                                    items.append(it)
                        levels[lvl] = items[:4]
                return LearningModule(
                    module_id=f"mod-{uuid.uuid4().hex[:8]}",
                    focus_sounds=[],
                    focus_processes=["Speech Champion / Fluency Enrichment"],
                    outline_id="speech-champion-enrichment",
                    outline_title="Speech Champion: Advanced Fluency and Storytelling",
                    levels=levels,
                    rationale=(
                        f"Speech Champion! Clear pronunciation across all sounds. "
                        f"Enjoy an advanced {grade_text} vocabulary and storytelling "
                        f"adventure on Mastery Island."
                    ),
                    generated_by="rule-based",
                    grade=grade_text,
                )
            raise NoOutlineError(
                "No professional outline matches the detected processes")

        matched = outlines if outlines else [outline]
        grade_document = self._grade_documents.document_for_grade(grade)
        process_documents = self._module_catalog.get_documents_for_findings(findings)

        try:
            module = self._primary_builder.build(
                findings=findings, outlines=matched, bank=self._bank,
                grade_document=grade_document, process_documents=process_documents)
        except Exception as exc:
            module = self._fallback_builder.build(
                findings=findings, outlines=matched, bank=self._bank,
                grade_document=grade_document, process_documents=process_documents)
            module.warning = (
                f"LLM builder unavailable ({exc.__class__.__name__}); "
                f"generated with the rule-based builder instead."
            )
            return module

        if self._llm_fallback_reason and not module.warning:
            module.warning = (
                f"LLM builder unavailable ({self._llm_fallback_reason}); "
                f"generated with the rule-based builder instead."
            )
        return module
