# Test 2 → 1:1 NBME Parity: Replacement & Repair Plan

Status: PROPOSED (research complete, awaiting go)
Branch: capy/spec-120-reconstruction
Owner exam: Test 2 (`june2026_nbme120_candidate` manifest, 120 items, 6×20)

## 1. Goal & success criteria

Make Test 2 a 1:1 match to a real NBME Step 1 form on:
- question accuracy (no wrong/missing/incorrect image assets)
- system/subject distribution
- difficulty curve
- media/table density
- block structure and item count (6×20 = 120)

Done = every served Test 2 item is accurate and renders correctly, and the structural deltas vs the real-form blueprint are ≤ tolerance (see §6).

## 2. Current state (researched)

- 30 Test 2 items are currently flagged and image-suppressed (`test2_render_flags.py`) because their image assets are wrong/missing/bad-crop.
  - by organ system: Multisystem 9, Cardiovascular 5, MSK/Skin 4, Behavioral/Nervous 4, Respiratory 3, Reproductive/Endocrine 3, Renal/Urinary 1, Heme/Immune 1
  - by difficulty: 22 medium, 6 easy, 2 hard
  - 20 of 30 stems actually require a figure; 10 do not.
- Replacement pool (exam_ready, not quarantined, NOT already in Test 2): 988 items → 264 with valid image files, 706 text-only.
- Per-slot availability: 27/30 flagged slots have ≥4 image-valid replacements at exact (system, difficulty); only 3 slots (Multisystem/easy) have zero image-valid replacement at exact key.
- Whole qbank: 403 image items, but 52 have broken/tiny files → replacements must be file-validated.

### Parity insight (drives the plan)
- Real official NBME 120: **21/119 image items = 17.6%**.
- Test 2 today: **43/120 = 35.8%** — roughly **2× too many images**.
- So the fix is not just "swap bad image → good image." Replacing broken image items with a mix of clean-image and accurate text-only items simultaneously (a) fixes accuracy and (b) moves media density toward the real 17.6%.

## 3. Approach (deterministic, reproducible)

Build a deterministic replacement engine (`scripts/repair_test2_blueprint.py`) that, per flagged slot, selects the best non-Test-2 qbank item.

Candidate filter: `exam_ready` AND not `quarantined` AND not already in Test 2 AND (if image item) all image files exist & ≥5KB AND concept_fingerprint not already used in Test 2 (dedup).

Ranking (matches `blueprint-match-selection` order):
1. organ_system exact match (hard requirement)
2. difficulty_band exact match (hard requirement; fallback ladder below)
3. media-type match (photo/CT/graph/table vs needed type) for image-essential slots
4. source-form match (preserve 24/form provenance where possible)
5. subject match, then stem-length bucket similarity

Per-slot target media decision:
- image-essential stem (20) → require a clean-image replacement of matching media type.
- non-essential stem (10) + the 3 zero-image-availability slots → use an accurate text-only item (also pulls image density toward parity).

Fallback ladder when exact (system, difficulty, clean-image) is empty:
1. same system, adjacent difficulty (easy↔medium / medium↔hard)
2. same system, text-only accurate item
3. nearest-system within same discipline + same difficulty
4. leave slot flagged + log for manual review (never insert off-blueprint filler)

Every decision written to `artifacts/research/test2-repair-decision-log.jsonl` (slot, candidates, evidence, chosen, confidence) per `research-loop`.

## 4. Parallelization (honest)

The selection math parallelizes cleanly per system bucket; the manifest write does NOT (single shared file — parallel Build agents would collide on `gold_runtime.json` / manifest / render-flags). So:
- Parallelize candidate scoring across the 8 system buckets inside one script (concurrent compute, deterministic output).
- Apply all swaps in a single atomic manifest rewrite + one render-flags update.
- This avoids the classic failure of N agents racing the same JSON.

## 5. Phases & gates

- Phase 1 — Engine + dry run: build scorer, emit proposed swap table + decision log, NO writes. Gate: every flagged slot has a resolved candidate or explicit manual-review flag; distribution deltas previewed.
- Phase 2 — Apply swaps: rewrite manifest (preserve block positions), clear render flags for replaced slots, bump manifest version, regenerate exam JSON export. Gate: 120 unique IDs, 6×20, all referenced image files valid.
- Phase 3 — Evals (`eval-and-parity-qa`): system/difficulty/media deltas vs real-NBME blueprint, duplicate-leakage = 0, explanation presence = 100%, ordering fidelity. Gate: deltas ≤ tolerance.
- Phase 4 — Contract tests + deploy: `tests.test_api_contract` green, deploy both Vercel surfaces.
- Phase 5 — Browser parity QA: start Test 2, walk blocks, confirm every served item renders an accurate image or clean text (no suppression banners remain), resume/history intact.

## 6. Tolerances
- question count 120, blocks 6×20: exact.
- system distribution: within ±1 item per system vs current blueprint targets.
- difficulty: hold 23 easy / 82 medium / 15 hard (±1).
- media density: target real-form band (~18–22%); hard fix-only floor = no broken/wrong assets served.
- duplicate leakage: 0.

## 7. Key decision for the user
Media density target:
- A) Fix-only: replace the 30 bad-image items, keep image density ~33–36% (still ~2× real). Lower effort, but not truly 1:1 on media.
- B) Parity (recommended): replace the 30 and let non-essential slots become accurate text-only items so density moves toward the real ~17.6%. Truer 1:1; touches only the already-flagged 30 slots.
- C) Aggressive parity: B plus swapping some currently-valid image items to reach ~21 image items exactly. Closest to real, but edits items that aren't currently broken (larger blast radius).

## 8. Risks
- Replacement images in the broader pool include 52 broken files → strict file validation required (mitigated in candidate filter).
- 3 Multisystem/easy slots have no clean-image option → resolved as text-only (acceptable, aids parity).
- Concept duplication risk → fingerprint dedup against existing Test 2 set.
