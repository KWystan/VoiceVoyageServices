"""
Phoneme classification utilities with model-vocabulary and panphon fallback.

Layer 1: hardcoded curated sets from constants.py (fast path, O(1)) — the
clinical English inventory.
Layer 2: full model-vocabulary labels loaded once at import time by
constants.py from data/wav2vec2_manners.csv / data/wav2vec2_places.csv —
deterministic labels for every token the ASR model can emit (regenerate via
scripts/build_vocab_label_csvs.py; place columns arrive pre-folded to
ASHA-coarse labels via constants.PLACE_COLUMN_TO_COARSE).
Layer 3: panphon.FeatureTable for anything still unknown.
This ensures robustness against unexpected IPA symbols from Wav2Vec2
while maintaining performance for common phonemes.
"""
import logging
from typing import Optional

from .constants import (
    STOPS, FRICATIVES, AFFRICATES, LIQUIDS, GLIDES,
    NASALS, VOWELS, VELARS, PALATALS, ALVEOLARS, LABIALS,
    DENTALS, GLOTTALS,
    VOCAB_MANNERS, VOCAB_PLACES, PLACE_COLUMN_TO_COARSE,
)
from ipa.normalization import clean, same_phoneme, canonicalize  # noqa: F401 — re-exported for back-compat

logger = logging.getLogger(__name__)

# ── Panphon fallback (lazy-loaded singleton) ────────────────────────
_panphon_ft = None
_panphon_load_attempted = False


def _get_panphon_ft():
    """Lazy-load panphon FeatureTable. Returns None if unavailable."""
    global _panphon_ft, _panphon_load_attempted
    if not _panphon_load_attempted:
        _panphon_load_attempted = True
        try:
            import panphon
            _panphon_ft = panphon.FeatureTable()
            logger.info("panphon FeatureTable loaded successfully")
        except ImportError:
            _panphon_ft = None
            logger.warning(
                "panphon not available; manner/place will use hardcoded sets only"
            )
        except Exception as exc:
            _panphon_ft = None
            logger.warning("panphon load failed: %s", exc)
    return _panphon_ft


# ── Layer 2: full model-vocabulary labels ───────────────────────────
# Loaded once at import time by constants.py from data/wav2vec2_*.csv
# (fail-fast on bad data). VOCAB_PLACES values arrive pre-folded to the
# ASHA-coarse labels below via PLACE_COLUMN_TO_COARSE.
_VALID_MANNERS = frozenset(
    {"Stop", "Fricative", "Affricate", "Nasal", "Liquid", "Glide", "Vowel"}
)
_VALID_PLACES = frozenset({"Velar", "Palatal", "Alveolar", "Labial", "Glottal"})

# Back-compat alias — the mapping now lives in constants.py (single source).
_FINE_TO_COARSE_PLACE = PLACE_COLUMN_TO_COARSE

_vocab_labels: tuple[dict, dict] = (VOCAB_MANNERS, VOCAB_PLACES)


def _get_vocab_labels() -> tuple[dict, dict]:
    """Return the model-vocabulary label maps: (manners, places).

    Both are ASHA-coarse, loaded at import time by constants.py from the
    wav2vec2 CSVs. Kept as a function for call-site compatibility.
    """
    return _vocab_labels


def manner(phoneme: str) -> Optional[str]:
    """Get manner of articulation for a phoneme.

    Uses hardcoded sets first (fast), then the full model-vocabulary
    label CSVs, then panphon features as a final fallback.

    The ``"#"`` word-boundary token returns ``"Boundary"``, which
    causes ``is_consonant("#")`` to return ``False`` — this
    automatically prevents cross-word cluster reductions.

    Returns: "Stop", "Fricative", "Affricate", "Nasal", "Liquid",
             "Glide", "Vowel", "Boundary", or None.
    """
    if phoneme == "#":
        return "Boundary"

    p = clean(phoneme)

    # ── Fast path: hardcoded sets ──
    if p in STOPS: return "Stop"
    if p in FRICATIVES: return "Fricative"
    if p in AFFRICATES: return "Affricate"
    if p in NASALS: return "Nasal"
    if p in LIQUIDS: return "Liquid"
    if p in GLIDES: return "Glide"
    if p in VOWELS: return "Vowel"

    # ── Layer 2: full model-vocabulary labels ──
    vocab_manner = _get_vocab_labels()[0].get(p)
    if vocab_manner in _VALID_MANNERS:
        return vocab_manner

    # ── Slow path: panphon feature lookup ──
    ft = _get_panphon_ft()
    if ft is not None:
        try:
            seg = ft.fts(p)
            if not hasattr(seg, "numeric"):
                return None
            vec = seg.numeric()
            # panphon feature vector indices for this version:
            #   0=syl  1=son  2=cons  3=cont  4=delrel
            #   5=lat  6=nas  7=strid 8=voi   9=sg
            #  10=cg  11=ant 12=cor  13=distr 14=lab
            #  15=hi  16=lo  17=back 18=round 19=velaric
            #  20=tense 21=long 22=hitone 23=hireg
            if vec[0] == 1:          # syl → vowel
                return "Vowel"
            if vec[6] == 1:          # nas
                return "Nasal"
            if vec[2] == 1 and vec[3] == -1:   # +cons, -cont → stop
                return "Stop"
            if vec[2] == 1 and vec[3] == 1 and vec[1] == -1:
                return "Fricative"   # +cons, +cont, -son → fricative
            if vec[5] == 1:          # lat → liquid
                return "Liquid"
            if vec[1] == 1 and vec[2] == -1:   # +son, -cons → glide
                return "Glide"
        except Exception:
            pass

    return None


def place(phoneme: str) -> Optional[str]:
    """Get place of articulation for a phoneme.

    Uses hardcoded sets first, then the full model-vocabulary label CSVs,
    then panphon features.

    Returns: "Velar", "Palatal", "Alveolar", "Labial", "Dental",
             "Glottal", or None.
    """
    p = clean(phoneme)

    # ── Fast path: hardcoded sets ──
    if p in VELARS: return "Velar"
    if p in PALATALS: return "Palatal"
    if p in ALVEOLARS: return "Alveolar"
    if p in LABIALS: return "Labial"
    if p in DENTALS: return "Alveolar"   # ASHA: dental → alveolar
    if p in GLOTTALS: return "Glottal"

    # ── Vowels don't have a place of articulation ──
    if p in VOWELS:
        return None

    # ── Layer 2: full model-vocabulary labels (pre-folded to coarse) ──
    vocab_place = _get_vocab_labels()[1].get(p)
    if vocab_place in _VALID_PLACES:
        return vocab_place

    # ── Slow path: panphon feature lookup ──
    ft = _get_panphon_ft()
    if ft is not None:
        try:
            seg = ft.fts(p)
            if not hasattr(seg, "numeric"):
                return None
            vec = seg.numeric()
            # panphon place features:
            # 14=lab, 12=cor, 13=distr, 11=ant, 17=back, 15=hi
            if vec[14] == 1:         # labial
                return "Labial"
            if vec[12] == 1:         # coronal → alveolar (includes dental per ASHA)
                return "Alveolar"
            if vec[17] == 1:         # back → velar/dorsal (k, ɡ, ŋ)
                return "Velar"
            # Palatal approximant j: hi=1, back=-1, no coronal, no labial
            if vec[15] == 1 and vec[17] != 1 and vec[14] == -1 and vec[12] == -1:
                return "Palatal"
        except Exception:
            pass

    return None


def is_consonant(phoneme: str) -> bool:
    """Check if a phoneme is a consonant (not vowel, not gap, not boundary)."""
    m = manner(phoneme)
    return m not in ("Vowel", "Boundary", None)


def get_position(idx: int, breakdown: list[dict]) -> str:
    """Get word-relative position ("Initial", "Medial", "Final").

    Scans the breakdown for ``"#"`` boundary tokens to determine
    the word boundaries around ``idx``, rather than using global
    utterance indices.  For single-word inputs (no ``"#"`` tokens),
    behaves identically to the old signature.

    Cluster-aware: a consonant belonging to a contiguous consonant run
    inherits the position of the whole run — the second member of a
    word-initial cluster ("plane" -> p l eɪ n) reports "Initial", and
    a final-cluster member ("milk" -> ... l k) reports "Final".
    Vowels are never part of a run and keep pure index semantics.

    Parameters
    ----------
    idx : int
        Index of the target phoneme in the breakdown.
    breakdown : list[dict]
        The full breakdown (including ``#`` entries).

    Returns
    -------
    str
        ``"Initial"``, ``"Medial"``, or ``"Final"``.
    """
    # Scan backwards for the nearest # — word start is one past it
    word_start = 0
    for j in range(idx - 1, -1, -1):
        if breakdown[j].get("expected") == "#":
            word_start = j + 1
            break

    # Scan forwards for the nearest # — word end is one before it
    word_end = len(breakdown) - 1
    for j in range(idx + 1, len(breakdown)):
        if breakdown[j].get("expected") == "#":
            word_end = j - 1
            break

    # Expand over adjacent consonants within the same word so every
    # member of a cluster shares the cluster's position ("#"-bounded,
    # since is_consonant("#") is False anyway)
    anchor_start, anchor_end = idx, idx
    if is_consonant(breakdown[idx].get("expected", "")):
        while (anchor_start - 1 >= word_start
               and is_consonant(breakdown[anchor_start - 1].get("expected", ""))):
            anchor_start -= 1
        while (anchor_end + 1 <= word_end
               and is_consonant(breakdown[anchor_end + 1].get("expected", ""))):
            anchor_end += 1

    if anchor_start == word_start:
        return "Initial"
    if anchor_end == word_end:
        return "Final"
    return "Medial"
