"""NBME 120 generator — blueprint-balanced over the curated gold pool.
6 blocks x 20, matched to NBME Step 1 organ-system blueprint + difficulty mix,
deduplicated by concept_fingerprint. Returns {format,totalQuestions,blocks,questionIds}.
"""
import collections
import json
import random
from pathlib import Path

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


ROOT = Path(__file__).resolve().parents[2]
LOCAL_MANIFEST_PATH = Path(__file__).resolve().parent / "artifacts" / "manifests" / "june2026_nbme120_candidate.json"
TEST2_MANIFEST_PATH = ROOT / "artifacts" / "manifests" / "june2026_nbme120_candidate.json"


def _load_test2_manifest():
    manifest_path = LOCAL_MANIFEST_PATH if LOCAL_MANIFEST_PATH.exists() else TEST2_MANIFEST_PATH
    manifest = json.loads(manifest_path.read_text())
    blocks = manifest.get("blocks", [])
    all_ids = [qid for block in blocks for qid in block.get("questionIds", [])]
    available = {q["id"]: q for q in load_questions()}
    missing_ids = [qid for qid in all_ids if qid not in available]
    not_ready_ids = [qid for qid in all_ids if qid in available and not available[qid].get("exam_ready", True)]

    if manifest.get("total_questions") != 120:
        raise ValueError("Test 2 manifest must contain 120 questions")
    if manifest.get("block_sizes") != [20, 20, 20, 20, 20, 20]:
        raise ValueError("Test 2 manifest must contain 6 blocks of 20 questions")
    if len(all_ids) != 120 or len(set(all_ids)) != 120:
        raise ValueError("Test 2 manifest must contain 120 unique question IDs")
    if missing_ids:
        raise ValueError(f"Test 2 manifest references missing qbank IDs: {missing_ids[:5]}")
    if not_ready_ids:
        raise ValueError(f"Test 2 manifest references non-ready qbank IDs: {not_ready_ids[:5]}")

    return manifest, all_ids


def generate_test1():
    """Legacy alias for the deterministic June-style 120 candidate reconstruction."""
    return generate_test2(format_slug="test1", title="TEST 1 — June 2026 NBME 120 Candidate Reconstruction")


def generate_test2(format_slug="test2", title="TEST 2 — June 2026 NBME 120 Candidate Reconstruction"):
    """Return the fixed deterministic June-style 120 candidate reconstruction."""
    manifest, all_ids = _load_test2_manifest()
    blocks = [
        {
            "blockNumber": block["block"],
            "timeLimit": block.get("timeLimitMinutes", 30),
            "questionIds": block["questionIds"],
            "selectionRationaleByQuestion": block.get("selection_rationale_by_question", {}),
            "selectionDetailsByQuestion": block.get("selection_details_by_question", {}),
        }
        for block in manifest["blocks"]
    ]
    return {
        "format": format_slug,
        "title": title,
        "timed": True,
        "totalQuestions": manifest["total_questions"],
        "blocks": blocks,
        "questionIds": all_ids,
        "strategy": manifest.get("strategy"),
        "sourceForms": manifest.get("source_forms", []),
        "sourceProxyForm": manifest.get("source_proxy_form"),
        "manifestSlug": manifest.get("exam_slug"),
    }
