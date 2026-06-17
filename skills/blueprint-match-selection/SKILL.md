---
name: blueprint-match-selection
description: Use when assembling a 120-style exam from the existing qbank by matching a target blueprint, block structure, and item sequence. Optimize selection and ranking; do not invent questions when the qbank already contains the source material.
---

# Blueprint Match Selection

## Purpose

Select the best existing qbank items to reconstruct a target form or form-style exam with maximum structural fidelity.

The user has already stated the source qbank contains real extracted NBME Step 1 questions from multiple forms. Treat this as a retrieval and curation problem first, not a generation problem.

## Use when

- Building Test 1 / 120-style forms from existing items
- Matching block composition, topic balance, and question feel
- Ranking duplicate or near-duplicate candidate items
- Freezing deterministic manifests for production use

## Default workflow

1. Define the target blueprint:
   - block sizes
   - ordering constraints
   - subject/system distribution
   - media/table density
   - difficulty curve
2. Build candidate pools from normalized qbank items.
3. Rank candidates using evidence in this order:
   - exact source-form match
   - strong duplicate/near-duplicate match
   - blueprint fit
   - media/layout parity
4. Optimize the selector with `dspy` or equivalent prompt/program tuning.
5. Emit a deterministic manifest, never a one-off ad hoc list.

## Hard rules

- Prefer exact recovered items over synthetic paraphrases.
- Do not “improve” stems or options.
- Do not shuffle block order unless the target spec explicitly says to.
- Do not mix in off-blueprint filler just to reach 120.
- If coverage is incomplete, report the gaps explicitly.

## Output artifacts

- `artifacts/manifests/<exam_slug>.json`
- `artifacts/manifests/<exam_slug>.explanations.json`
- `artifacts/manifests/<exam_slug>.coverage_report.json`

## Minimum manifest fields

```json
{
  "exam_slug": "test1",
  "source_forms": ["form_a", "form_b"],
  "blocks": [
    {
      "block": 1,
      "question_ids": ["..."],
      "selection_rationale_by_question": {
        "<question_id>": "exact|duplicate|blueprint-fit"
      }
    }
  ]
}
```

## Verification

- Total question count is exact
- Block counts are exact
- No duplicate question IDs within a form
- Coverage report explains every non-exact selection
