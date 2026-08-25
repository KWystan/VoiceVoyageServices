"""Phoneme classification constants for the phoneme service.

Single source of truth: the two vocabulary-label CSVs
(regenerate via scripts/build_vocab_label_csvs.py).

  data/wav2vec2_manners.csv   manner label per ASR-vocabulary token
  data/wav2vec2_places.csv    PMV-chart place column per token
                              (docs/place-manner-voice-chart.md §2)

Both are loaded once at import. The curated sets below (STOPS, VELARS, …)
are derived from the same rows, so the CSVs and the sets can never drift
apart. Place columns fold to the coarse labels detectors use via
PLACE_COLUMN_TO_COARSE. Only script ɡ (U+0261) appears in tokens;
normalize_ipa() converts ASCII g before lookup.
"""

import csv
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# PMV chart columns folded to the ASHA-coarse labels place() returns:
# Bilabial/Labiodental → Labial · Dental → Alveolar · Postalveolar → Palatal.
PLACE_COLUMN_TO_COARSE: dict[str, str] = {
    "Bilabial": "Labial",
    "Labiodental": "Labial",
    "Dental": "Alveolar",
    "Alveolar": "Alveolar",
    "Postalveolar": "Palatal",
    "Palatal": "Palatal",
    "Velar": "Velar",
    "Glottal": "Glottal",
}


def _labels(filename: str, column: str) -> dict[str, str]:
    with open(_DATA_DIR / filename, encoding="utf-8", newline="") as f:
        return {row["phoneme"]: row[column] for row in csv.DictReader(f)}


_manners = _labels("wav2vec2_manners.csv", "manner")
_place_columns = _labels("wav2vec2_places.csv", "place")

# Full model-vocabulary lookups (Layer 2 in detection/utils.py).
VOCAB_MANNERS: dict[str, str] = _manners
VOCAB_PLACES: dict[str, str] = {
    phoneme: PLACE_COLUMN_TO_COARSE[column]
    for phoneme, column in _place_columns.items()
}


def _manner(label: str) -> set[str]:
    return {p for p, m in _manners.items() if m == label}


# Place sets cover CONSONANTS only — vowel-labeled tokens must fall through
# place()'s VOWELS guard to None, exactly as when sets were hand-curated.
_consonants = {p for p, m in _manners.items() if m != "Vowel"}


def _place(*columns: str) -> set[str]:
    return {p for p, c in _place_columns.items() if c in columns and p in _consonants}


# ── Manner sets ──────────────────────────────────────────────────────

STOPS      = _manner("Stop")
FRICATIVES = _manner("Fricative")
AFFRICATES = _manner("Affricate")
NASALS     = _manner("Nasal")
LIQUIDS    = _manner("Liquid")
GLIDES     = _manner("Glide")
VOWELS     = _manner("Vowel")

MANNER_MAP: dict[str, set[str]] = {
    "Stop": STOPS,
    "Fricative": FRICATIVES,
    "Affricate": AFFRICATES,
    "Nasal": NASALS,
    "Liquid": LIQUIDS,
    "Glide": GLIDES,
    "Vowel": VOWELS,
}

# ── Place sets ───────────────────────────────────────────────────────

VELARS    = _place("Velar")
PALATALS  = _place("Postalveolar", "Palatal")
ALVEOLARS = _place("Alveolar", "Dental")   # Dental → Alveolar per ASHA
LABIALS   = _place("Bilabial", "Labiodental")
DENTALS   = _place("Dental")
GLOTTALS  = _place("Glottal")

# SLP convention (docs/place-manner-voice-chart.md §6.2/§9): the rhotic is
# coronal-alveolar for Fronting/Backing gates (/ɹ/→[w] must classify as
# Gliding, not Fronting), despite its Postalveolar chart column.
PALATALS  -= {"ɹ"}
ALVEOLARS |= {"ɹ"}
