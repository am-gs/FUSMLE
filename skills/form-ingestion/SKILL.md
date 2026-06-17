---
name: form-ingestion
description: Use when extracting official NBME/120-style forms, screenshots, or PDFs into structured question records with preserved block order, images, tables, and answer choices. Prefer extraction into deterministic artifacts over freeform notes.
---

# Form Ingestion

## Purpose

Turn source exam materials into a canonical machine-readable dataset without losing ordering, media, or layout-dependent meaning.

This project already has a qbank. The job here is not to generate new medical content. The job is to recover and structure existing content accurately.

## Use when

- A PDF, screenshot set, or scanned form needs to be ingested
- Questions, answer choices, images, or tables need structured extraction
- Block boundaries or question ordering matter
- You need a repeatable artifact that later selection/eval skills can consume

## Default workflow

1. Inventory the source files and identify:
   - form name
   - block count
   - page ranges per block
   - image/table-heavy pages
2. Prefer structured extraction first:
   - use `docling` for PDFs and mixed-layout documents
   - use OCR/media tooling only on pages where direct parsing is weak
3. Emit one canonical artifact per form:
   - `artifacts/forms/<form_slug>/questions.json`
   - `artifacts/forms/<form_slug>/assets/`
4. Preserve:
   - original question order
   - block number
   - page number
   - source file and coordinates when available
   - image/table references
5. Flag uncertain rows instead of guessing.

## Required output shape

Each extracted question record should include:

```json
{
  "source_form": "nbme_form_x",
  "block": 1,
  "question_number": 17,
  "source_pages": [12, 13],
  "stem": "...",
  "options": [
    {"label": "A", "text": "..."},
    {"label": "B", "text": "..."}
  ],
  "answer_key": null,
  "has_image": false,
  "image_assets": [],
  "tables": [],
  "extraction_confidence": "high",
  "notes": []
}
```

## Rules

- Never silently rewrite medical content for style.
- Never collapse answer choices into one blob.
- Never renumber questions to make downstream code happy.
- If a page is ambiguous, mark the field uncertain and continue.
- Keep block order sacred. Exam feel dies when ordering drifts.

## Fast path

- Clean PDF: `docling` extraction first
- Scanned PDF or screenshots: OCR only for the weak pages
- Tables/images: preserve external asset files and link them from the question record

## Verification

- Question count matches the source form
- Block sizes match the source form
- Random sample of stems/options matches the original pages exactly
- Image/table references resolve to real files
