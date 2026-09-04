# Dynamic module document convention

These files provide human-reviewed educational context for text-only module
selection. They do not contain executable prompts, diagnose a child, or replace
the canonical word bank.

## Required layout

```text
modules/
  kinder_age_4/
    expected_errors/
    delayed_errors/
    atypical_errors/
  kinder_age_5/
    expected_errors/
    delayed_errors/
    atypical_errors/
```

The category names are retained for compatibility with the existing thesis
documents. They are internal routing labels only. User-facing text must use
descriptive wording such as â€œpractice focusâ€ or â€œconsider professional reviewâ€
and must not present these folders as a diagnosis.

Each filename is a unique `snake_case` process slug within its age folder, for
example `fronting_velar.md`. Every age folder must contain exactly one
`general_articulation.md` fallback. Do not place age or category in the filename.

## Required header fields

Every file begins with one H1 title followed by these bold fields:

```markdown
# Learning Module: Display Name (Track / Age)
**Module ID**: `unique-module-id`
**Target Process**: descriptive process tag
**Target Age / Grade**: age and educational placement
**Evidence Note**: internal evidence-routing note; not a diagnosis
**Educational Standard**: cited educational anchor
**Island Gameplay Map**: existing map level
```

The full document is for expert review. Runtime code extracts only compact
metadata; it never sends the full file to the LLM.

## Mapping rules

- `ModuleCatalog.normalize_slug()` is the sole process-to-file mapping seam.
- Add a mapping test whenever a process slug is added or renamed.
- Age 4 is labeled an ECCD/pre-kindergarten adaptation unless verified school
  placement says otherwise. Age 5 is the DepEd Kindergarten track.
- Keep language and dialect assumptions explicit. Current content is an English
  reference catalog and is not a Philippine diagnostic norm.
- Module text may reference only canonical entries in `data/word_bank.json`.
- Generate text only. Do not add image prompts, URLs, audio, SSML, or asset paths.

## Validation workflow

From the `VoiceVoyageServices` repository:

```bash
python -X utf8 scripts/sync_word_bank_catalog.py --check
python -X utf8 -m pytest dynamic_modules_service/tests
```

The service also validates folder presence, category names, unique slugs, and
the required general fallback when it starts.

