"""Prompt building for the LLM module builder.

Builds the system + user prompts from findings, outlines and word bank.
The prompt instructs the LLM to act as a pediatric speech-language
pathologist and to SELECT ONLY from the provided items (no inventing).
NO personal data ever enters the prompt — findings only.
"""

import json

from domain.models import AssessmentFindings, ModuleOutline, PracticeLevel
from config import config

_SYSTEM_PROMPT = """You are a pediatric speech-language pathologist. \
You create personalized practice modules for children who have phonological \
process errors. You receive: the child's detected phonological processes, \
candidate professional module outlines, and practice item pools.

You must:
1. Choose the ONE most appropriate outline for the child's errors.
2. For each level (syllable, word, phrase, sentence), select the best \
{items_per_level} items from the provided pool — never more, never fewer.
3. Avoid items that contain OTHER phonemes the child has difficulty with \
(their error sounds must not appear in the items, except the target sound).
4. Sequence levels from easiest to hardest (syllables first).
5. Provide a short, human-like rationale (1-2 sentences).

STRICT RULES:
- ONLY select items that exist in the provided pools. NEVER invent new words.
- Respond with valid JSON only, in exactly this shape:
{{
  "outline_id": "<id from the outlines list>",
  "rationale": "<short clinical rationale>",
  "levels": {{
    "syllable": ["<item text>", ...],
    "word": ["<item text>", ...],
    "phrase": ["<item text>", ...],
    "sentence": ["<item text>", ...]
  }}
}}
"""


class PromptBuilder:
    """Builds system + user prompts for module generation."""

    def __init__(self, config=config):
        self._config = config

    def build(
        self,
        *,
        findings: AssessmentFindings,
        outlines: list[ModuleOutline],
        bank_items: dict[PracticeLevel, list[dict]],
    ) -> tuple[str, str]:
        system = _SYSTEM_PROMPT.format(items_per_level=self._config.items_per_level)

        user_payload = {
            "child": {
                "age": findings.age,
                "pcc": findings.pcc,
            },
            "detected_processes": [
                {"process": p.process, "position": p.position, "detail": p.detail}
                for p in findings.processes
            ],
            "candidate_outlines": [
                {
                    "id": o.id,
                    "title": o.title,
                    "focus_process": o.focus_process,
                    "target_sounds": list(o.target_sounds),
                }
                for o in outlines
            ],
            "item_pools": {
                level.value: [
                    {"text": it["text"], "target_sound": it["target_sound"],
                     "position": it["position"], "phonemes": it["phonemes"]}
                    for it in items
                ]
                for level, items in bank_items.items()
            },
        }
        return system, json.dumps(user_payload, ensure_ascii=False)
