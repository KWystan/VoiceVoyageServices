"""
Model-10: Pronunciation Assessment API (Forced Alignment Pipeline).

Replaces the old CTC-argmax + Needleman-Wunsch pipeline with
torchaudio.functional.forced_align for strict 1-to-1 phoneme alignment.

API contract:
    POST /assess  — word, file, age (required)
    GET  /health  — model status

This module is a thin HTTP adapter: form parsing + error mapping.
All pipeline logic lives in ``services.service``.
"""

import sys
import subprocess
import logging

# Windows UTF-8 workaround for panphon IPA parsing
if not sys.flags.utf8_mode:
    subprocess.call([sys.executable, "-X", "utf8"] + sys.argv)
    sys.exit()

import os
import asyncio
import uvicorn


from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Load dedicated .env (its own, not root) — mirrors dynamic service behavior
def _load_dotenv():
    for cand in [os.path.join(_PROJECT_ROOT, ".env"), os.path.join(os.path.dirname(_PROJECT_ROOT), ".env")]:
        if os.path.exists(cand):
            with open(cand, encoding="utf-8") as f:
                for line in f:
                    line=line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k,_,v=line.partition("=")
                    k=k.strip(); v=v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k]=v
            break
_load_dotenv()

try:
    from phoneme_service.config import config
except ImportError:
    from config import config
from assessment.service import AssessmentService
from assessment.errors import (
    AlignmentError,
    AssessmentError,
    AudioQualityError,
    OutOfVocabularyError,
)
from model.forced_aligner import ForcedAlignmentError

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Non-blocking warmup — prevents Railway probe timeout (model 1.4GB)
# ---------------------------------------------------------------------------

_model_ready = asyncio.Event()
_model_status = "initializing"


async def _background_warmup():
    global _model_status
    # Dedicated env var: HF_TOKEN presence logged without leaking value
    tok = config.model.get_hf_token()
    logger.info("[STARTUP] Background warmup started... (HF_TOKEN=%s, VV_FP16=%s, PHONEME_PRELOAD=%s)",
                "set" if tok else "missing", config.model.use_fp16, config.model.preload_in_background)
    if not tok:
        logger.warning("[STARTUP] HF_TOKEN not set — unauthenticated Hub (rate-limited, slower)")
    try:
        from audio.processor import get_denoiser
        await asyncio.to_thread(lambda: get_denoiser()._lazy_load())
        logger.info("DeepFilterNet denoiser pre-loaded.")
    except Exception as exc:
        logger.warning("DeepFilterNet startup warmup skipped: %s", exc)

    if not config.model.preload_in_background:
        logger.info("[STARTUP] PHONEME_PRELOAD=0 — skipping Wav2Vec2 preload (lazy on first /assess)")
    else:
        try:
            from model.forced_aligner import get_aligner
            import torch

            def _load_wav2vec():
                a = get_aligner()
                a._lazy_load()
                t = torch.zeros(16000, dtype=torch.float32)
                a._loader.get_logits(t)

            await asyncio.to_thread(_load_wav2vec)
            logger.info("Wav2Vec2 pre-loaded & quantized.")
        except Exception as exc:
            logger.warning("Wav2Vec2 background warmup skipped: %s", exc)

    _model_status = "ready"
    _model_ready.set()
    logger.info("[STARTUP] Phoneme service ready.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_background_warmup())
    yield


app = FastAPI(title="Model-10 Pronunciation Assessment", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.server.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

service = AssessmentService()


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------

@app.post("/assess")
async def assess_pronunciation(
    word: str = Form(...),
    file: UploadFile = File(...),
    age: int = Form(..., ge=2, le=12),
):
    """Assess pronunciation of a target word from an audio recording.

    Parameters
    ----------
    word : str
        Target English word to assess.
    file : UploadFile
        Audio recording (WAV, MP3, OGG).
    age : int
        Child's age in years (required).

    Returns
    -------
    dict with ``overall_score``, ``expected_ipa``, ``detected_ipa``,
    ``assessment`` (backward-compatible with Flutter app), plus
    ``pcc``, ``phoneme_header``, and ``age_applicable_processes``.
    """
    if not _model_ready.is_set():
        try:
            await asyncio.wait_for(_model_ready.wait(), timeout=45.0)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=503, detail="Model is still initializing. Please retry in 10 seconds.")

    try:
        raw_audio = await file.read()
        result = service.assess(word=word, age=age, audio_bytes=raw_audio)
        return JSONResponse(content=result)

    except OutOfVocabularyError as exc:
        logger.error("OOV word error: %s", exc)
        return JSONResponse(status_code=400, content=exc.payload)
    except AudioQualityError as exc:
        logger.info("Audio quality rejection: %s", exc.details)
        return JSONResponse(status_code=400, content=exc.payload)
    except AlignmentError as exc:
        logger.error("Alignment error: %s", exc)
        return JSONResponse(status_code=400, content=exc.payload)
    except AssessmentError as exc:
        logger.error("Assessment error: %s", exc)
        return JSONResponse(status_code=400, content=exc.payload)
    except ForcedAlignmentError as exc:
        logger.error("ForcedAlignmentError: %s", exc)
        return JSONResponse(
            status_code=400,
            content={"error": "Alignment Error", "details": str(exc)},
        )
    except Exception as exc:
        logger.exception("Unhandled error in /assess")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "details": str(exc)},
        )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {"service": "Voice Voyage Phoneme Service", "status": "online", "model_status": _model_status, "model": config.model.wav2vec_model_id}


@app.get("/health")
async def health():
    return {"status": "ok", "model": config.model.wav2vec_model_id, "model_ready": _model_ready.is_set(), "model_status": _model_status}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Railway injects PORT, Azure injects WEBSITES_PORT; respect either
    raw = os.environ.get("PORT") or os.environ.get("WEBSITES_PORT")
    try:
        port = int(raw) if raw else config.server.port
    except ValueError:
        port = config.server.port
    uvicorn.run(
        app,
        host=config.server.host,
        port=port,
    )
