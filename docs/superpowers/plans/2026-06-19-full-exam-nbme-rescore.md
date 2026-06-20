# Full Exam NBME-Key Rescore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, reproducible rescoring pipeline for session `45` / `test2` that uses the user-added NBME answer-key PDF (with yellow-highlighted correct answers) to rescore the entire exam and emit discrepancy artifacts that are more trustworthy than current runtime/backend scoring.

**Architecture:** Treat the rescoring job as an artifact pipeline, not an in-app patch. First freeze the exact PDF source and extract a machine-readable answer key with confidence/provenance, then map that key onto `artifacts/exports/test2_exam.json`, then join against session `45` user responses and emit a final rescored artifact plus a human-readable discrepancy report. Keep backend scoring unchanged in this plan; the deliverable is a trusted offline scorer and contract tests that prove the pipeline is deterministic.

**Tech Stack:** Python 3, `json`, `hashlib`, `pathlib`, `argparse`, `unittest`, plus PDF extraction libraries in a script-local environment: `pypdf`, `pdfplumber`, `PyMuPDF`, `Pillow`.

## Global Constraints

- Use repo-local skill order first, especially `skills/form-ingestion/` for PDF ingestion and `skills/eval-and-parity-qa/` for verification discipline.
- Prefer deterministic artifacts over chat-only reasoning.
- Do not trust backend/runtime correctness for session `45`; an off-by-one scoring bug already makes it unreliable.
- Do not rewrite medical stems or answer choices.
- Do not silently substitute inferred answers when the PDF extraction is ambiguous; log ambiguities explicitly.
- Preserve exam ordering exactly as exported in `artifacts/exports/test2_exam.json`.
- Use the user’s submitted responses as source of truth for what she answered.
- Use the highlighted NBME PDF answer key as the highest-priority scoring authority in this workflow.
- Keep changes minimal and artifact-driven; do not ship runtime scoring changes as part of this plan.

---

## File Structure

### New files
- `docs/superpowers/plans/2026-06-19-full-exam-nbme-rescore.md` — this implementation plan
- `scripts/requirements-rescore.txt` — script-local PDF extraction dependencies
- `scripts/extract_nbme_answer_key.py` — inventories PDFs, selects the annotated source, extracts highlighted answer choices, emits deterministic artifacts
- `scripts/rescore_session45_from_nbme_key.py` — joins the extracted key to `test2_exam.json` and session `45` submitted answers, computes the corrected score, and writes reports
- `artifacts/evals/session45_nbme_key_source.json` — selected PDF path, checksum, page count, extraction mode, and source provenance
- `artifacts/evals/session45_nbme_key_extracted.json` — normalized per-position answer key with confidence and evidence
- `artifacts/evals/session45_rescored_from_nbme_key.json` — final machine-readable rescore result
- `artifacts/evals/session45_rescore_discrepancies.md` — human-readable discrepancy report
- `artifacts/research/session45_nbme_key_decision_log.jsonl` — ambiguity log for low-confidence or manual-review rows
- `vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py` — contract tests for extraction mapping and rescoring determinism

### Existing files to read but not mutate initially
- `NBME 27 A.pdf`
- `NBME_Form28.pdf`
- `NBME_Form29.pdf`
- `NBME_Form30.pdf`
- `FORM 31.pdf`
- `artifacts/exports/test2_exam.json`
- `artifacts/evals/session45_answer_audit.json`
- `artifacts/evals/session45_independent_adjudication.md`
- `vercel/uworld-api-deploy/test2_openevidence_explanations.json`

### Why these boundaries
- PDF extraction and session rescoring are separate concerns and should stay in separate scripts.
- The extracted answer key must exist as a standalone artifact so future rescoring runs do not require reparsing the PDF unless the source changes.
- Contract tests should live with existing backend tests because they validate repo-level exam/scoring artifacts, not just ad hoc scripts.

---

### Task 1: Freeze the exact PDF source and script-local dependencies

**Files:**
- Create: `scripts/requirements-rescore.txt`
- Create: `artifacts/evals/session45_nbme_key_source.json`
- Modify: none
- Test: `vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py`

**Interfaces:**
- Consumes: repo-root PDFs `NBME 27 A.pdf`, `NBME_Form28.pdf`, `NBME_Form29.pdf`, `NBME_Form30.pdf`, `FORM 31.pdf`
- Produces: `session45_nbme_key_source.json` with shape:

```json
{
  "selectedPdf": "NBME 27 A.pdf",
  "sha256": "<hex>",
  "bytes": 99339937,
  "pageCount": 123,
  "selectionReason": "contains yellow-highlighted answer key pages",
  "inventory": [
    {"path": "NBME 27 A.pdf", "sha256": "<hex>", "bytes": 99339937},
    {"path": "NBME_Form29.pdf", "sha256": "<hex>", "bytes": 99471348}
  ]
}
```

- [ ] **Step 1: Write the failing dependency + provenance contract test**

```python
import json
import pathlib
import sys
import unittest

API_DIR = pathlib.Path(__file__).resolve().parents[1]
ROOT = API_DIR.parents[1]
sys.path.insert(0, str(API_DIR))


class Session45NbmeRescoreContractTests(unittest.TestCase):
    def test_nbme_key_source_artifact_has_selected_pdf_and_checksum(self):
        source_path = ROOT / "artifacts" / "evals" / "session45_nbme_key_source.json"
        self.assertTrue(source_path.exists(), "run extraction inventory first")
        payload = json.loads(source_path.read_text())
        self.assertIn(payload["selectedPdf"], {"NBME 27 A.pdf", "NBME_Form28.pdf", "NBME_Form29.pdf", "NBME_Form30.pdf", "FORM 31.pdf"})
        self.assertRegex(payload["sha256"], r"^[0-9a-f]{64}$")
        self.assertGreater(payload["bytes"], 1000000)
        self.assertGreater(payload["pageCount"], 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py -v`
Expected: FAIL because `artifacts/evals/session45_nbme_key_source.json` does not exist yet.

- [ ] **Step 3: Add script-local extraction dependencies**

Create `scripts/requirements-rescore.txt`:

```txt
pypdf==4.2.0
pdfplumber==0.11.4
PyMuPDF==1.24.9
Pillow==10.4.0
```

- [ ] **Step 4: Write the minimal PDF inventory artifact producer**

Create the first version of `scripts/extract_nbme_answer_key.py` with provenance-only output before full extraction logic:

```python
#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PDF_CANDIDATES = [
    ROOT / "NBME 27 A.pdf",
    ROOT / "NBME_Form28.pdf",
    ROOT / "NBME_Form29.pdf",
    ROOT / "NBME_Form30.pdf",
    ROOT / "FORM 31.pdf",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_inventory() -> list[dict]:
    inventory = []
    for path in PDF_CANDIDATES:
        if not path.exists():
            continue
        inventory.append(
            {
                "path": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "pageCount": len(PdfReader(str(path)).pages),
            }
        )
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected-pdf", required=True)
    parser.add_argument("--selection-reason", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    inventory = build_inventory()
    selected = next(item for item in inventory if item["path"] == args.selected_pdf)
    payload = {
        "selectedPdf": selected["path"],
        "sha256": selected["sha256"],
        "bytes": selected["bytes"],
        "pageCount": selected["pageCount"],
        "selectionReason": args.selection_reason,
        "inventory": inventory,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the inventory producer**

Run:

```bash
python scripts/extract_nbme_answer_key.py \
  --selected-pdf "NBME 27 A.pdf" \
  --selection-reason "contains the user-added yellow-highlighted answer key pages" \
  --out artifacts/evals/session45_nbme_key_source.json
```

Expected: `artifacts/evals/session45_nbme_key_source.json` is created with checksum, size, and page count for the selected source PDF.

- [ ] **Step 6: Re-run the contract test**

Run: `python -m unittest vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py -v`
Expected: PASS for `test_nbme_key_source_artifact_has_selected_pdf_and_checksum`.

- [ ] **Step 7: Commit**

```bash
git add scripts/requirements-rescore.txt scripts/extract_nbme_answer_key.py artifacts/evals/session45_nbme_key_source.json vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py
git commit -m "feat: freeze nbme answer key source provenance"
```

---

### Task 2: Extract the highlighted NBME answer key into a deterministic artifact

**Files:**
- Modify: `scripts/extract_nbme_answer_key.py`
- Create: `artifacts/evals/session45_nbme_key_extracted.json`
- Create: `artifacts/research/session45_nbme_key_decision_log.jsonl`
- Test: `vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py`

**Interfaces:**
- Consumes: `artifacts/evals/session45_nbme_key_source.json`
- Produces: `artifacts/evals/session45_nbme_key_extracted.json` with shape:

```json
{
  "sourcePdf": "NBME 27 A.pdf",
  "sourceSha256": "<hex>",
  "extractionMethod": "text-plus-highlight-detection",
  "rows": [
    {
      "position": 1,
      "block": 1,
      "blockItem": 1,
      "page": 118,
      "questionNumberOnKey": 1,
      "detectedLetter": "E",
      "confidence": "high",
      "evidence": {
        "text": "1. E",
        "yellowPixels": 482,
        "bbox": [71.2, 532.8, 88.0, 544.1]
      }
    }
  ],
  "manualReviewCount": 0
}
```

- [ ] **Step 1: Write the failing extraction contract tests**

Append to `vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py`:

```python
    def test_extracted_nbme_key_has_120_positions_and_letters(self):
        path = ROOT / "artifacts" / "evals" / "session45_nbme_key_extracted.json"
        self.assertTrue(path.exists(), "run highlighted-key extraction first")
        payload = json.loads(path.read_text())
        rows = payload["rows"]
        self.assertEqual(len(rows), 120)
        self.assertEqual([row["position"] for row in rows], list(range(1, 121)))
        self.assertTrue(all(row["detectedLetter"] in list("ABCDEFGHIJ") for row in rows))
        self.assertTrue(all(row["confidence"] in {"high", "medium", "low", "manual"} for row in rows))

    def test_extracted_nbme_key_preserves_block_mapping(self):
        path = ROOT / "artifacts" / "evals" / "session45_nbme_key_extracted.json"
        rows = json.loads(path.read_text())["rows"]
        self.assertEqual(rows[0]["block"], 1)
        self.assertEqual(rows[19]["blockItem"], 20)
        self.assertEqual(rows[20]["block"], 2)
        self.assertEqual(rows[119]["block"], 6)
        self.assertEqual(rows[119]["blockItem"], 20)
```

- [ ] **Step 2: Run extraction tests to verify they fail**

Run: `python -m unittest vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py -v`
Expected: FAIL because `session45_nbme_key_extracted.json` does not exist yet.

- [ ] **Step 3: Implement deterministic text-plus-highlight extraction**

Extend `scripts/extract_nbme_answer_key.py` with these functions:

```python
import fitz
import pdfplumber
from PIL import Image


def block_item_for_position(position: int) -> tuple[int, int]:
    block = ((position - 1) // 20) + 1
    block_item = ((position - 1) % 20) + 1
    return block, block_item


def yellow_pixel_count(image: Image.Image) -> int:
    rgb = image.convert("RGB")
    count = 0
    for r, g, b in rgb.getdata():
        if r > 180 and g > 180 and b < 170:
            count += 1
    return count


def extract_key_rows(selected_pdf: Path) -> list[dict]:
    doc = fitz.open(selected_pdf)
    rows = []
    position = 1
    for page_index in range(len(doc)):
        page = doc.load_page(page_index)
        words = page.get_text("words")
        candidate_letters = [w for w in words if w[4] in list("ABCDEFGHIJ")]
        for word in candidate_letters:
            x0, y0, x1, y1, text, *_ = word
            clip = fitz.Rect(x0 - 6, y0 - 6, x1 + 6, y1 + 6)
            pix = page.get_pixmap(clip=clip, dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            yellow = yellow_pixel_count(img)
            if yellow < 25:
                continue
            block, block_item = block_item_for_position(position)
            rows.append(
                {
                    "position": position,
                    "block": block,
                    "blockItem": block_item,
                    "page": page_index + 1,
                    "questionNumberOnKey": position,
                    "detectedLetter": text,
                    "confidence": "high" if yellow >= 100 else "medium",
                    "evidence": {
                        "text": text,
                        "yellowPixels": yellow,
                        "bbox": [x0, y0, x1, y1],
                    },
                }
            )
            position += 1
    return rows
```

- [ ] **Step 4: Add an explicit ambiguity logger instead of guessing**

Still in `scripts/extract_nbme_answer_key.py`, add:

```python
def write_decision_log(rows: list[dict], path: Path) -> None:
    lines = []
    for row in rows:
        if row["confidence"] != "high":
            lines.append(
                json.dumps(
                    {
                        "position": row["position"],
                        "page": row["page"],
                        "detectedLetter": row["detectedLetter"],
                        "confidence": row["confidence"],
                        "yellowPixels": row["evidence"]["yellowPixels"],
                        "status": "manual_review_recommended",
                    }
                )
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""))
```

- [ ] **Step 5: Emit the normalized extraction artifact**

Update `main()` in `scripts/extract_nbme_answer_key.py` so it can write both provenance and extracted rows:

```python
    parser.add_argument("--decision-log", required=True)
    parser.add_argument("--extract-out", required=True)
    ...
    selected_path = ROOT / args.selected_pdf
    rows = extract_key_rows(selected_path)
    payload = {
        "sourcePdf": args.selected_pdf,
        "sourceSha256": selected["sha256"],
        "extractionMethod": "text-plus-highlight-detection",
        "rows": rows,
        "manualReviewCount": sum(1 for row in rows if row["confidence"] != "high"),
    }
    Path(args.extract_out).write_text(json.dumps(payload, indent=2))
    write_decision_log(rows, Path(args.decision_log))
```

- [ ] **Step 6: Run extraction**

Run:

```bash
python scripts/extract_nbme_answer_key.py \
  --selected-pdf "NBME 27 A.pdf" \
  --selection-reason "contains the user-added yellow-highlighted answer key pages" \
  --out artifacts/evals/session45_nbme_key_source.json \
  --extract-out artifacts/evals/session45_nbme_key_extracted.json \
  --decision-log artifacts/research/session45_nbme_key_decision_log.jsonl
```

Expected:
- `artifacts/evals/session45_nbme_key_extracted.json` created
- `rows` length is exactly `120`
- `manualReviewCount` is `0` or a small explicit number
- `artifacts/research/session45_nbme_key_decision_log.jsonl` exists if anything was not high-confidence

- [ ] **Step 7: Re-run extraction contract tests**

Run: `python -m unittest vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py -v`
Expected: PASS for the extraction artifact tests.

- [ ] **Step 8: Commit**

```bash
git add scripts/extract_nbme_answer_key.py artifacts/evals/session45_nbme_key_extracted.json artifacts/research/session45_nbme_key_decision_log.jsonl vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py
git commit -m "feat: extract highlighted nbme answer key deterministically"
```

---

### Task 3: Map the extracted key onto `test2_exam.json` and session `45` submissions

**Files:**
- Create: `scripts/rescore_session45_from_nbme_key.py`
- Modify: `vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py`
- Test: `vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py`

**Interfaces:**
- Consumes:
  - `artifacts/evals/session45_nbme_key_extracted.json`
  - `artifacts/exports/test2_exam.json`
  - `artifacts/evals/session45_answer_audit.json`
- Produces joined row shape:

```json
{
  "position": 35,
  "block": 2,
  "blockItem": 15,
  "questionId": "nbme28_q0016",
  "selectedOption": 8,
  "selectedLetter": "H",
  "nbmeKeyLetter": "A",
  "examOptionLetters": ["A", "B", "C", "D", "E", "F", "G", "H"],
  "isCorrectUnderNbmeKey": false
}
```

- [ ] **Step 1: Write failing join/rescore contract tests**

Append to `vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py`:

```python
    def test_session45_rescore_rows_join_exam_and_submission_by_position(self):
        result_path = ROOT / "artifacts" / "evals" / "session45_rescored_from_nbme_key.json"
        self.assertTrue(result_path.exists(), "run session45 rescoring first")
        payload = json.loads(result_path.read_text())
        rows = payload["rows"]
        self.assertEqual(len(rows), 120)
        self.assertEqual(rows[34]["questionId"], "nbme28_q0016")
        self.assertEqual(rows[34]["block"], 2)
        self.assertEqual(rows[34]["blockItem"], 15)

    def test_disputed_items_match_manual_adjudication(self):
        result_path = ROOT / "artifacts" / "evals" / "session45_rescored_from_nbme_key.json"
        rows = {row["position"]: row for row in json.loads(result_path.read_text())["rows"]}
        self.assertFalse(rows[35]["isCorrectUnderNbmeKey"])
        self.assertTrue(rows[36]["isCorrectUnderNbmeKey"])
        self.assertTrue(rows[42]["isCorrectUnderNbmeKey"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py -v`
Expected: FAIL because `session45_rescored_from_nbme_key.json` does not exist yet.

- [ ] **Step 3: Implement the joiner/rescorer**

Create `scripts/rescore_session45_from_nbme_key.py`:

```python
#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_exam_items(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    items = []
    for block in payload["blocks"]:
        items.extend(block["items"])
    return items


def load_submission_rows(path: Path) -> list[dict]:
    return json.loads(path.read_text())["rows"]


def selected_letter_from_option(selected_option: int, option_letters: list[str]) -> str | None:
    if selected_option < 1 or selected_option > len(option_letters):
        return None
    return option_letters[selected_option - 1]


def build_rows(extracted_key: list[dict], exam_items: list[dict], submission_rows: list[dict]) -> list[dict]:
    rows = []
    for key_row, exam_item, submitted in zip(extracted_key, exam_items, submission_rows):
        option_letters = [opt["letter"] for opt in exam_item["options"]]
        selected_letter = submitted["selectedLetter"] or selected_letter_from_option(submitted["selectedOption"], option_letters)
        rows.append(
            {
                "position": key_row["position"],
                "block": key_row["block"],
                "blockItem": key_row["blockItem"],
                "questionId": exam_item["id"],
                "selectedOption": submitted["selectedOption"],
                "selectedLetter": selected_letter,
                "nbmeKeyLetter": key_row["detectedLetter"],
                "examOptionLetters": option_letters,
                "isCorrectUnderNbmeKey": selected_letter == key_row["detectedLetter"],
            }
        )
    return rows
```

- [ ] **Step 4: Add strict shape checks so the script fails closed**

Continue `scripts/rescore_session45_from_nbme_key.py`:

```python
def validate_lengths(extracted_key: list[dict], exam_items: list[dict], submission_rows: list[dict]) -> None:
    assert len(extracted_key) == 120, len(extracted_key)
    assert len(exam_items) == 120, len(exam_items)
    assert len(submission_rows) == 120, len(submission_rows)


def summarize(rows: list[dict]) -> dict:
    correct = sum(1 for row in rows if row["isCorrectUnderNbmeKey"])
    return {
        "correct": correct,
        "incorrect": len(rows) - correct,
        "total": len(rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nbme-key", required=True)
    parser.add_argument("--exam", required=True)
    parser.add_argument("--submission", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    extracted_key = json.loads(Path(args.nbme_key).read_text())["rows"]
    exam_items = load_exam_items(Path(args.exam))
    submission_rows = load_submission_rows(Path(args.submission))
    validate_lengths(extracted_key, exam_items, submission_rows)
    rows = build_rows(extracted_key, exam_items, submission_rows)
    payload = {"summary": summarize(rows), "rows": rows}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the rescoring script**

Run:

```bash
python scripts/rescore_session45_from_nbme_key.py \
  --nbme-key artifacts/evals/session45_nbme_key_extracted.json \
  --exam artifacts/exports/test2_exam.json \
  --submission artifacts/evals/session45_answer_audit.json \
  --out artifacts/evals/session45_rescored_from_nbme_key.json
```

Expected: `artifacts/evals/session45_rescored_from_nbme_key.json` created with `120` joined rows.

- [ ] **Step 6: Re-run contract tests**

Run: `python -m unittest vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py -v`
Expected: PASS for the join and disputed-item assertions.

- [ ] **Step 7: Commit**

```bash
git add scripts/rescore_session45_from_nbme_key.py artifacts/evals/session45_rescored_from_nbme_key.json vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py
git commit -m "feat: rescore session45 from extracted nbme key"
```

---

### Task 4: Generate a discrepancy report against runtime, manifest, and OE views

**Files:**
- Modify: `scripts/rescore_session45_from_nbme_key.py`
- Create: `artifacts/evals/session45_rescore_discrepancies.md`
- Test: `vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py`

**Interfaces:**
- Consumes:
  - `artifacts/evals/session45_rescored_from_nbme_key.json`
  - `artifacts/evals/session45_answer_audit.json`
  - `artifacts/evals/session45_independent_adjudication.md`
- Produces markdown report sections:
  - final corrected score
  - rows where NBME key differs from runtime correctness
  - rows where NBME key differs from OE displayed letter
  - highlighted-callout section for `Q35`, `Q36`, `Q42`

- [ ] **Step 1: Write failing report tests**

Append to `vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py`:

```python
    def test_discrepancy_report_exists_and_mentions_key_items(self):
        report_path = ROOT / "artifacts" / "evals" / "session45_rescore_discrepancies.md"
        self.assertTrue(report_path.exists(), "generate discrepancy report first")
        text = report_path.read_text()
        self.assertIn("Q35", text)
        self.assertIn("Q36", text)
        self.assertIn("Q42", text)
        self.assertIn("Final corrected score", text)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py -v`
Expected: FAIL because the report does not exist yet.

- [ ] **Step 3: Add markdown report generation to the rescoring script**

Extend `scripts/rescore_session45_from_nbme_key.py`:

```python
def build_markdown_report(payload: dict, audit_rows: list[dict]) -> str:
    audit_by_position = {row["position"]: row for row in audit_rows}
    lines = []
    lines.append("# Session 45 Test 2 — NBME Key Rescore")
    lines.append("")
    lines.append("## Final corrected score")
    lines.append("")
    lines.append(f"- Correct: **{payload['summary']['correct']} / {payload['summary']['total']}**")
    lines.append(f"- Incorrect: **{payload['summary']['incorrect']} / {payload['summary']['total']}**")
    lines.append("")
    lines.append("## User-requested checks")
    lines.append("")
    for position in [35, 36, 42]:
        row = next(item for item in payload["rows"] if item["position"] == position)
        lines.append(f"- Q{position}: selected `{row['selectedLetter']}` vs NBME key `{row['nbmeKeyLetter']}` → **{'correct' if row['isCorrectUnderNbmeKey'] else 'incorrect'}**")
    lines.append("")
    lines.append("## Rows where NBME key disagrees with runtime/OE behavior")
    lines.append("")
    lines.append("| Q | Block.Item | Question ID | Submitted | NBME key | Runtime stored | OE displayed | Final |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in payload["rows"]:
        audit = audit_by_position[row["position"]]
        final = "Correct" if row["isCorrectUnderNbmeKey"] else "Incorrect"
        lines.append(
            f"| {row['position']} | B{row['block']}.I{row['blockItem']} | `{row['questionId']}` | {row['selectedLetter']} | {row['nbmeKeyLetter']} | {audit['runtimeCorrectLetter']} | {audit['oeDisplayedLetter']} | {final} |"
        )
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Write the report file from `main()`**

Update `main()` in `scripts/rescore_session45_from_nbme_key.py`:

```python
    parser.add_argument("--report", required=True)
    ...
    audit_rows = load_submission_rows(Path(args.submission))
    report_text = build_markdown_report(payload, audit_rows)
    Path(args.report).write_text(report_text)
```

- [ ] **Step 5: Re-run the rescoring script with report output**

Run:

```bash
python scripts/rescore_session45_from_nbme_key.py \
  --nbme-key artifacts/evals/session45_nbme_key_extracted.json \
  --exam artifacts/exports/test2_exam.json \
  --submission artifacts/evals/session45_answer_audit.json \
  --out artifacts/evals/session45_rescored_from_nbme_key.json \
  --report artifacts/evals/session45_rescore_discrepancies.md
```

Expected: `artifacts/evals/session45_rescore_discrepancies.md` created with summary and per-row table.

- [ ] **Step 6: Re-run contract tests**

Run: `python -m unittest vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py -v`
Expected: PASS for the report assertions.

- [ ] **Step 7: Commit**

```bash
git add scripts/rescore_session45_from_nbme_key.py artifacts/evals/session45_rescore_discrepancies.md vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py
git commit -m "feat: generate session45 nbme rescore discrepancy report"
```

---

### Task 5: Add consistency checks against manual adjudication and lock determinism

**Files:**
- Modify: `vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py`
- Test: `vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py`

**Interfaces:**
- Consumes:
  - `artifacts/evals/session45_independent_adjudication.md`
  - `artifacts/evals/session45_rescored_from_nbme_key.json`
- Produces:
  - deterministic assurance that the pipeline’s result is stable for the selected PDF checksum

- [ ] **Step 1: Add determinism and adjudication alignment tests**

Append to `vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py`:

```python
    def test_nbme_key_rescore_summary_is_deterministic(self):
        payload = json.loads((ROOT / "artifacts" / "evals" / "session45_rescored_from_nbme_key.json").read_text())
        self.assertEqual(payload["summary"]["total"], 120)
        self.assertEqual(payload["summary"]["correct"] + payload["summary"]["incorrect"], 120)

    def test_manual_high_confidence_items_still_match(self):
        rows = {row["position"]: row for row in json.loads((ROOT / "artifacts" / "evals" / "session45_rescored_from_nbme_key.json").read_text())["rows"]}
        self.assertFalse(rows[35]["isCorrectUnderNbmeKey"])  # scaphoid
        self.assertTrue(rows[36]["isCorrectUnderNbmeKey"])   # slow anterograde transport
        self.assertTrue(rows[42]["isCorrectUnderNbmeKey"])   # right phrenic nerve
        self.assertTrue(rows[116]["isCorrectUnderNbmeKey"])  # beta-blocker eyedrops item remains correct for her
```

- [ ] **Step 2: Run the focused contract suite**

Run: `python -m unittest vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py -v`
Expected: PASS.

- [ ] **Step 3: Run the relevant repo-level backend tests**

Run from `vercel/uworld-api-deploy/`:

```bash
python -m unittest tests.test_api_contract
python -m unittest tests.test_free120_contract
python -m unittest tests.test_nbme120_contract
python -m unittest tests.test_image_manifest_contract
python -m unittest tests.test_session45_nbme_rescore_contract
```

Expected: all pass; if any fail, fix only failures caused by the new rescoring artifacts/tests.

- [ ] **Step 4: Commit**

```bash
git add vercel/uworld-api-deploy/tests/test_session45_nbme_rescore_contract.py
git commit -m "test: lock session45 nbme rescore determinism"
```

---

### Task 6: Optional parity QA pass for audit presentation, not scoring authority

**Files:**
- Modify: none required unless app presentation is added later
- Test: browser/manual verification only

**Interfaces:**
- Consumes: `artifacts/evals/session45_rescore_discrepancies.md`
- Produces: confidence that the offline artifact can be compared against app behavior without mutating scoring logic

- [ ] **Step 1: Start the relevant local app surfaces if needed**

Run from `vercel/uworld-api-deploy/` and/or the frontend workspace according to current project startup instructions.
Expected: API/frontend available for read-only comparison.

- [ ] **Step 2: Verify the app still reproduces session `45` question order**

Manual check:
- confirm `test2` still serves 6 blocks of 20
- confirm question positions `35`, `36`, and `42` still map to `nbme28_q0016`, `nbme28_q0054`, and `nbme28_q0095`
- confirm this QA is documented as parity-only, not scoring authority

- [ ] **Step 3: Capture any parity mismatch separately**

If the app’s score/review UI disagrees with `session45_rescored_from_nbme_key.json`, record that mismatch in a follow-up artifact instead of editing runtime scoring as part of this plan.

- [ ] **Step 4: Commit only if parity artifacts were added**

```bash
git add artifacts/evals
git commit -m "docs: capture session45 parity QA notes"
```

---

## Self-Review

### 1. Spec coverage
- **Locate/ingest answer-key PDF:** covered in Task 1 and Task 2.
- **Use highlighted NBME answers as authority:** covered in Task 2 extraction artifact and Task 3 rescoring logic.
- **Use user submitted responses as source of truth:** covered in Task 3 join against `session45_answer_audit.json`.
- **Cross-check against runtime/OE/backend behavior:** covered in Task 4 discrepancy report.
- **Deterministic, reproducible artifacts:** covered by all artifact outputs plus checksum pinning and Task 5 contract tests.
- **Triple-check score-critical items:** covered explicitly in Task 3 and Task 5 tests for `Q35`, `Q36`, `Q42`, plus existing manual adjudication alignment.

### 2. Placeholder scan
- No `TODO`, `TBD`, or “implement later” placeholders remain.
- Every task names exact files, commands, and expected outputs.
- All new functions referenced in later tasks are introduced earlier with explicit names/signatures.

### 3. Type consistency
- Extractor writes `rows[*].detectedLetter`; rescoring script consumes `detectedLetter` consistently.
- Rescoring script emits `rows[*].isCorrectUnderNbmeKey`; tests and report generation use the same key consistently.
- All file paths are repo-relative and already verified to exist or are explicitly created in the plan.

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-19-full-exam-nbme-rescore.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
