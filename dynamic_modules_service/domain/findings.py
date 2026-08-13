"""FindingsAnalyzer — extracts practice focus sounds from assessment findings.

Pure domain logic: detected processes -> which phonemes the child should
practice (the target of each detected process), deduplicated.
"""

import re
from typing import Optional

from domain.models import AssessmentFindings, DetectedProcess, FocusSound

_DETAIL_TARGET_RE = re.compile(r"/([^/]+)/")


class FindingsAnalyzer:
    """Turns detected processes into practice focus sounds."""

    def focus_sounds(self, findings: AssessmentFindings) -> list[FocusSound]:
        """Extract one FocusSound per detected process, deduplicated.

        The target sound comes from ``DetectedProcess.target_sound`` when
        present, otherwise parsed from the detail string (``/k/ -> [t]``).
        """
        seen: set[tuple[str, str]] = set()
        result: list[FocusSound] = []

        for proc in findings.processes:
            sound = proc.target_sound or self._parse_target_sound(proc.detail)
            if not sound:
                continue
            key = (sound, proc.position or "")
            if key in seen:
                continue
            seen.add(key)
            result.append(FocusSound(
                sound=sound,
                position=proc.position or "",
                source_process=proc.process,
            ))
        return result

    @staticmethod
    def _parse_target_sound(detail: str) -> Optional[str]:
        match = _DETAIL_TARGET_RE.search(detail or "")
        return match.group(1) if match else None
