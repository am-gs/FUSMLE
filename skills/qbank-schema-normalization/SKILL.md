---
name: qbank-schema-normalization
description: Use when normalizing extracted exam materials and existing qbank rows into one canonical schema for matching, deduplication, and deterministic form assembly. Prefer typed validation and explicit uncertainty over lossy conversions.
---

# QBank Schema Normalization

## Purpose

Map heterogeneous source items into one canonical schema so the system can compare, deduplicate, and assemble exam manifests deterministically.

## Use when

- Existing qbank rows have inconsistent fields
- Extracted forms need to line up with current qbank data
- You need reliable subject/system/block metadata
- You need a typed contract for later matching and eval steps

## Default workflow

1. Define one canonical item schema.
2. Normalize existing qbank items into that schema.
3. Normalize extracted form items into that same schema.
4. Store both raw and normalized values when fidelity matters.
5. Validate all outputs with typed schemas before writing artifacts.

## Canonical fields

Every normalized item should include at least:

- `item_id`
- `source`
- `source_form`
- `question_number`
- `block`
- `stem`
- `options`
- `subject`
- `system`
- `discipline`
- `organ_system`
- `has_image`
- `has_table`
- `answer_key`
- `explanation`
- `tags`
- `difficulty_estimate`
- `duplicate_group`
- `normalization_notes`

## Preferred tooling

- `instructor` for structured extraction/repair
- Pydantic models for validation
- Keep raw source text adjacent to normalized text for auditability

## Rules

- Do not discard source-only fields just because the current app does not use them.
- Do not force certainty on subject/system if the item is ambiguous; mark uncertainty explicitly.
- Normalize answer choices into ordered arrays, not ad hoc blobs.
- Record duplicates as relationships, not deletions.

## Output artifacts

- `artifacts/qbank/normalized_items.jsonl`
- `artifacts/qbank/duplicate_groups.json`
- `artifacts/qbank/normalization_report.json`

## Verification

- 100% of rows validate against the canonical schema
- No missing option arrays
- Duplicate groups are explicit
- Random audit sample can be traced back to raw source text
