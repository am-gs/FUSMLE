# NBME 29 answer-key / scoring-metadata audit

Date: 2026-06-19

Scope: `vercel/uworld-api-deploy/gold_runtime.json` rows whose `id` matches `nbme29_q*`.

## Inventory checked

- Total `nbme29_q*` rows in `gold_runtime.json`: **200**
- `exam_ready: true`: **188**
- `exam_ready: false`: **12**
- `pdf_verified: true`: **21**
- `option_parse_error: true`: **4**
- Rows with structurally invalid `correct_answer` (out of range for current options): **3**

## Method

1. Enumerated all `nbme29_q*` runtime rows.
2. Correlated them with `qbank_index.json` provenance fields (`source_pdf_page`, `pdf_verified`, `exam_ready`).
3. Reviewed the PDF-verified subset and prior repo audit artifacts (`session45_answer_audit.*`, `session45_independent_adjudication.md`) as suspect lists only, not as source of truth.
4. Flagged only discrepancies directly supported by the stored runtime rows and source-form/asset state.

## Confirmed discrepancies

### 1) `nbme29_q0118`
- Runtime row: `gold_runtime.json:27106-27139`
- Problem: `correct_answer` is **0**, but the row has exactly **1** option.
- Why this is confirmed wrong: valid answers in this schema are 1-based option numbers. `0` cannot index any option and is therefore scoring-invalid on its face.
- Additional evidence:
  - `option_parse_error: true`
  - `exam_ready: false`
  - `qbank_index.json:8744-8758` shows `n_options: 1`, `pdf_verified: false`
- User-visible impact: none in normal named-exam flows while `exam_ready: false` is respected; high risk if this row is ever surfaced by generic qbank/test generation or if `exam_ready` gating regresses.
- Confidence: **high**

### 2) `nbme29_q0129`
- Runtime row: `gold_runtime.json:27702-27740`
- Problem: `correct_answer` is **0**, but the row has exactly **1** option.
- Why this is confirmed wrong: same schema-level invalidity as above; answer key is out of range.
- Additional evidence:
  - `option_parse_error: true`
  - `exam_ready: false`
  - `qbank_index.json:8931-8945` shows `n_options: 1`, `pdf_verified: false`
- User-visible impact: none if `exam_ready: false` gating holds; scoring-invalid if the row is ever exposed.
- Confidence: **high**

### 3) `nbme29_q0185`
- Runtime row: `gold_runtime.json:30552-30585`
- Problem: `correct_answer` is **0**, but the row has exactly **1** option.
- Why this is confirmed wrong: answer key is structurally impossible for the present option list.
- Additional evidence:
  - `option_parse_error: true`
  - `exam_ready: false`
  - `qbank_index.json:9883-9897` shows `n_options: 1`, `pdf_verified: false`
- User-visible impact: none if `exam_ready: false` gating holds; scoring-invalid if surfaced.
- Confidence: **high**

## Ambiguous / manual-adjudication items

### `nbme29_q0105`
- Runtime row: `gold_runtime.json:26463-26496`
- Current state:
  - `option_parse_error: true`
  - only **1** collapsed option is present
  - `correct_answer: 1`
  - `exam_ready: false`
- Supporting concern: the stored image asset `images_crop/nbme29_q0105_img01.webp` appears unrelated to the ROC-curve prompt, so the source linkage/asset state also looks wrong.
- Why I am not calling this a confirmed key mismatch: with the options collapsed and the image apparently mismatched, I cannot defensibly recover the intended labeled answer from repo evidence alone.
- Recommendation: manual source-form re-ingestion/adjudication before this row is ever made exam-ready.

## Negative finding

For the **21 NBME 29 rows that are `pdf_verified: true`**, I did **not** find concrete evidence in the repo that their current `correct_answer` values are wrong. Some older audit artifacts show disagreement between displayed letters and runtime/session behavior, but those artifacts are consistent with indexing/mapping problems in the audit/session layer rather than with a demonstrably wrong `gold_runtime.json` answer key for the PDF-verified NBME 29 rows.

## Recommended next action

1. Treat `nbme29_q0118`, `nbme29_q0129`, and `nbme29_q0185` as confirmed broken metadata rows.
2. Re-ingest the four `option_parse_error` NBME 29 rows (`q0105`, `q0118`, `q0129`, `q0185`) from source-form assets before any attempt to expose them in exam-ready pools.
3. If you want a deeper pass next, I can produce a second artifact that manually adjudicates the remaining **167** non-`pdf_verified`, `exam_ready: true` NBME 29 keys one-by-one, but that would require heavier source reconstruction and should be done as a separate evidence pass.
