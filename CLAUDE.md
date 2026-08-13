# CLAUDE.md

Guidance for working in the **FinalPhonemeRecognizer** backend of Voice Voyage.

## Overview

FastAPI pronunciation-assessment API. WAV audio in → Wav2Vec2 forced alignment
against target IPA phonemes → per-phoneme scores → phonological process
detection → clinical metrics (PCC/PCC-R/PVC) → parent-friendly
curriculum summary. Serves the Flutter app (`Thesis/`) via `POST /assess`.

## Commands

```bash
python -X utf8 main.py              # Start API server (port 8001)
python -m pytest tests/              # Run all tests (261) — tests/ is local-only
python -X utf8 records/simulate_curated.py   # Random-error simulation (records/)
python -X utf8 scripts/age_norms.py  # Dev-only age norms (kept for reference)
pip install -r requirements.txt
docker build -t phoneme-recognizer . && docker run -p 8001:8001 phoneme-recognizer
```

**Windows UTF-8 note:** always use `python -X utf8` (or `PYTHONUTF8=1`) —
panphon IPA parsing breaks without it.

**Git note:** remote is `github.com/KWystan/phoneme-recognizer` (single
`first commit`). Only runtime files are tracked. Ignored: `archive/`,
`docs/`, `scripts/`, `tests/`, `records/`, `.agents/`, `.vscode/`,
`models/`, `__pycache__/`, and ALL `__init__.py` files (kept local by
request — imports are submodule-style so a fresh clone works without them).

## Architecture (self-explanatory folders, dependency rule)

```
main.py (thin HTTP adapter)
  └─ assessment/   — orchestration + DI (service.py, errors.py, response_builder.py)
  └─ ipa/          — phoneme symbols & text (curated_words.py, normalization.py,
                     clean_text.py, panphon_module.py)
  └─ detection/    — clinical analysis (detector.py, pcc.py, syllable.py,
                     curriculum_map.py, utils.py, constants.py)
  └─ audio/        — audio I/O (processor.py, quality.py, utils.py, noise_remover.py)
  └─ model/        — ML model (loader.py, forced_aligner.py)
```

Dependencies point inward: `assessment → {ipa, detection, audio, model}`,
`detection → ipa`, `model → ipa`, `ipa → nothing internal`. No cycles
(verified by the dependency check). OOP where state/lifecycle/polymorphism
earns it (service, preparer, loader/aligner singletons, response builder);
pure functions stay functions.

## Data Flow

```
WAV audio → audio/processor (AudioPreparer: load → mono → resample 16kHz →
single VAD pass → SNR → quality gate → denoise if SNR < 20dB)
→ model/forced_aligner (torchaudio forced_align on expected IPA tokens)
→ per-phoneme segments: predicted, confidence, score
→ detection/detector (declarative _SUBSTITUTION_SPECS + deletions)
  → ASHA hierarchy filter → pcc.py
→ curriculum_map.py (age-filtered parent labels) → ResponseBuilder → JSON
```

Expected IPA comes from `data/curated_words.csv` (word → comma-separated
phonemes, 65 app words, all verified present in the Wav2Vec2 vocab).
`ipa/word_to_ipa.py` (eng_to_ipa) remains as a dev fallback.

## Key Modules

| File | Responsibility |
|---|---|
| `main.py` | Thin HTTP adapter: `POST /assess` + `GET /health`; error mapping to status codes |
| `assessment/service.py` | **`AssessmentService`** — OOP orchestrator, collaborators injected (testable with fakes) |
| `assessment/errors.py` | Domain errors: `AssessmentError` family (`OutOfVocabularyError`, `AudioQualityError`, `AlignmentError`) |
| `assessment/response_builder.py` | **`ResponseBuilder`** — shapes the flat /assess schema (Flutter-compatible) |
| `config.py` | Singleton `AppConfig` — thresholds, model id, `pcc_pass_threshold` (80), `min_consonants_for_full_pcc` (3), boost amounts |
| `model/loader.py` | Wav2Vec2 loader singleton (`facebook/wav2vec2-lv-60-espeak-cv-ft`) |
| `model/forced_aligner.py` | CTC forced alignment; `_build_segment()` per phoneme; `predicted` = argmax token; `confidence` = mean prob of the EXPECTED token |
| `audio/processor.py` | **`AudioPreparer`** class — load → single VAD pass → SNR → quality gate → conditional denoise (denoiser injectable) |
| `audio/quality.py` | 5 checks (rms, clipping, duration, speech ratio, SNR); `check_all()` groups hard/soft |
| `ipa/normalization.py` | **Alphabet translation layer** — `clean()`, `normalize_ipa()`, `canonicalize()`, `same_phoneme()` |
| `ipa/clean_text.py` | `clean_ipa()`, `tokenize_ipa()` (syllabic-əl guard), `_clean_word()` |
| `ipa/word_to_ipa.py` | eng_to_ipa wrapper (dev fallback; custom map for pa/ba/ta/ka syllables) |
| `ipa/panphon_module.py` | Close-pair/devoicing boost table (config-sourced), feature distance |
| `detection/detector.py` | **Declarative detector table** (`_SUBSTITUTION_SPECS` + predicates) + 3 deletion detectors + ASHA hierarchy |
| `detection/utils.py` | `manner()`, `place()`, `is_consonant()`, `get_position(idx, breakdown)` |
| `detection/pcc.py` | PCC/PCC-R/PVC, severity bands, `compute_overall_score()` blend |
| `detection/soda.py` | SODA typology (S/O/D/A) |
| `detection/curriculum_map.py` | Table-driven `_TRANSLATORS` → parent display labels, age-bracket filter |
| `data/curated_words.csv` | Curated word → phonemes (single source of truth for assessment) |

## The Alphabet Translation Layer (`ipa/normalization.py`)

The expected side (curated list) and the predicted side (raw Wav2Vec2
espeak-ng tokens) use different IPA spellings for the same phonemes. All
correctness comparisons go through `same_phoneme()`:

- **`clean()`** — strips stress/length/aspiration marks (`ˈ ˌ ː ˑ ʰ ʷ ʲ ˠ ɫ`,
  digits). Keeps `̥` so devoicing stays detectable.
- **`normalize_ipa()`** — single-pass longest-match mapping: allographs
  (`g→ɡ`, `ɹ→r`, `ɾ→r`, `ʧ→tʃ`), espeak syllabics (`l̩→əl`, `r̩→ɚ`), foreign
  vowels (`ai→aɪ`, `a→ɑ`, `ei→eɪ`, `au→aʊ`, `ou→oʊ`, `e→ɛ`, `o→ɔ`).
  Identity guards (`aɪ→aɪ`…) prevent corruption of multi-char tokens.
- **`same_phoneme(a, b)`** — canonicalize both sides and compare. Flap
  `ɾ` matches both medial /t/ and /d/; `d̥` ≠ `d` by design.

Used by: `forced_aligner._compute_score`, PCC correctness, SODA `C`,
detector `_is_substitution`.

## Scoring Philosophy

1. **Match** — `same_phoneme(predicted, expected)` → 100 (allophonic
   spellings like `tʰ`, `l̩`, `ɹ`, `ɑ1` score 100)
2. **Mismatch** — `confidence * 100`, duration penalties (short <0.03s −20,
   long >0.5s −10), close-pair +20 / devoicing +15 boosts
3. **Deletion** — predicted `-` or too short → 0

**No confidence gate on substitutions**: `confidence` is the expected
token's probability, so a mismatch implies it is < 0.5 — confident wrong
phonemes (0.4–0.5) are still flagged. Overall score = PCC (blended with
FA average when consonants < `min_consonants_for_full_pcc`); pass ≥ 80.

## Detector Notes

- 14 detectors + ASHA hierarchy (manner > place > sonority > voicing >
  deletions). `_index` keys group by phoneme; WSD sets `skip_indices`.
- Affricate→stop/fricative is **Deaffrication** (never Stopping).
- `n→k` fires Denasalization (masks Backing). Word-final cluster deletions
  report Cluster Reduction over FCD.
- Medial singleton deletion → `Consonant Deletion@Medial` →
  "Medial Consonant Deletion" label.
- `tokenize_ipa` guard: `əl` only matches word-final or before a consonant
  (`balloon` → `b,ə,l,u,n`), keeping the /l/ visible as a consonant.
- No process fires for vowel-only errors or allophonic spellings.

## Tests (local-only, 261)

| File | Covers |
|---|---|
| `tests/test_assessment_service.py` | **Full pipeline with fakes** — schema contract, errors (OOV/quality/alignment), age filtering, DI |
| `tests/test_main_endpoint.py` | HTTP contract via TestClient — 200/400/500 mapping, /health |
| `tests/test_hierarchy.py` | ASHA hierarchy, exclusivity, declarative registry, alphabet translation, scoring |
| `tests/test_ipa_normalization.py` | clean/normalize/canonicalize/same_phoneme, digraph guards |
| `tests/test_detector_stress.py` | 127-word scenario stress (all detectors) |
| `tests/test_clean_text.py` | tokenization (əl guard), normalization |
| `tests/test_curriculum_map.py` | age brackets, display labels (incl. Medial), translators |
| `tests/test_pcc.py` | PCC/PCC-R/PVC, severity bands, overall-score blend |
| `tests/test_soda.py` | SODA classification, additions, distortions |
| `tests/test_syllable.py` | syllabification, coda fix, weak syllable deletion |
| `tests/test_audio_quality.py` / `test_audio_processor.py` | quality checks, load/mono/resample, SNR, AudioPreparer |
| `tests/test_forced_aligner.py` | path→segments, token resolution, predicted resolution, segment building, score |
| `tests/test_panphon_module.py` | boost table, config references |

`records/` (gitignored) holds the curated-word simulation: script + 1,300
trial results CSV (`simulation_results.csv`).  `scripts/age_norms.py` is the
McLeod & Crowe norms module, kept in the dev folder for reference (not part
of the /assess flow).
