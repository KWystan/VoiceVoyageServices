import io
import numpy as np
import soundfile as sf
from functools import lru_cache

from .utils import resample, compute_snr
from .quality import check_all as check_audio_quality
from .noise_remover import DeepFilterNoiseRemover
from config import config


@lru_cache(maxsize=1)
def get_denoiser() -> DeepFilterNoiseRemover:
    """Lazy initializer for DeepFilterNet denoiser."""
    return DeepFilterNoiseRemover()


class AudioPreparer:
    """Loads, quality-checks and (if needed) denoises assessment audio.

    One pipeline: load -> mono/resample -> single VAD pass -> SNR ->
    quality gate -> conditional denoise.  The denoiser is injected via
    ``denoiser_factory`` so tests can stub it out.
    """

    def __init__(self, *, config=config, denoiser_factory=get_denoiser):
        self._config = config
        self._denoiser_factory = denoiser_factory

    def prepare(self, audio_source):
        """Prepare audio for assessment.

        Args:
            audio_source: bytes or file path.

        Returns:
            dict with keys: audio, ok, issues, quality.
        """
        audio, sr = _load_audio(audio_source)

        # Single VAD pass — segments drive both the speech check and SNR
        speech_segments = _get_speech_segments(audio, sr)
        snr_result = compute_snr(audio, sr, speech_segments=speech_segments)
        snr_db = snr_result["snr_db"]

        # Run all quality checks
        quality = check_audio_quality(audio, sr, snr_db, speech_segments)

        # Reject on hard failures
        if not quality["passed"]:
            return {
                "ok": False,
                "issues": [c["message"] for c in quality["hard_issues"]],
                "quality": quality,
            }

        # Denoise if SNR is low (even if quality passes, denoising helps accuracy)
        if snr_result["needs_denoise"]:
            audio = self._denoiser_factory().clean_audio_from_array(audio, sr)

        return {
            "audio": audio,
            "ok": True,
            "issues": [],
            "quality": quality,
        }


def clean_and_prepare_audio(audio_source):
    """Convenience wrapper around ``AudioPreparer().prepare()``."""
    return AudioPreparer().prepare(audio_source)


def _load_audio(audio_source):
    """Load WAV bytes/path, convert to mono, resample to the target rate.

    Returns ``(audio, sr)`` — ``audio`` is a 1-D float32 array at
    ``config.audio.target_sample_rate``.
    """
    target_sr = config.audio.target_sample_rate

    audio, sr = sf.read(
        io.BytesIO(audio_source) if isinstance(audio_source, bytes) else audio_source,
        dtype="float32"
    )

    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return resample(audio, sr, target_sr), target_sr


def _get_speech_segments(audio: np.ndarray, sr: int) -> list:
    """Get VAD speech timestamps for quality analysis.

    Reuses the cached VAD model so it doesn't reload.
    """
    import torch
    from silero_vad import get_speech_timestamps

    from .utils import get_vad_model

    _model = get_vad_model()
    audio_pt = torch.from_numpy(audio)
    return get_speech_timestamps(
        audio_pt, _model, sampling_rate=sr,
        threshold=config.audio.vad_threshold,
    )
