"""Mock data loading — implements the Outlines and WordBank ports.

Loads the professional module outlines and word bank from JSON files.
Swap this module for a real database later WITHOUT touching the domain.
"""

import json
from typing import Optional

from domain.models import (
    FocusSound,
    ModuleOutline,
    PracticeItem,
    PracticeLevel,
)
from config import config


class MockOutlines:
    """Outlines port backed by data/module_outlines.json."""

    def __init__(self, path=None):
        self._path = path or config.outlines_path
        self._outlines = self._load()

    def _load(self) -> list[ModuleOutline]:
        with open(self._path, encoding="utf-8") as f:
            raw = json.load(f)
        outlines = []
        for entry in raw["outlines"]:
            levels = {}
            for level_name, items in entry["levels"].items():
                level = PracticeLevel.from_value(level_name)
                levels[level] = tuple(
                    PracticeItem(
                        text=it["text"],
                        level=level,
                        target_sound=it["target_sound"],
                        position=it.get("position", ""),
                        phonemes=it.get("phonemes", ""),
                    )
                    for it in items
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

    def by_id(self, outline_id: str) -> Optional[ModuleOutline]:
        return next((o for o in self._outlines if o.id == outline_id), None)


class MockWordBank:
    """WordBank port backed by data/word_bank.json."""

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
                target_sound=it["target_sound"],
                position=it.get("position", ""),
                phonemes=it.get("phonemes", ""),
            )
            items[(item.text, item.level)] = item
        return items

    def items_for(self, level: PracticeLevel, target_sound: str) -> list[PracticeItem]:
        return [
            it for it in self._items.values()
            if it.level == level and it.target_sound == target_sound
        ]

    def get(self, text: str, level: PracticeLevel) -> Optional[PracticeItem]:
        return self._items.get((text, level))
