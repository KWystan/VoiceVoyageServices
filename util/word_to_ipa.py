import re
import eng_to_ipa
from util.ipa_normalization import normalize_ipa
from util.clean_text import _clean_word


# eng_to_ipa wraps unknown/out-of-vocabulary words in asterisks.
# Pattern: one or more asterisks at start and end with content between.
_OOV_PATTERN: re.Pattern = re.compile(r"^\*+\s*(.+?)\s*\*+$")

# Custom IPA override map for CV syllables used in Bubble Bay game level.
# These are not real English words so eng_to_ipa cannot convert them.
_CUSTOM_IPA_MAP: dict[str, str] = {
    "pa": "pɑ",
    "ba": "bɑ",
    "ta": "tɑ",
    "ka": "kɑ",
}


def word_to_ipa(word: str) -> str:
    """Convert an English word to IPA using eng_to_ipa.

    Raises
    ------
    ValueError
        If the word is out-of-vocabulary (eng_to_ipa returns an
        asterisk-wrapped placeholder).
    """
    word = _clean_word(word)
    if not word:
        return ""

    # Check custom IPA map first (for CV syllables etc. that eng_to_ipa cannot handle)
    word_lower = word.lower()
    if word_lower in _CUSTOM_IPA_MAP:
        return normalize_ipa(_CUSTOM_IPA_MAP[word_lower])

    ipa = eng_to_ipa.convert(word)

    # Detect OOV: eng_to_ipa wraps unknown words like *pider*
    m = _OOV_PATTERN.match(ipa)
    if m:
        unknown = m.group(1)
        raise ValueError(
            f"Word '{word}' is out-of-vocabulary for eng_to_ipa "
            f"(returned '*{unknown}*'). "
            f"Add '{word}' to the dictionary or use a known word."
        )

    ipa = re.sub(r"['?/]", "", ipa).strip()
    # Normalize on the EXPECTED (target) side too: eng_to_ipa emits ligatures
    # (ae, oh) and script-g allographs, while the Wav2Vec2/detected side is run
    # through normalize_ipa in main.py. Without symmetric normalization the
    # two sides use different Unicode for the same phoneme and score_pair
    # returns near-zero. Apply the SAME map here so both sides agree.
    ipa = normalize_ipa(ipa)
    return ipa
