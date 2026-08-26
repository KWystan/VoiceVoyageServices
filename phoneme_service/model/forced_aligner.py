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

try:
    from phoneme_service.config import config
except ImportError:
    from config import config
from ipa.panphon_module import get_phonetic_similarity
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

def _extract_target_spans(
    path: torch.Tensor,
    token_ids: list[int],
    time_stride: float,
) -> list[dict]:
    """Extract frame spans for each target token from the CTC alignment path.

    In a CTC path (T frames), targets appear in strictly monotonic order
    interspersed with blank frames (0). This function deterministically
    tracks the contiguous frame interval for each target token index.
    """
    spans: list[dict] = []
    T = len(path)
    L = len(token_ids)

    curr_target_idx = 0
    t = 0
    while t < T and curr_target_idx < L:
        target_tid = token_ids[curr_target_idx]
        if path[t] == target_tid:
            start_f = t
            while t < T and path[t] == target_tid:
                t += 1
            end_f = t - 1
            duration_f = end_f - start_f + 1
            spans.append({
                "target_idx": curr_target_idx,
                "token": target_tid,
                "start_frame": start_f,
                "end_frame": end_f,
                "start_sec": round(start_f * time_stride, 4),
                "end_sec": round((end_f + 1) * time_stride, 4),
                "duration_sec": round(duration_f * time_stride, 4),
            })
            curr_target_idx += 1
        else:
            t += 1

    # Any omitted / unassigned target tokens
    while curr_target_idx < L:
        spans.append({
            "target_idx": curr_target_idx,
            "token": token_ids[curr_target_idx],
            "start_frame": 0,
            "end_frame": 0,
            "start_sec": 0.0,
            "end_sec": 0.0,
            "duration_sec": 0.0,
        })
        curr_target_idx += 1

    return spans


def _resolve_token_ids(
    tokens: list[str],
    tokenizer,
) -> list[int]:
    """Map IPA phoneme strings to tokenizer vocabulary IDs.

    Word-boundary '#' markers are ignored (not sent to CTC targets).
    Raises ForcedAlignmentError if any token is out-of-vocabulary.
    """
    ids: list[int] = []
    for ph in tokens:
        if ph == "#":
            continue
        tid = tokenizer.convert_tokens_to_ids(ph)
        if tid is None or tid == tokenizer.unk_token_id:
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
        if predicted in ("-", None, ""):
            return 0.0

        cfg = config.forced_alignment

        # Continuous Panphon feature similarity [0, 100]
        sim = get_phonetic_similarity(expected, predicted)

        # Blend feature similarity (85%) with acoustic confidence (15%)
        score = sim * 0.85 + (confidence * 100.0) * 0.15

        # Short duration adjustment:
        # If the sound is phonetically close (sim >= 50.0), short duration
        # in running speech is preserved and does not wipe out similarity.
        # If the sound is an unrelated gross error (sim < 50.0), apply short penalty.
        if duration_sec < cfg.duration_penalty_short_threshold_sec:
            if sim < 50.0:
                score = max(0.0, score - cfg.duration_penalty_short_amount)
        elif duration_sec > cfg.duration_penalty_long_threshold_sec:
            score = max(0.0, score - cfg.duration_penalty_long_amount)

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
        and the resulting [0, 100] score.
        """
        if seg.get("duration_sec", 0.0) <= 0:
            return {
                "phoneme": expected,
                "predicted": "-",
                "start_sec": 0.0,
                "end_sec": 0.0,
                "duration_sec": 0.0,
                "confidence": 0.0,
                "score": 0.0,
            }

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

    def _align_single_word(
        self,
        audio_tensor: torch.Tensor,
        target_ipa_tokens: list[str],
        sample_rate: int,
    ) -> dict:
        """Run forced alignment for a single word / syllable (no '#' boundaries)."""
        fs = self.time_stride

        # 1. Get logits from the model
        logits: torch.Tensor = self._loader.get_logits(audio_tensor)  # (1, T, V)

        # 2. Convert to log-probabilities
        log_probs = torch.nn.functional.log_softmax(logits, dim=-1)  # (1, T, V)

        T = log_probs.size(1)
        if T < 2:
            raise ForcedAlignmentError(
                f"Audio too short: only {T} frames after feature extraction."
            )

        clean_targets = [ph for ph in target_ipa_tokens if ph != "#"]
        if not clean_targets:
            raise ForcedAlignmentError("Target IPA token list is empty.")

        clean_token_ids = _resolve_token_ids(
            clean_targets, self.processor.tokenizer
        )
        L = len(clean_token_ids)
        if L == 0:
            raise ForcedAlignmentError("Resolved target token list is empty.")

        targets = torch.tensor([clean_token_ids], device=self.device, dtype=torch.int32)
        input_lengths = torch.tensor([T], dtype=torch.int32)
        target_lengths = torch.tensor([L], dtype=torch.int32)

        # 3. Run forced alignment on clean targets
        blank = self.blank_id
        forced_out = F.forced_align(
            log_probs,
            targets,
            input_lengths,
            target_lengths,
            blank=blank,
        )

        if isinstance(forced_out, tuple):
            path: torch.Tensor = forced_out[0]  # (1, T)
            neg_log_lik: torch.Tensor | None = forced_out[1]
            nll_val: float | None = (
                float(neg_log_lik.sum().cpu().item()) if neg_log_lik is not None else None
            )
        else:
            path = forced_out  # (1, T)
            nll_val = None

        path = path.squeeze(0)  # (T,)

        # 4. Extract deterministic spans
        spans = _extract_target_spans(path, clean_token_ids, fs)

        # 5. Build per-phoneme output
        aligned: list[dict] = []
        probs_all = torch.softmax(logits, dim=-1)  # (1, T, V)

        for i, ph in enumerate(clean_targets):
            span = spans[i]
            target_tid = clean_token_ids[i]
            aligned.append(self._build_segment(
                span, ph, target_tid, probs_all
            ))

        avg_conf = round(
            float(torch.tensor([s["confidence"] for s in aligned]).mean().item()), 4
        ) if aligned else 0.0

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

    def _align_phrase_word_by_word(
        self,
        audio_tensor: torch.Tensor,
        target_ipa_tokens: list[str],
        sample_rate: int,
    ) -> dict:
        """Align a multi-word phrase by segmenting and evaluating each word independently."""
        fs = self.time_stride

        # 1. Split tokens by '#' into per-word groups
        word_groups: list[list[str]] = []
        current_group: list[str] = []
        for ph in target_ipa_tokens:
            if ph == "#":
                if current_group:
                    word_groups.append(current_group)
                    current_group = []
            else:
                current_group.append(ph)
        if current_group:
            word_groups.append(current_group)

        if not word_groups:
            raise ForcedAlignmentError("No word groups found in target tokens.")

        # 2. Run a global forward pass on the full audio to find word time windows
        logits: torch.Tensor = self._loader.get_logits(audio_tensor)  # (1, T, V)
        log_probs = torch.nn.functional.log_softmax(logits, dim=-1)
        T = log_probs.size(1)

        all_clean_tokens = [ph for ph in target_ipa_tokens if ph != "#"]
        all_clean_tids = _resolve_token_ids(all_clean_tokens, self.processor.tokenizer)

        targets = torch.tensor([all_clean_tids], device=self.device, dtype=torch.int32)
        input_lengths = torch.tensor([T], dtype=torch.int32)
        target_lengths = torch.tensor([len(all_clean_tids)], dtype=torch.int32)

        forced_out = F.forced_align(
            log_probs, targets, input_lengths, target_lengths, blank=self.blank_id
        )
        global_path: torch.Tensor = (
            forced_out[0].squeeze(0).cpu()
            if isinstance(forced_out, tuple)
            else forced_out.squeeze(0).cpu()
        )

        # 3. Locate time windows for each word and align each word independently
        token_offset = 0
        merged_segments: list[dict] = []
        num_samples = audio_tensor.size(0)

        for word_idx, w_tokens in enumerate(word_groups):
            w_tids = all_clean_tids[token_offset : token_offset + len(w_tokens)]
            token_offset += len(w_tokens)

            # Find frame indices where this word's token IDs occurred in the global path
            word_frames: list[int] = []
            for tid in w_tids:
                matching_t = (global_path == tid).nonzero(as_tuple=True)[0]
                if len(matching_t) > 0:
                    word_frames.extend(matching_t.tolist())

            if word_frames:
                start_f = max(0, min(word_frames) - 2)
                end_f = min(T - 1, max(word_frames) + 2)
            else:
                start_f = int(T * (word_idx / len(word_groups)))
                end_f = int(T * ((word_idx + 1) / len(word_groups))) - 1

            start_samp = int(start_f * fs * sample_rate)
            end_samp = min(num_samples, int((end_f + 1) * fs * sample_rate))
            word_audio_slice = audio_tensor[start_samp:end_samp]

            time_offset = round(start_f * fs, 4)

            # Evaluate word slice independently using single-word aligner
            if word_audio_slice.size(0) >= int(0.04 * sample_rate):
                try:
                    word_res = self._align_single_word(
                        word_audio_slice, w_tokens, sample_rate
                    )
                    w_segs = word_res["segments"]
                except Exception as exc:
                    logger.warning("Word %d (%s) slice alignment fallback: %s", word_idx, w_tokens, exc)
                    w_segs = [{
                        "phoneme": ph,
                        "predicted": "-",
                        "start_sec": 0.0,
                        "end_sec": 0.0,
                        "duration_sec": 0.0,
                        "confidence": 0.0,
                        "score": 0.0,
                    } for ph in w_tokens]
            else:
                w_segs = [{
                    "phoneme": ph,
                    "predicted": "-",
                    "start_sec": 0.0,
                    "end_sec": 0.0,
                    "duration_sec": 0.0,
                    "confidence": 0.0,
                    "score": 0.0,
                } for ph in w_tokens]

            for s in w_segs:
                if s["duration_sec"] > 0:
                    s["start_sec"] = round(s["start_sec"] + time_offset, 4)
                    s["end_sec"] = round(s["end_sec"] + time_offset, 4)
                merged_segments.append(s)

            if word_idx < len(word_groups) - 1:
                boundary_time = round((end_f + 1) * fs, 4)
                merged_segments.append({
                    "phoneme": "#",
                    "predicted": "#",
                    "start_sec": boundary_time,
                    "end_sec": boundary_time,
                    "duration_sec": 0.0,
                    "confidence": 1.0,
                    "score": 100.0,
                })

        non_boundary = [s for s in merged_segments if s["phoneme"] != "#"]
        avg_conf = round(
            float(torch.tensor([s["confidence"] for s in non_boundary]).mean().item()), 4
        ) if non_boundary else 0.0

        overall_score = round(
            float(torch.tensor([s["score"] for s in non_boundary]).mean().item()), 2
        ) if non_boundary else 0.0

        return {
            "ok": True,
            "segments": merged_segments,
            "overall_confidence": avg_conf,
            "overall_score": overall_score,
            "neg_log_likelihood": None,
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
            List of IPA phoneme strings, e.g. ["b", "ʌ", "t"] or with "#" boundaries.
        sample_rate : int, optional
            Audio sample rate.  Defaults to `config.audio.target_sample_rate`.

        Returns
        -------
        dict with keys:
            - "ok": bool
            - "segments": list[dict]  (present only if ok=True)
            - "overall_confidence": float
            - "overall_score": float
            - "error": str  (present only if ok=False)
            - "neg_log_likelihood": float or None
        """
        if sample_rate is None:
            sample_rate = config.audio.target_sample_rate

        self._lazy_load()

        try:
            if "#" in target_ipa_tokens:
                return self._align_phrase_word_by_word(
                    audio_tensor, target_ipa_tokens, sample_rate
                )
            else:
                return self._align_single_word(
                    audio_tensor, target_ipa_tokens, sample_rate
                )

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
