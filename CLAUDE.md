# Claude / Cross-Agent Quickstart

Read `AGENTS.md` first. It is the canonical project operating manual.

## Fast truth

- This repo is for **retrieving, curating, freezing, and validating** NBME-style exams from the existing qbank.
- Prefer exact recovery and deterministic manifests over generation.
- Use local skills in `skills/` before upstream catalogs.

## Local skills

- `skills/form-ingestion/`
- `skills/qbank-schema-normalization/`
- `skills/blueprint-match-selection/`
- `skills/manifest-build-and-freeze/`
- `skills/eval-and-parity-qa/`
- `skills/research-loop/`

## Critical rules

- no silent substitutions
- no medical stem rewrites
- no named exam shipping without manifest + eval artifact
- no 1:1 fidelity claims without evidence

## Useful workspace resources

- `/home/sota-skills/docling`
- `/home/sota-skills/instructor`
- `/home/sota-skills/dspy`
- `/home/sota-skills/promptfoo`
- `/home/sota-skills/pydantic-ai`
- `/home/agent-skill-sources/anthropic-skills`
- `/home/agent-skill-sources/openai-skills`

If you need details, stop being heroic and open `AGENTS.md`.
