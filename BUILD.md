# Build Agent Checklist

Read `AGENTS.md` first.

## Default behavior

- make the smallest correct change
- preserve live behavior unless the task explicitly changes it
- write deterministic artifacts when reconstructing named exams
- keep provenance for non-exact selections

## For exam-curation work

1. ingest or inspect source materials
2. normalize to canonical schema
3. resolve duplicates/candidates explicitly
4. freeze a deterministic manifest
5. verify through tests and browser flow

## Do not

- invent content when existing qbank content can be recovered
- change ordering casually
- hide uncertainty
- ship without evidence
