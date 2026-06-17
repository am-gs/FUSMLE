# FUSMLE Agent Context

This repository now carries project-local agent context and skills for reconstructing NBME-style exams from the existing qbank.

## Core rule

Treat this as a **retrieval and curation** system, not a synthetic content generator.

The qbank already contains real extracted NBME Step 1 questions from multiple forms. Prefer exact recovery, normalization, duplicate resolution, deterministic manifest building, and parity QA over prompty reinvention.

## Repository surfaces

- `vercel/uworld-frontend/` — live frontend
- `vercel/uworld-api-deploy/` — live backend
- `skills/` — project-local curation skills

## Local skill load order

Use project-local skills first:

1. `skills/form-ingestion/`
2. `skills/qbank-schema-normalization/`
3. `skills/blueprint-match-selection/`
4. `skills/manifest-build-and-freeze/`
5. `skills/eval-and-parity-qa/`
6. `skills/research-loop/`

## What each local skill is for

- `form-ingestion` — turn official forms, screenshots, and PDFs into canonical structured artifacts while preserving block order and media fidelity
- `qbank-schema-normalization` — force extracted forms and current qbank rows into one typed schema for matching and dedupe
- `blueprint-match-selection` — build 120-style exams from the existing qbank using exact-match/duplicate/blueprint-fit ranking
- `manifest-build-and-freeze` — freeze curated selections into deterministic manifests for app use
- `eval-and-parity-qa` — run structural evals and browser QA before shipping
- `research-loop` — resolve ambiguous candidate slots with a bounded evidence loop and a decision log

## Upstream skill catalogs available in this environment

These are workspace resources, not repo content:

- `/home/agent-skill-sources/anthropic-skills`
- `/home/agent-skill-sources/openai-skills`
- `/home/agent-skill-sources/agent-skills-hub`
- `/home/agent-skill-sources/claude-skills`

Use them for patterns and reusable workflows, but do not blindly import noise into this repo.

## SOTA tool repos available in this environment

- `/home/sota-skills/docling` — document/PDF/layout extraction
- `/home/sota-skills/instructor` — structured extraction with validation
- `/home/sota-skills/dspy` — ranking/prompt/program optimization
- `/home/sota-skills/promptfoo` — regression/eval harness
- `/home/sota-skills/pydantic-ai` — typed agents/evals/durable workflows
- `/home/andrej-karpathy-skills` — execution discipline and anti-bloat heuristics

## Recommended workflow for named exams

1. Ingest source form artifacts into canonical structured records.
2. Normalize source records and qbank rows into one schema.
3. Build duplicate groups and candidate pools.
4. Select items with a retrieval-first ranking strategy.
5. Freeze the chosen exam into a deterministic manifest.
6. Run structural evals and browser parity QA.
7. Ship only versioned manifests, not ad hoc runtime generation.

## Hard constraints

- Do not rewrite medical stems/options for style.
- Do not renumber or reorder items casually.
- Do not substitute non-exact items silently.
- Do not ship a named exam without a manifest and eval artifact.
- Do not claim 1:1 fidelity without evidence.

## Default artifact paths

- `artifacts/forms/<form_slug>/...`
- `artifacts/qbank/...`
- `artifacts/manifests/...`
- `artifacts/evals/...`
- `artifacts/research/...`

## Decision rule for ambiguous slots

Pick in this order:

1. exact source recovery
2. explicit duplicate relationship
3. strongest blueprint fit
4. documented fallback

If you cannot justify the pick in writing, it is not ready.
