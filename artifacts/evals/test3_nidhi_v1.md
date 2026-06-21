# test3_nidhi_v1 eval

- Status: **pass**
- Mode: `surrogate`
- Strict mode would fail: `True`
- Total questions: `120`
- Block sizes: `[20, 20, 20, 20, 20, 20]`

## Constraint summary

- Source forms: NBME 27, NBME 28, NBME 29, Form 30, Form 31
- Hard excluded question IDs: `239`
- Hard excluded concept fingerprints: `120`
- Unresolved prior source labels: `['session24_nbme120_simulation']`

## Distribution

- Systems: `{'Behavioral/Nervous & Special Senses': 13, 'Cardiovascular': 11, 'GI': 10, 'General Principles': 13, 'Hemat/Lymph/Immune': 10, 'MSK/Skin': 10, 'Multisystem': 21, 'Renal/Urinary': 7, 'Reproductive/Endocrine': 15, 'Respiratory': 10}`
- Difficulty: `{'easy': 23, 'hard': 15, 'medium': 82}`
- Images: `30`
- Forms: `{'Form 30': 25, 'Form 31': 23, 'NBME 27': 24, 'NBME 28': 24, 'NBME 29': 24}`

## Integrity

- Duplicate question ID leakage: `0`
- Duplicate concept fingerprints: `0` groups
- Excluded question ID overlap: `0`
- Prior concept-fingerprint fallback count: `0`

## Checks

- PASS `manifest_slug`
- PASS `block_sizes`
- PASS `total_questions`
- PASS `export_exam_slug`
- PASS `excluded_question_overlap`
- PASS `duplicate_fingerprints`
- PASS `concept_fallback_count`

## Notes

- This build is a personalized deterministic reconstruction, not an exact named-form recovery.
- The Step 1 blueprint was adjusted minimally after Multisystem availability dropped below the raw target in the post-exclusion five-form pool.
- Any future non-zero concept fallback should be treated as a review trigger before routing is wired.
