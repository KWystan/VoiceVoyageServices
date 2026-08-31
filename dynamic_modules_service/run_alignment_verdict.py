"""Strict alignment verdict — checks what we WANT vs what we GET."""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

data = json.loads(pathlib.Path(ROOT / "run_20_case_audit_output.json").read_text(encoding="utf-8"))

def strict_checks(entry):
    issues = []
    warns = []
    inp = entry["input"]
    out = entry["output"]
    label = entry["label"]
    exp = entry["expect"]
    cid = entry["id"]

    # 1. Strict grade suitability (no fallback pollution)
    # We want: every item grades must contain parsed grade (or for Kinder, allow 0 or 1 but flag as compromise)
    parsed = out["parse_grade"]
    for lvl, details in out["levels_detail"].items():
        for it in details:
            grades = tuple(it["grades"])
            if parsed == 0:
                # Kinder: want 0, but current bank has only 3 items with 0 — so fallback to 1 is expected compromise, but mark as alignment gap
                if 0 not in grades:
                    warns.append(f"{lvl} '{it['text']}' grades {grades} has no 0 (Kinder fallback to Grade1)")
            else:
                if parsed not in grades:
                    # For Grade3, many items are 1,2 only — this is a content gap, flag as misalignment
                    issues.append(f"{lvl} '{it['text']}' grades {grades} missing Grade {parsed}")

    # 2. Vowelization / Prevocalic should be flagged as generic (0 specific items)
    if out["outline_id"] in ("vowelization", "prevocalic-voicing"):
        # Check if items actually target that process
        # For these outlines, 0 items in bank have that process tag, so any item is generic
        # Flag as alignment gap (not code bug, but curriculum gap)
        # Verify by checking if any item's processes includes the expected process
        # Pull from levels_detail
        has_specific = False
        for lvl, details in out["levels_detail"].items():
            for it in details:
                if out["outline_id"] == "vowelization" and "Vowelization" in it["processes"]:
                    has_specific = True
                if out["outline_id"] == "prevocalic-voicing" and "Prevocalic Voicing" in it["processes"]:
                    has_specific = True
        if not has_specific:
            issues.append(f"OUTLINE {out['outline_id']} has 0 bank items with that process — module is GENERIC, not targeted")

    # 3. Grade parsing bugs: cases 19,20 are intentional probes — they SHOULD be misaligned
    if cid == 19:
        # Grade 10 should ideally be rejected or mapped to 3, but currently maps to 1 due to '1' in string
        if out["grade"] == "Grade 1":
            issues.append("GRADE PARSE BUG: 'Grade 10' incorrectly -> Grade 1 (substring '1' match)")
        else:
            warns.append(f"'Grade 10' parsed to {out['grade']} (expected strict rejection or Grade 3)")
    if cid == 20:
        if out["grade"] == "Kinder":
            issues.append("GRADE PARSE BUG: 'sky' incorrectly -> Kinder (contains 'k')")
        else:
            warns.append(f"'sky' parsed to {out['grade']}")

    # 4. Atypical advisory must be present for ICD, Backing, Denasalization (and also Frication/Liquidization if they had outlines)
    if cid in (12,13,18):
        if "CLINICAL ADVISORY" not in out["rationale"]:
            issues.append("Missing CLINICAL ADVISORY for atypical process")
    # Also check WSD is not flagged atypical (correct)
    if cid == 8:
        if "CLINICAL ADVISORY" in out["rationale"]:
            issues.append("WSD should NOT have atypical advisory")

    # 5. Weak Syllable Deletion for Grade 3: we expect multisyllabic, but phrases are low-grade
    if cid == 8:
        #Already flagged via grade suitability above; also check phrase content
        phrases = out["levels"]["phrase"]
        if any(p in ("my cookie","my father","a big cup") for p in phrases):
            # These are Grade1-2 phrases, not ideal for Grade3
            warns.append(f"G3 WSD phrases are low-grade: {phrases}")

    # 6. Multi-error case 17 should exclude other error sounds
    if cid == 17:
        # Other error s should not appear in items for k-focused module
        for lvl, details in out["levels_detail"].items():
            for it in details:
                phon = it["phonemes"]
                # if s in phonemes and outline is fronting-k (targets k), s is other error
                if "s" in [p.strip() for p in phon.split(",") if p.strip()]:
                    # But need to ensure it's not coincidental (many words contain s)
                    # For strict, any s-containing item when child has s error is misaligned
                    warns.append(f"multi: {lvl} '{it['text']}' contains other error 's' phoneme {phon}")

    # 7. Check levels all 4 present and 1-4 items (already PASS, but strict)
    for lvl in ("syllable","word","phrase","sentence"):
        if lvl not in out["levels"]:
            issues.append(f"missing level {lvl}")
        elif not (1 <= len(out["levels"][lvl]) <= 4):
            issues.append(f"{lvl} count {len(out['levels'][lvl])} out of 1-4")

    # 8. Check gameplay doc slug alignment
    # For cases with process_docs, slug should match expected process
    # e.g. Fronting -> fronting_velar, Backing -> backing, etc.
    # Not strict fail, but warn if general_articulation fallback used unexpectedly
    if out.get("process_docs"):
        for d in out["process_docs"]:
            if d["slug"] == "general_articulation" and exp.get("outline") not in (None,):
                # If we expected a specific process but got general fallback, that's a gap
                if cid not in (14,15): # those are expected generic fallback? Actually they have slugs
                    pass
                else:
                    warns.append(f"process doc fallback to general_articulation for {label}")

    return issues, warns

print("=== STRICT ALIGNMENT AUDIT (what we WANT vs what we GET) ===\n")
overall_pass = 0
overall_fail = 0
for entry in data:
    issues, warns = strict_checks(entry)
    status = "ALIGNED" if not issues else "MISALIGNED"
    if status == "ALIGNED":
        overall_pass += 1
    else:
        overall_fail += 1
    print(f"[{status:10}] Case {entry['id']:2d}: {entry['label']}")
    print(f"           Input age={entry['input']['age']} grade={entry['input']['grade']!r} -> parsed {entry['output']['parse_grade']} ({entry['output']['grade']}) | outline {entry['output']['outline_id']} | focus {entry['output']['focus_sounds']}")
    # Show first sentence of rationale
    print(f"           Rationale: {entry['output']['rationale'][:120]}...")
    # Show levels summary
    lvls = ", ".join(f"{k}:{len(v)}" for k,v in entry['output']['levels'].items())
    print(f"           Levels: {lvls}")
    if issues:
        for iss in issues:
            print(f"           !! {iss}")
    if warns:
        for w in warns:
            print(f"           -- {w}")
    # Show representative items for misalignment cases
    if issues or warns:
        # print one example per level with grade mismatch
        pass
    print()

print(f"=== STRICT SUMMARY: {overall_pass} ALIGNED / {overall_fail} MISALIGNED / {len(data)} total ===")
print("\nInterpretation:")
print("- ALIGNED = meets intended curriculum + clinical spec (grade-appropriate items, correct outline, advisory where needed)")
print("- MISALIGNED = gaps between intent and current output (content sparsity, parse bugs, generic fallback, grade fallback)")
