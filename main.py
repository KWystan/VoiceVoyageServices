"""
Model-10: Pronunciation Assessment API (Forced Alignment Pipeline).

Replaces the old CTC-argmax + Needleman-Wunsch pipeline with
torchaudio.functional.forced_align for strict 1-to-1 phoneme alignment.

API contract:
    POST /assess  — word, file, age (required)
    GET  /health  — model status
"""

import sys
import subprocess
import logging

# Windows UTF-8 workaround for panphon IPA parsing
if not sys.flags.utf8_mode:
    subprocess.call([sys.executable, "-X", "utf8"] + sys.argv)
    sys.exit()

import os
import torch
import uvicorn


from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import config
from util.word_to_ipa import word_to_ipa
from util.clean_text import _clean_word, clean_ipa, tokenize_ipa
from audio_util.audio_processor import clean_and_prepare_audio
from audio_util.forced_aligner import get_aligner, ForcedAlignmentError
from phoneme_processes import ProcessDetector
from phoneme_processes import pcc as pcc_module
from phoneme_processes import curriculum_map

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

detector = ProcessDetector()

# ---------------------------------------------------------------------------
# Startup warmup
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def warmup():
    """Pre-load DeepFilterNet denoiser so the first noisy recording
    doesn't incur a ~5s lazy-load penalty."""
    try:
        from audio_util.audio_processor import get_denoiser
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
    age: int = Form(...),
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
        # ----- Step 1: Clean target word -----
        word = _clean_word(word)

        # ----- Step 2: Convert target word to IPA -----
        expected_ipa_raw = word_to_ipa(word)
        expected_ipa = clean_ipa(expected_ipa_raw)

        # ----- Step 3: Read and clean audio -----
        raw_audio = await file.read()
        audio_result = clean_and_prepare_audio(raw_audio)

        if not audio_result["ok"]:
            issues = audio_result["issues"]
            quality = audio_result.get("quality", {})
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid Audio",
                    "details": issues,
                    "quality_check": {
                        "passed": False,
                        "hard_issues": [
                            {"check": q["check"], "message": q["message"]}
                            for q in quality.get("hard_issues", [])
                        ] if quality else issues,
                    },
                },
            )

        audio_array = audio_result["audio"]  # np.ndarray, float32, mono, 16kHz

        # ----- Step 4: Tokenize target IPA -----
        expected_tokens = tokenize_ipa(expected_ipa)
        if not expected_tokens:
            return JSONResponse(
                status_code=400,
                content={"error": "Empty phoneme sequence after tokenization."},
            )

        # ----- Step 5: Forced Alignment -----
        audio_tensor = torch.from_numpy(audio_array).float()
        aligner = get_aligner()

        fa_result = aligner.align(audio_tensor, expected_tokens)

        if not fa_result.get("ok", False):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Forced Alignment Failed",
                    "details": fa_result.get("error", "Unknown alignment error"),
                },
            )

        segments = fa_result["segments"]  # includes predicted, score, confidence

        # ----- Step 6: Build breakdown from alignment segments -----
        breakdown: list[dict] = []
        expected_phonemes: list[str] = []
        detected_phonemes: list[str] = []

        for i, seg in enumerate(segments):
            breakdown.append({
                "expected": seg["phoneme"],
                "predicted": seg["predicted"],
                "score": seg["score"],
                "confidence": seg.get("confidence", 1.0),
                "duration_sec": seg.get("duration_sec", 1.0),
            })
            expected_phonemes.append(seg["phoneme"])
            detected_phonemes.append(seg["predicted"])

        # ----- Step 7: Detect phonological processes -----
        processes = detector.detect(breakdown)

        # ----- Step 8: Compute PCC scores -----
        pcc_data = pcc_module.compute_all(breakdown)
        pcc_score = pcc_data.get("pcc", {}).get("pcc", 0.0)
        pcc_r_score = pcc_data.get("pcc_r", {}).get("pcc_r", 0.0)
        pvc_score = pcc_data.get("pvc", {}).get("pvc", 0.0)
        pcc_severity = pcc_data.get("pcc", {}).get("severity", "N/A")

        # ----- Step 9: Curriculum summary (age-applicable processes) -----
        applicable_processes = curriculum_map.get_curriculum_summary(
            processes, age
        )

        # Use PCC as the overall score. For words with few consonants,
        # blend PCC with forced-alignment average score to avoid
        # the "80% PCC wall" where 1-2 wrong consonants produce
        # extreme scores (0%, 50%, 100%).
        total_consonants = pcc_data.get("pcc", {}).get("total_consonants", 0)
        min_cons = config.forced_alignment.min_consonants_for_full_pcc
        if total_consonants == 0:
            overall_score = fa_result.get("overall_score", 0.0)
        elif total_consonants < min_cons:
            # Blend: ratio = consonants / min_cons (e.g. 1/3, 2/3)
            pcc_weight = total_consonants / min_cons
            fa_weight = 1.0 - pcc_weight
            overall_score = (
                pcc_score * pcc_weight + fa_result.get("overall_score", 0.0) * fa_weight
            )
        else:
            overall_score = pcc_score

        # ----- Step 10: Determine pass/fail -----
        # Pass/fail is determined server-side based on overall_score threshold.
        # For vowel-only words, the forced-alignment average score is used instead.
        passed = overall_score >= config.forced_alignment.pcc_pass_threshold

        # ----- Step 11: Build flat response -----
        # New fields + backward-compatible fields for the Flutter app.
        return {
            # --- Flutter-compatible fields ---
            "target_word": word,
            "expected_ipa": ",".join(expected_phonemes),
            "detected_ipa": ",".join(detected_phonemes),
            "overall_score": round(overall_score, 2),
            "assessment": {
                "phoneme_breakdown": breakdown,
                "detected_processes": processes,
            },
            # --- New fields ---
            "age": age,
            "passed": passed,
            "pcc": round(pcc_score, 2),
            "pcc_r": round(pcc_r_score, 2),
            "pvc": round(pvc_score, 2),
            "pcc_severity": pcc_severity,
            "phoneme_header": {
                "expected_sequence": ",".join(expected_phonemes),
                "detected_sequence": ",".join(detected_phonemes),
            },
            "age_applicable_processes": applicable_processes,

            # --- Audio quality assessment ---
            "quality": {
                "warnings": [
                    {"check": q["check"], "message": q["message"]}
                    for q in audio_result.get("quality", {}).get("warnings", [])
                ],
                "rms_value": audio_result.get("quality", {}).get("rms_value", 0.0),
            },
        }

    except ValueError as exc:
        logger.error("OOV word error: %s", exc)
        return JSONResponse(
            status_code=400,
            content={"error": "Out-of-Vocabulary Word", "details": str(exc)},
        )
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
