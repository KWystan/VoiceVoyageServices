"""Centralized configuration for Model-10.

All hardcoded values, thresholds, and model identifiers are defined here.
Import and use these constants throughout the codebase.

Dedicated env vars (Railway → Variables):
  HF_TOKEN         — Hugging Face read token (high rate-limits, private cache)
  VV_FP16          — 1/0 use float16 on CPU to halve RAM (default 1)
  PHONEME_PRELOAD  — 1/0 preload Wav2Vec2 in background (default 1, 0 = lazy)
"""
import os
from dataclasses import dataclass, field


def _csv_env(name: str, default: str = "") -> list[str]:
    return [
        value.strip()
        for value in os.environ.get(name, default).split(",")
        if value.strip()
    ]


@dataclass
class AudioConfig:
    """Audio processing configuration."""
    target_sample_rate: int = 16000
    deepfilter_sample_rate: int = 48000
    vad_threshold: float = 0.3
    snr_denoise_threshold: float = 20.0

    # Quality thresholds
    min_rms: float = 0.01           # Minimum RMS (float32) for speech-level volume
    max_clipping_ratio: float = 0.10  # Max proportion of samples at ±1.0
    min_duration_sec: float = 0.3    # Minimum recording length in seconds (lowered for quick CV syllables like "PA", "BA")
    max_duration_sec: float = field(
        default_factory=lambda: float(os.environ.get("MAX_AUDIO_DURATION_SEC", "12"))
    )
    max_upload_bytes: int = field(
        default_factory=lambda: int(os.environ.get("MAX_AUDIO_UPLOAD_BYTES", "10485760"))
    )
    min_speech_ratio: float = 0.05   # Min proportion of audio that should be speech


@dataclass
class ForcedAlignmentConfig:
    """Phoneme-level forced alignment configuration.

    Parameters for torchaudio.functional.forced_align and scoring.
    """
    blank_token_id: int = 0
    # Minimum duration for a real phoneme production. Segments below this are
    # deletions, not substitutions: an omitted initial consonant (child says
    # "ell" for "bell") leaves only a ~20-40ms voiceless onset burst, which
    # Wav2Vec2 (espeak-ng) maps to its default stop token [t] — a real stop is
    # never this short. Must not exceed duration_penalty_short_threshold_sec.
    min_phoneme_duration_sec: float = 0.03
    duration_penalty_short_threshold_sec: float = 0.03
    duration_penalty_long_threshold_sec: float = 0.50
    duration_penalty_short_amount: float = 20.0
    duration_penalty_long_amount: float = 10.0
    close_pair_boost: float = 20.0
    devoicing_boost: float = 15.0
    pcc_pass_threshold: float = 80.0  # PCC >= this means "passed"
    min_consonants_for_full_pcc: int = 3  # Below this, blend PCC with FA score


@dataclass
class ServerConfig:
    """FastAPI server configuration."""
    host: str = "0.0.0.0"
    port: int = 8001
    environment: str = field(
        default_factory=lambda: os.environ.get("APP_ENV", "development").strip().lower()
    )
    cors_origins: list[str] = field(
        default_factory=lambda: _csv_env(
            "CORS_ORIGINS", "http://127.0.0.1,http://localhost"
        )
    )
    auth_mode: str = field(
        default_factory=lambda: os.environ.get("VV_AUTH_MODE", "off").strip().lower()
    )
    api_token_env: str = "VV_API_TOKEN"

    @property
    def is_production(self) -> bool:
        return self.environment in {"production", "prod"}

    def validate_runtime(self) -> None:
        if self.auth_mode not in {"off", "firebase", "token"}:
            raise RuntimeError(
                "VV_AUTH_MODE must be one of: off, firebase, token"
            )
        if "*" in self.cors_origins:
            raise RuntimeError("Wildcard CORS origins are not permitted")
        if self.is_production and any(
            not origin.startswith("https://") for origin in self.cors_origins
        ):
            raise RuntimeError("Production CORS origins must use HTTPS")
        if self.is_production and self.auth_mode not in {"firebase", "token"}:
            raise RuntimeError(
                "Production requires VV_AUTH_MODE=firebase or VV_AUTH_MODE=token"
            )
        if self.auth_mode == "token" and not os.environ.get(self.api_token_env):
            raise RuntimeError(
                f"{self.api_token_env} must be set when VV_AUTH_MODE=token"
            )


@dataclass
class ModelConfig:
    """ML model configuration."""
    wav2vec_model_id: str = "facebook/wav2vec2-lv-60-espeak-cv-ft"
    device: str = "auto"
    # Dedicated HF token env name (read in loader.py, configurable for Railway)
    hf_token_env: str = "HF_TOKEN"
    # Memory toggles (read from env at import time) — B3 7GB safe with INT8 quant, fp16 causes Half/float mismatch on CPU
    use_fp16: bool = field(default_factory=lambda: os.environ.get("VV_FP16", "0") in ("1", "true", "True"))
    preload_in_background: bool = field(default_factory=lambda: os.environ.get("PHONEME_PRELOAD", "1") in ("1", "true", "True"))

    def resolve_device(self) -> str:
        """Resolve 'auto' to actual device string using lazy torch import."""
        if self.device != "auto":
            return self.device
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def get_hf_token(self) -> str | None:
        return os.environ.get(self.hf_token_env) or os.environ.get("HF_TOKEN") or None


@dataclass
class AppConfig:
    """Top-level assessment pipeline configuration."""
    audio: AudioConfig = field(default_factory=AudioConfig)
    forced_alignment: ForcedAlignmentConfig = field(default_factory=ForcedAlignmentConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    model: ModelConfig = field(default_factory=ModelConfig)


# Singleton config instance
config = AppConfig()
