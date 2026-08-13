"""
DeepFilterNet noise remover bridge.

Provides DeepFilterNoiseRemover class with lazy torchaudio compat
for denoising audio arrays.
"""

import logging
import sys
import types
from typing import NamedTuple

import numpy as np

from config import config

logger = logging.getLogger(__name__)


def _install_torchaudio_backend_shim() -> None:
    """Recreate ``torchaudio.backend`` removed in torchaudio >= 2.9.

    deepfilternet 0.5.x does ``from torchaudio.backend.common import
    AudioMetaData`` at import time, but torchaudio 2.9+ deleted the
    ``torchaudio.backend`` subpackage.  We never call deepfilternet's
    file I/O (audio is passed as numpy arrays), so a minimal type-only
    stand-in is enough to let the package import.
    """
    try:
        import torchaudio
    except ImportError:
        return
    if hasattr(torchaudio, "backend"):
        return

    class AudioMetaData(NamedTuple):
        sample_rate: int = 0
        num_frames: int = 0
        num_channels: int = 0
        bits_per_sample: int = 0
        encoding: str = ""

    backend = types.ModuleType("torchaudio.backend")
    common = types.ModuleType("torchaudio.backend.common")
    common.AudioMetaData = AudioMetaData
    backend.common = common
    sys.modules["torchaudio.backend"] = backend
    sys.modules["torchaudio.backend.common"] = common


class DeepFilterNoiseRemover:
    """DeepFilterNet-based noise reduction.

    Uses deepfilternet (deepfilter.net) to remove background noise
    from audio signals.
    """

    def __init__(self):
        self._model = None
        self._df_state = None
        self._enhance = None
        self._loaded = False

    def _lazy_load(self):
        """Lazy-load the DeepFilterNet model on first use."""
        if self._loaded:
            return
        self._loaded = True  # Mark first so failed loads don't retry every call
        try:
            _install_torchaudio_backend_shim()
            from df import enhance, init_df
            # DeepFilterNet 0.5.x API: init_df() loads the pretrained model
            # and returns (model, df_state, suffix).
            self._model, self._df_state, _ = init_df(
                log_level="ERROR", log_file=None
            )
            self._enhance = enhance
            logger.info("DeepFilterNet model loaded.")
        except ImportError:
            logger.warning("deepfilternet not installed. Using passthrough.")
        except Exception as exc:
            logger.warning("DeepFilterNet load failed (%s). Using passthrough.", exc)

    def clean_audio_from_array(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Denoise audio array in-place.

        Args:
            audio: float32 numpy array (mono).
            sr: sample rate of the audio.

        Returns:
            Denoised float32 numpy array.
        """
        self._lazy_load()
        if self._model is None:
            return audio

        try:
            # DeepFilterNet expects 48kHz audio
            if sr != config.audio.deepfilter_sample_rate:
                import librosa
                audio_resampled = librosa.resample(
                    audio, orig_sr=sr, target_sr=config.audio.deepfilter_sample_rate
                )
            else:
                audio_resampled = audio

            # Process through DeepFilterNet (expects a [C, T] tensor)
            import torch
            audio_tensor = torch.from_numpy(audio_resampled).unsqueeze(0)
            cleaned = self._enhance(self._model, self._df_state, audio_tensor)
            cleaned = cleaned.squeeze(0).numpy()

            # Resample back if needed
            if sr != config.audio.deepfilter_sample_rate:
                cleaned = librosa.resample(
                    cleaned,
                    orig_sr=config.audio.deepfilter_sample_rate,
                    target_sr=sr,
                )

            return cleaned.astype(np.float32)
        except Exception as exc:
            logger.warning("DeepFilterNet processing failed (%s). Using original.", exc)
            return audio
