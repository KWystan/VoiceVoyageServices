import numpy as np
import torch
import librosa
import soundfile as sf
from silero_vad import load_silero_vad, get_speech_timestamps
from functools import lru_cache
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


def compute_snr(audio: np.ndarray, sr: int = None) -> dict:
    """Measure SNR. Returns snr_db, ok, needs_denoise."""
    if sr is None:
        sr = config.audio.target_sample_rate
    denoise_threshold = config.audio.snr_denoise_threshold

    if len(audio) == 0:
        return {"snr_db": 0.0, "ok": False, "needs_denoise": True}

    _model = get_vad_model()
    audio_pt = torch.from_numpy(audio)
    speech_segs = get_speech_timestamps(audio_pt, _model, sampling_rate=sr, threshold=config.audio.vad_threshold)

    if not speech_segs:
        return {"snr_db": 0.0, "ok": False, "needs_denoise": True}

    mask = np.zeros(len(audio), dtype=bool)
    for seg in speech_segs:
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
        "snr_db": round(snr_db, 1),
        "ok": snr_db >= denoise_threshold,
        "needs_denoise": snr_db < denoise_threshold,
    }


def format_check(audio_path: str) -> dict:
    """Check if WAV file is 16kHz, mono, 16-bit PCM. Returns status and audio array."""
    sr_target = config.audio.target_sample_rate
    info = sf.info(audio_path)
    issues = []

    if info.samplerate != sr_target:
        issues.append(f"Sample rate is {info.samplerate}Hz, need {sr_target}Hz")
    if info.channels != 1:
        issues.append(f"Channels is {info.channels}, need 1 (mono)")
    if info.subtype != "PCM_16":
        issues.append(f"Bit depth is {info.subtype}, need PCM_16")

    audio, sr = sf.read(audio_path, dtype="float32")

    # Fix sample rate
    if sr != sr_target:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=sr_target)

    # Fix channels
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    return {"ok": len(issues) == 0, "issues": issues, "audio": audio, "sr": sr_target}
