"""Curated word list — the runtime source of truth for expected IPA.

Loads ``data/curated_words.csv`` (word -> comma-separated phonemes,
65 app words) and serves it as the expected-side converter.  Unknown
words raise ``ValueError`` (mapped to a 400 by the API adapter).

The eng_to_ipa library is NO LONGER a runtime dependency — it lives on
as a dev-only tool in ``scripts/word_to_ipa.py`` for drafting new words.
"""

import csv
from functools import lru_cache
from pathlib import Path

from ipa.clean_text import _clean_word

_CURATED_CSV = Path(__file__).resolve().parent.parent / "data" / "curated_words.csv"


@lru_cache(maxsize=1)
def _load_curated() -> dict[str, list[str]]:
    """Load the CSV once into ``{word: [phonemes]}``."""
    curated: dict[str, list[str]] = {}
    with open(_CURATED_CSV, encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if not row or row[0] == "word":
                continue
            phonemes = [p.strip() for p in row[1].split(",") if p.strip()]
            if phonemes:
                curated[row[0].strip().lower()] = phonemes
    return curated


def curated_ipa(word: str) -> str:
    """Return the curated IPA string for ``word`` (e.g. "dɔɡ").

    Raises
    ------
    ValueError
        If the word is not in ``data/curated_words.csv``.
    """
    key = _clean_word(word).lower()
    phonemes = _load_curated().get(key)
    if phonemes is None:
        raise ValueError(
            f"Word '{word}' is not in the curated word list "
            f"({_CURATED_CSV.name}). "
            f"Add it to data/curated_words.csv or use scripts/word_to_ipa.py "
            f"to draft its phonemes."
        )
    return "".join(phonemes)


def curated_phonemes(word: str) -> list[str]:
    """Return the curated phoneme tokens for ``word`` (e.g. ["d", "ɔ", "ɡ"])."""
    return _load_curated()[_clean_word(word).lower()]


def curated_words() -> list[str]:
    """All words in the curated list (sorted)."""
    return sorted(_load_curated())
