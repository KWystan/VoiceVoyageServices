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

---

## Deployment & hardware specs

Both services are stateless `FastAPI + uvicorn` (`phoneme_service/main.py:60,160`, `dynamic_modules_service/main.py:15`), no DB/volume. Health probe `GET /health` (`phoneme_service/main.py:150`). Base image `python:3.10-slim` (`phoneme_service/Dockerfile:3`, `dynamic_modules_service/Dockerfile:3`).

### phoneme_service (port 8001) — heavy ML

* System: `ffmpeg + git + libsndfile1` `phoneme_service/Dockerfile:8`; Python 3.10 `PYTHONUTF8=1` `Dockerfile:23`
* Deps: `torch>=2.12,<2.14` + `torchaudio>=2.10,<2.12` + `transformers>=5.8` + `librosa + soundfile + panphon + silero-vad + deepfilternet` `phoneme_service/requirements.txt:3`
* Model: `facebook/wav2vec2-lv-60-espeak-cv-ft` `config.py:58` Large 317M, `~1.4 GB` safetensors, lazy `get_loader()` `model/loader.py:99`, `device: auto → cuda if available else cpu` `config.py:59`. Extras lazily cached: `Silero VAD ~6 MB` `audio/utils.py:11`, `DeepFilterNet ~7 MB` `audio/noise_remover.py:84`, startup warmup `main.py:76` pre-loads denoiser.
* Env: `PORT` override (`${PORT:-8001}` `Dockerfile:27`), `PYTHONUTF8=1`; `CORS *` `config.py:52`. First boot downloads from `huggingface.co` unless baked — needs egress `443`.

| tier | vCPU | RAM | Disk (SSD) | GPU | notes |
|---|---|---|---|---|---|
| Minimum (1 concurrent, CPU) | 2 | 4 GB | 20 GB | none | `railway.json:11` healthcheck `300s` for cold load. Inference `1-3s` CPU. Image `~3.5-4.5 GB` uncompressed (torch `~1.2 GB` + model `1.4 GB`). |
| Recommended (5-10 concurrent) | 4 | 8 GB | 30 GB | none | headroom for `48k` denoise resample `config.py:13` + `torch.no_grad` `model/loader.py:72` |
| Accelerated | 4 | 8-16 GB | 30 GB | T4/L4 16 GB | `config:resolve_device()` auto uses `cuda`; latency `~300ms`. Optional. |

`x86_64` only (`torchaudio` wheel). Single `uvicorn` worker `main.py:160` — do not `workers>1` on CPU (each forks model). Scale horizontally via replicas.

### dynamic_modules_service (port 8002) — lightweight

* System: `python:3.10-slim` no apt `Dockerfile:3`; deps `fastapi + uvicorn + openai>=1.40 + httpx + pydantic` `requirements.txt:1`
* Data: `word_bank.json` 114 kB + `module_outlines.json` 7.8 kB + `prompt.md` 5 kB + grade docs `config.py:41`; all cached after first request.
* Env: `ZEN_API_KEY` `config.py:21` via `env_file: .env` `docker-compose.yml:20`, `PORT` override. Egress `https://opencode.ai/zen/v1` `config.py:20`.
* No model/weights — cold start `<2s`, P95 `<200ms` rule-based, `2-6s` LLM path.

| tier | vCPU | RAM | Disk | GPU |
|---|---|---|---|---|
| Minimum & recommended | 0.5-1 | 512 MB - 1 GB | 1 GB | none |

Image `~300-400 MB`.

### Single-VM `docker-compose.yml:5` (both together)

Sum + overhead: **minimum `2-4 vCPU / 8 GB / 30 GB`**, **recommended `4 vCPU / 16 GB / 40 GB`** on `Debian 12 / Ubuntu 22.04 + Docker 24+`. Inbound `8001,8002` (or `80/443` via reverse proxy), outbound `443` to `huggingface.co` (first boot) + `opencode.ai`. Payload per `POST /assess`: `16kHz mono WAV 3s ~96 kB` + response `~2 kB`.

---

## Hugging Face Spaces — Docker free tier

`hf/` is the deploy kit: `hf/Dockerfile.phoneme` / `hf/Dockerfile.modules` are copied to Space root `Dockerfile` by `hf/deploy_hf.ps1:50` (needs `SDK: Docker`, `hardware: CPU Basic (free)`). `CMD ... --port ${PORT:-8001}` `hf/Dockerfile.phoneme:28` binds the Space-injected `PORT=7860`.

* **dynamic_modules_service — yes on free** `hf/deploy_hf.ps1:13`. No weights, `<400 MB`, starts `<2s` — within HF `~60s` startup probe.
* **phoneme_service — no on free** — free `CPU basic` (2 vCPU/16 GB) has `~60s` startup probe vs `60-90s` cold model download + `main.py:76` `warmup()` denoiser lazy-load, so probe fails → container killed → `building/starting forever → crashed` loop. Build also pulls full `torch + torchaudio` and re-downloads `1.4 GB` weights each restart (`model/loader.py:49` fallback) on ephemeral disk. `railway.json:11` uses `healthcheckTimeout:300` for this reason (Railway tolerates it, HF free does not).

Fixes if HF is required: bake weights (`COPY models/` into image), use `torch --index-url https://download.pytorch.org/whl/cpu` slim wheels, lazy-load `Wav2Vec2` on first `POST /assess` not `startup`, remove blocking `warmup`, or swap to smaller `wav2vec2-base-960h` (`~360 MB`). Or keep HF for `modules` and host `phoneme` on Railway Hobby / Fly.io / `4vCPU/8GB` VPS (self-contained `Railway.Dockerfile:26` already configured).

---

## Dev workflow — hot reload

**Flutter app** `Thesis/AGENT.md` `flutter run -d windows` hot reload is a `Dart VM` feature — injects code into running isolate, preserves `ChangeNotifier` state (`ScreeningController`, `GameSessionController`). Use it for ocean-map / screening wizard iteration (`lib/views/screening/screening_page.dart:194`). `flutter clean && flutter pub get` only on dependency changes.

**Backend services** — `uvicorn main:app` `phoneme_service/main.py:160` is **without `--reload` in prod/Docker** (`hf/Dockerfile.phoneme:28`, `Dockerfile:27`). `--reload` re-executes `model/loader.py:38` + `1.4 GB` load on every file save (~60s, doubles RAM per reload). For local dev you may run `python -X utf8 -m uvicorn main:app --reload --port 8001` temporarily, but disable before `docker compose up --build` or HF/Railway deploy.

## Tests

| Service | Count | Key files |
|---|---|---|
| phoneme_service | 241 | test_assessment_service, test_main_endpoint, test_detector_stress, test_hierarchy, test_ipa_normalization, test_forced_aligner, test_pcc, test_syllable, test_audio_*, test_curriculum_map, test_clean_text, test_panphon_module |
| dynamic_modules_service | (see `tests/`) | test_module_service (LLM + fallback), test_module_builders (rule-based), test_prompt_and_parser (no-PII, invented/duplicate/over-limit rejection), test_llm_clients (MockTransport), test_routes (Form params), test_findings |
