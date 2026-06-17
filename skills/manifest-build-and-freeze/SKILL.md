---
name: manifest-build-and-freeze
description: Use when turning curated qbank selections into reproducible exam manifests and app-ready fixtures. Prefer deterministic manifests and versioned artifacts over runtime randomness.
---

# Manifest Build and Freeze

## Purpose

Convert curated selections into production-safe assets that the app can load repeatably.

## Use when

- A reconstructed exam is ready to be frozen
- `generate_test1()` or related exam builders should stop depending on ad hoc runtime assembly
- You need stable IDs for resume/history behavior

## Default workflow

1. Read the approved selection manifest.
2. Validate all referenced qbank IDs exist.
3. Freeze order, block assignments, and metadata into versioned artifacts.
4. Wire the app to load the frozen manifest deterministically.
5. Keep a provenance trail so later edits are diffable.

## Required outputs

- versioned manifest file
- provenance metadata
- app fixture or loader input
- diff-friendly changelog of added/removed/swapped items

## Rules

- Runtime generation is acceptable for exploration, not for final named exams.
- Stable question ordering is mandatory for resume/history consistency.
- Changing a live named exam requires a manifest version bump.
- Keep provenance so a human can answer “why is this item here?”

## Verification

- Loader resolves every question ID
- Resume/history logic still works with the frozen ordering
- Re-running the builder produces identical output on unchanged inputs
