"""NBME 120 generator — blueprint-balanced over the curated gold pool.
6 blocks x 20, matched to NBME Step 1 organ-system blueprint + difficulty mix,
deduplicated by concept_fingerprint. Returns {format,totalQuestions,blocks,questionIds}.
"""
import random, collections
from qbank_data import load_questions

BLUEPRINT = {
    "General Principles": 0.11, "Hemat/Lymph/Immune": 0.08,
    "Behavioral/Nervous & Special Senses": 0.11, "MSK/Skin": 0.08,
    "Cardiovascular": 0.09, "Respiratory": 0.08, "GI": 0.08,
    "Renal/Urinary": 0.06, "Reproductive/Endocrine": 0.12, "Multisystem": 0.19,
}
TOTAL = 120


def _targets():
    raw = {k: v * TOTAL for k, v in BLUEPRINT.items()}
    base = {k: int(v) for k, v in raw.items()}
    rem = TOTAL - sum(base.values())
    for k, _ in sorted(raw.items(), key=lambda x: -(x[1] - int(x[1])))[:rem]:
        base[k] += 1
    return base


def generate_nbme120(exclude_ids=None):
    exclude = set(exclude_ids or [])
    pool = [q for q in load_questions() if q.get("exam_ready", True) and q["id"] not in exclude]
    by_sys = collections.defaultdict(list)
    for q in pool:
        by_sys[q.get("organ_system") or "Multisystem"].append(q)
    rng = random.Random()
    chosen, fps = [], set()
    for sysname, n in _targets().items():
        cand = by_sys.get(sysname, [])[:]
        rng.shuffle(cand)
        picked = 0
        for q in cand:
            if picked >= n:
                break
            fp = q.get("concept_fingerprint", "")
            if fp and fp in fps:
                continue
            chosen.append(q); fps.add(fp); picked += 1
    # backfill to 120 from any ready item
    if len(chosen) < TOTAL:
        rest = [q for q in pool if q not in chosen]
        rng.shuffle(rest)
        for q in rest:
            if len(chosen) >= TOTAL:
                break
            fp = q.get("concept_fingerprint", "")
            if fp and fp in fps:
                continue
            chosen.append(q); fps.add(fp)
    chosen = chosen[:TOTAL]
    rng.shuffle(chosen)
    blocks = []
    for b in range(6):
        blk = chosen[b * 20:(b + 1) * 20]
        subj = collections.Counter((q.get("organ_system") or "Unknown") for q in blk)
        diff = collections.Counter((q.get("difficulty_band") or "unknown") for q in blk)
        blocks.append({
            "blockNumber": b + 1, "timeLimit": 30,
            "questionIds": [q["id"] for q in blk],
            "subjects": dict(subj), "difficulty": dict(diff),
        })
    return {
        "format": "nbme120", "totalQuestions": len(chosen),
        "blocks": blocks,
        "questionIds": [qid for blk in blocks for qid in blk["questionIds"]],
    }


# ---- TEST 1: the OFFICIAL April 2026 Step 1 Sample (119 items, fixed order) ----
import re as _re
from qbank_data import get_question_by_id as _get

# Official block boundaries (last block has 19 items)
_TEST1_BLOCKS = [(1, 20), (21, 40), (41, 60), (61, 80), (81, 100), (101, 119)]


def generate_test1():
    """Return the fixed official April 2026 NBME 120 sample exam: 119 items in
    official order, split into the 6 official blocks, timed (30 min/block)."""
    blocks = []
    for bi, (lo, hi) in enumerate(_TEST1_BLOCKS, start=1):
        ids = []
        for n in range(lo, hi + 1):
            qid = "nbme120_q%03d" % n
            q = _get(qid)
            if q and q.get("exam_ready", False):
                ids.append(qid)
        blocks.append({
            "blockNumber": bi,
            "timeLimit": 30,
            "questionIds": ids,
            "itemRange": "%d-%d" % (lo, hi),
        })
    all_ids = [qid for blk in blocks for qid in blk["questionIds"]]
    return {
        "format": "test1",
        "title": "TEST 1 — NBME April 2026 Official Sample",
        "timed": True,
        "totalQuestions": len(all_ids),
        "blocks": blocks,
        "questionIds": all_ids,
    }
