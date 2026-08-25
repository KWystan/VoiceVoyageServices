#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import difflib
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from collections import Counter

from detection.detector import ProcessDetector
from detection import curriculum_map
from detection import pcc as pcc_module
from detection.utils import manner, place, is_consonant

DATA_PATH = os.path.join(os.path.dirname(__file__), "tests", "data", "phonological_process_dataset.json")
BUGLOG_DIR = os.path.join(os.path.dirname(__file__), "buglog")
BUGLOG_FILE = os.path.join(BUGLOG_DIR, "detector_audit.log")

os.makedirs(BUGLOG_DIR, exist_ok=True)

data = json.loads(open(DATA_PATH, encoding="utf-8").read())
detector = ProcessDetector()

# File/line pointers for audit report
LOGIC_LOC = {
    "Cluster Reduction": "detection/detectors/deletion.py:17 (detect_cluster_reduction)",
    "Final Consonant Deletion": "detection/detectors/deletion.py:38 (detect_final_consonant_deletion)",
    "Initial Consonant Deletion": "detection/detectors/deletion.py:61 (detect_initial_consonant_deletion)",
    "Medial Consonant Deletion": "detection/detectors/deletion.py:82 (detect_medial_consonant_deletion)",
    "Backing": "detection/detectors/substitution.py:160 (is_backing)",
    "Fronting": "detection/detectors/substitution.py:141 (is_fronting)",
    "Stopping": "detection/detectors/substitution.py:109 (is_stopping)",
    "Frication": "detection/detectors/substitution.py:123 (is_frication)",
    "Deaffrication": "detection/detectors/substitution.py:129 (is_deaffrication)",
    "Denasalization": "detection/detectors/substitution.py:135 (is_denasalization)",
    "Gliding": "detection/detectors/substitution.py:172 (is_gliding)",
    "Liquidization": "detection/detectors/substitution.py:178 (is_liquidization)",
    "Vowelization": "detection/detectors/substitution.py:184 (is_vowelization)",
    "Prevocalic Voicing": "detection/detectors/voicing.py:248 (detect_voicing_errors)",
    "Devoicing": "detection/detectors/voicing.py:248",
    "Final Devoicing": "detection/detectors/voicing.py:248",
    "Weak Syllable Deletion": "detection/syllable.py:78 (detect_weak_syllable_deletion)",
    "hierarchy": "detection/detectors/hierarchy.py:13 (ASHA_HIERARCHY + apply_clinical_hierarchy)",
    "get_position": "detection/utils.py:get_position",
    "curriculum": "detection/curriculum_map.py:_AGE_PROCESS_MAP + get_curriculum_summary",
    "pcc": "detection/pcc.py:compute_pcc / compute_overall_score",
}

def build_breakdown(target, child):
    sm = difflib.SequenceMatcher(None, target, child)
    bd = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                t = target[i1 + k]
                c = child[j1 + k]
                bd.append({'expected': t, 'predicted': c, 'score': 100.0, 'confidence': 0.95, 'duration_sec': 0.08})
        elif tag == 'replace':
            # replace block size should be equal for our dataset (1:1 substitution)
            # if sizes differ, align one-to-one up to min, extras become deletions/insertions
            n = min(i2 - i1, j2 - j1)
            for k in range(n):
                t = target[i1 + k]
                c = child[j1 + k]
                bd.append({'expected': t, 'predicted': c, 'score': 45.0, 'confidence': 0.45, 'duration_sec': 0.09})
            # leftover target -> deletions
            for k in range(n, i2 - i1):
                t = target[i1 + k]
                bd.append({'expected': t, 'predicted': '-', 'score': 0.0, 'confidence': 0.0, 'duration_sec': 0.12})
            # leftover child -> insertions (epenthesis, not expected in dataset)
            for k in range(n, j2 - j1):
                c = child[j1 + k]
                # insertion: child has extra phoneme not in target -> model as insertion not handled; flag as missing detector
                # we append as extra expected '-'? but detector expects expected list; for audit mark insertion
                bd.append({'expected': '-', 'predicted': c, 'score': 45.0, 'confidence': 0.45, 'duration_sec': 0.08})
        elif tag == 'delete':
            for k in range(i1, i2):
                t = target[k]
                bd.append({'expected': t, 'predicted': '-', 'score': 0.0, 'confidence': 0.0, 'duration_sec': 0.12})
        elif tag == 'insert':
            for k in range(j1, j2):
                c = child[k]
                bd.append({'expected': '-', 'predicted': c, 'score': 45.0, 'confidence': 0.45, 'duration_sec': 0.08})
    return bd

issues = []
buglog_lines = []
counters = Counter()
hierarchy_wins = []
curriculum_gaps = []

for idx, entry in enumerate(data):
    word = entry['Word']
    target = entry['Target IPA']
    child = entry['Child IPA']
    exp_proc = entry['Process']
    exp_pos = entry['Position']
    exp_detail = entry['Detail']
    entry_id = f"#{idx:03d} {word}"

    bd = build_breakdown(target, child)
    detected = detector.detect(bd)
    detected_names = [d['process'] for d in detected]
    detected_set = set(detected_names)

    # ---- Bugs: wrong process or no process ----
    bug_flag = False
    bug_reason = ""
    # Normalize Vowelization naming: dataset uses Vowelization
    # Detector may emit Fronting vs Palatal Fronting detail? But process name Fronting.
    # Check exact match
    if exp_proc not in detected_set:
        bug_flag = True
        bug_reason = f"Expected {exp_proc} not detected; got {detected_names or '[]'}"
    elif len(detected) > 1:
        # multiple processes for single expected entry (except grin/plus/stop etc with 2 deletions but dataset expects one string detail)
        # For cluster with 2 phonemes deleted detail "/ɡ,r/ deleted" expects one entry with detail containing both, but our detector emits two separate Cluster Reduction entries
        # Check: detail has "," -> expects single entry with comma?
        if "," in exp_detail and "Cluster Reduction" == exp_proc:
            if len(detected) != 1:
                # This is not necessarily bug, detector emits per phoneme; dataset lumps
                bug_reason = f"Multi-phoneme cluster detail lumped but detector emits {len(detected)} entries"
                # not flagging as bug strictly, but note
                bug_flag = False
        else:
            # Check hierarchy: Stopping over Fronting etc
            if exp_proc not in detected_names:
                bug_reason = f"Hierarchy kept {detected_names} over expected {exp_proc}"
                bug_flag = True
    # Wrong process type: detector emits different process name
    if not bug_flag and detected_names and exp_proc not in detected_names:
        bug_flag = True
        bug_reason = f"Wrong process: expected {exp_proc}, got {detected_names}"

    # Position mismatch
    if detected:
        # find entry matching expected process
        pos_match = next((d for d in detected if d['process']==exp_proc), None)
        if pos_match and pos_match['position'] != exp_pos:
            bug_flag = True
            bug_reason += f" | Position mismatch: expected {exp_pos}, got {pos_match['position']} at {LOGIC_LOC['get_position']}"

    # Score anomalies: check breakdown scores
    score_anomaly = ""
    for b in bd:
        if b['predicted'] == b['expected'] and b['score'] != 100:
            score_anomaly = f"Perfect match scoring {b['score']} <100 at detection/syllable scoring"
        if b['predicted'] == '-' and b['score'] != 0:
            score_anomaly = f"Deletion scoring {b['score']} !=0"

    # Curriculum gaps
    cur_gap = ""
    for age in [4,5,6,8]:
        cur = curriculum_map.get_curriculum_summary(detected, age_years=age)
        cur_labels = set(c['display_label'] for c in cur)
        for d in detected:
            # map raw process to display label via _translate
            exp_ph, pred_ph = curriculum_map._parse_detail(d['detail'])
            if not exp_ph and d['process']=="Weak Syllable Deletion":
                exp_ph = curriculum_map._extract_syllable(d['detail']) or "σ"
            translated = curriculum_map._translate_error(d, exp_ph, pred_ph)
            disp = translated['display_label']
            # If detected process display label not in applicable labels for ANY age up to 8, it's gap? Actually check if filtered at child's age (assume 4-8 range)
            # We test if at age 8 it would be filtered
            if disp not in curriculum_map._get_applicable_labels(curriculum_map._years_to_bracket(age)):
                cur_gap = f"{disp} filtered at Age {age} bracket (_AGE_PROCESS_MAP)"
                # only report for age 5 typical case
                if age==5 and exp_proc in ["Gliding","Palatal Fronting","Deaffrication"]:
                    pass
    # If detected empty but expected exists, that also may be curriculum gap not detector bug — check

    # Hierarchy logical error check: run pre-hierarchy detectors manually to see dropped
    # For simplicity, flag if expected is Stopping but Fronting also applicable -> hierarchy should keep Stopping (priority 2 vs 6) -> not error
    # If dataset expects Fronting for a case where exp is Fricative (Stopping also true) -> hierarchy would drop Fronting -> logical mismatch
    hierarchy_note = ""
    if exp_proc == "Fronting":
        # if target is fricative, Stopping also fires if pred is stop — hierarchy keeps Stopping
        for b in bd:
            if b['predicted'] != '-' and b['predicted'] != b['expected']:
                if manner(b['expected']) == "Fricative" and manner(b['predicted']) == "Stop":
                    hierarchy_note = f"Stopping (pri 2) would mask Fronting (pri 6) at {LOGIC_LOC['hierarchy']}"
                    # check if detected actually contains Fronting or Stopping
                    if "Stopping" in detected_set and "Fronting" not in detected_set:
                        hierarchy_note += " -> hierarchy correctly kept Stopping over Fronting"
                    break

    # Missing detectors: epenthesis/insertion, metathesis, assimilation (harmony)
    missing_note = ""
    # detect insertions (child longer than target)
    if len(child) > len(target):
        missing_note = "Epenthesis/insertion detected (child has extra phoneme) — no detector covers epenthesis"
    # metathesis: check if order differs but same phonemes
    if not bug_flag and not detected and sorted(target)==sorted(child) and target != child:
        missing_note = "Potential metathesis (same phonemes, different order) — no detector"

    status = "Flagged Error"  # as requested, all flagged for audit
    # Determine type for buglog
    error_type = "Bugs" if bug_flag else ("Logical errors" if hierarchy_note else ("Curriculum gap" if cur_gap else "OK"))
    # For buglog, include predicted vs expected, what went wrong
    predicted_str = ",".join(child)
    expected_str = ",".join(target)
    # Determine what system caught vs expected
    actual_str = ",".join(detected_names) if detected_names else "None"
    # Build one-line log
    # Format: ID | Word | Type | Expected(Proc/Pos/Detail) | Predicted Child | Detected | WhatWentWrong | FileLine | Status
    line = (f"ID={entry_id} | Word={word} | Type={exp_proc} | Expected={expected_str} -> Child={predicted_str} "
            f"| Detail={exp_detail} | ExpectedPos={exp_pos} | Detected={actual_str} "
            f"| Positions={[d['position'] for d in detected]} | Details={[d['detail'] for d in detected]} "
            f"| WhatWentWrong={bug_reason or hierarchy_note or cur_gap or missing_note or score_anomaly or 'None'} "
            f"| ExpectedDetail={exp_detail} | Logic={LOGIC_LOC.get(exp_proc, 'unknown')} | Status={status}")
    buglog_lines.append(line)

    if bug_flag or hierarchy_note or cur_gap or missing_note or score_anomaly:
        issues.append({
            "id": entry_id,
            "word": word,
            "expected_proc": exp_proc,
            "detected": detected,
            "bug_reason": bug_reason,
            "hierarchy_note": hierarchy_note,
            "cur_gap": cur_gap,
            "missing": missing_note,
            "score_anomaly": score_anomaly,
            "target": target,
            "child": child,
            "breakdown": bd,
        })

# Write buglog
with open(BUGLOG_FILE, "w", encoding="utf-8") as f:
    for l in buglog_lines:
        f.write(l + "\n")

print(f"Total entries: {len(data)}")
print(f"Buglog written to {BUGLOG_FILE} with {len(buglog_lines)} lines")
# Summary stats
from collections import Counter
exp_c = Counter(e['Process'] for e in data)
detected_all = []
for idx, entry in enumerate(data):
    bd = build_breakdown(entry['Target IPA'], entry['Child IPA'])
    detected = detector.detect(bd)
    detected_all.extend([d['process'] for d in detected])
det_c = Counter(detected_all)
print("Expected counts:", exp_c)
print("Detected counts:", det_c)
print(f"Issues flagged: {len(issues)}")
# show first 20 issues
for iss in issues[:20]:
    print(iss)
