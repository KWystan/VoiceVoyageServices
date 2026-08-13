import io
import numpy as np
import soundfile as sf
from functools import lru_cache

from .audio_utils import has_speech, resample, compute_snr, format_check
from .audio_quality import check_all as check_audio_quality
from .noise_remover_deepfilter import DeepFilterNoiseRemover
from config import config


@lru_cache(maxsize=1)
def get_denoiser() -> DeepFilterNoiseRemover:
    """Lazy initializer for DeepFilterNet denoiser."""
    return DeepFilterNoiseRemover()


def clean_and_prepare_audio(audio_source):
    """Load audio, check quality, denoise if needed.

    Args:
        audio_source: bytes or file path.

    Returns:
        dict with keys: audio, ok, issues, quality.
    """
    target_sr = config.audio.target_sample_rate

    # Load
    audio, sr = sf.read(
        io.BytesIO(audio_source) if isinstance(audio_source, bytes) else audio_source,
        dtype="float32"
    )

    # Mono + resample to target rate
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio = resample(audio, sr, target_sr)

    # Check speech via VAD
    has_speech_flag = has_speech(audio, target_sr)
    speech_segments = _get_speech_segments(audio, target_sr) if has_speech_flag else []

    # Compute SNR (needed for quality checks regardless of VAD)
    snr_result = compute_snr(audio, target_sr)
    snr_db = snr_result["snr_db"]

    # Run all quality checks
    quality = check_audio_quality(audio, target_sr, snr_db, speech_segments)

    # Reject on hard failures
    if not quality["passed"]:
        issues = [c["message"] for c in quality["hard_issues"]]
        return {
            "audio": audio,
            "ok": False,
            "issues": issues,
            "quality": quality,
        }

    # Denoise if SNR is low (even if quality passes, denoising helps accuracy)
    if snr_result["needs_denoise"]:
        denoiser = get_denoiser()
        audio = denoiser.clean_audio_from_array(audio, target_sr)

    return {
        "audio": audio,
        "ok": True,
        "issues": [],
        "quality": quality,
    }


def _get_speech_segments(audio: np.ndarray, sr: int) -> list:
    """Get VAD speech timestamps for quality analysis.

    Reuses the cached VAD model so it doesn't reload.
    """
    from .audio_utils import get_vad_model
    import torch

    _model = get_vad_model()
    from silero_vad import get_speech_timestamps
    audio_pt = torch.from_numpy(audio)
    return get_speech_timestamps(
        audio_pt, _model, sampling_rate=sr,
        threshold=config.audio.vad_threshold,
    )
