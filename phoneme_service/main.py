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
import uvicorn


from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

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

app = FastAPI(title="Model-10 Pronunciation Assessment", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.server.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = AssessmentService()

# ---------------------------------------------------------------------------
# Startup warmup
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def warmup():
    """Pre-load DeepFilterNet denoiser so the first noisy recording
    doesn't incur a ~5s lazy-load penalty."""
    try:
        from audio.processor import get_denoiser
        denoiser = get_denoiser()
        denoiser._lazy_load()
        logger.info("DeepFilterNet denoiser pre-loaded on startup.")
    except Exception as exc:
        logger.warning("DeepFilterNet startup warmup skipped: %s", exc)


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

@app.get("/health")
async def health():
    return {"status": "ok", "model": config.model.wav2vec_model_id}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
    )
