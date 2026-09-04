"""AssessmentService — the OOP orchestrator of the /assess pipeline.

Owns the full flow: word -> IPA -> audio prepare -> forced alignment ->
breakdown -> process detection -> clinical metrics -> curriculum ->
flat response.  All collaborators are injected via the constructor so the
pipeline is testable with fakes (no model loading required).

Errors are raised as ``services.errors`` subclasses and mapped to HTTP
responses by the API adapter (``main.py``).
"""

import numpy as np
import torch

try:
    from phoneme_service.config import config as default_config
except ImportError:
    from config import config as default_config
from ipa.clean_text import _clean_word, clean_ipa, tokenize_ipa
from ipa.curated_words import curated_ipa as default_word_to_ipa
from audio.processor import AudioPreparer
from model.forced_aligner import get_aligner
from detection.detector import ProcessDetector
from detection import pcc as pcc_module
from detection import curriculum_map

from .errors import (
    AlignmentError,
    AssessmentError,
    AudioQualityError,
    OutOfVocabularyError,
)
from .response_builder import ResponseBuilder


class AssessmentService:
    """Orchestrates a pronunciation assessment end-to-end."""

    def __init__(
        self,
        *,
        word_to_ipa_fn=default_word_to_ipa,
        audio_preparer=None,
        aligner=None,
        detector=None,
        pcc=pcc_module,
        curriculum=curriculum_map,
        response_builder=None,
        config=default_config,
    ):
        # word_to_ipa_fn defaults to the curated word list (data/curated_words.csv)
        # — the runtime source of truth for expected IPA.  Any callable with
        # the same contract (str -> IPA string, ValueError on unknown) works.
        self._word_to_ipa = word_to_ipa_fn if word_to_ipa_fn is not None \
            else default_word_to_ipa
        self._audio_preparer = audio_preparer if audio_preparer is not None \
            else AudioPreparer()
        self._aligner = aligner if aligner is not None else get_aligner()
        self._detector = detector if detector is not None else ProcessDetector()
        self._pcc = pcc
        self._curriculum = curriculum
        self._response_builder = response_builder if response_builder is not None \
            else ResponseBuilder()
        self._config = config

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def assess(self, *, word: str, age: int, audio_bytes: bytes) -> dict:
        """Run the full assessment pipeline.

        Parameters
        ----------
        word : str
            Target English word.
        age : int
            Child's age in years.
        audio_bytes : bytes
            Raw recording (WAV, MP3, OGG).

        Returns
        -------
        dict
            The flat /assess response (success only).

        Raises
        ------
        AssessmentError subclasses for recoverable failures;
        ForcedAlignmentError and unexpected exceptions propagate.
        """
        # 1. Clean word + convert to IPA
        word = _clean_word(word)
        try:
            expected_ipa = clean_ipa(self._word_to_ipa(word))
        except ValueError as exc:
            raise OutOfVocabularyError(
                "Out-of-Vocabulary Word", details=str(exc)
            ) from exc

        # 2. Prepare + quality-gate the audio
        audio_result = self._audio_preparer.prepare(audio_bytes)
        if not audio_result["ok"]:
            raise AudioQualityError(
                issues=audio_result["issues"],
                quality=audio_result.get("quality", {}),
            )

        # 3. Tokenize target IPA
        expected_tokens = tokenize_ipa(expected_ipa)
        if not expected_tokens:
            raise AssessmentError("Empty phoneme sequence after tokenization.")

        # 4. Forced alignment
        audio_tensor = torch.from_numpy(
            audio_result["audio"]  # np.ndarray, float32, mono, 16kHz
        ).float()
        fa_result = self._aligner.align(audio_tensor, expected_tokens)
        if not fa_result.get("ok", False):
            raise AlignmentError(
                "Forced Alignment Failed",
                details=fa_result.get("error", "Unknown alignment error"),
            )

        # 5. Build the breakdown from alignment segments
        breakdown, expected_phonemes, detected_phonemes = \
            self._build_breakdown(fa_result["segments"])

        # 6. Detect phonological processes
        processes = self._detector.detect(breakdown)

        # 7. Educational observation summary. Age is retained for content
        # selection, not used as a diagnostic cut-off.
        applicable_processes = self._curriculum.get_curriculum_summary(
            processes, age
        )

        # 8. Acoustic/phoneme metrics + app practice result
        pcc_data = self._pcc.compute_all(breakdown)
        pcc_score = pcc_data.get("pcc", {}).get("pcc", 0.0)
        overall_score = self._pcc.compute_overall_score(
            pcc_score=pcc_score,
            fa_average=fa_result.get("overall_score", 0.0),
            total_consonants=pcc_data.get("pcc", {}).get("total_consonants", 0),
            min_consonants=self._config.forced_alignment.min_consonants_for_full_pcc,
        )
        passed = overall_score >= self._config.forced_alignment.pcc_pass_threshold

        # 9. Shape the flat response
        return self._response_builder.build(
            word=word,
            expected_phonemes=expected_phonemes,
            detected_phonemes=detected_phonemes,
            breakdown=breakdown,
            processes=processes,
            applicable_processes=applicable_processes,
            age=age,
            passed=passed,
            overall_score=overall_score,
            pcc_data=pcc_data,
            audio_result=audio_result,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_breakdown(segments: list[dict]) -> tuple[list[dict], list[str], list[str]]:
        """Map aligner segments to the API breakdown + phoneme sequences."""
        breakdown: list[dict] = []
        expected_phonemes: list[str] = []
        detected_phonemes: list[str] = []

        for seg in segments:
            breakdown.append({
                "expected": seg["phoneme"],
                "predicted": seg["predicted"],
                "score": seg["score"],
                "confidence": seg.get("confidence", 1.0),
                "duration_sec": seg.get("duration_sec", 1.0),
            })
            expected_phonemes.append(seg["phoneme"])
            detected_phonemes.append(seg["predicted"])

        return breakdown, expected_phonemes, detected_phonemes
