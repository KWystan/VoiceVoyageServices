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

from config import config
from models import AssessmentFindings, ModuleOutline, PracticeLevel


class LLMError(Exception):
    """The LLM provider failed (network, auth, timeout, empty reply)."""


class ZenLLMClient:
    """OpenCode Zen chat-completions client (OpenAI-compatible SDK)."""

    def __init__(self, *, model, base_url, api_key=None,
                 api_key_env="ZEN_API_KEY", timeout=60.0, max_retries=2,
                 http_client=None):
        from openai import OpenAI

        key = api_key or os.environ.get(api_key_env)
        if not key:
            raise LLMError(f"ZEN_API_KEY is not set (expected env var '{api_key_env}')")
        self._model = model
        self._client = OpenAI(base_url=base_url, api_key=key, timeout=timeout,
                              max_retries=max_retries, http_client=http_client)

    def complete(self, *, system: str, user: str) -> str:
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                temperature=0.4,
            )
        except Exception as exc:
            raise LLMError(f"OpenCode Zen request failed: {exc}") from exc
        content = resp.choices[0].message.content
        if not content:
            raise LLMError("OpenCode Zen returned an empty response")
        return content


class PromptBuilder:
    """Builds the LLM prompt: static system prompt from data/prompt.md
    plus the per-request user payload (age, detected processes, candidate
    outlines and the full word bank).  No PII ever enters the prompt."""

    def __init__(self, config=config):
        self._config = config
        self._system = self._load_prompt()

    def _load_prompt(self) -> str:
        with open(self._config.prompt_path, encoding="utf-8") as f:
            return f.read()

    def build(self, *, findings, outlines, bank_items, asha=None):
        user_payload = {
            "child": {"age": findings.age},
            "detected_processes": [
                {"process": p.process, "position": p.position, "detail": p.detail}
                for p in findings.processes
            ],
            "candidate_outlines": [
                {"id": o.id, "title": o.title, "focus_process": o.focus_process,
                 "target_sounds": list(o.target_sounds)}
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
