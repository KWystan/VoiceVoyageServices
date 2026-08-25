# Bug Log — phoneme_service

One line per bug. `FIXED` = fix applied and verified by the local test suite; `OPEN` = reproduced/diagnosed, awaiting work.

## Detection & classification

| ID | Date | Bug | Status |
|----|------|-----|--------|
| BUG-001 | 2026-08-24 | Stale running service used old `is_deletion` burst-artifact rule — sub-threshold mismatched stop fragments read as deletions ("plane" payload: `/p/ -> [b]` @0.02s fired a false `Cluster Reduction /p/ deleted`) — gate has since been rewritten to blank-prediction-only (`detection/detectors/gates.py`) | FIXED |
| BUG-002 | 2026-08-24 | Wrong position labeling for cluster members — `/l/` of "plane" tagged "Medial" although it belongs to the word-initial cluster; `get_position` was pure index-based, not cluster-aware (`detection/utils.py`) | FIXED |
| BUG-003 | 2026-08-24 | Double-counted Cluster Reduction — adjacent deleted consonants each emitted their own event ("stop" -> [ɑp] produced two entries) because the ASHA hierarchy groups per single `_index` and never merges across indices (`detection/detectors/deletion.py`) | FIXED |
| BUG-004 | 2026-08-24 | Double-counted Final Consonant Deletion on fully deleted coda clusters ("milk" -> [mɪ] yielded CR x2 + FCD x2 rows); FCD detector now run-merges like CR and the hierarchy keeps CR (rank 13) over FCD (rank 14) | FIXED |
| BUG-005 | 2026-08-24 | Merged multi-index deletion events were wholesale-dropped when ANY member index overlapped Weak Syllable Deletion's `skip_indices` ("umbrella" medial cluster vanished entirely); orchestrator now trims covered indices and keeps the remainder (`detection/detector.py`) | FIXED |
| BUG-006 | 2026-08-24 | Voiceless-to-voiced substitutions only labeled when the NEXT phoneme was a vowel — any other `/p/ -> [b]` event (e.g. "plane" before /l/) went completely unreported; added plain `Voicing` label (`detection/detectors/voicing.py`), registered in `ASHA_HIERARCHY` (rank 12) and the curriculum translator map | FIXED |
| BUG-007 | 2026-08-24 | `eː`/`oː` normalization gap — `clean()` stripped the length mark BEFORE the translation table ran, making every `Xː` table entry dead code; FACE/GOAT monophthongs fell through `e→ɛ` / `o→ɔ`, scoring correct productions 0 and driving PVC to 0% / "Severe". Fix: `eː→eɪ`, `oː→oʊ`, `aː→ɑ` in `_IPA_NORMALIZE` + reordered `canonicalize()`/`same_phoneme()` to translate raw spellings before stripping (`ipa/normalization.py`) — vocab-wide sweep over all 381 model tokens confirms exactly 3 intended changes, near-vowel pairs (ɛ/eɪ, ɔ/oʊ) stay distinct | FIXED |
| BUG-008 | 2026-08-24 | Degenerate forced alignment — every phoneme segment exactly one CTC frame (0.02 s) even at confidence 0.98 ("plane" payload), suggesting alignment collapse on very fast audio (`model/forced_aligner.py`) | OPEN |
| BUG-009 | 2026-08-24 | Weak Syllable Deletion position is utterance-relative (first syllable = "Initial") while every other detector reports word-relative positions — inconsistent labels on multi-word phrases (`detection/syllable.py:113`) | OPEN |
| BUG-010 | 2026-08-24 | Substitution detectors do not respect WSD `skip_indices` — a substituted consonant inside an already-deleted syllable produces both a WSD row and a substitution row for the same span (possibly intentional; needs policy call) (`detection/detector.py:57-59`) | OPEN |

## Curriculum & downstream

| ID | Date | Bug | Status |
|----|------|-----|--------|
| BUG-011 | 2026-08-24 | Clinical status never escalates with age — all 10 "Expected Error" translators are structurally age-blind: `_translate_error` (`curriculum_map.py:164`) takes no `age_years`, `get_curriculum_summary` holds it but uses it only for bracket filtering; verified live: Cluster Reduction / Stopping / Fronting / Gliding all read "Expected Error" at age 8, and WSD relabels to "Syllable Reduction" at 8 yet stays "Expected Error" | OPEN |

## Audit notes — BUG-011 (reported-bug audit, 2026-08-24)

**Confirmed:** every age-sensitive translator returns "Expected Error" unconditionally —

| Process | Site | Elimination age (approx.) | Status at age 8 |
|---|---|---|---|
| Cluster Reduction | `_tl_fixed` :255 | ~5 | Expected Error |
| Weak Syllable Deletion | `_tl_fixed` :256 | ~4-5 | Expected Error (as "Syllable Reduction") |
| Fronting / Palatal Fronting | `_tl_fronting` :204,:206 | ~5 | Expected Error |
| Stopping | `_tl_stopping` :219 | ~3-4 | Expected Error |
| Gliding | `_tl_gliding` :230 | ~6-7 (source-variable) | Expected Error |
| Deaffrication | `_tl_deaffrication` :242 | ~5-6 | Expected Error |
| Prevocalic Voicing / Devoicing / Final Devoicing | `_tl_voicing` :248 | ~3-4 | Expected Error (but see BUG-012) |

Red-flag hardcodes (Backing, Frication, Denasalization, Vowelization, Liquidization, FCD/ICD/MCD) are correctly age-invariant — always atypical.

**Also verified:** the cumulative bracket filter already handles the too-young side (at age 3, CR/Gliding/Deaffrication are filtered out of `age_applicable_processes` entirely); only the too-old escalation is missing.

**Agreed fix shape:** post-process in `get_curriculum_summary` after translation — `_ASHA_ELIMINATION_AGES: dict[str, int]`; if `age_years >= elimination_age`, flip "Expected Error" → "Delayed". One function, no translator signature changes.

**Implementation caveats:**
1. Pin exact elimination ages against the ASHA practice portal before coding — sources vary (gliding is commonly cited ~6-7, not 5; stopping 3-4, not 3).
2. Voicing-family rows stay invisible until BUG-012 lands (their labels never reach `age_applicable_processes` at any age).
3. "Delayed" is a NEW status string — audited Thesis/lib: zero references to any `clinical_status` value today, so no app breakage risk, but the app also doesn't render statuses specially yet (follow-up UX work).
| BUG-012 | 2026-08-24 | Voicing-family display labels (`Devoicing`, `Prevocalic Voicing`, `Voicing`) — plus `Vowelization`, `Denasalization` — were absent from every `_AGE_PROCESS_MAP` bracket, so they never surfaced in `age_applicable_processes` (filtered at the applicability check); also Cluster Reduction sat one bracket late (Age 5) and Deaffrication two brackets late (Age 6-7). Fix: fact-checked placements against Grunwell (1987)/Bowen 2015 p.73, Shriberg (1993) synthesis via Bilinguistics, ASHA portal norms — all typical-during-preschool processes moved into Age 4 (CR elim 4;0; voicing/devoicing 3;0; deaffrication ~4;0; vowelization ~6;0 but typical throughout; denasalization ~2;6); Age 6-7 bracket now empty | FIXED |

**BUG-012 fact-check addendum:** Bowen Table 3 + Grunwell Table 2.4 (fetched from speech-language-therapy.com): prevocalic voicing 3;0, word-final devoicing 3;0, FCD 3;3, velar fronting 3;6, palatal fronting 3;9, WSD 4;0, cluster reduction 4;0, gliding 5;0, stopping 3;0-5;0 by target. Bilinguistics SLP guide (ASHA CEU provider, citing Shriberg 1993/Khan 1982/Hodson & Paden): CR ~4y, gliding ~7y, persistence ≥8y = red flag. Deaffrication (~4;0), vowelization (~6;0), denasalization (~2;6) per ASHA-portal-aligned norms — reported values differ from source to source by months, which is immaterial at year-granularity brackets. Two deliberate deviations from the reported table: Deaffrication placed in **Age 4** (not Age 5 — if eliminated by 4;0 it is a normal pattern DURING ages 2-4, same logic as FCD 3;3 in Age 4), and Palatal Fronting left in Age 5 despite Grunwell's 3;9 (flagged as optional product follow-up).

## Housekeeping

| ID | Date | Bug | Status |
|----|------|-----|--------|
| BUG-013 | 2026-08-24 | Two separate panphon `FeatureTable` instances — eager module-level load in `detection/detectors/voicing.py` vs lazy singleton in `detection/utils.py` (duplicated load cost/memory) | OPEN |
| BUG-014 | 2026-08-24 | Docstring drift — `place()` in `detection/utils.py:147` claims it can return "Dental" but dental phonemes fold to "Alveolar" (`utils.py:157`) | OPEN |
