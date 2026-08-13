"""Data loading — module outlines and the word bank.

The word bank (data/word_bank.json) is the SINGLE source of item text +
phonemes for the whole service; module outlines (data/module_outlines.json)
reference items by text only.  The LLM prompt knowledge lives in
data/prompt.md (ASHA summary + rules).
"""

import csv
import json
from pathlib import Path

from config import config
from models import (
    FocusSound,
    ModuleOutline,
    PracticeItem,
    PracticeLevel,
)


class MockOutlines:
    """Professional module outlines backed by data/module_outlines.json.

    Level pools reference item TEXTS; the actual items (word + phonemes)
    come from the word bank — a single source of truth.
    """

    def __init__(self, bank: "MockWordBank", path=None):
        self._path = path or config.outlines_path
        self._bank = bank
        self._outlines = self._load()

    def _load(self) -> list[ModuleOutline]:
        with open(self._path, encoding="utf-8") as f:
            raw = json.load(f)
        outlines = []
        for entry in raw["outlines"]:
            levels = {}
            for level_name, texts in entry["levels"].items():
                level = PracticeLevel.from_value(level_name)
                levels[level] = tuple(
                    item for item in (
                        self._bank.get(text, level) for text in texts
                    ) if item is not None
                )
            outlines.append(ModuleOutline(
                id=entry["id"],
                title=entry["title"],
                focus_process=entry["focus_process"],
                target_sounds=tuple(entry["target_sounds"]),
                levels=levels,
            ))
        return outlines

    def outlines_for(self, focus_sounds: list[FocusSound]) -> list[ModuleOutline]:
        """Outlines sharing at least one target sound, best match first."""
        focus = {s.sound for s in focus_sounds}
        matches = [o for o in self._outlines if focus & set(o.target_sounds)]
        return sorted(matches, key=lambda o: -len(focus & set(o.target_sounds)))


class MockWordBank:
    """Practice items backed by data/word_bank.json — the single source
    of item text + phonemes for the whole service.

    Items carry an optional ``theme`` tag (``ocean`` | ``general``) so the
    LLM can prefer themed words that match the app's underwater world.
    """

    def __init__(self, path=None):
        self._path = path or config.word_bank_path
        self._items = self._load()

    def _load(self) -> dict[tuple, PracticeItem]:
        with open(self._path, encoding="utf-8") as f:
            raw = json.load(f)
        items = {}
        for it in raw["items"]:
            level = PracticeLevel.from_value(it["level"])
            item = PracticeItem(
                text=it["text"],
                level=level,
                target_sound="",  # position-agnostic; selection is by level only
                phonemes=it.get("phonemes", ""),
                theme=it.get("theme", "general"),
            )
            items[(item.text, item.level)] = item
        return items

    def items_for(self, level: PracticeLevel) -> list[PracticeItem]:
        return [
            it for it in self._items.values()
            if it.level == level
        ]

    def get(self, text: str, level: PracticeLevel):
        return self._items.get((text, level))
