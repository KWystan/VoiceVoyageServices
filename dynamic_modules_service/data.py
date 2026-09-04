"""Data loading — word bank, module outlines, and grade-level documents.

The word bank (data/word_bank.json) is the SINGLE source of item text +
phonemes + metadata for the whole service.  Module outlines
(data/module_outlines.json) define process templates whose level pools are
resolved from the bank at load time.  Grade-level gameplay documents
(data/Grade *.md) are the LLM's curriculum/age context — they replaced the
old ASHA CSV word lists, which no code loads.
"""

import json
import re
from pathlib import Path
from typing import Optional

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

    These provide full LLM curriculum context: islands, levels, MATATAG foci,
    ASHA targets, 5-stage mechanics, and dynamic-content guidance.
    0 = Kindergarten / 5-Stage foundation (Ages 4-5)
    1 = Grade 1 (Ages 5-6)
    2 = Grade 2 (Ages 6-7)
    3 = Grade 3 (Age 8)
    """

    def __init__(self, docs=None):
        self._docs = dict(docs or config.grade_docs)

    def grade_for_age(self, age: int) -> int:
        return self.grade_for_age_static(age)

    @staticmethod
    def grade_for_age_static(age: int) -> int:
        if age <= 5:
            return 0
        if age == 6:
            return 1
        if age <= 7:
            return 2  # Grade 2
        return 3  # Grade 3

    @staticmethod
    def parse_grade(grade_str: Optional[str] = None, default_age: Optional[int] = None) -> int:
        """Parses a grade string ("Kinder", "Grade 1", "Grade 2", "Grade 3", etc.)
        into an integer grade index (0, 1, 2, 3). Falls back to default_age mapping."""
        if grade_str is not None:
            s = str(grade_str).strip().lower()
            if any(k in s for k in ("kinder", "k", "grade 0", "grade0")) or s == "0":
                return 0
            if "1" in s or "one" in s or s in ("g1", "grade 1", "grade1", "first", "grade 1st"):
                return 1
            if "2" in s or "two" in s or s in ("g2", "grade 2", "grade2", "second", "grade 2nd"):
                return 2
            if "3" in s or "three" in s or s in ("g3", "grade 3", "grade3", "third", "grade 3rd"):
                return 3
        if default_age is not None:
            return GradeDocuments.grade_for_age_static(default_age)
        return 0

    @staticmethod
    def format_grade(grade_int: int) -> str:
        """Returns standard grade text: 'Kinder', 'Grade 1', 'Grade 2', 'Grade 3'."""
        if grade_int == 0:
            return "Kinder"
        return f"Grade {grade_int}"

    def document_for_grade(self, grade: int) -> str:
        path = self._docs.get(grade)
        if path is None:
            # Fallback to Grade 1 or Kindergarten
            path = self._docs.get(1) or self._docs.get(0)
        if path is None:
            raise KeyError(f"No grade document for grade {grade}")
        return Path(path).read_text(encoding="utf-8")

    def document_for_age(self, age: int, grade: Optional[str] = None) -> str:
        return self.document_for_grade(self.parse_grade(grade, default_age=age))

    @staticmethod
    def constraints_for(age: int, grade: Optional[str] = None) -> dict:
        """Return concise, machine-facing curriculum constraints.

        The full Markdown documents remain the human source of truth. Keeping
        this payload small prevents curriculum prose from crowding out the
        closed candidate list sent to the LLM.
        """

        grade_int = GradeDocuments.parse_grade(grade, default_age=age)
        if grade_int == 0:
            return {
                "track": (
                    "ECCD/pre-kindergarten adaptation"
                    if age <= 4
                    else "DepEd MATATAG Kindergarten"
                ),
                "age_years": age,
                "content": "familiar home, school, body, family, food, and story vocabulary",
                "phrase_words": [2, 4],
                "sentence_words": [2, 5],
                "progression": ["listen", "recognize", "guided_say", "independent_say", "context"],
                "safeguards": [
                    "educational practice only; do not diagnose",
                    "accept Philippine English and multilingual variation",
                    "use positive, specific feedback",
                ],
            }
        return {
            "track": GradeDocuments.format_grade(grade_int),
            "age_years": age,
            "content": "familiar, functional, grade-appropriate vocabulary",
            "phrase_words": [2, 5],
            "sentence_words": [3, 7],
            "progression": ["syllable", "word", "phrase", "sentence"],
            "safeguards": [
                "educational practice only; do not diagnose",
                "accept dialectal and multilingual variation",
            ],
        }


class ModuleCatalog:
    """Discovers, maps, and loads specific error process markdown files.

    Structure on disk:
      modules/kinder_age_{4|5}/{expected_errors|delayed_errors|atypical_errors}/
      {process_slug}.md
    """

    def __init__(self, modules_dir: Optional[Path] = None):
        self._dir = Path(modules_dir or (Path(__file__).resolve().parent / "modules"))

    def validate_layout(self) -> None:
        """Fail fast on ambiguous or malformed age/category module files."""

        slug_pattern = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
        required_categories = {
            "expected_errors",
            "delayed_errors",
            "atypical_errors",
        }
        for age_folder in ("kinder_age_4", "kinder_age_5"):
            root = self._dir / age_folder
            if not root.is_dir():
                raise ValueError(f"Missing module folder: {root}")
            present_categories = {
                path.name for path in root.iterdir() if path.is_dir()
            }
            missing = required_categories - present_categories
            if missing:
                raise ValueError(
                    f"{age_folder} is missing category folders: {sorted(missing)}"
                )
            seen: set[str] = set()
            for module_file in sorted(root.rglob("*.md")):
                slug = module_file.stem
                if not slug_pattern.fullmatch(slug):
                    raise ValueError(
                        f"Module filename must be snake_case: {module_file}"
                    )
                if slug in seen:
                    raise ValueError(
                        f"Duplicate module slug '{slug}' in {age_folder}"
                    )
                seen.add(slug)
            if "general_articulation" not in seen:
                raise ValueError(
                    f"{age_folder} requires general_articulation.md"
                )

    def normalize_slug(self, process_name: str, target_sound: str = "") -> str:
        p = (process_name or "").strip().lower()
        t = (target_sound or "").strip().lower()

        if p == "affrication" or p.startswith("affricat"):
            return "affrication"

        if "reduplic" in p:
            return "reduplication"

        if "harmony" in p or "assimilat" in p:
            return "consonant_harmony"

        if "stop" in p:
            if t in ("v", "/v/"):
                return "stopping_v"
            if t in ("sh", "zh", "ʃ", "ʒ", "/ʃ/", "/ʒ/"):
                return "stopping_sh_zh"
            if t in ("th", "θ", "ð", "/θ/", "/ð/"):
                return "stopping_th"
            return "stopping_s_z"

        if "front" in p:
            if "palatal" in p or t in ("sh", "ʃ", "/ʃ/"):
                return "fronting_palatal"
            return "fronting_velar"

        if "back" in p:
            return "backing"

        if "deaffric" in p:
            return "deaffrication"

        if "glide" in p or "gliding" in p:
            if t in ("l", "/l/"):
                return "gliding_l"
            return "gliding_r"

        if "prevocalic" in p or p == "voicing":
            return "prevocalic_voicing"

        if "vowel" in p or "vocal" in p:
            return "vowelization"

        if "weak" in p or "syllable" in p:
            return "weak_syllable_deletion"

        if "cluster" in p:
            if "3" in p or "three" in p or t in ("str", "spr", "skr"):
                return "cluster_reduction_3el"
            return "cluster_reduction_2el"

        if "initial" in p and "consonant" in p:
            return "initial_consonant_deletion"

        if "medial" in p and "consonant" in p:
            return "medial_consonant_deletion"

        if "final" in p and "consonant" in p:
            return "final_consonant_deletion"

        if "liquid" in p:
            return "liquidization"

        if "fricat" in p:
            return "frication"

        if "denasal" in p:
            return "denasalization"

        if "devoic" in p:
            return "devoicing"

        return "general_articulation"

    def get_document(self, process_name: str, target_sound: str = "", grade_int: int = 0, age: int = 4) -> tuple[str, Path, str]:
        slug = self.normalize_slug(process_name, target_sound)

        # 1. Look in age-based folders (kinder_age_4, kinder_age_5) across subfolders (expected_errors, atypical_errors, delayed_errors)
        age_folder_name = "kinder_age_5" if age >= 5 else "kinder_age_4"
        fallback_folder_name = "kinder_age_4" if age >= 5 else "kinder_age_5"

        primary_dir = self._dir / age_folder_name
        fallback_dir = self._dir / fallback_folder_name

        matched_file = None

        # Helper to find file in directory recursively
        def find_file(dir_path: Path, target_slug: str) -> Path | None:
            if not dir_path.exists():
                return None
            for p in dir_path.rglob(f"{target_slug}.md"):
                return p
            return None

        matched_file = find_file(primary_dir, slug)
        if not matched_file:
            matched_file = find_file(fallback_dir, slug)
        if not matched_file:
            matched_file = find_file(primary_dir, "general_articulation")
        if not matched_file:
            matched_file = find_file(fallback_dir, "general_articulation")

        # 2. Backward compatibility with legacy folders
        if not matched_file:
            folder = self._dir / slug
            if folder.exists():
                files = list(folder.glob("*.md"))
                if files:
                    matched_file = files[0]

        if not matched_file:
            matched_file = next(self._dir.rglob("general_articulation.md"), self._dir / "kinder_age_4" / "expected_errors" / "general_articulation.md")

        return matched_file.read_text(encoding="utf-8"), matched_file, slug

    def get_documents_for_findings(self, findings) -> list[dict]:
        grade_int = GradeDocuments.parse_grade(getattr(findings, "grade", None), default_age=getattr(findings, "age", 4))
        age = getattr(findings, "age", 4)
        results = []
        processes = getattr(findings, "processes", [])
        for p in processes:
            proc_name = getattr(p, "process", str(p))
            detail = getattr(p, "detail", "")
            target_sound = getattr(p, "target_sound", "")
            if not target_sound and "/" in detail:
                parts = detail.split("/")
                if len(parts) >= 2:
                    target_sound = parts[1]
            doc_text, doc_path, slug = self.get_document(proc_name, target_sound, grade_int, age)
            summary = self._summarize_document(doc_text, doc_path)
            results.append({
                "process": proc_name,
                "target_sound": target_sound,
                "slug": slug,
                "path": str(doc_path),
                **summary,
            })
        return results

    @staticmethod
    def _summarize_document(doc_text: str, doc_path: Path) -> dict:
        """Extract compact empirical metadata from a human module document."""

        lines = [line.strip() for line in doc_text.splitlines() if line.strip()]
        title = next(
            (line.lstrip("# ") for line in lines if line.startswith("#")),
            doc_path.stem.replace("_", " ").title(),
        )

        def field(label: str) -> str:
            pattern = re.compile(
                rf"^\*\*{re.escape(label)}\*\*:\s*(.+?)\s*$",
                re.IGNORECASE,
            )
            for line in lines[:24]:
                match = pattern.match(line)
                if match:
                    return match.group(1).strip()
            return ""

        category_labels = {
            "expected_errors": "developmental_reference",
            "delayed_errors": "monitor_and_support",
            "atypical_errors": "professional_review_context",
        }
        return {
            "title": title,
            "category": category_labels.get(
                doc_path.parent.name, "educational_context"
            ),
            "evidence_note": field("Evidence Note") or field("Clinical Status"),
            "educational_standard": field("Educational Standard"),
            "gameplay_map": field("Island Gameplay Map"),
        }


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
            ts_set = set(entry.get("target_sounds", []))
            levels = {
                level: tuple(
                    it for it in self._bank.items_for_outline(level, entry["focus_process"])
                    if not ts_set or it.target_sound in ts_set
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
        focus = {str(s.sound).strip().strip("/[]") for s in focus_sounds}
        processes = {s.source_process.casefold() for s in focus_sounds}
        scored = []
        for o in self._outlines:
            overlap = focus & set(o.target_sounds)
            if not overlap:
                continue
            process_match = o.focus_process.casefold() in processes
            # Penalize broad catch-all outlines (ICD / FCD) unless that specific deletion process was detected
            is_catch_all = o.id in ("initial-consonant-deletion", "final-consonant-deletion")
            penalty = -5 if (is_catch_all and not process_match) else 0
            score = (10 if process_match else 0) + len(overlap) + penalty
            # Tie-break: higher score first, then tighter/more specific target sound sets
            scored.append(((score, -len(o.target_sounds)), o))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [o for _, o in scored]

    def outlines_for_processes(self, process_names: list[str]) -> list[ModuleOutline]:
        """Outlines whose focus process is among the detected processes.

        Used when the findings carry no usable target sound (e.g. Weak
        Syllable Deletion, whose detail has no phoneme) so the module
        builder can still match a plan.
        """
        aliases = {
            "voicing": "Prevocalic Voicing",
            "syllable reduction": "Syllable Reduction",
        }
        wanted = {
            aliases.get(str(name).strip().casefold(), str(name).strip()).casefold()
            for name in process_names
            if str(name).strip()
        }
        return [
            outline
            for outline in self._outlines
            if outline.focus_process.casefold() in wanted
        ]


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
        raw_items = raw.get("items")
        if not isinstance(raw_items, list):
            raise ValueError("word_bank.json must contain an 'items' list")
        for index, it in enumerate(raw_items):
            if not isinstance(it, dict):
                raise ValueError(f"word bank item {index} must be an object")
            level = PracticeLevel.from_value(it["level"])
            text = str(it.get("text", "")).strip()
            phonemes = str(it.get("phonemes", "")).strip()
            processes = tuple(str(p).strip() for p in it.get("processes", []) if str(p).strip())
            grades = tuple(int(g) for g in it.get("grades", [1]))
            if not text:
                raise ValueError(f"word bank item {index} has empty text")
            if not phonemes:
                raise ValueError(f"word bank item '{text}' has no phonemes")
            if not processes:
                raise ValueError(f"word bank item '{text}' has no process tags")
            if not grades or any(grade not in {0, 1, 2, 3} for grade in grades):
                raise ValueError(f"word bank item '{text}' has invalid grades")
            item = PracticeItem(
                text=text,
                level=level,
                target_sound=it.get("target_sound", ""),
                position=it.get("position", ""),
                phonemes=phonemes,
                syllable_complexity=it.get("syllable_complexity", ""),
                processes=processes,
                grades=grades,
                gameplay_level=it.get("gameplay_level", ""),
                language=it.get("language", "en"),
                language_variety=it.get(
                    "language_variety", "project-english-reference"
                ),
            )
            key = (item.text, item.level)
            if key in items:
                raise ValueError(
                    f"duplicate word bank item '{item.text}' at level '{item.level.value}'"
                )
            items[key] = item
        return items

    def items_for(self, level: PracticeLevel) -> list[PracticeItem]:
        return [it for it in self._items.values() if it.level == level]

    def items_for_outline(self, level: PracticeLevel,
                          process: str) -> list[PracticeItem]:
        """Bank items usable by an outline: level matches and the item's
        related processes include the outline's focus process."""
        level_items = [it for it in self._items.values() if it.level == level]
        exact = [it for it in level_items if process in it.processes]
        if exact:
            return exact

        aliases = {
            "Syllable Reduction": "Weak Syllable Deletion",
            "Final Devoicing": "Devoicing",
            "Voicing": "Prevocalic Voicing",
        }
        alias = aliases.get(process)
        if alias:
            matched = [it for it in level_items if alias in it.processes]
            if matched:
                return matched

        # Some authored outlines predate item-level process tags. Returning
        # this level here is safe because MockOutlines immediately applies the
        # outline's closed target-sound filter; selected items remain bank- and
        # target-constrained. General articulation intentionally spans targets.
        metadata_selected = {
            "Prevocalic Voicing",
            "Denasalization",
            "Vowelization",
            "Affrication",
            "Reduplication",
            "Consonant Harmony",
            "Frication",
            "Liquidization",
            "Medial Consonant Deletion",
            "Speech Intelligibility & Enrichment",
        }
        if process in metadata_selected:
            return level_items
        return []

    def get(self, text: str, level: PracticeLevel):
        return self._items.get((text, level))


# Standard production aliases
WordBank = MockWordBank
ModuleOutlines = MockOutlines
