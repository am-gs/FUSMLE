# June 2026 NBME 120 Reconstruction Spec

Status: Draft  
Artifact target: technical spec + scoring rubric + deterministic candidate manifest  
Primary source of truth: existing qbank entries from `NBME 27`, `NBME 28`, `NBME 29`, `Form 30`, and `Form 31`

## Goal

Build **one fixed deterministic 120-question exam** from the five-form qbank so that it resembles the June 2026 NBME 120 experience in:

- block structure
- system/subject distribution
- difficulty curve
- image frequency
- rendering fidelity of stems, answer options, and media assets

The qbank is the source of truth. This is a **selection and curation** problem, not a synthetic question-writing task.

## Scope

In scope:

- deterministic candidate selection from the existing five-form qbank
- blueprint matching to a June 2026 proxy
- media/rendering coverage checks
- coverage report documenting where parity is met vs impossible from source

Out of scope for this artifact:

- shipping the final exam into app generation routes
- synthetic table creation to fake parity
- silently rewriting question content

## Target exam contract

- total questions: `120`
- blocks: `6`
- block size: `20` each
- time limit: `30 minutes` per block
- output mode: one fixed manifest, not a stochastic generator

## June 2026 proxy

The current repo’s official `NBME 120` sample payload is used as the **format proxy** for:

- block composition
- broad organ-system balance
- difficulty distribution
- image frequency
- block-level feel

Because that source has `119` items, the reconstruction scales it to `120` by:

- preserving the first five 20-question block patterns
- expanding the final block from 19 to 20 items
- assigning the extra slot to `Multisystem`
- preserving the overall image total at `21`
- scaling overall difficulty to `23 easy / 82 medium / 15 hard`

## Source pool

Selection pool:

- `NBME 27`
- `NBME 28`
- `NBME 29`
- `Form 30`
- `Form 31`

Pool constraints observed from current qbank:

- ready items available: `870`
- image-bearing items available: `123`
- table-bearing items available: `0`
- option-table items available: `0`
- options missing: `0`
- option parse errors: `0`

## Selection policy

Per the repo context:

1. duplicate
2. near-duplicate
3. blueprint fit

For this initial artifact:

- exact duplicate proxy = repeated `concept_fingerprint`
- near-duplicate detector = **not yet implemented**
- all other picks = `blueprint-fit`

This means the initial manifest is honest but incomplete with respect to the desired fallback ladder. It supports `duplicate → blueprint-fit` now and leaves near-duplicate detection as a follow-up.

## Deterministic selection rules

The candidate builder must:

1. select only `exam_ready` items from the five-form pool
2. deduplicate by `concept_fingerprint` where present
3. hit the block-level system quotas derived from the June 2026 proxy
4. hit the block-level difficulty quotas derived from the June 2026 proxy
5. hit the block-level image quotas derived from the June 2026 proxy
6. keep form contributions balanced when possible
7. emit stable ordering and provenance for every chosen question

## Broad system targets for 120

- `Multisystem`: `29`
- `Behavioral/Nervous & Special Senses`: `18`
- `MSK/Skin`: `13`
- `Reproductive/Endocrine`: `13`
- `Cardiovascular`: `12`
- `Renal/Urinary`: `11`
- `GI`: `9`
- `Respiratory`: `7`
- `General Principles`: `4`
- `Hemat/Lymph/Immune`: `4`

## Difficulty targets for 120

- `easy`: `23`
- `medium`: `82`
- `hard`: `15`

## Image targets

Per block image targets:

- Block 1: `3`
- Block 2: `4`
- Block 3: `4`
- Block 4: `4`
- Block 5: `3`
- Block 6: `3`

Total image target: `21`

## Known hard gap

The five-form source pool currently exposes:

- `0` table-bearing items
- `0` option-table items

The official `NBME 120` sample proxy contains:

- `14` table-bearing items
- `3` option-table items

Therefore full table parity is **currently impossible** from the chosen source pool and must be reported as an unmet coverage dimension, not hand-waved away.

## Scoring rubric

Total: `100`

### 1. Structural parity — 25

- 10: total question count exact
- 10: block sizes exact
- 5: time limit / block model exact

### 2. Blueprint parity — 25

- 15: broad system counts match target
- 10: per-block system counts match target

### 3. Difficulty parity — 15

- 10: global easy/medium/hard counts match target
- 5: per-block difficulty counts match target

### 4. Media parity — 15

- 10: image frequency matches target globally and by block
- 5: table / option-table parity

### 5. Rendering fidelity — 10

- 4: all questions have parsed options
- 3: no option parse errors
- 3: image-bearing questions resolve to media assets

### 6. Selection integrity — 10

- 4: no duplicate question IDs
- 3: concept-fingerprint dedupe respected
- 3: provenance recorded per selected question

Penalty rule:

- any silent substitution or missing provenance fails the artifact regardless of numeric score

## Acceptance criteria

1. A deterministic manifest exists with exactly `120` unique question IDs.
2. Every block contains exactly `20` question IDs.
3. The manifest records provenance per question.
4. The coverage report explicitly lists met targets and unmet targets.
5. Table parity gaps are called out as source-pool limitations, not implementation bugs.
6. The candidate artifact is reproducible from a checked-in script.

## Deliverables for this phase

- `artifacts/specs/june2026_nbme120_reconstruction_spec.md`
- `artifacts/manifests/june2026_nbme120_candidate.json`
- `artifacts/evals/june2026_nbme120_candidate_coverage_report.json`
- `scripts/generate_june2026_120_candidate.py`
