# FUSMLE Agent Operating System

This file is the **source of truth** for AI agents working in this repository.

If another local context file exists (`CLAUDE.md`, `CAPTAIN.md`, `BUILD.md`, `REVIEW.md`), treat it as a role-specific view of this document, not a competing spec.

## 1. Mission

Operate this repo as a **retrieval, curation, manifest, and parity-QA system** for Step 1 exam experiences built from the existing qbank.

The qbank already contains real extracted NBME Step 1 content from multiple forms. The highest-value work is:

1. recover source materials accurately
2. normalize them into one schema
3. resolve duplicates and blueprint matches
4. freeze deterministic manifests
5. verify the app serves them correctly

Do **not** default to synthetic generation when exact or near-exact recovered content exists.

## 2. Repository surfaces

- `vercel/uworld-frontend/` — static frontend served by Vercel
- `vercel/uworld-api-deploy/` — Flask backend and exam APIs
- `vercel/uworld-api-deploy/gold_runtime.json` — runtime qbank payload
- `vercel/uworld-api-deploy/images_crop/`, `images_pages/` — image assets used by questions
- `skills/` — project-local agent skills for curation/reconstruction work

## 3. Source-of-truth priority

When sources disagree, use this order:

1. explicit runtime data or source form artifacts
2. deterministic manifests already frozen in the repo
3. normalized artifacts generated from source material
4. qbank heuristics / duplicate inference
5. LLM judgment

LLM judgment is the tie-breaker of last resort, not the foundation.

## 4. Non-negotiables

- Do not rewrite medical stems or answer choices for style.
- Do not silently substitute non-exact items.
- Do not casually renumber or reorder items.
- Do not ship named exams from ad hoc runtime assembly if a manifest can be frozen.
- Do not claim 1:1 or “official” fidelity without evidence.
- Do not merge blueprint fit and exact recovery into one vague bucket.
- Do not treat a passing UI smoke as proof of content fidelity.

## 5. Local skill load order

Use project-local skills first:

1. `skills/form-ingestion/`
2. `skills/qbank-schema-normalization/`
3. `skills/blueprint-match-selection/`
4. `skills/manifest-build-and-freeze/`
5. `skills/eval-and-parity-qa/`
6. `skills/research-loop/`

### Skill activation matrix

| Situation | Skill |
|---|---|
| PDF/screenshots/forms need extraction | `form-ingestion` |
| qbank rows and extracted forms need one typed schema | `qbank-schema-normalization` |
| building or repairing a 120-style form from existing items | `blueprint-match-selection` |
| converting a curated selection into production-safe app input | `manifest-build-and-freeze` |
| comparing candidate manifests or validating shipped exam UX | `eval-and-parity-qa` |
| uncertain duplicate/candidate slot needs evidence loop | `research-loop` |

## 6. Upstream skill catalogs available in this environment

These are workspace resources, not repo content:

- `/home/agent-skill-sources/anthropic-skills`
- `/home/agent-skill-sources/openai-skills`
- `/home/agent-skill-sources/agent-skills-hub`
- `/home/agent-skill-sources/claude-skills`

Use them as pattern libraries and reusable tactics. Do **not** vendor bulk noise into the repo without a clear project benefit.

## 7. SOTA tool repos available in this environment

- `/home/sota-skills/docling` — high-fidelity document/PDF/layout extraction
- `/home/sota-skills/instructor` — typed structured extraction and validation
- `/home/sota-skills/dspy` — ranking and prompt/program optimization
- `/home/sota-skills/promptfoo` — eval/regression harness
- `/home/sota-skills/pydantic-ai` — typed agents, evals, durable execution
- `/home/andrej-karpathy-skills` — anti-bloat / anti-assumption execution discipline

### Default tool mapping

- source PDF or screenshot extraction → `docling` first, OCR only where needed
- schema repair / content normalization → `instructor` + Pydantic models
- selector optimization / retrieval ranking → `dspy`
- side-by-side candidate evaluation / regression gating → `promptfoo`
- durable multi-step orchestration if needed → `pydantic-ai`

## 8. Canonical artifact contract

Prefer writing deterministic artifacts instead of leaving work implicit in prompts or chats.

### Default paths

- `artifacts/forms/<form_slug>/...`
- `artifacts/qbank/...`
- `artifacts/manifests/...`
- `artifacts/evals/...`
- `artifacts/research/...`

### Minimum expected outputs by phase

| Phase | Artifact |
|---|---|
| source extraction | `artifacts/forms/<form_slug>/questions.json` |
| normalization | `artifacts/qbank/normalized_items.jsonl` |
| dedupe | `artifacts/qbank/duplicate_groups.json` |
| selection | `artifacts/manifests/<exam_slug>.json` |
| coverage explanation | `artifacts/manifests/<exam_slug>.coverage_report.json` |
| parity/evals | `artifacts/evals/<exam_slug>.json` and `.md` |
| ambiguity logging | `artifacts/research/<exam_slug>-decision-log.jsonl` |

## 9. Named exam reconstruction workflow

Follow this exact order:

1. ingest source form artifacts into canonical question records
2. normalize source items and qbank rows into one schema
3. build duplicate groups and candidate pools
4. rank candidates with a retrieval-first selector
5. freeze the chosen exam into a deterministic manifest
6. verify with structural evals and browser parity QA
7. only then wire or ship app behavior

If a phase is skipped, assume the output is suspect.

## 10. Candidate selection policy

When filling any exam slot, choose in this order:

1. exact source recovery
2. explicit duplicate relationship
3. strongest blueprint fit
4. documented fallback

For any slot that is not exact recovery, record why.

### Never acceptable

- “This seemed close enough”
- “The model preferred it”
- “We needed to get to 120”

## 11. Manifest policy

Named exams such as Test 1, NBME 120 derivatives, or curated 120-style forms should be backed by a **versioned deterministic manifest**, not runtime randomness.

Manifest requirements:

- stable question IDs
- stable ordering
- stable block assignments
- provenance for each selection
- diffable changes when a form changes

If manifest content changes, bump the manifest version and note why.

## 12. App behavior rules

When touching the shipped experience:

- preserve resume/history behavior
- preserve stable question ordering
- verify block transitions
- verify image/table assets still resolve
- verify named-exam behavior is consistent across fresh sessions and resumed sessions

If a backend or manifest change can alter exam ordering, treat it as high risk.

## 13. Verification gates

Do not declare named-exam work complete until the following are true:

1. artifact generation completed without schema drift
2. question counts and block counts match target
3. duplicate leakage is zero or explicitly justified
4. coverage report explains all non-exact selections
5. relevant backend tests pass
6. browser parity QA passes on the served flow

### Known useful backend checks

Run from `vercel/uworld-api-deploy/`:

```bash
python -m unittest tests.test_api_contract
python -m unittest tests.test_free120_contract
python -m unittest tests.test_nbme120_contract
python -m unittest tests.test_image_manifest_contract
```

If you change named-exam generation or manifest wiring, run the relevant subset and then do a real browser flow.

## 14. Research and ambiguity policy

If source recovery is incomplete or duplicate groups are messy:

- narrow the uncertainty precisely
- gather the smallest evidence set that can resolve it
- compare candidates against raw source artifacts and normalized rows
- record the decision and confidence
- move on

Do not disappear into open-ended “research.”

## 15. Shipping policy

Prefer the smallest correct change.

For content fidelity work:

- content correctness beats elegance
- deterministic artifacts beat prompt cleverness
- reproducibility beats speed theater

For code changes:

- frontend-only behavior change → verify in browser
- backend-only content/selection change → verify through API and browser
- manifest change → verify loader resolution, history/resume, and exam counts

## 16. Cross-agent compatibility

This repo should be understandable to multiple agent runtimes.

- `AGENTS.md` = canonical operating manual
- `CLAUDE.md` = Claude/Cursor/Gemini-friendly compatibility shim
- `CAPTAIN.md` = Capy/Captain repo-specific execution brief
- `BUILD.md` = implementation-agent checklist
- `REVIEW.md` = review-agent checklist

If these files diverge, update them so `AGENTS.md` remains the ground truth.
