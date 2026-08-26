"""Data loading — word bank, module outlines, and grade-level documents.

The word bank (data/word_bank.json) is the SINGLE source of item text +
phonemes + metadata for the whole service.  Module outlines
(data/module_outlines.json) define process templates whose level pools are
resolved from the bank at load time.  Grade-level gameplay documents
(data/Grade *.md) are the LLM's curriculum/age context — they replaced the
old ASHA CSV word lists, which no code loads.
"""

import json
from pathlib import Path

try:
    from dynamic_modules_service.config import config
except ImportError:
    from config import config
from models import (
    ModuleOutline,
    PracticeItem,
    PracticeLevel,
)


class GradeDocuments:
    """The grade-level gameplay Markdown documents, keyed by grade.

    These are full LLM context: islands, levels, MATATAG foci, ASHA targets,
    UI templates and dynamic-content guidance per grade.  Grades follow the
    app's age brackets: 1 = ages 5-6, 2 = ages 6-7, 3 = age 8.  Age 4
    children use the Grade 1 document (the Kindergarten document is not
    shipped with this service).
    """

    def __init__(self, docs=None):
        self._docs = dict(docs or config.grade_docs)

    def grade_for_age(self, age: int) -> int:
        if age <= 5:
            return 1
        if age <= 7:
            return 2
        return 3

    def document_for_grade(self, grade: int) -> str:
        path = self._docs.get(grade)
        if path is None:
            raise KeyError(f"No grade document for grade {grade}")
        return Path(path).read_text(encoding="utf-8")

    def document_for_age(self, age: int) -> str:
        return self.document_for_grade(self.grade_for_age(age))


class MockOutlines:
    """Professional module outlines backed by data/module_outlines.json.

    Outlines define the process template (id, title, focus process, target
    sounds, grades).  Level pools are resolved from the WORD BANK at load
    time — bank items whose ``processes`` include the outline's focus
    process — so the pools can never drift from the bank.
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
            levels = {
                level: tuple(
                    self._bank.items_for_outline(level, entry["focus_process"])
                )
                for level in PracticeLevel
            }
            outlines.append(ModuleOutline(
                id=entry["id"],
                title=entry["title"],
                focus_process=entry["focus_process"],
                target_sounds=tuple(entry["target_sounds"]),
                grades=tuple(entry.get("grades", [1, 2, 3])),
                gameplay_level=entry.get("gameplay_level", ""),
                levels=levels,
            ))
        return outlines

    def all(self) -> list[ModuleOutline]:
        return list(self._outlines)

    def outlines_for(self, focus_sounds: list) -> list[ModuleOutline]:
        """Outlines matching the focus sounds, best match first.

        An outline matches when it shares a target sound with the findings;
        outlines whose focus process also matches the findings are ranked
        above sound-only matches (e.g. Gliding /l/ must not pick the
        Cluster-Reduction L-blend outline just because both involve /l/).
        """
        focus = {s.sound for s in focus_sounds}
        processes = {s.source_process for s in focus_sounds}
        scored = []
        for o in self._outlines:
            overlap = focus & set(o.target_sounds)
            if not overlap:
                continue
            process_match = o.focus_process in processes
            scored.append(((2 if process_match else 0) + len(overlap), o))
        scored.sort(key=lambda pair: -pair[0])
        return [o for _, o in scored]

    def outlines_for_processes(self, process_names: list[str]) -> list[ModuleOutline]:
        """Outlines whose focus process is among the detected processes.

        Used when the findings carry no usable target sound (e.g. Weak
        Syllable Deletion, whose detail has no phoneme) so the module
        builder can still match a plan.
        """
        wanted = set(process_names)
        return [o for o in self._outlines if o.focus_process in wanted]


class MockWordBank:
    """Practice items backed by data/word_bank.json — the single source
    of item text + phonemes + metadata for the whole service.

    Items are TEXT-ONLY (no image/audio assets).  Each carries the metadata
    the LLM needs: syllable complexity, target sound + position, related
    processes, grades, and gameplay level.
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
                target_sound=it.get("target_sound", ""),
                position=it.get("position", ""),
                phonemes=it.get("phonemes", ""),
                syllable_complexity=it.get("syllable_complexity", ""),
                processes=tuple(it.get("processes", [])),
                grades=tuple(it.get("grades", [1])),
                gameplay_level=it.get("gameplay_level", ""),
            )
            items[(item.text, item.level)] = item
        return items

    def items_for(self, level: PracticeLevel) -> list[PracticeItem]:
        return [it for it in self._items.values() if it.level == level]

    def items_for_outline(self, level: PracticeLevel,
                          process: str) -> list[PracticeItem]:
        """Bank items usable by an outline: level matches and the item's
        related processes include the outline's focus process."""
        return [it for it in self._items.values()
                if it.level == level and process in it.processes]

    def get(self, text: str, level: PracticeLevel):
        return self._items.get((text, level))
