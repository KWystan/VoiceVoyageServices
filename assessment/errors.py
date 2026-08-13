"""Domain errors for the assessment pipeline.

All errors raised by ``AssessmentService`` derive from ``AssessmentError``
(recoverable, maps to HTTP 400).  Unexpected exceptions are left to
propagate and become HTTP 500 in the API adapter.
"""


class AssessmentError(Exception):
    """Base class for recoverable assessment failures (HTTP 400)."""

    def __init__(self, message: str, details=None):
        super().__init__(message)
        self.message = message
        self.details = details

    @property
    def payload(self) -> dict:
        """Flat error payload matching the /assess API contract."""
        payload = {"error": self.message}
        if self.details is not None:
            payload["details"] = self.details
        return payload


class OutOfVocabularyError(AssessmentError):
    """The target word is not in the curated word list."""


class AudioQualityError(AssessmentError):
    """The recording failed a hard audio quality check."""

    def __init__(self, issues: list[str], quality: dict):
        super().__init__("Invalid Audio", details=issues)
        self.quality = quality

    @property
    def payload(self) -> dict:
        hard_issues = [
            {"check": q["check"], "message": q["message"]}
            for q in self.quality.get("hard_issues", [])
        ] if self.quality else self.details
        return {
            "error": self.message,
            "details": self.details,
            "quality_check": {"passed": False, "hard_issues": hard_issues},
        }


class AlignmentError(AssessmentError):
    """Forced alignment failed (reported by the aligner, not an exception)."""
