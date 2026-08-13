# Voice Voyage Services

Backend monorepo for **Voice Voyage** — a speech-screening and phonics-learning
app. Two independent FastAPI services run side by side (separate processes,
separate containers, no shared bottleneck):

| Service | Folder | Port | Job |
|---|---|---|---|
| **Phoneme Service** | `phoneme_service/` | 8001 | WAV audio → Wav2Vec2 forced alignment → phoneme scores, phonological process detection, PCC metrics |
| **Dynamic Modules Service** | `dynamic_modules_service/` | 8002 | Assessment findings → personalized practice module (syllables → words → phrases → sentences) via OpenCode Zen (DeepSeek V4 Flash Free), with a rule-based fallback |

## Quick start (local)

```bash
# phoneme service
cd phoneme_service
python -X utf8 -m uvicorn main:app --port 8001

# dynamic modules service (LLM; rule-based fallback without a key)
cd dynamic_modules_service
copy ..\.env.example ..\.env        # fill in ZEN_API_KEY
python -X utf8 -m uvicorn main:app --port 8002
```

## Docker (both services at once)

```bash
copy .env.example .env              # fill in ZEN_API_KEY
docker compose up --build
# phoneme          -> http://localhost:8001/health
# dynamic-modules  -> http://localhost:8002/health
```

## API

- `POST phoneme_service:8001/assess` — multipart `word`, `age`, `file` → assessment response
- `POST dynamic_modules_service:8002/module` — JSON `{age, processes, pcc}` → practice module
- Both expose `GET /health`

See each service's `CLAUDE.md`-adjacent docs and the root `CLAUDE.md` for architecture details.
