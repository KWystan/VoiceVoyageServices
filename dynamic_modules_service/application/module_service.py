"""ModuleService — the use case: findings -> personalized practice module.

Orchestrates: analyze findings -> match outlines -> build via the primary
builder (LLM when configured, rule-based otherwise) -> graceful fallback
to rule-based on any LLM failure.
"""

from typing import Optional

from domain.findings import FindingsAnalyzer
from domain.models import AssessmentFindings, LearningModule
from domain.ports import LLMClient, ModuleBuilder, Outlines, WordBank
from domain.outlines import OutlineSelector
from config import config as default_config


class NoFindingsError(Exception):
    """No focus sounds could be extracted from the findings."""


class ModuleService:
    """Builds personalized practice modules from assessment findings."""

    def __init__(
        self,
        *,
        analyzer=None,
        outlines=None,
        bank=None,
        selector=None,
        primary_builder: Optional[ModuleBuilder] = None,
        fallback_builder: Optional[ModuleBuilder] = None,
        config=default_config,
    ):
        self._analyzer = analyzer or FindingsAnalyzer()
        self._outlines = outlines
        self._bank = bank
        self._selector = selector or OutlineSelector()
        self._config = config
        self._fallback_builder = fallback_builder or self._make_rule_builder()
        self._primary_builder = primary_builder if primary_builder is not None \
            else self._make_primary_builder()

    def _make_rule_builder(self) -> ModuleBuilder:
        from application.module_builders import RuleBasedModuleBuilder
        return RuleBasedModuleBuilder(config=self._config)

    def _make_primary_builder(self) -> ModuleBuilder:
        if self._config.llm_provider == "zen":
            try:
                from application.module_builders import LLMModuleBuilder
                from infrastructure.llm_clients import ZenLLMClient
                from infrastructure.prompt_builder import PromptBuilder
                from infrastructure.llm_response_parser import LLMResponseParser

                client = ZenLLMClient(
                    model=self._config.llm_model,
                    base_url=self._config.zen_base_url,
                    api_key_env=self._config.api_key_env,
                    timeout=self._config.request_timeout_sec,
                )
                return LLMModuleBuilder(
                    client=client,
                    prompt_builder=PromptBuilder(config=self._config),
                    parser=LLMResponseParser(config=self._config),
                    config=self._config,
                )
            except Exception:
                # Missing API key or provider error -> rule-based fallback
                return self._fallback_builder
        return self._fallback_builder

    def build_module(self, findings: AssessmentFindings) -> LearningModule:
        focus_sounds = self._analyzer.focus_sounds(findings)
        if not focus_sounds:
            raise NoFindingsError(
                "No focus sounds could be extracted from the detected processes"
            )

        candidates = self._outlines.outlines_for(focus_sounds)
        outline = self._selector.best(candidates, focus_sounds)
        if outline is None:
            from application.module_builders import NoOutlineError
            raise NoOutlineError(
                "No professional outline matches the detected processes"
            )
        matched = [outline]

        try:
            return self._primary_builder.build(
                findings=findings, outlines=matched, bank=self._bank)
        except Exception as exc:
            module = self._fallback_builder.build(
                findings=findings, outlines=matched, bank=self._bank)
            module.warning = (
                f"LLM builder unavailable ({exc.__class__.__name__}); "
                f"generated with the rule-based builder instead."
            )
            return module
