# NBME 27 answer-key audit — 2026-06-19

Scope: `vercel/uworld-api-deploy/gold_runtime.json` items with ids of the form `nbme27_page-*`.

Constraints followed:
- read-only with no app/runtime code changes
- evidence order prioritized toward in-repo source artifacts over heuristics
- no reliance on OpenEvidence as source of truth

## Inventory reviewed

- Total `NBME 27` runtime items found in `vercel/uworld-api-deploy/gold_runtime.json`: **198**
- Items with `pdf_verified: true` provenance in runtime metadata: **28**
- Items with directly inspectable full-page NBME 27 review screenshots on disk that show the highlighted correct answer: **3**
  - `nbme27_page-94` ↔ `vercel/uworld-api-deploy/images_pages/nbme27/page94.webp`
  - `nbme27_page-115` ↔ `vercel/uworld-api-deploy/images_pages/nbme27/page115.webp`
  - `nbme27_page-120` ↔ `vercel/uworld-api-deploy/images_pages/nbme27/page120.webp`

## Direct answer-key checks performed

### 1. `nbme27_page-94`
- Runtime key in `gold_runtime.json`: `correct_answer = 2` → `B`
- Source artifact checked: `vercel/uworld-api-deploy/images_pages/nbme27/page94.webp`
- Screenshot evidence: page explicitly shows **`Correct Answer: B.`** and highlights choice `B) Folic acid`
- Result: **matches runtime**

### 2. `nbme27_page-115`
- Runtime key in `gold_runtime.json`: `correct_answer = 4` → `D`
- Source artifact checked: `vercel/uworld-api-deploy/images_pages/nbme27/page115.webp`
- Screenshot evidence: page explicitly shows **`Correct Answer: D.`** and highlights choice `D) Testosterone`
- Result: **matches runtime**

### 3. `nbme27_page-120`
- Runtime key in `gold_runtime.json`: `correct_answer = 3` → `C`
- Source artifact checked: `vercel/uworld-api-deploy/images_pages/nbme27/page120.webp`
- Screenshot evidence: page explicitly shows **`Correct Answer: C.`** and highlights choice `C`
- Result: **matches runtime**

## Confirmed discrepancies

**None confirmed from available in-repo answer-key evidence.**

## Ambiguities / limits

1. The repo contains **198** NBME 27 runtime items, but only **3** currently have directly inspectable NBME 27 full-page review screenshots that expose the answer key on disk.
2. **28** items carry `pdf_verified: true` / `source_pdf_page` metadata, but in the currently available repo state that provenance confirms question-page linkage, not an independent answer-key artifact.
3. `artifacts/evals/session45_answer_audit.json` surfaces several NBME 27 rows, but it appears to mix option-number and letter/index mappings in a way that can generate false positives, so it was **not** treated as authoritative evidence of wrong runtime keys.
4. `vercel/uworld-api-deploy/nbme27_qc_updates.json` only contains additive entries for `nbme27_page-198` and `nbme27_page-199`; it does not document answer-key corrections for the audited NBME 27 items.

## Recommended next action

Recover or generate a deterministic NBME 27 answer-key artifact for the remaining items — ideally either:
- full-page review screenshots for the missing `nbme27_page-*` questions, or
- a canonical NBME 27 extracted answer-key manifest under `artifacts/forms/` or `artifacts/research/`

Then rerun this audit against that artifact to expand from the current **3 direct checks** to the full NBME 27 set.
