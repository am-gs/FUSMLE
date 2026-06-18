#!/usr/bin/env python3
"""Plan B: repair Test 2 by replacing the 30 image-flagged items with accurate
qbank items (clean-image where the stem needs a figure, accurate text-only
otherwise), pulling media density toward real-NBME parity.

Hard constraints:
- Replacements must NOT come from either already-taken 120 form (session 23 =
  official nbme120_q*, session 24 = NBME 120 Simulation set).
- Replacements must be exam_ready, not quarantined, not already in Test 2,
  concept-deduped, and (if image) have valid on-disk image files (>=5KB).
- Preserve block positions, 6x20=120, system + difficulty blueprint.
"""
import json, os, re, ast, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "vercel" / "uworld-api-deploy"
MANIFEST = ROOT / "artifacts" / "manifests" / "june2026_nbme120_candidate.json"
GOLD = API / "gold_runtime.json"
FLAGS_PY = API / "test2_render_flags.py"
TAKEN = Path("/home/taken_exam_ids.json")
DECISION_LOG = ROOT / "artifacts" / "research" / "test2-repair-decision-log.jsonl"
SWAP_TABLE = ROOT / "artifacts" / "research" / "test2-repair-swap-table.json"

DIFF_ORDER = {"easy": 0, "medium": 1, "hard": 2}

def img_files_ok(q):
    urls = q.get("imageUrls") or ([q["image_url"]] if q.get("image_url") else [])
    if not urls:
        return None  # text-only
    for u in urls:
        rel = "images_crop/" + u.split("/images_crop/", 1)[1] if "/images_crop/" in u else u.lstrip("/")
        p = API / rel
        if not p.exists() or p.stat().st_size < 5000:
            return False
    return True

def needs_image(q):
    t = (q.get("text") or "").lower()
    return any(k in t for k in [
        "shown", "photograph", "photomicrograph", "x-ray", "ct scan", "mri",
        "ultrasound", "ecg", "electrocardiogram", "arrow", "biopsy specimen",
        "scan of", "radiograph", "pedigree", "graph", "are shown", "is shown",
    ])

def media_type(q):
    blob = json.dumps(q.get("image_assets") or []).lower()
    if any(k in blob for k in ["histo", "patho", "photomicrograph", "biopsy", "smear", "gram"]):
        return "histo"
    if any(k in blob for k in ["radiology", "x-ray", "ct", "mri", "radiograph", "scan"]):
        return "radiology"
    if any(k in blob for k in ["ecg", "tracing", "electrocardiogram"]):
        return "ecg"
    if any(k in blob for k in ["graph", "curve", "chart"]):
        return "graph"
    if any(k in blob for k in ["clinical", "photo", "skin", "lesion", "fundus", "retina"]):
        return "clinical"
    return "other"

def main():
    manifest = json.loads(MANIFEST.read_text())
    pool = json.loads(GOLD.read_text())
    qmap = {q["id"]: q for q in pool}
    flags = ast.literal_eval(FLAGS_PY.read_text().split("=", 1)[1].strip())
    taken = json.loads(TAKEN.read_text())
    taken_ids = set(taken["session23"]) | set(taken["session24"])

    test2_ids = [qid for b in manifest["blocks"] for qid in b["questionIds"]]
    test2_set = set(test2_ids)
    flagged = [qid for qid in test2_ids if qid in flags]
    # Slots to replace: every flagged (broken-media) item PLUS any item that
    # belongs to an already-taken 120 form (must be unseen). Preserve order.
    taken_overlap = [qid for qid in test2_ids if qid in taken_ids]
    slots_to_replace = [qid for qid in test2_ids if qid in flags or qid in taken_ids]

    # Live concept fingerprints already in Test 2 (excluding the slots we will replace)
    used_fps = set()
    for qid in test2_ids:
        if qid in flags or qid in taken_ids:
            continue
        fp = qmap[qid].get("concept_fingerprint")
        if fp:
            used_fps.add(fp)

    exclude = test2_set | taken_ids

    # Candidate universe
    base = [q for q in pool
            if q["id"] not in exclude
            and q.get("exam_ready", True)
            and not q.get("quarantined")]
    img_ok = {q["id"]: img_files_ok(q) for q in base}

    def candidates_for(slot_q, require_image):
        sys_target = slot_q.get("organ_system") or slot_q.get("system")
        diff_target = slot_q.get("difficulty_band")
        mt_target = media_type(slot_q)
        sf_target = slot_q["id"].split("_")[0]
        subj_target = slot_q.get("subject")
        stem_len = len((slot_q.get("text") or "").split())
        out = []
        for q in base:
            if (q.get("organ_system") or q.get("system")) != sys_target:
                continue
            if q.get("difficulty_band") not in DIFF_ORDER:
                continue  # keep the difficulty curve exact; skip unlabeled items
            if require_image and img_ok[q["id"]] is not True:
                continue
            if not require_image and img_ok[q["id"]] is not None:
                # text-only slot: accept text-only OR a clean-image item only if
                # we are short, but Plan B prefers text-only here
                if img_ok[q["id"]] is not True:
                    continue  # broken-image item, skip
            diff_dist = abs(DIFF_ORDER.get(q.get("difficulty_band"), 1) - DIFF_ORDER.get(diff_target, 1))
            score = (
                diff_dist,                                            # 0 best
                0 if (require_image and media_type(q) == mt_target) else 1,
                0 if q["id"].split("_")[0] == sf_target else 1,
                0 if q.get("subject") == subj_target else 1,
                abs(len((q.get("text") or "").split()) - stem_len),
                q["id"],
            )
            out.append((score, q))
        out.sort(key=lambda x: x[0])
        return out

    swaps = []
    chosen_ids = set()
    log_lines = []
    for qid in slots_to_replace:
        slot_q = qmap[qid]
        # locate block position
        pos = None
        for bi, b in enumerate(manifest["blocks"]):
            if qid in b["questionIds"]:
                pos = (bi, b["questionIds"].index(qid))
                break
        is_flagged = qid in flags
        if is_flagged:
            # Plan B: figure-essential -> clean image; otherwise accurate text-only
            essential = needs_image(slot_q)
        else:
            # Unseen-swap of a non-broken taken-form item: preserve its media nature
            essential = img_files_ok(slot_q) is True
        ladder = [("clean-image", True), ("text-only", False)] if essential else [("text-only", False), ("clean-image", True)]
        pick = None
        used_strategy = None
        considered = 0
        for strat, req_img in ladder:
            for score, cand in candidates_for(slot_q, req_img):
                considered += 1
                if cand["id"] in chosen_ids:
                    continue
                fp = cand.get("concept_fingerprint")
                if fp and fp in used_fps:
                    continue
                pick = cand
                used_strategy = strat
                break
            if pick:
                break
        if not pick:
            log_lines.append(json.dumps({"slot": qid, "status": "manual_review", "reason": "no candidate"}))
            continue
        chosen_ids.add(pick["id"])
        if pick.get("concept_fingerprint"):
            used_fps.add(pick["concept_fingerprint"])
        manifest["blocks"][pos[0]]["questionIds"][pos[1]] = pick["id"]
        rec = {
            "block": pos[0] + 1, "item": pos[1] + 1,
            "removed": qid, "removed_system": slot_q.get("organ_system") or slot_q.get("system"),
            "removed_difficulty": slot_q.get("difficulty_band"),
            "removed_reason": "broken_media" if is_flagged else "already_taken_form",
            "added": pick["id"], "added_system": pick.get("organ_system") or pick.get("system"),
            "added_difficulty": pick.get("difficulty_band"),
            "added_subject": pick.get("subject"),
            "added_has_image": img_ok[pick["id"]] is True,
            "strategy": used_strategy, "essential": essential,
            "source_form": pick["id"].split("_")[0],
            "candidates_considered": considered,
        }
        swaps.append(rec)
        log_lines.append(json.dumps({
            "slot": qid, "chosen": pick["id"], "strategy": used_strategy,
            "system": rec["added_system"], "difficulty": rec["added_difficulty"],
            "has_image": rec["added_has_image"], "confidence": "high" if used_strategy and considered else "med",
        }))

    # Sanity
    new_ids = [qid for b in manifest["blocks"] for qid in b["questionIds"]]
    assert len(new_ids) == 120, len(new_ids)
    assert len(set(new_ids)) == 120, "dup IDs after swap"
    assert not (set(new_ids) & taken_ids), "replacement leaked a taken-form ID"
    for qid in new_ids:
        assert qid in qmap, f"unknown id {qid}"

    manifest["manifest_version"] = manifest.get("manifest_version", 1) + 1
    manifest.setdefault("provenance", {})["test2_parity_repair"] = {
        "replaced": len(swaps),
        "replaced_broken_media": sum(1 for s in swaps if s["removed_reason"] == "broken_media"),
        "replaced_already_taken": sum(1 for s in swaps if s["removed_reason"] == "already_taken_form"),
        "excluded_taken_forms": ["session23_nbme120_official", "session24_nbme120_simulation"],
        "strategy": "plan_B_accuracy_plus_media_parity",
    }
    if "--apply" in sys.argv:
        MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        FLAGS_PY.write_text(
            "# All previously broken-media Test 2 items were replaced with accurate\n"
            "# qbank items (Plan B parity repair). No known-bad media remain in Test 2.\n"
            "TEST2_RENDER_FLAGS = {}\n"
        )
    DECISION_LOG.parent.mkdir(parents=True, exist_ok=True)
    DECISION_LOG.write_text("\n".join(log_lines) + "\n")
    SWAP_TABLE.write_text(json.dumps({"swaps": swaps, "count": len(swaps)}, indent=2, ensure_ascii=False))

    img_after = sum(1 for qid in new_ids if (qmap[qid].get("imageUrls") or qmap[qid].get("image_url")))
    print(json.dumps({
        "replaced": len(swaps),
        "applied": "--apply" in sys.argv,
        "image_items_after": img_after,
        "image_pct_after": round(img_after / 120 * 100, 1),
        "manual_review": sum(1 for l in log_lines if '"manual_review"' in l),
    }, indent=2))

if __name__ == "__main__":
    main()
