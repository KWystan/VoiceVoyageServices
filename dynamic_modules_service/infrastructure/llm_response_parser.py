"""LLM response parsing — LLM JSON -> a validated item selection.

The LLM is only allowed to select items that exist in the provided word
bank; anything invented is rejected.  A malformed response raises
``InvalidLLMResponse`` (the service then falls back to rule-based).
"""

import json
from typing import Optional

from domain.models import PracticeLevel


class InvalidLLMResponse(Exception):
    """The LLM returned something we cannot use (malformed or unsafe)."""


class LLMResponseParser:
    """Parses and validates the LLM's JSON selection."""

    def __init__(self, config=None):
        from config import config as default_config
        self._config = config or default_config

    def parse(
        self,
        raw: str,
        *,
        allowed_outline_ids: set[str],
        bank_lookup,
    ) -> dict:
        """Return ``{"outline_id", "rationale", "levels": {level: [PracticeItem]}}``.

        ``bank_lookup`` is a callable ``(text, level) -> PracticeItem | None``.
        """
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise InvalidLLMResponse(f"response is not valid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise InvalidLLMResponse("response is not a JSON object")

        outline_id = data.get("outline_id")
        if outline_id not in allowed_outline_ids:
            raise InvalidLLMResponse(
                f"outline_id '{outline_id}' is not among the candidates"
            )

        rationale = str(data.get("rationale", "") or "")

        levels_raw = data.get("levels")
        if not isinstance(levels_raw, dict):
            raise InvalidLLMResponse("missing 'levels' object")

        unknown = set(levels_raw) - set(self._config.levels_order)
        if unknown:
            raise InvalidLLMResponse(
                f"unknown level key(s): {sorted(unknown)}"
            )

        levels = {}
        for level_name in self._config.levels_order:
            texts = levels_raw.get(level_name)
            if not isinstance(texts, list):
                raise InvalidLLMResponse(f"level '{level_name}' must be a list")
            level = PracticeLevel.from_value(level_name)
            items = []
            for text in texts:
                item = bank_lookup(str(text), level)
                if item is None:
                    raise InvalidLLMResponse(
                        f"item '{text}' for level '{level_name}' is not in the "
                        f"word bank (invented items are rejected)"
                    )
                items.append(item)
            levels[level] = items

        return {"outline_id": outline_id, "rationale": rationale, "levels": levels}
