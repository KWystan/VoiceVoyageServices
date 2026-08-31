"""20-case audit for dynamic_modules_service — age/grade alignment check.

Run: python -X utf8 run_20_case_audit.py
Produces console table + JSON dump.
"""
import sys, json, pathlib

# Ensure imports work both as package and flat
ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data import MockWordBank, MockOutlines, GradeDocuments, ModuleCatalog
from models import AssessmentFindings, DetectedProcess, PracticeLevel
from service import ModuleService, RuleBasedModuleBuilder, FindingsAnalyzer

bank = MockWordBank()
outlines = MockOutlines(bank)
grade_docs = GradeDocuments()
catalog = ModuleCatalog()

# Use deterministic rule-based builder (no LLM variability)
svc = ModuleService(
    outlines=outlines,
    bank=bank,
    grade_documents=grade_docs,
    module_catalog=catalog,
    primary_builder=RuleBasedModuleBuilder(),
)

# ---------------------------------------------------------------------------
# 20 cases — each: id, age, grade, processes, expected (for human check)
# ---------------------------------------------------------------------------
cases = [
    {
        "id": 1,
        "label": "Kinder Fronting /k/",
        "age": 4, "grade": "Kinder",
        "procs": [("Fronting", "Initial", "/k/ -> [t]")],
        "expect": {"grade": "Kinder", "outline": "fronting-k", "focus": ["k"], "advisory": False},
    },
    {
        "id": 2,
        "label": "Age 4 no grade Fronting /k/ (infer Kinder)",
        "age": 4, "grade": None,
        "procs": [("Fronting", "Initial", "/k/ -> [t]")],
        "expect": {"grade": "Kinder", "outline": "fronting-k", "focus": ["k"]},
    },
    {
        "id": 3,
        "label": "G1 Stopping /s/ -> [t]",
        "age": 5, "grade": "Grade 1",
        "procs": [("Stopping", "Initial", "/s/ -> [t]")],
        "expect": {"grade": "Grade 1", "outline": "stopping-s", "focus": ["s"]},
    },
    {
        "id": 4,
        "label": "G1 Stopping /θ/ -> [t] (th)",
        "age": 5, "grade": "Grade 1",
        "procs": [("Stopping", "Initial", "/θ/ -> [t]")],
        "expect": {"grade": "Grade 1", "outline": "stopping-th", "focus": ["θ"]},
    },
    {
        "id": 5,
        "label": "G1 Gliding /r/ -> [w]",
        "age": 6, "grade": "Grade 1",
        "procs": [("Gliding", "Initial", "/r/ -> [w]")],
        "expect": {"grade": "Grade 1", "outline": "gliding-r", "focus": ["r"]},
    },
    {
        "id": 6,
        "label": "G2 Gliding /r/ -> [w] (grade 2 items)",
        "age": 6, "grade": "Grade 2",
        "procs": [("Gliding", "Initial", "/r/ -> [w]")],
        "expect": {"grade": "Grade 2", "outline": "gliding-r", "focus": ["r"]},
    },
    {
        "id": 7,
        "label": "G2 Deaffrication /tʃ/ -> [ʃ]",
        "age": 7, "grade": "Grade 2",
        "procs": [("Deaffrication", "Initial", "/tʃ/ -> [ʃ]")],
        "expect": {"grade": "Grade 2", "outline": "deaffrication-ch", "focus": ["tʃ"]},
    },
    {
        "id": 8,
        "label": "G3 Weak Syllable Deletion (no target)",
        "age": 8, "grade": "Grade 3",
        "procs": [("Weak Syllable Deletion", "Medial", "Weak syllable 'ba' deleted in 'banana'")],
        "expect": {"grade": "Grade 3", "outline": "weak-syllable-deletion", "focus": []},
    },
    {
        "id": 9,
        "label": "G1 Cluster Reduction /bl/ -> [b]",
        "age": 5, "grade": "Grade 1",
        "procs": [("Cluster Reduction", "Initial", "/bl/ -> [b]")],
        "expect": {"grade": "Grade 1", "outline": "cluster-reduction-l", "focus": ["bl"]},
    },
    {
        "id": 10,
        "label": "G3 Cluster Reduction /st/ -> [t]",
        "age": 8, "grade": "Grade 3",
        "procs": [("Cluster Reduction", "Initial", "/st/ -> [t]")],
        "expect": {"grade": "Grade 3", "outline": "cluster-reduction-s", "focus": ["st"]},
    },
    {
        "id": 11,
        "label": "Kinder Final Consonant Deletion /t/ final",
        "age": 4, "grade": "Kinder",
        "procs": [("Final Consonant Deletion", "Final", "/t/ deleted in 'cat'")],
        "expect": {"grade": "Kinder", "outline": "final-consonant-deletion", "focus": ["t"]},
    },
    {
        "id": 12,
        "label": "G1 Initial Consonant Deletion /p/",
        "age": 5, "grade": "Grade 1",
        "procs": [("Initial Consonant Deletion", "Initial", "/p/ deleted in 'pig'")],
        "expect": {"grade": "Grade 1", "outline": "initial-consonant-deletion", "focus": ["p"], "advisory": True},
    },
    {
        "id": 13,
        "label": "G1 Backing /t/ -> [k] ATYPICAL",
        "age": 5, "grade": "Grade 1",
        "procs": [("Backing", "Initial", "/t/ -> [k]")],
        "expect": {"grade": "Grade 1", "outline": "backing-t", "focus": ["t"], "advisory": True},
    },
    {
        "id": 14,
        "label": "G2 Vowelization /l/ -> [o] (0 bank items)",
        "age": 6, "grade": "Grade 2",
        "procs": [("Vowelization", "Final", "/l/ -> [o]")],
        "expect": {"grade": "Grade 2", "outline": "vowelization", "focus": ["l"], "note": "0 specific items -> generic fallback"},
    },
    {
        "id": 15,
        "label": "G1 Prevocalic Voicing /p/ -> [b] (0 bank)",
        "age": 5, "grade": "Grade 1",
        "procs": [("Prevocalic Voicing", "Initial", "/p/ -> [b]")],
        "expect": {"grade": "Grade 1", "outline": "prevocalic-voicing", "focus": ["p"]},
    },
    {
        "id": 16,
        "label": "G1 Speech Champion (no errors)",
        "age": 6, "grade": "Grade 1",
        "procs": [],
        "expect": {"grade": "Grade 1", "outline": "speech-champion-enrichment", "focus": []},
    },
    {
        "id": 17,
        "label": "G1 Multi Fronting /k/ + Stopping /s/",
        "age": 5, "grade": "Grade 1",
        "procs": [("Fronting", "Initial", "/k/ -> [t]"), ("Stopping", "Initial", "/s/ -> [t]")],
        "expect": {"grade": "Grade 1", "outline": "fronting-k", "note": "tie break by -len(targets) or input order"},
    },
    {
        "id": 18,
        "label": "G2 Denasalization /m/ -> [b]",
        "age": 6, "grade": "Grade 2",
        "procs": [("Denasalization", "Initial", "/m/ -> [b]")],
        "expect": {"grade": "Grade 2", "outline": "denasalization", "focus": ["m"], "advisory": True},
    },
    {
        "id": 19,
        "label": "BUG: grade='Grade 10' (contains 1)",
        "age": 5, "grade": "Grade 10",
        "procs": [("Fronting", "Initial", "/k/ -> [t]")],
        "expect": {"grade": "Grade 1", "note": "BUG: parses as Grade 1 due to '1' in string"},
    },
    {
        "id": 20,
        "label": "BUG: grade='sky' (contains k)",
        "age": 5, "grade": "sky",
        "procs": [("Fronting", "Initial", "/k/ -> [t]")],
        "expect": {"grade": "Kinder", "note": "BUG: 'k' in 'sky' -> Kinder"},
    },
]

def evaluate(case, module):
    """Check alignment heuristics."""
    issues = []
    warns = []
    exp = case["expect"]

    # Grade check
    if exp.get("grade") and module.grade != exp["grade"]:
        issues.append(f"GRADE MISMATCH exp {exp['grade']} got {module.grade}")
    # Outline check
    if exp.get("outline") and module.outline_id != exp["outline"]:
        # For multi case allow either
        if case["id"] != 17:
            issues.append(f"OUTLINE MISMATCH exp {exp['outline']} got {module.outline_id}")
        else:
            warns.append(f"multi outline got {module.outline_id} (exp fronting-k or stopping-s)")
    # Focus sounds
    if "focus" in exp:
        got_focus = [s.sound for s in module.focus_sounds]
        if got_focus != exp["focus"]:
            # For some, focus derived from outline when sound not in outline? Allow but flag
            warns.append(f"focus {got_focus} vs exp {exp['focus']}")
    # Advisory
    if exp.get("advisory"):
        if "CLINICAL ADVISORY" not in (module.rationale or ""):
            issues.append("MISSING CLINICAL ADVISORY")
    else:
        if exp.get("advisory") is False and "CLINICAL ADVISORY" in (module.rationale or ""):
            issues.append("UNEXPECTED ADVISORY")
    # Levels: 4 levels, 1-4 items each, no duplicates, all items from bank, grades suitability
    for lvl, items in module.levels.items():
        if not (1 <= len(items) <= 4):
            issues.append(f"{lvl.value} has {len(items)} items (expected 1-4)")
        texts = [i.text for i in items]
        if len(set(texts)) != len(texts):
            issues.append(f"{lvl.value} duplicates {texts}")
        # Check grade suitability
        parsed_grade = GradeDocuments.parse_grade(case["grade"], default_age=case["age"])
        for it in items:
            # Grade check: allow grade 0 fallback to 1
            if parsed_grade == 0:
                if parsed_grade not in it.grades and 1 not in it.grades:
                    warns.append(f"{lvl.value} item '{it.text}' grades {it.grades} not suitable for Kinder(0) (fallback allowed 1)")
            else:
                if parsed_grade not in it.grades:
                    warns.append(f"{lvl.value} item '{it.text}' grades {it.grades} not in {parsed_grade}")
            # Bank membership: check via bank.get
            if bank.get(it.text, lvl) is None:
                issues.append(f"{lvl.value} item '{it.text}' not in bank (invented)")
    # Check error_sound exclusion: items should not contain OTHER error sounds
    # For multi case, error_sounds = child_sounds - outline_targets. We replicate logic.
    # For single process, error_sounds should be empty, so skip.
    if len(case["procs"]) > 1:
        from service import FindingsAnalyzer
        findings = AssessmentFindings(
            age=case["age"], grade=case["grade"],
            processes=tuple(DetectedProcess(process=p, position=pos, detail=d) for p, pos, d in case["procs"])
        )
        child_focus = FindingsAnalyzer().focus_sounds(findings)
        # outline targets
        target_sounds = set()
        for o in outlines.all():
            if o.id == module.outline_id:
                target_sounds = set(o.target_sounds)
                break
        child_sounds = {s.sound for s in child_focus}
        error_sounds = child_sounds - target_sounds
        for lvl, items in module.levels.items():
            for it in items:
                sounds = {p.strip() for p in it.phonemes.split(",") if p.strip()} if it.phonemes else set()
                if sounds & error_sounds:
                    warns.append(f"{lvl.value} item '{it.text}' contains other error {sounds & error_sounds}")

    # Module catalog docs
    if module.outline_id not in ("speech-champion-enrichment",):
        # process_documents should have been loaded; check rationale mentions grade label
        pass

    return issues, warns

results = []
for case in cases:
    findings = AssessmentFindings(
        age=case["age"],
        grade=case["grade"],
        processes=tuple(DetectedProcess(process=p, position=pos, detail=d) for p, pos, d in case["procs"])
    )
    try:
        mod = svc.build_module(findings)
        issues, warns = evaluate(case, mod)
        # Collect details
        results.append({
            "id": case["id"],
            "label": case["label"],
            "input": {"age": case["age"], "grade": case["grade"], "procs": case["procs"]},
            "expect": case["expect"],
            "output": {
                "grade": mod.grade,
                "outline_id": mod.outline_id,
                "outline_title": mod.outline_title,
                "focus_sounds": [s.sound for s in mod.focus_sounds],
                "focus_processes": mod.focus_processes,
                "generated_by": mod.generated_by,
                "warning": mod.warning,
                "rationale": mod.rationale,
                "levels": {lvl.value: [it.text for it in items] for lvl, items in mod.levels.items()},
                "levels_detail": {
                    lvl.value: [{"text": it.text, "target": it.target_sound, "pos": it.position,
                                 "grades": list(it.grades), "phonemes": it.phonemes,
                                 "processes": list(it.processes)} for it in items]
                    for lvl, items in mod.levels.items()
                },
                # ModuleCatalog docs for this findings
                "process_docs": [
                    {"slug": d["slug"], "path": pathlib.Path(d["path"]).name if "path" in d else "?", "len": len(d["doc_text"])}
                    for d in catalog.get_documents_for_findings(findings)
                ] if case["procs"] else [],
                "parse_grade": GradeDocuments.parse_grade(case["grade"], default_age=case["age"]),
                "grade_for_age": GradeDocuments.grade_for_age_static(case["age"]),
            },
            "issues": issues,
            "warns": warns,
            "status": "PASS" if not issues else "FAIL",
        })
        status = "PASS" if not issues else "FAIL"
        print(f"[{status:4}] Case {case['id']:2d}: {case['label']}")
        print(f"      Input grade={case['grade']!r} age={case['age']} -> parse_grade {GradeDocuments.parse_grade(case['grade'], default_age=case['age'])} ({GradeDocuments.format_grade(GradeDocuments.parse_grade(case['grade'], default_age=case['age']))}) outline={mod.outline_id} grade={mod.grade} focus={[s.sound for s in mod.focus_sounds]}")
        print(f"      Levels: " + " | ".join(f"{k}:{len(v)}" for k,v in mod.levels.items()))
        if issues:
            for iss in issues:
                print(f"      !! ISSUE: {iss}")
        if warns:
            for w in warns[:3]:
                print(f"      -- warn: {w}")
        if case["id"] in (14,15,19,20):
            # show more for known buggy
            print(f"      rationale: {mod.rationale[:140]}...")
        print()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        results.append({"id": case["id"], "label": case["label"], "error": str(exc), "status": "ERROR"})
        print(f"[ERROR] Case {case['id']}: {exc}\n")

# Summary
passed = sum(1 for r in results if r.get("status")=="PASS")
failed = sum(1 for r in results if r.get("status")=="FAIL")
errors = sum(1 for r in results if r.get("status")=="ERROR")
print(f"\n=== SUMMARY: {passed} PASS / {failed} FAIL / {errors} ERROR / {len(results)} total ===")

# Dump JSON for inspection
out_path = ROOT / "run_20_case_audit_output.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"Full output -> {out_path}")

# Also print alignment verdict table
print("\n=== ALIGNMENT VERDICT ===")
for r in results:
    print(f"{r['id']:2d} {r['label'][:50]:50} => grade {r['output']['grade'] if 'output' in r else 'ERR':12} outline {r['output']['outline_id'] if 'output' in r else 'ERR':30} status {r['status']}")
