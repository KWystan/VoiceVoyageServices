"""Centralized configuration for Model-10.

All hardcoded values, thresholds, and model identifiers are defined here.
Import and use these constants throughout the codebase.
"""
from dataclasses import dataclass, field


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
    min_speech_ratio: float = 0.05   # Min proportion of audio that should be speech


@dataclass
class ForcedAlignmentConfig:
    """Phoneme-level forced alignment configuration.

    Parameters for torchaudio.functional.forced_align and scoring.
    """
    blank_token_id: int = 0
    min_phoneme_duration_sec: float = 0.01
    confidence_threshold: float = 0.4
    duration_penalty_short_threshold_sec: float = 0.03
    duration_penalty_long_threshold_sec: float = 0.50
    duration_penalty_short_amount: float = 20.0
    duration_penalty_long_amount: float = 10.0
    close_pair_boost: float = 20.0
    devoicing_boost: float = 15.0
    max_topk_candidates: int = 3
    pcc_pass_threshold: float = 80.0  # PCC >= this means "passed"
    min_consonants_for_full_pcc: int = 3  # Below this, blend PCC with FA score


@dataclass
class AlignmentConfig:
    """Legacy alignment config (retained for archive compatibility)."""
    gap_penalty: float = 0.8


@dataclass
class ServerConfig:
    """FastAPI server configuration."""
    host: str = "0.0.0.0"
    port: int = 8001
    cors_origins: list = field(default_factory=lambda: ["*"])


@dataclass
class ModelConfig:
    """ML model configuration."""
    wav2vec_model_id: str = "facebook/wav2vec2-lv-60-espeak-cv-ft"
    device: str = "auto"

    def resolve_device(self) -> str:
        """Resolve 'auto' to actual device string using lazy torch import."""
        if self.device != "auto":
            return self.device
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"


@dataclass
class AppConfig:
    """Top-level application configuration."""
    audio: AudioConfig = field(default_factory=AudioConfig)
    forced_alignment: ForcedAlignmentConfig = field(default_factory=ForcedAlignmentConfig)
    alignment: AlignmentConfig = field(default_factory=AlignmentConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    model: ModelConfig = field(default_factory=ModelConfig)


# Singleton config instance
config = AppConfig()
