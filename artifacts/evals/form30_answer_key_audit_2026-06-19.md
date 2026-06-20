# Form 30 answer-key audit — 2026-06-19

## Scope

- Audited only `Form 30`-derived rows in `vercel/uworld-api-deploy/gold_runtime.json`
- Inclusion rule: question id starts with `form30_page-`
- No app/runtime code changed

## Count checked

- **200** Form 30 items in `gold_runtime.json`

## What I checked

1. Structural validation of all 200 runtime rows
   - `correct_answer` is present and within the option count
   - the selected option's `id` matches the 1-based answer index
   - the selected option's `letter` matches the 1-based answer index
2. Derivative export consistency
   - checked Form 30 items embedded in `artifacts/exports/test1_exam.json`
   - checked Form 30 items embedded in `artifacts/exports/test2_exam.json`
   - in both exports, `correctAnswer.index` and `correctAnswer.letter` are internally consistent for all included Form 30 items
3. Manual adjudication of previously flagged rows
   - reviewed the 20 Form 30 rows called mismatches in `artifacts/evals/session45_answer_audit.json`
   - checked representative rows directly against the runtime stem/options/explanation and source-linked image metadata where available

## Confirmed mismatches

- **None confirmed** in `vercel/uworld-api-deploy/gold_runtime.json`

I did **not** find defensible evidence in the repo that any Form 30 runtime answer key is wrong.

## Important finding: prior audit artifact appears mis-mapped

`artifacts/evals/session45_answer_audit.json` appears to have an **off-by-one/index-to-letter mapping problem** for Form 30 rows, which creates false OE/runtime mismatch signals.

Examples:

- `form30_page-155`
  - runtime row: `correct_answer = 2` → option **B** `Enalapril`
  - export row: `correctAnswer.index = 2`, `correctAnswer.letter = B`
  - session45 artifact reports runtime correct option/letter as **3 / C**
- `form30_page-174`
  - runtime row: `correct_answer = 5` → option **E** `Spleen`
  - export row: `correctAnswer.index = 5`, `correctAnswer.letter = E`
  - session45 artifact reports runtime correct option/letter as **6 / F**
- `form30_page-101`
  - runtime row: `correct_answer = 2` → option **B** `Eosinophils`
  - export row: `correctAnswer.index = 2`, `correctAnswer.letter = B`
  - session45 artifact reports runtime correct option/letter as **3 / C**

This means the session45 mismatch artifact is **not reliable evidence** that the underlying Form 30 qbank keys are wrong.

## Ambiguous items needing manual adjudication

- **No specific Form 30 item is being surfaced as a confirmed key discrepancy or a narrow unresolved item-level ambiguity from the repo evidence available here.**

Repo-level limitation:

- I did **not** find a local Form 30 PDF or official answer-key artifact in the repo to do a direct source-vs-runtime diff.
- Because of that, this audit is strongest on:
  - repo-internal answer-key consistency
  - manual adjudication of previously flagged rows
  - detection of derivative artifact bugs

## Recommended next action

1. Treat `gold_runtime.json` Form 30 answer keys as **not shown incorrect by current repo evidence**.
2. Do **not** use `artifacts/evals/session45_answer_audit.json` as proof of Form 30 key defects without fixing its index/letter mapping first.
3. If you want higher-confidence source-of-truth verification, add the actual **Form 30 source PDF and/or official answer-key artifact** to the repo and rerun a form-scoped comparison directly against that source.
