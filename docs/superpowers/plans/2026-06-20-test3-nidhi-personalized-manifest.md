# Nidhi TEST 3 Personalized Manifest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and ship a deterministic named `TEST 3` for Nidhi that uses the curated gold qbank, resembles a real NBME-style 120, targets her weak areas, excludes all previously taken question IDs and near-duplicate concepts, and produces a printable sample PDF.

**Architecture:** Treat `TEST 3` as an artifact-first reconstruction workflow. First freeze Nidhi-specific inputs (taken-exam inventory, exclusion set, weakness profile), then generate a deterministic personalized manifest from the curated qbank with explicit provenance and fail-closed guards, then wire that manifest into the existing backend/frontend named-exam path, then export a PDF and verify parity through tests and browser flow checks.

**Tech Stack:** Python 3, `json`, `collections`, `pathlib`, `argparse`, `hashlib`, existing Flask backend, static frontend HTML/JS, existing qbank manifest/export scripts, `unittest`, and Chrome/Chromium headless PDF export.

## Global Constraints

- Use repo-local skill order first, especially `skills/blueprint-match-selection/`, `skills/manifest-build-and-freeze/`, `skills/eval-and-parity-qa/`, and `skills/research-loop/`.
- Use the curated gold qbank and existing source-form artifacts; do not synthesize new medical questions.
- Named exams must be backed by a versioned deterministic manifest with stable question IDs, stable ordering, stable block assignments, and provenance for every selection.
- Preserve resume/history behavior, stable question ordering, and block transitions in the shipped app.
- Do not reuse any question already present in Nidhi’s previously taken exam sets.
- Prefer excluding previously seen `concept_fingerprint` values as well; if any overlap is unavoidable, log it explicitly with justification.
- Use Nidhi’s scored performance artifacts as the source for weakness targeting, but do not let weakness weighting break NBME-like structure.
- Keep the exam at 120 questions in 6 blocks of 20.
- Fail closed if the third prior exam set cannot be proven or reconstructed locally; do not bluff certainty.
- Generate deterministic artifacts under `artifacts/research/`, `artifacts/manifests/`, `artifacts/evals/`, and `artifacts/exports/`.
- Do not declare completion until artifact generation, counts, duplicate leakage checks, relevant backend tests, and browser parity QA pass.

---

## File Structure

### New files
- `docs/superpowers/plans/2026-06-20-test3-nidhi-personalized-manifest.md` — this implementation plan
- `scripts/build_nidhi_test3_inputs.py` — freezes prior-exam inventory and exclusion/weakness input artifacts
- `scripts/generate_nidhi_test3_manifest.py` — deterministic Nidhi-specific selector and artifact writer
- `scripts/export_test3_pdf.py` — TEST 3 PDF/HTML export using a manifest slug or explicit path
- `artifacts/research/nidhi_test3_taken_exam_inventory.json` — explicit inventory of prior Nidhi exam sets used for exclusion
- `artifacts/research/nidhi_test3_exclusion_set.json` — stable set of excluded question IDs and concept fingerprints
- `artifacts/research/nidhi_test3_weakness_profile.json` — weighted topic/system/difficulty profile derived from Nidhi’s prior performance
- `artifacts/research/nidhi_test3_decision-log.jsonl` — ambiguity and fallback log
- `artifacts/manifests/test3_nidhi_v1.json` — frozen deterministic manifest
- `artifacts/manifests/test3_nidhi_v1.coverage_report.json` — coverage and rationale report
- `artifacts/manifests/test3_nidhi_v1.explanations.json` — optional human-facing rationale payload for each slot
- `artifacts/evals/test3_nidhi_v1.json` — machine-readable eval results
- `artifacts/evals/test3_nidhi_v1.md` — human-readable eval summary
- `artifacts/exports/test3_exam.json` — full exported exam payload used by the app/PDF
- `artifacts/exports/test3_nidhi_v1_with_answers.html` — printable answer-key HTML
- `artifacts/exports/test3_nidhi_v1_with_answers.pdf` — printable answer-key PDF

### Existing files to modify
- `vercel/uworld-api-deploy/nbme120.py` — add `generate_test3()` backed by the frozen manifest
- `vercel/uworld-api-deploy/index.py` — add TEST 3 API route and history/resume/review support
- `vercel/uworld-api-deploy/tests/test_api_contract.py` — extend named-exam contract coverage
- `vercel/uworld-frontend/createtest.html` — add TEST 3 launch affordance
- `vercel/uworld-frontend/qbank.html` — support `exam=test3` parity with TEST 1/2 behavior

### Existing files to read for ground truth
- `artifacts/exports/test1_exam.json`
- `artifacts/exports/test2_exam.json`
- `artifacts/exports/nbme120_official_sample_exam.json`
- `artifacts/evals/session45_independent_adjudication.md`
- `artifacts/evals/session45_answer_audit.json`
- `scripts/generate_june2026_120_candidate.py`
- `scripts/repair_test2_blueprint.py`
- `scripts/export_june2026_120_pdf.py`
- `vercel/uworld-api-deploy/gold_runtime.json`
- `vercel/uworld-api-deploy/qbank_index.json`

---

### Task 1: Freeze Nidhi’s prior-exam inventory and exclusion set

**Files:**
- Create: `scripts/build_nidhi_test3_inputs.py`
- Create: `artifacts/research/nidhi_test3_taken_exam_inventory.json`
- Create: `artifacts/research/nidhi_test3_exclusion_set.json`
- Create: `artifacts/research/nidhi_test3_decision-log.jsonl`
- Test: `vercel/uworld-api-deploy/tests/test_api_contract.py`

**Interfaces:**
- Consumes: `artifacts/exports/test1_exam.json`, `artifacts/exports/test2_exam.json`, `artifacts/exports/nbme120_official_sample_exam.json`, repo evidence for `session23_official_nbme120` and `session24_nbme120_simulation`
- Produces:
  - `build_inputs() -> dict`
  - `write_taken_exam_inventory(out_path: Path) -> None`
  - `write_exclusion_set(out_path: Path) -> None`

- [ ] **Step 1: Write a failing contract assertion for TEST 3 input artifacts**

```python
self.assertTrue((ROOT / "artifacts" / "research" / "nidhi_test3_exclusion_set.json").exists())
```

- [ ] **Step 2: Run the contract test to verify it fails**

Run: `python3 -m unittest tests.test_api_contract -v`
Expected: FAIL because the exclusion artifact does not exist yet.

- [ ] **Step 3: Implement `scripts/build_nidhi_test3_inputs.py`**

The script must:

```python
#!/usr/bin/env python3
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def collect_exam_ids(export_path: Path) -> list[str]:
    payload = json.loads(export_path.read_text())
    return [qid for block in payload["blocks"] for qid in block["questionIds"]]


def main() -> None:
    test1_ids = collect_exam_ids(ROOT / "artifacts" / "exports" / "test1_exam.json")
    test2_ids = collect_exam_ids(ROOT / "artifacts" / "exports" / "test2_exam.json")
    official_ids = collect_exam_ids(ROOT / "artifacts" / "exports" / "nbme120_official_sample_exam.json")
    exclusion_ids = sorted(set(test1_ids) | set(test2_ids) | set(official_ids))
    payload = {
        "user": "nidhitiyyagura@gmail.com",
        "examSets": [
            {"slug": "test1", "questionCount": len(test1_ids), "source": "artifacts/exports/test1_exam.json"},
            {"slug": "test2", "questionCount": len(test2_ids), "source": "artifacts/exports/test2_exam.json"},
            {"slug": "nbme120_official", "questionCount": len(official_ids), "source": "artifacts/exports/nbme120_official_sample_exam.json"},
        ],
        "excludedQuestionIds": exclusion_ids,
    }
    out = ROOT / "artifacts" / "research" / "nidhi_test3_exclusion_set.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
```

- [ ] **Step 4: Add fail-closed ambiguity handling**

The script must also emit `nidhi_test3_taken_exam_inventory.json` and refuse to proceed if the inferred three-set inventory cannot be expressed with evidence fields:

```python
{
  "slug": "nbme120_official",
  "evidence": ["artifacts/exports/nbme120_official_sample_exam.json", "artifacts/exports/test2_exam.json.exam.excludedTakenForms"],
  "confidence": "medium",
  "status": "repo-local surrogate until live session inventory is available"
}
```

- [ ] **Step 5: Run the input builder**

Run: `python3 scripts/build_nidhi_test3_inputs.py`
Expected: research artifacts written with explicit evidence and any unresolved ambiguity logged.

- [ ] **Step 6: Re-run the contract test**

Run: `python3 -m unittest tests.test_api_contract -v`
Expected: the new existence assertions pass.

- [ ] **Step 7: Commit**

```bash
git add scripts/build_nidhi_test3_inputs.py artifacts/research/nidhi_test3_taken_exam_inventory.json artifacts/research/nidhi_test3_exclusion_set.json artifacts/research/nidhi_test3_decision-log.jsonl vercel/uworld-api-deploy/tests/test_api_contract.py
git commit -m "feat: freeze nidhi test3 exclusion inputs"
```

---

### Task 2: Derive Nidhi’s weakness profile

**Files:**
- Modify/Create: `scripts/build_nidhi_test3_inputs.py`
- Create: `artifacts/research/nidhi_test3_weakness_profile.json`
- Test: `vercel/uworld-api-deploy/tests/test_api_contract.py`

**Interfaces:**
- Consumes: `artifacts/evals/session45_independent_adjudication.md`, `artifacts/evals/session45_answer_audit.json`, review summary dimensions already surfaced by backend
- Produces: `derive_weakness_profile() -> dict`

- [ ] **Step 1: Add a failing assertion for the weakness profile artifact**

```python
self.assertTrue((ROOT / "artifacts" / "research" / "nidhi_test3_weakness_profile.json").exists())
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_api_contract -v`
Expected: FAIL because the weakness artifact does not exist yet.

- [ ] **Step 3: Implement weakness extraction**

The script must summarize known misses into weighted targets, for example:

```python
{
  "user": "nidhitiyyagura@gmail.com",
  "sourceSessions": ["session45:test2"],
  "weights": {
    "systems": {"Behavioral/Nervous & Special Senses": 1.25, "MSK/Skin": 1.15},
    "disciplines": {"Gross Anatomy/Embryology": 1.2, "Pathology": 1.15},
    "difficulty": {"easy": 1.0, "medium": 1.1, "hard": 1.15}
  },
  "weakQuestionIds": ["nbme28_q0016", "nbme27_page-14"],
  "notes": ["Bound weakness weighting to avoid breaking NBME-like blueprint parity"]
}
```

- [ ] **Step 4: Run the builder again**

Run: `python3 scripts/build_nidhi_test3_inputs.py`
Expected: `artifacts/research/nidhi_test3_weakness_profile.json` exists and is deterministic.

- [ ] **Step 5: Re-run the test**

Run: `python3 -m unittest tests.test_api_contract -v`
Expected: PASS for the weakness-profile existence assertion.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_nidhi_test3_inputs.py artifacts/research/nidhi_test3_weakness_profile.json vercel/uworld-api-deploy/tests/test_api_contract.py
git commit -m "feat: derive nidhi test3 weakness profile"
```

---

### Task 3: Generate deterministic `test3_nidhi_v1` manifest and exported exam

**Files:**
- Create: `scripts/generate_nidhi_test3_manifest.py`
- Create: `artifacts/manifests/test3_nidhi_v1.json`
- Create: `artifacts/manifests/test3_nidhi_v1.coverage_report.json`
- Create: `artifacts/manifests/test3_nidhi_v1.explanations.json`
- Create: `artifacts/evals/test3_nidhi_v1.json`
- Create: `artifacts/evals/test3_nidhi_v1.md`
- Create: `artifacts/exports/test3_exam.json`
- Test: `vercel/uworld-api-deploy/tests/test_api_contract.py`

**Interfaces:**
- Consumes: `gold_runtime.json`, `qbank_index.json`, exclusion set, weakness profile
- Produces: `build_test3_manifest() -> dict`, `export_test3_exam() -> dict`

- [ ] **Step 1: Add failing contract checks for the frozen manifest**

```python
payload = json.loads((ROOT / "artifacts" / "manifests" / "test3_nidhi_v1.json").read_text())
self.assertEqual(payload["exam_slug"], "test3_nidhi_v1")
self.assertEqual(payload["block_sizes"], [20, 20, 20, 20, 20, 20])
```

- [ ] **Step 2: Run the contract test to verify it fails**

Run: `python3 -m unittest tests.test_api_contract -v`
Expected: FAIL because the manifest does not exist yet.

- [ ] **Step 3: Implement deterministic selection**

Base the selector on `scripts/generate_june2026_120_candidate.py`, but add:
- hard `question_id` exclusion from `nidhi_test3_exclusion_set.json`
- hard `concept_fingerprint` exclusion where available
- bounded weakness weighting from `nidhi_test3_weakness_profile.json`
- system/difficulty/image targets that preserve NBME-like structure
- deterministic tiebreakers on `id`
- decision-log entries for every fallback

- [ ] **Step 4: Write coverage/eval/export artifacts**

The generator must emit, at minimum:

```python
{
  "exam_slug": "test3_nidhi_v1",
  "title": "TEST 3 — Nidhi Personalized NBME-Style Reconstruction",
  "strategy": "deterministic_fixed_manifest",
  "source_forms": ["NBME 27", "NBME 28", "NBME 29", "Form 30", "Form 31"],
  "total_questions": 120,
  "block_sizes": [20, 20, 20, 20, 20, 20]
}
```

- [ ] **Step 5: Run the generator**

Run: `python3 scripts/generate_nidhi_test3_manifest.py`
Expected: manifest, coverage report, explanations, eval, and exported exam written successfully.

- [ ] **Step 6: Add deterministic rebuild check**

Run:

```bash
python3 scripts/generate_nidhi_test3_manifest.py
python3 scripts/generate_nidhi_test3_manifest.py
```

Expected: second run produces byte-for-byte identical core artifacts.

- [ ] **Step 7: Re-run the contract test**

Run: `python3 -m unittest tests.test_api_contract -v`
Expected: PASS for TEST 3 manifest structure assertions.

- [ ] **Step 8: Commit**

```bash
git add scripts/generate_nidhi_test3_manifest.py artifacts/manifests/test3_nidhi_v1.json artifacts/manifests/test3_nidhi_v1.coverage_report.json artifacts/manifests/test3_nidhi_v1.explanations.json artifacts/evals/test3_nidhi_v1.json artifacts/evals/test3_nidhi_v1.md artifacts/exports/test3_exam.json vercel/uworld-api-deploy/tests/test_api_contract.py
git commit -m "feat: freeze deterministic nidhi test3 manifest"
```

---

### Task 4: Wire backend TEST 3 generation and resume/history behavior

**Files:**
- Modify: `vercel/uworld-api-deploy/nbme120.py`
- Modify: `vercel/uworld-api-deploy/index.py`
- Modify: `vercel/uworld-api-deploy/tests/test_api_contract.py`

**Interfaces:**
- Consumes: `artifacts/manifests/test3_nidhi_v1.json`, `artifacts/exports/test3_exam.json`
- Produces: `generate_test3()`, `/api/qbank/generate-test3`

- [ ] **Step 1: Write a failing API contract test**

```python
response = self.client.get("/api/qbank/generate-test3")
self.assertEqual(response.status_code, 200)
self.assertEqual(response.get_json()["exam"]["slug"], "test3")
```

- [ ] **Step 2: Run the API contract test to verify it fails**

Run: `python3 -m unittest tests.test_api_contract -v`
Expected: FAIL because TEST 3 is not yet routed.

- [ ] **Step 3: Implement backend support**

Add a generator mirroring existing named-exam behavior:

```python
def generate_test3():
    return _load_frozen_exam_export("artifacts/exports/test3_exam.json", slug="test3")
```

And add route/history/resume handling in `index.py` for `test3` wherever `test1` and `test2` are treated specially.

- [ ] **Step 4: Re-run the API contract test**

Run: `python3 -m unittest tests.test_api_contract -v`
Expected: PASS for the TEST 3 generation route.

- [ ] **Step 5: Commit**

```bash
git add vercel/uworld-api-deploy/nbme120.py vercel/uworld-api-deploy/index.py vercel/uworld-api-deploy/tests/test_api_contract.py
git commit -m "feat: add backend test3 named exam support"
```

---

### Task 5: Wire frontend TEST 3 launch and parity review behavior

**Files:**
- Modify: `vercel/uworld-frontend/createtest.html`
- Modify: `vercel/uworld-frontend/qbank.html`

**Interfaces:**
- Consumes: `/api/qbank/generate-test3`, URL param `exam=test3`
- Produces: `startTest3()` UI flow

- [ ] **Step 1: Add a TODO-level UI smoke target in the plan implementation notes**

The frontend change must mirror TEST 1/2 launch behavior and suppress intermediate score display until exam completion.

- [ ] **Step 2: Implement the TEST 3 launch affordance**

Add a `TEST 3` button/action to `createtest.html` and a `startTest3()` method that requests `/api/qbank/generate-test3`.

- [ ] **Step 3: Implement `exam=test3` parity**

Update `qbank.html` so any logic that currently special-cases `test1` and `test2` includes `test3` for:
- history/resume labels
- block-mode handling
- suppression of intermediate score displays
- end-of-exam review labeling

- [ ] **Step 4: Manually verify the frontend path locally**

Run the local app flow and confirm TEST 3 can be started and resumed with stable ordering.

- [ ] **Step 5: Commit**

```bash
git add vercel/uworld-frontend/createtest.html vercel/uworld-frontend/qbank.html
git commit -m "feat: add frontend test3 launch flow"
```

---

### Task 6: Export sample TEST 3 PDF

**Files:**
- Create: `scripts/export_test3_pdf.py`
- Create: `artifacts/exports/test3_nidhi_v1_with_answers.html`
- Create: `artifacts/exports/test3_nidhi_v1_with_answers.pdf`

**Interfaces:**
- Consumes: `artifacts/manifests/test3_nidhi_v1.json`, `gold_runtime.json`
- Produces: HTML and PDF export files

- [ ] **Step 1: Implement a generalized exporter**

Base this script on `scripts/export_june2026_120_pdf.py`, but parameterize:
- manifest path or slug
- export title
- HTML output path
- PDF output path

- [ ] **Step 2: Run the exporter**

Run:

```bash
python3 scripts/export_test3_pdf.py \
  --manifest artifacts/manifests/test3_nidhi_v1.json \
  --title "TEST 3 — Nidhi Personalized NBME-Style Reconstruction" \
  --html artifacts/exports/test3_nidhi_v1_with_answers.html \
  --pdf artifacts/exports/test3_nidhi_v1_with_answers.pdf
```

Expected: HTML and PDF written successfully.

- [ ] **Step 3: Spot-check export counts**

Confirm the PDF/HTML cover indicates 120 questions and 6 blocks.

- [ ] **Step 4: Commit**

```bash
git add scripts/export_test3_pdf.py artifacts/exports/test3_nidhi_v1_with_answers.html artifacts/exports/test3_nidhi_v1_with_answers.pdf
git commit -m "feat: export nidhi test3 sample pdf"
```

---

### Task 7: Run verification gates and parity QA

**Files:**
- Modify if needed: any files required to fix issues found by tests or parity checks
- Create/update: `artifacts/evals/test3_nidhi_v1.json`, `artifacts/evals/test3_nidhi_v1.md`

**Interfaces:**
- Consumes: all prior artifacts and app wiring
- Produces: verified final status

- [ ] **Step 1: Run targeted contract tests**

Run from `vercel/uworld-api-deploy/`:

```bash
python3 -m unittest tests.test_api_contract -v
python3 -m unittest tests.test_nbme120_contract -v
python3 -m unittest tests.test_image_manifest_contract -v
```

Expected: PASS.

- [ ] **Step 2: Run deterministic artifact sanity checks**

Confirm:
- 120 unique question IDs
- 6 blocks of 20
- zero overlap with `excludedQuestionIds`
- zero overlap with excluded `concept_fingerprint` values unless explicitly justified

- [ ] **Step 3: Run browser parity QA**

Verify:
- fresh TEST 3 launch
- resume TEST 3 session
- block transitions
- review rendering
- image/table assets resolve

- [ ] **Step 4: Update final eval artifacts**

Record counts, parity results, duplicate leakage status, and any justified exceptions in:
- `artifacts/evals/test3_nidhi_v1.json`
- `artifacts/evals/test3_nidhi_v1.md`

- [ ] **Step 5: Commit**

```bash
git add artifacts/evals/test3_nidhi_v1.json artifacts/evals/test3_nidhi_v1.md
git commit -m "test: verify nidhi test3 parity and contracts"
```

---

## Self-Review

### Spec coverage
- Personalized Nidhi-only exam: covered by Tasks 1–3.
- No repeats across prior taken sets: covered by Task 1 exclusion inventory and Task 3 hard exclusion logic.
- NBME-like structure and formatting: covered by Task 3 selector constraints, Task 4 backend wiring, Task 5 frontend parity, and Task 6 PDF export.
- Deterministic frozen manifest: covered by Task 3.
- PDF sample as soon as ready: covered by Task 6.
- Verification and parity gates: covered by Task 7.

### Placeholder scan
- No `TODO`, `TBD`, or vague “handle appropriately” placeholders remain.
- Open uncertainty is explicit: the third exam set must be evidenced or logged as repo-local surrogate; the plan does not fake certainty.

### Type consistency
- Core outputs are consistently named: `test3_nidhi_v1`, `nidhi_test3_exclusion_set.json`, `nidhi_test3_weakness_profile.json`, `test3_exam.json`.
- Backend slug remains `test3`; frozen manifest slug remains `test3_nidhi_v1`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-20-test3-nidhi-personalized-manifest.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
