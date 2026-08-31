"""LLM integration — OpenCode Zen client, prompt building, response parsing.

ZenLLMClient talks to OpenCode Zen (OpenAI-compatible chat completions);
the API key is read from the environment (``ZEN_API_KEY``) — never from
files.  PromptBuilder grounds the decision in the child's ASHA context
and forbids inventing items; LLMResponseParser validates every selected
item against the word bank.
"""

import json
import os
from typing import Optional

try:
    from dynamic_modules_service.config import config
except ImportError:
    from config import config
from models import AssessmentFindings, ModuleOutline, PracticeLevel


class LLMError(Exception):
    """The LLM provider failed (network, auth, timeout, empty reply)."""


class OpenAICompatibleLLMClient:
    """Chat-completions client for OpenAI-compatible gateways (OpenRouter, OpenCode Zen)."""

    def __init__(self, *, model, base_url, api_key=None,
                 api_key_env="OPENROUTER_API_KEY", timeout=20.0, max_retries=2,
                 http_client=None, default_headers=None):
        from openai import OpenAI

        # Support primary env var, fallback to ZEN_API_KEY if OPENROUTER_API_KEY is not set
        key = api_key or os.environ.get(api_key_env)
        if not key and api_key_env == "OPENROUTER_API_KEY":
            key = os.environ.get("ZEN_API_KEY")
        elif not key and api_key_env == "ZEN_API_KEY":
            key = os.environ.get("OPENROUTER_API_KEY")

        if not key:
            raise LLMError(f"API key is not set (expected env var '{api_key_env}')")

        headers = {
            "HTTP-Referer": "https://voicevoyage.app",
            "X-Title": "Voice Voyage Dynamic Modules",
        }
        if default_headers:
            headers.update(default_headers)

        self._model = model
        self._client = OpenAI(
            base_url=base_url,
            api_key=key,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
            default_headers=headers,
        )

    def complete(self, *, system: str, user: str) -> str:
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
            )
        except Exception as exc:
            raise LLMError(f"LLM request failed ({self._model}): {exc}") from exc
        content = resp.choices[0].message.content
        if not content:
            raise LLMError(f"LLM returned an empty response ({self._model})")
        return content


# Backward-compatible alias
ZenLLMClient = OpenAICompatibleLLMClient
OpenRouterLLMClient = OpenAICompatibleLLMClient


class PromptBuilder:
    """Builds the LLM prompt: static system prompt from data/prompt.md
    plus the per-request user payload (age, detected processes, the full
    grade-level gameplay document for the child's age bracket, candidate
    outlines and the metadata-rich word bank).  No PII ever enters the
    prompt."""

    def __init__(self, config=config):
        self._config = config
        self._system = self._load_prompt()

    def _load_prompt(self) -> str:
        with open(self._config.prompt_path, encoding="utf-8") as f:
            return f.read()

    def build(self, *, findings, outlines, bank_items, grade_document=None, process_documents=None):
        from data import GradeDocuments
        grade_int = GradeDocuments.parse_grade(findings.grade, default_age=findings.age)
        grade_text = GradeDocuments.format_grade(grade_int)
        user_payload = {
            "child": {
                "age": findings.age,
                "grade": grade_text,
            },
            "detected_processes": [
                {"process": p.process, "position": p.position, "detail": p.detail}
                for p in findings.processes
            ],
            "process_curriculum_modules": [
                {
                    "process": pd.get("process"),
                    "target_sound": pd.get("target_sound"),
                    "slug": pd.get("slug"),
                    "content": pd.get("doc_text"),
                }
                for pd in (process_documents or [])
            ],
            "grade_document": grade_document or "",
            "candidate_outlines": [
                {"id": o.id, "title": o.title, "focus_process": o.focus_process,
                 "target_sounds": list(o.target_sounds),
                 "grades": list(o.grades),
                 "gameplay_level": o.gameplay_level}
                for o in outlines
            ],
            "word_bank": {
                level.value: [dict(it) for it in items]
                for level, items in bank_items.items()
            },
        }
        return self._system, json.dumps(user_payload, ensure_ascii=False)


class InvalidLLMResponse(Exception):
    """The LLM returned something we cannot use (malformed or unsafe)."""


class LLMResponseParser:
    """Parses and validates the LLM's JSON selection."""

    def __init__(self, config=config):
        self._config = config

    def parse(self, raw, *, allowed_outline_ids, bank_lookup):
        """Return {"outline_id", "rationale", "levels": {level: [PracticeItem]}}."""
        try:
            data = json.loads(self._strip_fences(raw))
        except (json.JSONDecodeError, TypeError) as exc:
            raise InvalidLLMResponse(f"response is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise InvalidLLMResponse("response is not a JSON object")

        outline_id = data.get("outline_id")
        if outline_id not in allowed_outline_ids:
            raise InvalidLLMResponse(f"outline_id '{outline_id}' is not among the candidates")

        levels_raw = data.get("levels")
        if not isinstance(levels_raw, dict):
            raise InvalidLLMResponse("missing 'levels' object")
        unknown = set(levels_raw) - set(self._config.levels_order)
        if unknown:
            raise InvalidLLMResponse(f"unknown level key(s): {sorted(unknown)}")

        levels = {}
        for level_name in self._config.levels_order:
            texts = levels_raw.get(level_name)
            if not isinstance(texts, list):
                raise InvalidLLMResponse(f"level '{level_name}' must be a list")
            if len(set(texts)) != len(texts):
                raise InvalidLLMResponse(
                    f"level '{level_name}' contains duplicate items "
                    f"({texts} — each item must be unique)")
            if len(texts) > self._config.items_per_level:
                raise InvalidLLMResponse(
                    f"level '{level_name}' has {len(texts)} items — "
                    f"maximum is {self._config.items_per_level}")
            level = PracticeLevel.from_value(level_name)
            items = []
            for text in texts:
                item = bank_lookup(str(text), level)
                if item is None:
                    raise InvalidLLMResponse(
                        f"item '{text}' for level '{level_name}' is not in the "
                        f"word bank (invented items are rejected)")
                items.append(item)
            levels[level] = items

        return {"outline_id": outline_id,
                "rationale": str(data.get("rationale", "") or ""),
                "levels": levels}

    @staticmethod
    def _strip_fences(raw: str) -> str:
        """Remove markdown code fences around the JSON payload.

        Many models wrap their JSON answer in ```json ... ``` blocks —
        tolerate that instead of rejecting the response.
        """
        text = (raw or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].lstrip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return text
