"""Audio quality checks for pronunciation recordings.

Each check returns a dict with ``passed`` (bool) and ``message`` (str).
``message`` is a human-readable description of what failed, suitable for
returning to the Flutter app so the user knows what to fix.
"""

import numpy as np
from config import config


def check_rms_level(audio: np.ndarray, sr: int = None) -> dict:
    """Verify audio has sufficient volume (RMS energy).

    Speech below this threshold is likely silence, a distant mic, or
    the child not speaking at all.
    """
    threshold = config.audio.min_rms
    rms = np.sqrt(np.mean(audio ** 2))
    passed = rms >= threshold
    return {
        "check": "rms_level",
        "passed": bool(passed),
        "message": (
            f"Audio is too quiet — RMS level is {rms:.4f}, "
            f"minimum {threshold:.4f} required. "
            "Please speak louder and closer to the microphone."
        ) if not passed else "Volume level is adequate.",
        "value": round(float(rms), 4),
    }


def check_clipping(audio: np.ndarray, sr: int = None) -> dict:
    """Detect hard clipping — samples at or near max amplitude.

    Mild clipping is tolerated (short plosives), but heavy clipping
    degrades the phoneme model's accuracy.
    """
    max_ratio = config.audio.max_clipping_ratio
    clipped = np.sum(np.abs(audio) >= 0.999)
    ratio = clipped / len(audio)
    passed = ratio <= max_ratio
    return {
        "check": "clipping",
        "passed": bool(passed),
        "message": (
            f"Audio is distorted — {clipped} of {len(audio)} samples "
            f"({ratio:.1%}) are clipped (maximum allowed {max_ratio:.1%}). "
            "Move the microphone slightly farther away or reduce gain."
        ) if not passed else "No clipping detected.",
        "value": round(float(ratio), 4),
    }


def check_duration(samples: int, sr: int) -> dict:
    """Verify audio is long enough to contain speech.

    Very short recordings (< ~0.5s) likely mean the recording was cut off
    or the microphone did not capture the child's attempt.
    """
    min_sec = config.audio.min_duration_sec
    duration_sec = samples / sr
    passed = duration_sec >= min_sec
    return {
        "check": "duration",
        "passed": bool(passed),
        "message": (
            f"Recording too short — {duration_sec:.1f}s, "
            f"minimum {min_sec:.1f}s required. "
            "Wait for the recording to finish before stopping."
        ) if not passed else f"Duration is adequate ({duration_sec:.1f}s).",
        "value": round(duration_sec, 1),
    }


def check_speech_ratio(
    audio: np.ndarray, sr: int, vad_segments: list
) -> dict:
    """Verify a reasonable proportion of the audio contains speech.

    A recording with 3 seconds of silence and only 0.1s of speech
    likely means the child started speaking late or the microphone
    barely picked them up.
    """
    min_ratio = config.audio.min_speech_ratio
    if len(audio) == 0:
        return {
            "check": "speech_ratio",
            "passed": False,
            "message": "No audio data to analyse.",
            "value": 0.0,
        }

    speech_samples = sum(
        seg["end"] - seg["start"] for seg in vad_segments
    ) if vad_segments else 0
    ratio = speech_samples / len(audio)
    passed = ratio >= min_ratio
    return {
        "check": "speech_ratio",
        "passed": bool(passed),
        "message": (
            f"Very little speech detected — only {ratio:.1%} of the recording "
            f"contains voice (minimum {min_ratio:.0%}). "
            "Make sure the child speaks clearly into the microphone."
        ) if not passed else (
            f"Speech occupies {ratio:.1%} of the recording."
        ),
        "value": round(float(ratio), 4),
    }


def check_snr(snr_db: float) -> dict:
    """Check signal-to-noise ratio.

    Low SNR recordings are noisy — the model may struggle to identify
    phonemes accurately.
    """
    threshold = config.audio.snr_denoise_threshold
    passed = snr_db >= threshold
    return {
        "check": "snr",
        "passed": bool(passed),
        "message": (
            f"Background noise too high — SNR is {snr_db:.1f} dB, "
            f"minimum {threshold:.0f} dB recommended. "
            "Please record in a quieter environment."
        ) if not passed else f"Signal-to-noise ratio is good ({snr_db:.1f} dB).",
        "value": snr_db,
    }


def check_all(audio: np.ndarray, sr: int, snr_db: float,
              vad_segments: list) -> dict:
    """Run all quality checks and return a summary.

    Returns
    -------
    dict with:
        - ``passed``: True if all *hard* checks pass.
        - ``hard_issues``: list of failing-check dicts that should reject.
        - ``warnings``: list of failing-check dicts that are advisory.
        - ``all_checks``: every check result (hard and soft).
    """
    hard_checks = [check_rms_level, check_duration, check_speech_ratio]
    soft_checks = [check_clipping, check_snr]

    all_results = []
    hard_issues = []
    warnings = []

    for check_fn in hard_checks:
        if check_fn in (check_duration,):
            # duration takes (samples, sr) signature
            result = check_fn(len(audio), sr)
        elif check_fn is check_speech_ratio:
            result = check_fn(audio, sr, vad_segments)
        else:
            result = check_fn(audio, sr)
        all_results.append(result)
        if not result["passed"]:
            hard_issues.append(result)

    for check_fn in soft_checks:
        if check_fn is check_snr:
            result = check_fn(snr_db)
        else:
            result = check_fn(audio, sr)
        all_results.append(result)
        if not result["passed"]:
            warnings.append(result)

    # Also include rms_level value for the overall assessment
    rms_result = next(
        (r for r in all_results if r["check"] == "rms_level"), None
    )
    rms_value = rms_result["value"] if rms_result else 0.0

    return {
        "passed": len(hard_issues) == 0,
        "hard_issues": hard_issues,
        "warnings": warnings,
        "all_checks": all_results,
        "rms_value": rms_value,
    }
