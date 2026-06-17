---
name: eval-and-parity-qa
description: Use when scoring how faithfully a curated exam matches the target blueprint and when validating app behavior end-to-end. Combine automated evals, deterministic checks, and browser QA before shipping.
---

# Eval and Parity QA

## Purpose

Prove that a curated exam is structurally faithful and that the app serves it correctly.

## Use when

- Comparing candidate manifests
- Preventing regressions in named exams
- Validating timer, resume, block flow, and assets in-browser

## Evaluation stack

1. `promptfoo` or equivalent for repeatable comparison runs
2. typed evaluators for structural checks
3. browser QA for user-facing parity

## Core eval dimensions

- exact question-count match
- exact block-count match
- subject/system distribution delta
- media/table parity
- duplicate leakage
- ordering fidelity
- explanation presence
- resume/history correctness in the app

## Browser QA checklist

- start exam
- complete partial block
- resume from history
- verify block transitions
- verify assets render
- verify score suppression rules if applicable

## Rules

- Do not ship based on “looks close enough.”
- Every named exam needs an eval artifact.
- Fail closed on duplicate leakage or block-count mismatches.

## Output artifacts

- `artifacts/evals/<exam_slug>.json`
- `artifacts/evals/<exam_slug>.md`
- screenshots for any UI parity issues
