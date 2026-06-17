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

- `/home/sota-skills/docling` if present
- `/home/sota-skills/instructor` if present
- `/home/sota-skills/dspy` if present
- `/home/sota-skills/promptfoo` if present
- `/home/sota-skills/pydantic-ai` if present
- `/home/agent-skill-sources/anthropic-skills` if present
- `/home/agent-skill-sources/openai-skills` if present

If you need details, stop being heroic and open `AGENTS.md`.
