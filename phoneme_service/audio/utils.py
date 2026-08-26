import numpy as np
import torch
import librosa
from silero_vad import load_silero_vad, get_speech_timestamps
from functools import lru_cache
try:
    from phoneme_service.config import config
except ImportError:
    from config import config


@lru_cache(maxsize=1)
def get_vad_model():
    """Lazy initializer for Silero VAD model."""
    return load_silero_vad()


def has_speech(audio: np.ndarray, sr: int = None, threshold: float = None) -> bool:
    """Return True if Silero VAD detects speech in the audio."""
    if sr is None:
        sr = config.audio.target_sample_rate
    if threshold is None:
        threshold = config.audio.vad_threshold
    if len(audio) == 0:
        return False
    _model = get_vad_model()
    audio_pt = torch.from_numpy(audio)
    segments = get_speech_timestamps(audio_pt, _model, sampling_rate=sr, threshold=threshold)
    return len(segments) > 0


def resample(audio: np.ndarray, orig_sr: int, target_sr: int = None) -> np.ndarray:
    """Resample audio to target sample rate."""
    if target_sr is None:
        target_sr = config.audio.target_sample_rate
    if orig_sr == target_sr:
        return audio
    return librosa.resample(audio, orig_sr=orig_sr, target_sr=target_sr)


def compute_snr(audio: np.ndarray, sr: int = None,
                speech_segments: list = None) -> dict:
    """Measure SNR. Returns snr_db, ok, needs_denoise.

    ``speech_segments`` are the VAD timestamps (list of dicts with
    ``start``/``end``).  When provided, the VAD model is NOT re-run —
    the caller should pass the segments it already computed so the model
    runs once per request.
    """
    if sr is None:
        sr = config.audio.target_sample_rate
    denoise_threshold = config.audio.snr_denoise_threshold

    if len(audio) == 0:
        return {"snr_db": 0.0, "ok": False, "needs_denoise": True}

    if speech_segments is None:
        _model = get_vad_model()
        audio_pt = torch.from_numpy(audio)
        speech_segments = get_speech_timestamps(
            audio_pt, _model, sampling_rate=sr,
            threshold=config.audio.vad_threshold,
        )

    if not speech_segments:
        return {"snr_db": 0.0, "ok": False, "needs_denoise": True}

    mask = np.zeros(len(audio), dtype=bool)
    for seg in speech_segments:
        mask[seg["start"]:seg["end"]] = True

    speech, noise = audio[mask], audio[~mask]
    if len(speech) == 0 or len(noise) == 0:
        return {"snr_db": 0.0, "ok": False, "needs_denoise": True}

    speech_rms = np.sqrt(np.mean(speech ** 2))
    noise_rms = np.sqrt(np.mean(noise ** 2))
    if noise_rms == 0:
        return {"snr_db": 99.0, "ok": True, "needs_denoise": False}

    snr_db = 20 * np.log10(speech_rms / noise_rms)
    return {
        # cast away numpy types — np.float64/np.bool_ break `is` checks and
        # are unsafe for JSON serialization
        "snr_db": float(round(snr_db, 1)),
        "ok": bool(snr_db >= denoise_threshold),
        "needs_denoise": bool(snr_db < denoise_threshold),
    }
