# CLAUDE.md

Guidance for working in the **Voice Voyage Services** monorepo — the backend
of Voice Voyage (speech screening + phonics learning).

## Two services (separate processes, run concurrently)

| Service | Folder | Port | Stack |
|---|---|---|---|
| Phoneme Service | `phoneme_service/` | 8001 | FastAPI, torch, Wav2Vec2 forced alignment |
| Dynamic Modules Service | `dynamic_modules_service/` | 8002 | FastAPI, OpenCode Zen (hy3-free free tier), rule-based fallback |

Both are fully self-contained (own config, deps, data, Dockerfile) and run
via `docker compose up` or independently.

## Cross-service contract

The two services connect through the mobile app (no direct service-to-service
calls). `POST phoneme_service:8001/assess` returns
`assessment.detected_processes` as `[{process, position, detail}]`; the app
forwards that array verbatim as the `processes` Form param (a JSON string) to
`POST dynamic_modules_service:8002/module`, alongside `age`. The dynamic
service's `FindingsAnalyzer` re-derives target sounds from `processes[].detail`
via regex `/([^/]+)/`, so the `detail` format `/expected/ -> [predicted]` is
part of the contract.

## Commands

```bash
# Phoneme service
cd phoneme_service
python -X utf8 -m uvicorn main:app --port 8001
python -X utf8 -m pytest tests/          # 241 tests (tests/ is local-only)
python -X utf8 records/simulate_curated.py   # simulation

# Dynamic modules service
cd dynamic_modules_service
python -X utf8 -m uvicorn main:app --port 8002
python -X utf8 -m pytest tests/          # tests/ is local-only

# Both together
docker compose up --build
```

**Windows UTF-8 note:** always use `python -X utf8` (or `PYTHONUTF8=1`).
Both `main.py` entry points also re-exec themselves with `-X utf8` when not
already in UTF-8 mode, so the services boot correctly even without the flag.

**Secrets:** `ZEN_API_KEY` lives in `.env` (gitignored; see `.env.example`).
Never hardcode API keys. The Dynamic Modules free tier may use prompt data
for model improvement — never send child names/IDs/PII in prompts (enforced
by a test).

**Git note:** remote `github.com/KWystan/phoneme-recognizer`; runtime files
tracked only. Ignored: `tests/`, `records/`, `scripts/`, `archive/`,
`docs/`, `models/`, `__pycache__/`, `.env`, all `__init__.py` (imports are
submodule-style — fresh clones boot as namespace packages).

---

## phoneme_service — architecture

```
main.py (thin HTTP adapter)
  └─ assessment/   — AssessmentService (DI orchestrator), errors, ResponseBuilder
  └─ ipa/          — curated_words (runtime source of truth), normalization,
                     clean_text, panphon_module
  └─ detection/    — detector (declarative _SUBSTITUTION_SPECS), pcc, syllable,
                     curriculum_map, utils, constants
  └─ audio/        — AudioPreparer: load → single VAD pass → SNR → quality → denoise
  └─ model/        — Wav2Vec2 loader, forced_aligner
```

Dependency rule: `assessment → {ipa, detection, audio, model}`,
`detection → ipa`, `model → ipa`, `ipa → nothing internal`. No cycles.
OOP where state/lifecycle earns it; pure functions stay functions.

Data flow: WAV → AudioPreparer → forced_aligner (expected IPA from
`data/curated_words.csv`) → per-phoneme segments → detector → ASHA hierarchy
→ PCC → curriculum labels → ResponseBuilder → JSON.

Alphabet translation: `ipa/normalization.py` — `same_phoneme()` maps raw
Wav2Vec2 spellings (`tʰ`, `l̩`, `ɹ`, `ɑ1`…) to curated spellings for all
correctness checks. Scoring: match → 100; mismatch → conf*100 ± duration
penalties + boosts; deletion → 0. No confidence gate on substitutions.
Pass ≥ 80 (PCC, blended with FA average for few-consonant words).

Detector design (`detection/detector.py`): substitution detectors are
declarative — one shared scanner (`_scan_substitutions`) driven by the
`_SUBSTITUTION_SPECS` table of (process name, pure predicate); adding a
process is one table row + one predicate. The voicing detector is the sole
exception (panphon features + position-dependent naming: Prevocalic Voicing /
Devoicing / Final Devoicing). Deletion detectors only fire on phonemes not
covered by Weak Syllable Deletion's `skip_indices`. Every process carries an
internal `_index`; `_apply_clinical_hierarchy` groups by `_index` and keeps
the highest-priority process per index (ASHA order: manner changes > place >
sonority > voicing > deletions), then strips `_index` from the response.

---

## dynamic_modules_service — architecture

```
main.py (FastAPI, port 8002 — endpoint here, like the phoneme service)
  └─ service.py   — ModuleService (use case), RuleBasedModuleBuilder,
                    LLMModuleBuilder, FindingsAnalyzer, OutlineSelector
  └─ llm.py       — ZenLLMClient (OpenAI-compatible), PromptBuilder,
                    LLMResponseParser
  └─ data.py      — MockOutlines, MockWordBank
  └─ models.py    — dataclasses (value objects)
  └─ data/        — module_outlines.json (MOCK outlines), word_bank.json,
                    prompt.md (ASHA summary + selection rules fed to the LLM),
                    ASHA-Aligned ... CSV word lists (reference only)
```

Endpoint: `POST /module` with Form params — `age: int = Form(...)` and
`processes: str = Form(...)` (JSON array of `{process, position, detail,
target_sound?}`). Minimal flat layout — no over-engineered layers.

Flow: findings → focus sounds → matching outlines → LLM (or rule-based)
selects items per level from the bank → validated `LearningModule`
(syllables → words → phrases → sentences) → JSON. Items are only ever
SELECTED from the bank — invented words are rejected. The word bank
(`data/word_bank.json`) is the single source of item text + phonemes;
`MockOutlines` resolves each outline's level pools by item text against the
bank, so outlines store text references only. The LLM prompt is a static
`data/prompt.md` (ASHA development summary per age bracket + selection
rules) — the `ASHA-Aligned ...` CSVs still sit in `data/` but no code loads
them. The `AshaGroup`/`AshaErrorPattern`/`AshaBracket` dataclasses in
`models.py` are vestigial (leftovers from a removed CSV parser).

Config: `llm_provider: none | zen`, `llm_model: hy3-free`,
`api_key_env: ZEN_API_KEY` (from env), `max_retries: 4`,
`request_timeout_sec: 60`. The free tier is provider-throttled; any failure
surfaces as `LLMError`, and `ModuleService.build_module` retries (4×) then
falls back to the rule-based builder, attaching a `warning` field to the
module. `deepseek-v4-flash-free` was retired (throttled provider-side);
working free-tier models are `hy3-free` and `laguna-s-2.1-free`.

## Tests

| Service | Count | Key files |
|---|---|---|
| phoneme_service | 241 | test_assessment_service, test_main_endpoint, test_detector_stress, test_hierarchy, test_ipa_normalization, test_forced_aligner, test_pcc, test_syllable, test_audio_*, test_curriculum_map, test_clean_text, test_panphon_module |
| dynamic_modules_service | (see `tests/`) | test_module_service (LLM + fallback), test_module_builders (rule-based), test_prompt_and_parser (no-PII, invented/duplicate/over-limit rejection), test_llm_clients (MockTransport), test_routes (Form params), test_findings |
