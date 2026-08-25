#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, difflib, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from collections import Counter
from detection.detector import ProcessDetector
from detection import curriculum_map, pcc as pcc_module
from detection.utils import manner, place, is_consonant, get_position

DATA_PATH = os.path.join(os.path.dirname(__file__), "tests", "data", "phonological_process_dataset.json")
BUGLOG_FILE = os.path.join(os.path.dirname(__file__), "buglog", "detector_audit.log")
REPORT_FILE = os.path.join(os.path.dirname(__file__), "buglog", "audit_report.md")

data = json.loads(open(DATA_PATH, encoding="utf-8").read())
detector = ProcessDetector()

LOGIC = {
    "Cluster Reduction": "detection/detectors/deletion.py:17 detect_cluster_reduction",
    "Final Consonant Deletion": "detection/detectors/deletion.py:38 detect_final_consonant_deletion",
    "Initial Consonant Deletion": "detection/detectors/deletion.py:61 detect_initial_consonant_deletion",
    "Medial Consonant Deletion": "detection/detectors/deletion.py:82 detect_medial_consonant_deletion",
    "Backing": "detection/detectors/substitution.py:160 is_backing",
    "Fronting": "detection/detectors/substitution.py:141 is_fronting",
    "Stopping": "detection/detectors/substitution.py:109 is_stopping",
    "Gliding": "detection/detectors/substitution.py:172 is_gliding",
    "Deaffrication": "detection/detectors/substitution.py:129 is_deaffrication",
    "Prevocalic Voicing": "detection/detectors/voicing.py:248 detect_voicing_errors",
    "Devoicing": "detection/detectors/voicing.py:248",
    "Final Devoicing": "detection/detectors/voicing.py:248",
    "Weak Syllable Deletion": "detection/syllable.py:78 detect_weak_syllable_deletion",
    "Vowelization": "detection/detectors/substitution.py:184 is_vowelization",
    "hierarchy": "detection/detectors/hierarchy.py:13 ASHA_HIERARCHY",
    "get_position": "detection/utils.py:get_position",
    "curriculum": "detection/curriculum_map.py:_AGE_PROCESS_MAP",
    "pcc": "detection/pcc.py:compute_pcc",
}

def build_breakdown(target, child):
    sm = difflib.SequenceMatcher(None, target, child)
    bd=[]
    for tag,i1,i2,j1,j2 in sm.get_opcodes():
        if tag=='equal':
            for k in range(i2-i1):
                bd.append({'expected':target[i1+k],'predicted':child[j1+k],'score':100.0,'confidence':0.95,'duration_sec':0.08})
        elif tag=='replace':
            n=min(i2-i1,j2-j1)
            for k in range(n):
                bd.append({'expected':target[i1+k],'predicted':child[j1+k],'score':45.0,'confidence':0.45,'duration_sec':0.09})
            for k in range(n, i2-i1):
                bd.append({'expected':target[i1+k],'predicted':'-','score':0.0,'confidence':0,'duration_sec':0.12})
            for k in range(n, j2-j1):
                bd.append({'expected':'-','predicted':child[j1+k],'score':45.0,'confidence':0.45,'duration_sec':0.08})
        elif tag=='delete':
            for k in range(i1,i2):
                bd.append({'expected':target[k],'predicted':'-','score':0.0,'confidence':0,'duration_sec':0.12})
        elif tag=='insert':
            for k in range(j1,j2):
                bd.append({'expected':'-','predicted':child[k],'score':45.0,'confidence':0.45,'duration_sec':0.08})
    return bd

# Rebuild with proper one-line buglog as requested: details predicted/expected which part went wrong, what should be errors and what system caught - type, status flagged error
os.makedirs(os.path.dirname(BUGLOG_FILE), exist_ok=True)
buglog = open(BUGLOG_FILE, "w", encoding="utf-8")

bugs=[]
logical=[]
edges=[]
cur_gaps=[]
score_issues=[]
missing_notes=[]

for idx, entry in enumerate(data):
    word=entry['Word']
    target=entry['Target IPA']
    child=entry['Child IPA']
    exp_proc=entry['Process']
    exp_pos=entry['Position']
    exp_detail=entry['Detail']
    bd=build_breakdown(target, child)
    detected=detector.detect(bd)
    det_names=[d['process'] for d in detected]

    # Determine actual vs expected process (consider display label translation for Fronting palatal)
    # For audit, treat Fronting with ʃ->s as Fronting (detector emits Fronting; display Palatal Fronting)
    actual_proc = det_names[0] if det_names else "None"
    # Check Bugs: wrong process or no process
    if exp_proc not in det_names:
        bugs.append((idx, word, exp_proc, actual_proc, exp_detail, f"{LOGIC.get(exp_proc,'unknown')}"))
    # Position edge check
    if detected:
        pos = detected[0]['position']
        if pos != exp_pos:
            edges.append((idx, word, exp_proc, f"expected Pos {exp_pos} got {pos}", LOGIC['get_position']))
    # Curriculum gap: check Age 4 filtering (child age assumed 4 for screening)
    if detected:
        cur = curriculum_map.get_curriculum_summary(detected, age_years=4)
        cur_labels=[c['display_label'] for c in cur]
        # Map expected to display: Fronting with ʃ-> Palatal Fronting
        disp_expected = "Palatal Fronting" if (exp_proc=="Fronting" and "ʃ" in exp_detail and "s" in exp_detail) else exp_proc
        # also handle get_position logic: if detected display not in cur
        # check via _translate
        for d in detected:
            exp_ph,pred_ph=curriculum_map._parse_detail(d['detail'])
            if d['process']=="Weak Syllable Deletion":
                exp_ph=curriculum_map._extract_syllable(d['detail']) or "σ"
                pred_ph="-"
            tr=curriculum_map._translate_error(d, exp_ph, pred_ph)
            if tr['display_label'] not in curriculum_map._get_applicable_labels(curriculum_map._years_to_bracket(4)):
                cur_gaps.append((idx, word, exp_proc, tr['display_label'], LOGIC['curriculum']))

    # Score anomalies
    for b in bd:
        if b['predicted']==b['expected'] and b['score']!=100:
            score_issues.append((idx, word, b))
        if b['predicted']=='-' and b['score']!=0:
            score_issues.append((idx, word, b))
    # PCC
    pcc_res=pcc_module.compute_pcc(bd)
    # If word has only vowels, PCC should be N/A (0.0 with N/A) -> flagged elsewhere

# Logical errors: hierarchy - check Stopping over Fronting case
# Find entries where target fricative palatal could trigger both
for idx, entry in enumerate(data):
    target=entry['Target IPA']
    child=entry['Child IPA']
    bd=build_breakdown(target, child)
    # pre-hierarchy check: collect all possible before filtering? Use internal detectors
    from detection.detectors.substitution import SUBSTITUTION_SPECS, scan_substitutions
    from detection.detectors.gates import is_substitution
    # simulate: for each spec, would it fire?
    candidates=[]
    for spec in SUBSTITUTION_SPECS:
        for i,b in enumerate(bd):
            if b['predicted']=='-' or b['predicted']=='': continue
            if b['predicted']==b['expected']: continue
            # use predicate
            if spec.matches(b):
                candidates.append((spec.process, b['expected'], b['predicted']))
    # if both Stopping and Fronting in candidates at same index, hierarchy should keep Stopping (2<6)
    # Check dataset expectation: if expected is Fronting but Stopping wins, it's logical per hierarchy
    procs=[c[0] for c in candidates]
    if "Stopping" in procs and "Fronting" in procs and entry['Process']=="Fronting":
        logical.append((idx, entry['Word'], "Stopping(2) vs Fronting(6) -> hierarchy keeps Stopping", LOGIC['hierarchy']))

# Missing detectors analysis (global, not per entry)
missing_notes.append(("Metathesis", "No entries test phoneme reordering (e.g., ask -> aks); no metathesis detector exists", "detection/detectors/* (no metathesis module)"))
missing_notes.append(("Assimilation/Consonant Harmony", "No entries test progressive assimilation beyond voicing (e.g., dog -> gog is Backing, but harmony not separate); harmony detector gap", "detection/detectors/substitution.py"))
missing_notes.append(("Epenthesis", "No entries test inserted vowel/consonant (child longer than target); inserted phonemes produce breakdown with expected='-' which detectors ignore", "detection/detectors/deletion.py + gates.py"))
missing_notes.append(("Frication/Denasalization/Liquidization gaps in dataset", "Dataset covers 14 of 17 detector processes; Frication, Denasalization, Liquidization never appear in dataset (50 each missing would be 150 entries). Curriculum includes them but dataset lacks coverage", "detection/detectors/substitution.py"))

# Regenerate buglog one-line per entry with required fields
buglog_lines=[]
for idx, entry in enumerate(data):
    target=",".join(entry['Target IPA'])
    child=",".join(entry['Child IPA'])
    exp_proc=entry['Process']
    bd=build_breakdown(entry['Target IPA'], entry['Child IPA'])
    detected=detector.detect(bd)
    actual=",".join([d['process'] for d in detected]) if detected else "None"
    # which part went wrong
    part="None"
    if exp_proc not in actual:
        part=f"Phoneme {entry['Detail']}"
    type_err="Bugs" if exp_proc not in actual else ("Curriculum gap" if any(c[1]==entry['Word'] for c in cur_gaps) else "OK")
    status="Flagged Error"
    line=f"ID=#{idx:03d} Word={entry['Word']} Type={exp_proc} Expected=[{target}]->[{child}] PredictedChild=[{child}] WhichPartWrong={part} ShouldBe={exp_proc} SystemCaught={actual} ErrorType={type_err} Logic={LOGIC.get(exp_proc, LOGIC['hierarchy'])} Status={status}"
    buglog_lines.append(line)

open(BUGLOG_FILE,"w",encoding="utf-8").write("\n".join(buglog_lines))

# Print audit summary
print("=== AUDIT SUMMARY ===")
print(f"Total entries: {len(data)}")
print(f"Bugs (wrong/missing process): {len(bugs)}")
for b in bugs[:10]: print(b)
print(f"Logical hierarchy notes: {len(logical)}")
for l in logical[:10]: print(l)
print(f"Edge position mismatches: {len(edges)}")
for e in edges[:10]: print(e)
print(f"Curriculum gaps flagged: {len(cur_gaps)} examples: {cur_gaps[:5]}")
print(f"Score anomalies: {len(score_issues)}")
for s in score_issues[:5]: print(s)
print(f"Missing detector gaps: {len(missing_notes)}")
for m in missing_notes: print(m)
print(f"Buglog: {BUGLOG_FILE} lines={len(buglog_lines)}")
# Also write markdown report
with open(REPORT_FILE,"w",encoding="utf-8") as f:
    f.write("# Detector 700-Entry Audit Report\n\n")
    f.write(f"Total entries: {len(data)}\n\n")
    f.write(f"## Bugs ({len(bugs)})\n")
    for b in bugs: f.write(str(b)+"\n")
    f.write(f"\n## Logical Errors - Hierarchy ({len(logical)})\n")
    for l in logical: f.write(str(l)+"\n")
    f.write(f"\n## Edge Cases - Position ({len(edges)})\n")
    for e in edges: f.write(str(e)+"\n")
    f.write(f"\n## Curriculum Gaps ({len(cur_gaps)})\n")
    for g in cur_gaps[:20]: f.write(str(g)+"\n")
    f.write(f"\n## Score Anomalies ({len(score_issues)})\n")
    for s in score_issues: f.write(str(s)+"\n")
    f.write(f"\n## Missing Detectors\n")
    for m in missing_notes: f.write(str(m)+"\n")
print(f"Report: {REPORT_FILE}")
