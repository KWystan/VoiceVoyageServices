"""Outline selection — pure domain logic for matching outlines to focus sounds."""

from typing import Optional

from domain.models import FocusSound, ModuleOutline


class OutlineSelector:
    """Picks the most relevant outline for the child's focus sounds."""

    def best(self, outlines: list[ModuleOutline],
             focus_sounds: list[FocusSound]) -> Optional[ModuleOutline]:
        """Return the outline with the most matching target sounds (first wins)."""
        if not outlines:
            return None
        focus = {s.sound for s in focus_sounds}
        return max(
            outlines,
            key=lambda o: len(focus & set(o.target_sounds)),
        )
