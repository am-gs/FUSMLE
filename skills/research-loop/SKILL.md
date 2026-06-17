---
name: research-loop
description: Use when gaps remain in form recovery, duplicate detection, or blueprint fidelity and you need an evidence-driven loop over sources, candidates, and evaluation results. Optimize for fast narrowing of uncertainty, not endless browsing.
---

# Research Loop

## Purpose

Run a bounded research loop when the exact composition of a target exam is still uncertain.

## Use when

- a block has multiple plausible candidate items
- duplicate groups are noisy
- extracted source material is incomplete
- you need to decide between exact match, near-duplicate, or blueprint fallback

## Loop

1. State the uncertainty precisely.
2. Gather the smallest evidence set that can resolve it.
3. Compare candidates against raw source artifacts and normalized qbank rows.
4. Record the decision and why it won.
5. Move on. Do not research for sport.

## Decision order

1. exact source recovery
2. explicit duplicate relationship
3. strongest blueprint fit
4. documented fallback

## Required artifact

Write disputed decisions to:

- `artifacts/research/<exam_slug>-decision-log.jsonl`

Each line should include:

- disputed slot
- candidates considered
- evidence used
- chosen candidate
- confidence

## Rules

- No silent substitutions
- No “best guess” without evidence notes
- If confidence is low, surface it instead of burying it
