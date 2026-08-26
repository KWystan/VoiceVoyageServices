"""Voice Voyage — Unified Services Gateway (FastAPI).

Combines both Phoneme Assessment and Dynamic Module Generation into a single,
lightweight, and direct application suitable for Railway, Docker, or local execution.

Endpoints:
    POST /assess  — Pronunciation assessment (word, age, audio file)
    POST /module  — Practice module generation (age, detected processes JSON)
    GET  /health  — Combined health check for both services
    GET  /        — Service overview & link to /docs
"""

import sys
import os
import json
import logging
import asyncio

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_PHONEME_DIR = os.path.join(_REPO_ROOT, "phoneme_service")
_DYNAMIC_DIR = os.path.join(_REPO_ROOT, "dynamic_modules_service")

for p in (_REPO_ROOT, _PHONEME_DIR, _DYNAMIC_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

# Load .env if present
def _load_dotenv():
    for candidate in [os.path.join(_REPO_ROOT, ".env"), os.path.join(_DYNAMIC_DIR, ".env")]:
        if os.path.exists(candidate):
            with open(candidate, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and not os.environ.get(k):
                            os.environ[k] = v
            break

_load_dotenv()

import uvicorn
import torch
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Optimize PyTorch memory & execution for cloud container
torch.set_grad_enabled(False)
try:
    torch.set_num_threads(2)
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("voicevoyage.unified")

# --- Service Imports ---
from assessment.service import AssessmentService
from assessment.errors import (
    AlignmentError,
    AssessmentError,
    AudioQualityError,
    OutOfVocabularyError,
)
from model.forced_aligner import ForcedAlignmentError

from dynamic_modules_service.models import AssessmentFindings, DetectedProcess
from dynamic_modules_service.service import ModuleService, NoFindingsError, NoOutlineError
from dynamic_modules_service.data import GradeDocuments, MockOutlines, MockWordBank
from dynamic_modules_service.config import config as dynamic_config

# State flags
_model_ready_event = asyncio.Event()
_model_loading_status = "initializing"

# Instantiate services
assessment_service = AssessmentService()

def make_dynamic_service() -> ModuleService:
    bank = MockWordBank()
    return ModuleService(
        outlines=MockOutlines(bank),
        bank=bank,
        grade_documents=GradeDocuments(),
    )

dynamic_service = make_dynamic_service()


async def _background_model_loader():
    """Load models in the background without blocking server startup / health checks."""
    global _model_loading_status
    logger.info("[STARTUP] Background model loader started...")
    
    # 1. Warmup DeepFilterNet
    try:
        from audio.processor import get_denoiser
        denoiser = get_denoiser()
        denoiser._lazy_load()
        logger.info("[STARTUP] ✓ DeepFilterNet denoiser pre-loaded.")
    except Exception as exc:
        logger.warning("[STARTUP] DeepFilterNet warmup skipped: %s", exc)

    # 2. Warmup Wav2Vec2 Forced Aligner
    try:
        from model.forced_aligner import get_aligner
        aligner = get_aligner()
        aligner._lazy_load()
        dummy_audio = torch.zeros(16000, dtype=torch.float32)
        aligner.model_loader.get_logits(dummy_audio)
        logger.info("[STARTUP] ✓ Wav2Vec2 model pre-loaded & quantized.")
    except Exception as exc:
        logger.warning("[STARTUP] Wav2Vec2 warmup error: %s", exc)

    _model_loading_status = "ready"
    _model_ready_event.set()
    logger.info("[STARTUP] ✓ Voice Voyage Unified Backend is 100% ready.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Non-blocking startup: Server binds port immediately in <0.5s
    asyncio.create_task(_background_model_loader())
    yield


# --- FastAPI Initialization ---
app = FastAPI(
    title="Voice Voyage Unified Services",
    description="Unified backend providing Pronunciation Assessment and Dynamic Practice Modules.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Root Overview ---
@app.get("/")
async def root():
    return {
        "service": "Voice Voyage Unified API",
        "version": "2.0.0",
        "status": "online",
        "model_status": _model_loading_status,
        "endpoints": {
            "assess": "POST /assess (form: word, age, file)",
            "module": "POST /module (form: age, processes)",
            "health": "GET /health",
            "docs": "GET /docs",
        }
    }


# --- Health Check Endpoint ---
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_ready": _model_ready_event.is_set(),
        "phoneme_service": {
            "status": "ok",
            "model": "facebook/wav2vec2-lv-60-espeak-cv-ft",
        },
        "dynamic_modules_service": {
            "status": "ok",
            "provider": dynamic_config.llm_provider,
            "model": dynamic_config.llm_model,
        }
    }


# --- Phoneme Assessment Endpoint ---
@app.post("/assess")
async def assess_pronunciation(
    word: str = Form(...),
    file: UploadFile = File(...),
    age: int = Form(..., ge=2, le=12),
):
    """Assess pronunciation of a target word or phrase from an audio recording."""
    # Ensure model has finished loading before assessing
    if not _model_ready_event.is_set():
        try:
            await asyncio.wait_for(_model_ready_event.wait(), timeout=45.0)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=503, detail="Model is still initializing. Please retry in 10 seconds.")

    try:
        raw_audio = await file.read()
        result = assessment_service.assess(word=word, age=age, audio_bytes=raw_audio)
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


# --- Dynamic Modules Endpoint ---
@app.post("/module")
def create_module(
    age: int = Form(...),
    processes: str = Form(...),
):
    """Build a personalized practice module from age + detected processes."""
    try:
        processes_data = json.loads(processes)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"processes is not valid JSON: {exc}",
        ) from exc

    findings = AssessmentFindings(
        age=age,
        processes=tuple(
            DetectedProcess(
                process=p.get("process", ""),
                position=p.get("position", ""),
                detail=p.get("detail", ""),
            )
            for p in processes_data
        ),
    )

    try:
        module = dynamic_service.build_module(findings)
    except (NoFindingsError, NoOutlineError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "module_id": module.module_id,
        "focus_sounds": [s.sound for s in module.focus_sounds],
        "focus_processes": module.focus_processes,
        "outline_id": module.outline_id,
        "outline_title": module.outline_title,
        "levels": [
            {
                "level": level.value,
                "items": [
                    {
                        "text": item.text,
                        "target_sound": item.target_sound,
                        "position": item.position,
                    }
                    for item in items
                ],
            }
            for level, items in module.levels.items()
        ],
        "rationale": module.rationale,
        "generated_by": module.generated_by,
        "warning": module.warning,
    }


if __name__ == "__main__":
    port_env = os.environ.get("PORT", "8000")
    try:
        port = int(port_env)
    except ValueError:
        port = 8000
    print(f"Starting Voice Voyage Unified API on port {port}...")
    uvicorn.run("app:app", host="0.0.0.0", port=port)
