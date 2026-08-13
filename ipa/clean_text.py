import re

from ipa.normalization import normalize_ipa  # re-exported for back-compat

_VOWELS = {
    'a', 'e', 'i', 'o', 'u', 'ə', 'ɔ', 'æ', 'ɑ', 'ʌ', 'ɛ', 'ɪ', 'ʊ',
    'aɪ', 'eɪ', 'oʊ', 'aʊ', 'ɔɪ', 'aː', 'eː', 'iː', 'oː', 'uː',
    'ɚ', 'ɝ', 'əl',
}
_CONSONANTS = {
    'p', 'b', 't', 'd', 'k', 'g', 'ɡ', 'f', 'v', 'θ', 'ð', 's', 'z', 'ʃ', 'ʒ', 'h', 'tʃ', 'dʒ', 'm', 'n', 'ŋ', 'l', 'r', 'ɹ', 'w', 'j',
}
_MULTI = sorted([p for p in (_VOWELS | _CONSONANTS) if len(p) > 1], key=len, reverse=True)


def clean_ipa(raw: str) -> str:
    cleaned = re.sub(r"[0-9:.\-|ˈˌːˑ]", "", raw)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def tokenize_ipa(ipa_string: str) -> list:
    if not ipa_string:
        return []
    tokens, i = [], 0
    n = len(ipa_string)
    while i < n:
        if ipa_string[i] == " ":
            tokens.append("#")
            i += 1
            continue
        matched = False
        for m in _MULTI:
            if ipa_string[i:].startswith(m):
                # Syllabic-l guard: 'əl' is only a genuine syllabic liquid
                # when it is word-final or followed by a consonant (apple,
                # bottle, vegetable).  When a vowel follows, the /l/ is the
                # onset of the next syllable (balloon "bəlun" -> b,ə,l,u,n),
                # so 'əl' must NOT swallow it — otherwise the consonant /l/
                # becomes invisible to process detection and PCC scoring.
                if (m == "əl" and i + len(m) < n
                        and ipa_string[i + len(m)] in _VOWELS):
                    continue
                tokens.append(m)
                i += len(m)
                matched = True
                break
        if not matched:
            tokens.append(ipa_string[i])
            i += 1
    return tokens


def _clean_word(word: str) -> str:
    word = re.sub(r"[^A-Za-z\s'-]", " ", word)
    return re.sub(r"\s+", " ", word).strip()
