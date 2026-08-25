"""
IPA normalization module — the alphabet translation layer between the
expected (curated) side and the Wav2Vec2 (espeak-ng) predicted side.

The pipeline compares phonemes produced by two different IPA dialects:

* **Expected side** — the curated word list (``data/curated_words.csv``,
  originally derived from eng_to_ipa output): ``g``/``r`` allographs, no
  aspiration marks, ``əl`` for syllabic l, ``ɚ`` for rhotic vowels.
* **Predicted side** — raw Wav2Vec2 vocabulary tokens (espeak-ng, 60
  languages): allophonic diacritics (``tʰ``, ``tʲ``, ``l̩``, ``r̩``),
  length marks (``iː``, ``æː``), stress digits (``ɑ1``, ``i2``),
  foreign spellings (``ai``, ``a``, ``ɵ``, ``ɐ``, ``ʉ``...).

This module is the SINGLE source of truth for translating between them:

* ``clean()``          — strip stress/length/aspiration/coarticulation marks
* ``normalize_ipa()``  — map allographs + foreign spellings to canonical
                         English IPA (longest-match single-pass, so ``a``
                         inside ``aɪ`` is never corrupted)
* ``canonicalize()``   — normalize_ipa() + clean() (the full translation)
* ``same_phoneme()``   — identity comparison through the translation

All correctness checks (``_compute_score``, PCC, SODA, substitution
detection) compare via ``same_phoneme()``.
"""

import re

# ---------------------------------------------------------------------------
# clean() — mark stripping
# ---------------------------------------------------------------------------

_STRIP_RE = re.compile(r'[0-9:.\-|\sˈˌːˑʰʷʲˠɫ]')


def clean(phoneme: str) -> str:
    """Strip stress marks, length marks, digits, aspiration/coarticulation marks.

    Removes length/stress (``ː ˑ ˈ ˌ``), digits, and common Wav2Vec2
    aspiration/coarticulatory modifiers (``ʰ ʷ ʲ ˠ``) and dark-l (``ɫ``)
    so allophonic variants compare equal to their base phoneme.  The
    voiceless-mark diacritic (``̥``) is deliberately NOT stripped so that
    devoiced productions (e.g. ``d̥``) remain distinct and can still be
    reported by the voicing detectors.
    """
    if not phoneme or phoneme == "-":
        return "-"
    cleaned = _STRIP_RE.sub('', phoneme)
    return cleaned if cleaned else "-"


# ---------------------------------------------------------------------------
# normalize_ipa() — allograph / foreign-spelling translation
# ---------------------------------------------------------------------------

_IPA_NORMALIZE: dict[str, str] = {
    # ---- Allograph unification (both directions covered where needed) ----
    'ɾ': 'r',        # flap -> canonical r (also handled in same_phoneme)
    'ɹ': 'r',        # rhotic -> canonical r
    'g': 'ɡ',        # ASCII g -> IPA ɡ (U+0261) — the only ɡ spelling used
    'ɭ': 'l',        # retroflex l -> l
    'ɕ': 'ʃ',        # alveolo-palatal -> ʃ
    'ʑ': 'ʒ',        # alveolo-palatal -> ʒ
    'ʧ': 'tʃ',       # ʧ ligature -> tʃ
    'ʤ': 'dʒ',       # ʤ ligature -> dʒ
    'œ': 'ə',
    'ɨ': 'i',
    'ʉ': 'u',
    'ɵ': 'ə',
    'ɐ': 'ɑ',
    'ɤ': 'ʌ',
    'ɶ': 'ɔ',
    # ---- Length-mark stripping (word-final after digraphs handled below) ----
    'ː': '',
    'ˑ': '',
    # ---- espeak-ng syllabic consonants -> canonical spellings ----
    'l̩': 'əl',
    'n̩': 'ən',
    'r̩': 'ɚ',
    # ---- English-relevant foreign/model vowel spellings ----
    # The vocab spells /aɪ/ as ``ai``, /eɪ/ as ``ei``, /aʊ/ as ``au``,
    # /oʊ/ as ``ou``, /ɑ/ as bare ``a``, /ɛ/ as ``e``, /ɔ/ as ``o`` in
    # its non-English entries.  Map them onto the curated English vowels.
    'ai': 'aɪ',
    'ei': 'eɪ',
    'au': 'aʊ',
    'ou': 'oʊ',
    'a': 'ɑ',
    'e': 'ɛ',
    'o': 'ɔ',
    # ---- Length-marked long vowels -> their short/diphthong bases ----
    # NOTE: espeak-ng spells English FACE and GOAT with monophthong
    # length marks ("eː", "oː") in many of its language entries, so
    # those two map directly onto the canonical curated DIPHTHONGS.
    # Mapping them to bare "e"/"o" instead would let them fall through
    # the single-char foreign-spelling rules (e -> ɛ, o -> ɔ) and
    # misread every correct FACE/GOAT production as DRESS/LOT.
    'eː': 'eɪ',
    'iː': 'i',
    'oː': 'oʊ',
    'uː': 'u',
    'aː': 'ɑ',
    'ɑː': 'ɑ',
    'ɔː': 'ɔ',
    'ɛː': 'ɛ',
    'ɪː': 'ɪ',
    'ʊː': 'ʊ',
    'æː': 'æ',
    'ʌː': 'ʌ',
    'ɜː': 'ɜ',
    'ɝː': 'ɝ',
    'ɚː': 'ɚ',
    # ---- Circumflexed diphthongs (espeak tonal spellings) ----
    'aɪ̂': 'aɪ',
    'aʊ̂': 'aʊ',
    'oʊ̂': 'oʊ',
    'eɪ̂': 'eɪ',
    'ɔɪ̂': 'ɔɪ',
    # ---- Identity guards: multi-char tokens that contain single-char
    #      keys above MUST match longest-first so 'a' inside 'aɪ' is
    #      never rewritten (aɪ -> ɑɪ would corrupt the expected side). ----
    'aɪ': 'aɪ',
    'aʊ': 'aʊ',
    'eɪ': 'eɪ',
    'oʊ': 'oʊ',
    'ɔɪ': 'ɔɪ',
    'əl': 'əl',
}

# Single-pass longest-match alternation: replaces each key at most once,
# never re-scanning replacement output, so chains like r->ɹ->r collapse
# to their intended net result.
_ALT_RE = re.compile(
    '|'.join(re.escape(k) for k in sorted(_IPA_NORMALIZE, key=len, reverse=True))
)


def normalize_ipa(ipa_string: str) -> str:
    """Map an IPA string (whole word or single phoneme) onto the curated
    English IPA alphabet.

    Applies all ``_IPA_NORMALIZE`` translations in a single longest-match
    pass — multi-character tokens (``aɪ``, ``əl``) always win over the
    single characters inside them (``a``, ``ə``).
    """
    if not ipa_string:
        return ipa_string
    return _ALT_RE.sub(lambda m: _IPA_NORMALIZE[m.group(0)], ipa_string)


# ---------------------------------------------------------------------------
# canonicalize() / same_phoneme() — the full translation
# ---------------------------------------------------------------------------


def canonicalize(phoneme: str) -> str:
    """Full alphabet translation for one phoneme: normalize_ipa() + clean().

    Order matters: the table runs on the RAW spelling first so its
    multi-character keys containing strippable marks (``eː``, ``oː``,
    ``l̩``, ``aɪ̂``…) resolve as intended; only then are residual
    stress/length/aspiration marks stripped.  Cleaning first would eat
    the length mark before the table ever sees it and turn every
    ``Xː`` entry into dead code.
    """
    return clean(normalize_ipa(phoneme))


def same_phoneme(a: str, b: str) -> bool:
    """Compare two phoneme spellings through the alphabet translation.

    Both sides are canonicalized (marks stripped, allographs/foreign
    spellings mapped), so a correct production spelled with an allophonic
    variant (aspirated ``tʰ``, syllabic ``l̩``, rhotic ``ɹ``) still matches
    its target phoneme.

    The American-English flap ``ɾ`` matches BOTH medial /t/ and /d/
    (water -> [wɔɾɚ], ladder -> [læɾɚ]) — the standard allophone, not an
    error.  The voiceless diacritic (``̥``) is preserved, so a devoiced
    production (``d̥`` vs ``d``) remains distinct and keeps its error status.
    """
    if not a or not b:
        return a == b
    ra, rb = clean(a), clean(b)
    if {ra, rb} in ({"t", "ɾ"}, {"d", "ɾ"}):
        return True
    return canonicalize(a) == canonicalize(b)
