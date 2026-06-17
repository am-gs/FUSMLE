# Captain Repo Brief

Use `AGENTS.md` as the source of truth.

## Repo-specific priorities

1. preserve live exam behavior
2. keep named exams deterministic
3. prefer artifact generation over prompt-only logic
4. verify backend + browser, not one or the other

## High-risk areas

- named exam composition
- question ordering
- resume/history behavior
- score visibility rules
- image/table asset binding
- persistence and session continuity

## Minimum acceptance for exam-curation changes

- exact question/block counts
- deterministic manifest or explicit reason not to freeze one
- no duplicate leakage
- backend contract checks where relevant
- browser parity QA through the actual flow
