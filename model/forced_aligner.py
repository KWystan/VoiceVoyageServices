"""
Phoneme-level forced alignment using torchaudio.functional.forced_align.

Replaces the old CTC-argmax free-transcription + Needleman-Wunsch pipeline
with a strict 1-to-1 forced alignment between target IPA tokens and audio.

Usage:
    aligner = PhonemeForcedAligner()
    result = aligner.align(audio_tensor, ["b", "ʌ", "t", ...])
    # result is a list of {"phoneme", "start_sec", "end_sec", "duration_sec", "confidence"}
"""

import logging
import math
from typing import Optional

import torch
import torchaudio.functional as F

from config import config
from ipa.panphon_module import lookup_boost
from model.loader import get_loader
from ipa.normalization import same_phoneme

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ForcedAlignmentError(RuntimeError):
    """Raised when forced alignment fails for a recoverable reason."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _path_to_segments(
    path: torch.Tensor,
    blank_id: int,
    time_stride: float,
) -> list[dict[str, int | float]]:
    """Convert a forced-alignment path (token IDs per frame) into phoneme
    segments with frame-based timing.

    Parameters
    ----------
    path : Tensor
        Shape (T,) — token ID at each frame (blank_id = silence/transition).
    blank_id : int
        Token ID representing blank / silence.
    time_stride : float
        Seconds per frame (e.g., 0.02 for 20 ms).

    Returns
    -------
    list[dict]
        Each dict has keys: phoneme, start_frame, end_frame, start_sec, end_sec.
        Consecutive duplicate tokens are merged into one segment.
    """
    segments: list[dict[str, int | float]] = []
    prev_id: int | None = None
    seg_start: int | None = None

    for t, tok_id in enumerate(path.tolist()):
        tok_id_int = int(tok_id)
        if tok_id_int == blank_id:
            # End any active segment
            if prev_id is not None and prev_id != blank_id and seg_start is not None:
                segments.append({
                    "token": prev_id,
                    "start_frame": seg_start,
                    "end_frame": t - 1,
                    "start_sec": round(seg_start * time_stride, 4),
                    "end_sec": round((t - 1) * time_stride, 4),
                })
                seg_start = None
        else:
            if tok_id_int != prev_id:
                # End previous segment if any
                if prev_id is not None and prev_id != blank_id and seg_start is not None:
                    segments.append({
                        "token": prev_id,
                        "start_frame": seg_start,
                        "end_frame": t - 1,
                        "start_sec": round(seg_start * time_stride, 4),
                        "end_sec": round((t - 1) * time_stride, 4),
                    })
                seg_start = t
        prev_id = tok_id_int

    # Flush last segment
    if prev_id is not None and prev_id != blank_id and seg_start is not None:
        segments.append({
            "token": prev_id,
            "start_frame": seg_start,
            "end_frame": len(path) - 1,
            "start_sec": round(seg_start * time_stride, 4),
            "end_sec": round((len(path) - 1) * time_stride, 4),
        })

    return segments


def _resolve_token_ids(
    tokens: list[str],
    tokenizer,
) -> list[int]:
    """Map IPA phoneme strings to tokenizer vocabulary IDs.

    The ``"#"`` boundary token maps to the CTC blank ID (silence frame),
    so the forced aligner naturally aligns it to inter-word pauses.

    Raises ForcedAlignmentError if any other token is out-of-vocabulary.
    """
    ids: list[int] = []
    blank_id = config.forced_alignment.blank_token_id
    for ph in tokens:
        if ph == "#":
            ids.append(blank_id)
            continue
        tid = tokenizer.convert_tokens_to_ids(ph)
        if tid is None or tid == tokenizer.unk_token_id:
            # Try removing stress / length marks
            stripped = ph.strip("ˈˌːˑ")
            tid = tokenizer.convert_tokens_to_ids(stripped)
        if tid is None or tid == tokenizer.unk_token_id:
            raise ForcedAlignmentError(
                f"Token '{ph}' is out-of-vocabulary for the Wav2Vec2 tokenizer."
            )
        ids.append(tid)
    return ids


# ---------------------------------------------------------------------------
# Main aligner
# ---------------------------------------------------------------------------

class PhonemeForcedAligner:
    """CTC forced-alignment based phoneme aligner.

    Uses torchaudio.functional.forced_align to produce a strict 1-to-1
    mapping between target IPA tokens and audio frames, returning per-phoneme
    timing and confidence scores.
    """

    def __init__(self) -> None:
        self._loader = None
        self._loaded = False

    # --- lazy loading ---

    def _lazy_load(self) -> None:
        if self._loaded:
            return
        loader = get_loader()
        self._loader = loader
        self._loaded = True
        logger.info("PhonemeForcedAligner: model loaded.")

    @property
    def model(self):
        self._lazy_load()
        return self._loader.model

    @property
    def processor(self):
        self._lazy_load()
        return self._loader.processor

    @property
    def device(self):
        self._lazy_load()
        return self._loader.device

    @property
    def time_stride(self) -> float:
        self._lazy_load()
        return self._loader.get_time_stride()

    @property
    def blank_id(self) -> int:
        self._lazy_load()
        return self._loader.get_blank_token_id()

    # --- predicted phoneme resolution ---

    def _resolve_predicted(
        self,
        avg_probs: torch.Tensor,
        tokenizer,
    ) -> tuple[str, float]:
        """Determine the model's top-1 predicted phoneme from averaged probs.

        Caller must provide per-frame probabilities averaged over the target
        segment, with blank already excluded (set to -1.0).

        Returns (predicted_phoneme, max_confidence).
        If all blank or below noise floor, returns ("-", 0.0).
        """
        top_prob, top_idx = avg_probs.topk(1)
        top_conf = float(top_prob[0].cpu().item())

        if top_conf < 0.05:
            return "-", top_conf

        predicted_id = int(top_idx[0].cpu().item())
        predicted_ph = tokenizer.convert_ids_to_tokens(predicted_id)
        if predicted_ph is None or predicted_ph in ("<pad>", "<unk>"):
            return "-", top_conf

        return predicted_ph, top_conf

    @staticmethod
    def _compute_score(
        expected: str,
        predicted: str,
        confidence: float,
        duration_sec: float,
    ) -> float:
        """Compute [0, 100] score for one aligned phoneme segment."""
        # Match through the alphabet translation: the model may spell a
        # correct production with an allophonic variant (tʰ, l̩, ɹ, ...)
        # that normalize_ipa/clean map back to the expected phoneme.
        if same_phoneme(predicted, expected):
            return 100.0
        if predicted in ("-", None):
            return 0.0

        cfg = config.forced_alignment

        score = confidence * 100.0

        if duration_sec < cfg.duration_penalty_short_threshold_sec:
            score -= cfg.duration_penalty_short_amount
        elif duration_sec > cfg.duration_penalty_long_threshold_sec:
            score -= cfg.duration_penalty_long_amount

        boost = lookup_boost(expected, predicted)
        score += boost

        return round(max(0.0, min(100.0, score)), 2)

    def _build_segment(
        self,
        seg: dict,
        expected: str,
        target_tid: int,
        probs_all: torch.Tensor,
    ) -> dict:
        """Build one aligned-segment dict from a raw path segment.

        Computes confidence (mean softmax prob of the EXPECTED token over
        the segment's frames), the model's argmax prediction, duration,
        and the resulting [0, 100] score.  Used by both the matched and
        the mismatch branches of ``align()``.
        """
        start_f = seg["start_frame"]
        end_f = seg["end_frame"]
        duration_f = end_f - start_f + 1

        token_probs = probs_all[0, start_f:end_f + 1, target_tid]
        confidence = float(token_probs.mean().cpu().item())
        if math.isnan(confidence):
            confidence = 0.0

        duration_sec = round(duration_f * self.time_stride, 4)
        avg_probs = probs_all[0, start_f:end_f + 1, :].mean(dim=0).clone()
        avg_probs[self.blank_id] = -1.0
        predicted_ph, _ = self._resolve_predicted(
            avg_probs, self.processor.tokenizer
        )
        seg_score = self._compute_score(
            expected, predicted_ph, confidence, duration_sec
        )

        return {
            "phoneme": expected,
            "predicted": predicted_ph,
            "start_sec": float(seg["start_sec"]),
            "end_sec": float(seg["end_sec"]),
            "duration_sec": duration_sec,
            "confidence": round(confidence, 4),
            "score": seg_score,
        }

    # --- public API ---

    def align(
        self,
        audio_tensor: torch.Tensor,
        target_ipa_tokens: list[str],
        sample_rate: Optional[int] = None,
    ) -> dict:
        """Run forced alignment of target IPA tokens against audio.

        Parameters
        ----------
        audio_tensor : torch.Tensor
            Shape (N,) — mono audio waveform (float32).
        target_ipa_tokens : list[str]
            List of IPA phoneme strings, e.g. ["b", "ʌ", "t"].
        sample_rate : int, optional
            Audio sample rate.  Defaults to `config.audio.target_sample_rate`.

        Returns
        -------
        dict with keys:
            - "ok": bool
            - "segments": list[dict]  (present only if ok=True)
                Each dict: {"phoneme", "start_sec", "end_sec",
                            "duration_sec", "confidence"}
            - "overall_confidence": float
            - "error": str  (present only if ok=False)
            - "neg_log_likelihood": float or None
        """
        if sample_rate is None:
            sample_rate = config.audio.target_sample_rate

        self._lazy_load()
        fs = self.time_stride

        try:
            # 1. Get logits from the model
            logits: torch.Tensor = self._loader.get_logits(audio_tensor)  # (1, T, V)

            # 2. Convert to log-probabilities
            log_probs = torch.nn.functional.log_softmax(logits, dim=-1)  # (1, T, V)

            T = log_probs.size(1)
            if T < 2:
                raise ForcedAlignmentError(
                    f"Audio too short: only {T} frames after feature extraction."
                )

            # 3. Map target tokens to token IDs
            token_ids = _resolve_token_ids(
                target_ipa_tokens, self.processor.tokenizer
            )
            L = len(token_ids)
            if L == 0:
                raise ForcedAlignmentError("Target IPA token list is empty.")

            targets = torch.tensor([token_ids], device=self.device, dtype=torch.int32)
            input_lengths = torch.tensor([T], dtype=torch.int32)
            target_lengths = torch.tensor([L], dtype=torch.int32)

            # 4. Run forced alignment
            blank = self.blank_id
            forced_out = F.forced_align(
                log_probs,
                targets,
                input_lengths,
                target_lengths,
                blank=blank,
            )

            # forced_out may be (path, neg_log_likelihood) or just path
            if isinstance(forced_out, tuple):
                path: torch.Tensor = forced_out[0]  # (1, T)
                neg_log_lik: torch.Tensor | None = forced_out[1]  # (1, T) per-frame or (1,) scalar
                nll_val: float | None = (
                    float(neg_log_lik.sum().cpu().item()) if neg_log_lik is not None else None
                )
            else:
                path = forced_out  # (1, T)
                nll_val = None

            path = path.squeeze(0)  # (T,)

            # 5. Convert path to phoneme segments
            raw_segments = _path_to_segments(path, blank, fs)

            # 6. Build per-phoneme output aligned to the target tokens
            #    (merge consecutive same-token segments)
            aligned: list[dict] = []
            probs_all = torch.softmax(logits, dim=-1)  # (1, T, V)

            # Assign each target token to its matching path segments
            # We iterate in parallel over target tokens and path segments
            tid_idx = 0
            seg_idx = 0
            while tid_idx < L and seg_idx < len(raw_segments):
                target_tid = token_ids[tid_idx]
                seg = raw_segments[seg_idx]
                seg_tid = seg["token"]

                if seg_tid == target_tid:
                    # This segment belongs to the current target token
                    aligned.append(self._build_segment(
                        seg, target_ipa_tokens[tid_idx], target_tid, probs_all
                    ))
                    tid_idx += 1
                    seg_idx += 1
                elif seg_tid == blank:
                    # Skip blank segments
                    seg_idx += 1
                else:
                    # Mismatch: the path predicted something other than the target
                    # Log it and advance both (segment is still used as-is)
                    logger.warning(
                        "Alignment mismatch at target idx %d: expected token %s (id=%d), "
                        "path has token id=%d. Using segment anyway.",
                        tid_idx, target_ipa_tokens[tid_idx], target_tid, seg_tid,
                    )
                    aligned.append(self._build_segment(
                        seg, target_ipa_tokens[tid_idx], target_tid, probs_all
                    ))
                    tid_idx += 1
                    seg_idx += 1

            # If we didn't process all target tokens, fill remaining with zero-confidence
            while tid_idx < L:
                logger.warning(
                    "No alignment frames for target token '%s' at index %d — setting zero confidence.",
                    target_ipa_tokens[tid_idx], tid_idx,
                )
                aligned.append({
                    "phoneme": target_ipa_tokens[tid_idx],
                    "predicted": "-",
                    "start_sec": 0.0,
                    "end_sec": 0.0,
                    "duration_sec": 0.0,
                    "confidence": 0.0,
                    "score": 0.0,
                })
                tid_idx += 1

            if not aligned:
                return {"ok": False, "error": "Forced alignment produced zero phoneme segments."}

            avg_conf = round(
                float(torch.tensor([s["confidence"] for s in aligned]).mean().item()), 4
            )

            overall_score = round(
                float(torch.tensor([s["score"] for s in aligned]).mean().item()), 2
            ) if aligned else 0.0

            return {
                "ok": True,
                "segments": aligned,
                "overall_confidence": avg_conf,
                "overall_score": overall_score,
                "neg_log_likelihood": nll_val,
            }

        except ForcedAlignmentError:
            raise
        except Exception as exc:
            logger.exception("Forced alignment failed unexpectedly.")
            return {
                "ok": False,
                "error": f"Forced alignment internal error: {exc}",
            }


# ---------------------------------------------------------------------------
# Singleton for easy reuse
# ---------------------------------------------------------------------------

from functools import lru_cache


@lru_cache(maxsize=1)
def get_aligner() -> PhonemeForcedAligner:
    """Return a singleton PhonemeForcedAligner (lazy-loaded)."""
    return PhonemeForcedAligner()
