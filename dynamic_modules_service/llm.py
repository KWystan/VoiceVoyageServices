"""Closed-world LLM selection for dynamic speech-practice modules."""

import json
import os

try:
    from dynamic_modules_service.config import config
except ImportError:
    from config import config
from models import PracticeLevel


class LLMError(Exception):
    """The configured LLM provider failed."""


class OpenAICompatibleLLMClient:
    """Small adapter for OpenAI-compatible chat-completions gateways."""

    def __init__(
        self,
        *,
        model,
        base_url,
        api_key=None,
        api_key_env="ZEN_API_KEY",
        timeout=60.0,
        max_retries=4,
        http_client=None,
        default_headers=None,
    ):
        from openai import OpenAI

        key = api_key or os.environ.get(api_key_env)
        if not key:
            raise LLMError(
                f"API key is not set (expected env var '{api_key_env}')"
            )

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
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        # Free-tier gateways often reject strict JSON schema with 400 or timeout
        use_response_format = not (
            self._model.endswith("-free") or "free" in self._model.lower()
        )
        kwargs = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.1,
        }
        if use_response_format:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            try:
                response = self._client.chat.completions.create(**kwargs)
            except Exception as exc:
                if use_response_format and ("400" in str(exc) or "response_format" in str(exc)):
                    kwargs.pop("response_format", None)
                    response = self._client.chat.completions.create(**kwargs)
                else:
                    raise
        except Exception as exc:
            raise LLMError(f"LLM request failed ({self._model}): {exc}") from exc
        content = response.choices[0].message.content
        if not content:
            raise LLMError(f"LLM returned an empty response ({self._model})")
        return content


ZenLLMClient = OpenAICompatibleLLMClient
OpenRouterLLMClient = OpenAICompatibleLLMClient


class PromptBuilder:
    """Build a concise request containing only prevalidated candidates."""

    def __init__(self, config=config):
        self._config = config
        self._system = self._load_prompt()

    def _load_prompt(self) -> str:
        with open(self._config.prompt_path, encoding="utf-8") as prompt_file:
            return prompt_file.read()

    def build(
        self,
        *,
        findings,
        outlines,
        candidate_items,
        curriculum_constraints,
        process_documents=None,
    ):
        payload = {
            "learner": {
                "age": findings.age,
                "grade": findings.grade,
            },
            "curriculum_constraints": curriculum_constraints,
            "findings": [
                {
                    "process": process.process,
                    "position": process.position,
                    "target_sound": process.target_sound,
                    "detail": process.detail,
                }
                for process in findings.processes
            ],
            "module_context": [
                {
                    key: value
                    for key, value in document.items()
                    if key not in {"path", "clinical_status", "evidence_note"}
                }
                for document in (process_documents or [])
            ],
            "candidates": [
                {
                    "outline": {
                        "id": outline.id,
                        "title": outline.title,
                        "process": outline.focus_process,
                        "target_sounds": list(outline.target_sounds),
                    },
                    "levels": {
                        level.value: [
                            {
                                "text": item.text,
                                "target_sound": item.target_sound,
                                "position": item.position,
                                "complexity": item.syllable_complexity,
                            }
                            for item in candidate_items[outline.id][level]
                        ]
                        for level in PracticeLevel
                    },
                }
                for outline in outlines
            ],
        }
        return self._system, json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class InvalidLLMResponse(Exception):
    """The LLM returned malformed or out-of-catalog content."""


class LLMResponseParser:
    """Validate the exact response schema and every selected item."""

    def __init__(self, config=config):
        self._config = config

    def parse(self, raw, *, allowed_items_by_outline, bank_lookup):
        try:
            data = json.loads(self._strip_fences(raw))
        except (json.JSONDecodeError, TypeError) as exc:
            raise InvalidLLMResponse("response is not valid JSON") from exc
        if not isinstance(data, dict):
            raise InvalidLLMResponse("response is not a JSON object")

        unknown_top_level = set(data) - {"outline_id", "rationale", "levels"}
        if unknown_top_level:
            raise InvalidLLMResponse(
                f"unknown response field(s): {sorted(unknown_top_level)}"
            )

        outline_id = data.get("outline_id")
        if outline_id not in allowed_items_by_outline:
            raise InvalidLLMResponse("outline_id is not among the candidates")

        levels_raw = data.get("levels")
        if not isinstance(levels_raw, dict):
            raise InvalidLLMResponse("missing 'levels' object")
        unknown_levels = set(levels_raw) - set(self._config.levels_order)
        if unknown_levels:
            raise InvalidLLMResponse(
                f"unknown level key(s): {sorted(unknown_levels)}"
            )

        allowed_levels = allowed_items_by_outline[outline_id]
        levels = {}
        for level_name in self._config.levels_order:
            values = levels_raw.get(level_name)
            if not isinstance(values, list) or any(
                not isinstance(value, str) for value in values
            ):
                raise InvalidLLMResponse(
                    f"level '{level_name}' must be a list of strings"
                )
            if len(values) != len(set(values)):
                raise InvalidLLMResponse(
                    f"level '{level_name}' contains duplicate items"
                )

            level = PracticeLevel.from_value(level_name)
            allowed_texts = allowed_levels[level]
            expected_count = min(
                self._config.items_per_level, len(allowed_texts)
            )
            if len(values) != expected_count:
                raise InvalidLLMResponse(
                    f"level '{level_name}' must contain exactly "
                    f"{expected_count} selected item(s)"
                )

            items = []
            for text in values:
                if text not in allowed_texts:
                    raise InvalidLLMResponse(
                        f"item '{text}' is outside the selected outline, grade, "
                        "or target-sound candidate pool"
                    )
                item = bank_lookup(text, level)
                if item is None:
                    raise InvalidLLMResponse(
                        f"item '{text}' is not in the word bank"
                    )
                items.append(item)
            levels[level] = items

        rationale = data.get("rationale", "")
        if not isinstance(rationale, str):
            raise InvalidLLMResponse("rationale must be a string")
        rationale = rationale.strip()
        if len(rationale) > 600:
            raise InvalidLLMResponse("rationale exceeds 600 characters")

        return {
            "outline_id": outline_id,
            "rationale": rationale,
            "levels": levels,
        }

    @staticmethod
    def _strip_fences(raw: str) -> str:
        text = (raw or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].lstrip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return text
