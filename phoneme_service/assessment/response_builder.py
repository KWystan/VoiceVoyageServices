"""Response shaping for the /assess endpoint.

``ResponseBuilder`` turns pipeline results into the flat response schema
that the Flutter app consumes.  It is a pure object — no I/O, no state —
kept as a class for a consistent service-layer API.
"""


class ResponseBuilder:
    """Assemble the flat /assess response (backward-compatible with Flutter)."""

    def build(
        self,
        *,
        word: str,
        expected_phonemes: list[str],
        detected_phonemes: list[str],
        breakdown: list[dict],
        processes: list[dict],
        applicable_processes: list[dict],
        age: int,
        passed: bool,
        overall_score: float,
        pcc_data: dict,
        audio_result: dict,
    ) -> dict:
        expected_ipa = ",".join(expected_phonemes)
        detected_ipa = ",".join(detected_phonemes)
        pcc = pcc_data.get("pcc", {})

        return {
            # --- Flutter-compatible fields ---
            "target_word": word,
            "expected_ipa": expected_ipa,
            "detected_ipa": detected_ipa,
            "overall_score": round(overall_score, 2),
            "assessment": {
                "phoneme_breakdown": breakdown,
                "detected_processes": processes,
            },
            # --- New fields ---
            "age": age,
            "passed": passed,
            "pcc": round(pcc.get("pcc", 0.0), 2),
            "pcc_r": round(pcc_data.get("pcc_r", {}).get("pcc_r", 0.0), 2),
            "pvc": round(pcc_data.get("pvc", {}).get("pvc", 0.0), 2),
            # Retain the legacy key but do not expose clinical severity
            # cut-offs from a single automated word attempt.
            "pcc_severity": "Not interpreted",
            "score_scope": "single educational app activity; not diagnostic",
            "phoneme_header": {
                "expected_sequence": expected_ipa,
                "detected_sequence": detected_ipa,
            },
            "age_applicable_processes": applicable_processes,

            # --- Audio quality assessment ---
            "quality": {
                "warnings": [
                    {"check": q["check"], "message": q["message"]}
                    for q in audio_result.get("quality", {}).get("warnings", [])
                ],
                "rms_value": audio_result.get("quality", {}).get("rms_value", 0.0),
            },
        }
