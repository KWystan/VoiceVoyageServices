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
try:
    from phoneme_service.config import config
except ImportError:
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
        import os
        import time
        import gc
        # Dedicated env var (config-driven, defaults to HF_TOKEN)
        hf_token = config.model.get_hf_token()

        # Free tier: use float16 + low_cpu_mem_usage to stay under ~700MB peak
        # (was float32 ~1.2GB -> Killed on 512MB/1GB free tier at pytorch_model.bin)
        _use_fp16 = self.device == "cpu" and config.model.use_fp16

        # Try loading from local cache first to avoid Hub chatter.
        # Fall back to regular download if not cached with 3-attempt retry.
        try:
            feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(
                model_id, local_files_only=True, token=hf_token
            )
            tokenizer = Wav2Vec2PhonemeCTCTokenizer.from_pretrained(
                model_id, local_files_only=True, do_phonemize=False, token=hf_token
            )
            self.model = Wav2Vec2ForCTC.from_pretrained(
                model_id, local_files_only=True, token=hf_token,
                torch_dtype=torch.float16 if _use_fp16 else None,
                low_cpu_mem_usage=True,
            ).to(self.device)
        except EnvironmentError:
            last_err = None
            for attempt in range(1, 4):
                try:
                    feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(
                        model_id, token=hf_token, trust_remote_code=False
                    )
                    tokenizer = Wav2Vec2PhonemeCTCTokenizer.from_pretrained(
                        model_id, do_phonemize=False, token=hf_token, trust_remote_code=False
                    )
                    self.model = Wav2Vec2ForCTC.from_pretrained(
                        model_id, token=hf_token, trust_remote_code=False,
                        torch_dtype=torch.float16 if _use_fp16 else None,
                        low_cpu_mem_usage=True,
                    ).to(self.device)
                    last_err = None
                    break
                except Exception as err:
                    last_err = err
                    if attempt < 3:
                        time.sleep(2 * attempt)
            if last_err:
                raise last_err

        # Dynamic INT8 Quantization on CPU reduces RAM from 1.2GB -> 300MB and speeds up inference
        # Skip quant if already fp16 (int8 on fp16 not supported; fp16 already ~600MB peak)
        if self.device == "cpu" and not _use_fp16:
            try:
                self.model = torch.quantization.quantize_dynamic(
                    self.model, {torch.nn.Linear}, dtype=torch.qint8
                )
            except Exception:
                pass
        # Hint GC after heavy load to drop temp buffers before health check
        try:
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

        self.processor: Wav2Vec2Processor = Wav2Vec2Processor(
            feature_extractor=feature_extractor, tokenizer=tokenizer
        )
        self.model.eval()
        logger = logging.getLogger(__name__)
        logger.info("Wav2Vec2ModelLoader loaded on %s (quantized=%s)", self.device, self.device == "cpu")

    def get_logits(self, audio_tensor: torch.Tensor) -> torch.Tensor:
        """Run model forward pass, return logits (B, T, V)."""
        inputs = self.processor(
            audio_tensor,
            sampling_rate=config.audio.target_sample_rate,
            return_tensors="pt",
            padding=True,
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        # If model is fp16, cast inputs to half to avoid float/Half mismatch
        try:
            # Check first param dtype (handles quantized wrapper)
            p = next(self.model.parameters(), None)
            if p is not None and p.dtype == torch.float16:
                inputs = {k: (v.half() if v.is_floating_point() else v) for k, v in inputs.items()}
        except Exception:
            pass
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
