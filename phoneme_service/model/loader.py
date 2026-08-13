"""
Wav2Vec2 model loader singleton.

Lazily loads facebook/wav2vec2-lv-60-espeak-cv-ft on first call.
Exposes the model, processor, and device for use by the forced aligner.

The old CTC-argmax free-transcription methods (_decode, transcribe_to_ipa)
have been removed. They are archived in archive/legacy_alignment/.
Use audio.forced_aligner.PhonemeForcedAligner instead.
"""

import logging
import torch
from transformers import (
    Wav2Vec2ForCTC,
    Wav2Vec2FeatureExtractor,
    Wav2Vec2PhonemeCTCTokenizer,
    Wav2Vec2Processor,
)
from functools import lru_cache
from config import config


class Wav2Vec2ModelLoader:
    """Lazy-loaded singleton wrapper around Wav2Vec2.

    Attributes:
        model:      Wav2Vec2ForCTC model (on correct device).
        processor:  Wav2Vec2Processor (feature extractor + tokenizer).
        device:     torch device string (cuda / cpu).
    """

    def __init__(self) -> None:
        model_id = config.model.wav2vec_model_id
        self.device: str = config.model.resolve_device()

        # Try loading from local cache first to avoid Hub chatter.
        # Fall back to regular download if not cached.
        try:
            feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(
                model_id, local_files_only=True
            )
            tokenizer = Wav2Vec2PhonemeCTCTokenizer.from_pretrained(
                model_id, local_files_only=True, do_phonemize=False
            )
            self.model = Wav2Vec2ForCTC.from_pretrained(
                model_id, local_files_only=True
            ).to(self.device)
        except EnvironmentError:
            feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(model_id)
            tokenizer = Wav2Vec2PhonemeCTCTokenizer.from_pretrained(
                model_id, do_phonemize=False
            )
            self.model = Wav2Vec2ForCTC.from_pretrained(model_id).to(self.device)

        self.processor: Wav2Vec2Processor = Wav2Vec2Processor(
            feature_extractor=feature_extractor, tokenizer=tokenizer
        )
        self.model.eval()
        logger = logging.getLogger(__name__)
        logger.info("Wav2Vec2ModelLoader loaded on %s", self.device)

    def get_logits(self, audio_tensor: torch.Tensor) -> torch.Tensor:
        """Run model forward pass, return logits (B, T, V)."""
        inputs = self.processor(
            audio_tensor,
            sampling_rate=config.audio.target_sample_rate,
            return_tensors="pt",
            padding=True,
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            logits: torch.Tensor = self.model(**inputs).logits
        return logits

    def get_blank_token_id(self) -> int:
        """Determine the CTC blank token ID from config or tokenizer."""
        cfg_blank = config.forced_alignment.blank_token_id
        if cfg_blank != 0:
            return cfg_blank
        # Auto-detect from tokenizer
        if self.processor.tokenizer.pad_token_id is not None:
            return self.processor.tokenizer.pad_token_id
        return 0

    def get_time_stride(self) -> float:
        """Return seconds per frame for the Wav2Vec2 feature encoder."""
        sr = config.audio.target_sample_rate
        if hasattr(self.model.config, "inputs_to_logits_ratio"):
            ratio = self.model.config.inputs_to_logits_ratio
        else:
            # Fallback: compute from conv dims
            ratio = 1
            for dim in self.model.config.conv_dim:
                ratio *= 2  # typical stride
        return ratio / sr


@lru_cache(maxsize=1)
def get_loader() -> Wav2Vec2ModelLoader:
    """Lazy initializer — loads Wav2Vec2 model on first call."""
    return Wav2Vec2ModelLoader()
