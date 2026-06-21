#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = ROOT / "artifacts"
EXPORTS_DIR = ARTIFACTS_DIR / "exports"
EVALS_DIR = ARTIFACTS_DIR / "evals"
RESEARCH_DIR = ARTIFACTS_DIR / "research"
QBANK_INDEX_PATH = ROOT / "vercel" / "uworld-api-deploy" / "qbank_index.json"

USER_EMAIL = "nidhitiyyagura@gmail.com"
DEFAULT_MODE = "surrogate"
SESSION24_LABEL = "session24_nbme120_simulation"
SESSION23_LABEL = "session23_official_nbme120"
TEST2_SESSION = "session45:test2"


class StrictModeBlocked(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        )
    )


def collect_exam_ids(export_path: Path) -> list[str]:
    payload = load_json(export_path)
    return [qid for block in payload["blocks"] for qid in block["questionIds"]]


def qid_hash(question_ids: list[str]) -> str:
    import hashlib

    digest = hashlib.sha256("\n".join(question_ids).encode("utf-8")).hexdigest()
    return digest[:16]


def load_qbank_index() -> dict[str, dict[str, Any]]:
    payload = load_json(QBANK_INDEX_PATH)
    return {row["id"]: row for row in payload["questions"]}


def sanitize_audit_title(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.split(r"REACTCOMPONENT!:!|b\d+:T[0-9a-f]+", value, maxsplit=1)[
        0
    ].strip()
    cleaned = re.sub(r"[,:;\-\s]+$", "", cleaned).strip()
    if not cleaned:
        return None
    if len(cleaned) > 200:
        cleaned = cleaned[:200].rstrip()
    return cleaned


def parse_independent_adjudication(adjudication_path: Path) -> list[dict[str, Any]]:
    lines = adjudication_path.read_text().splitlines()
    pattern = re.compile(
        r"^\|\s*(?P<position>\d+)\s*\|\s*(?P<slot>[^|]+?)\s*\|\s*`(?P<qid>[^`]+)`\s*\|\s*(?P<independent>[^|]+?)\s*\|\s*(?P<answer>[^|]+?)\s*\|\s*\*\*(?P<verdict>Correct|Incorrect)\*\*\s*\|\s*(?P<notes>.+?)\s*\|$"
    )
    rows: list[dict[str, Any]] = []
    for line in lines:
        match = pattern.match(line)
        if not match:
            continue
        rows.append(
            {
                "position": int(match.group("position")),
                "slot": match.group("slot").strip(),
                "questionId": match.group("qid").strip(),
                "independentAnswer": match.group("independent").strip(),
                "submittedAnswer": match.group("answer").strip(),
                "verdict": match.group("verdict").lower(),
                "notes": match.group("notes").strip(),
            }
        )
    if not rows:
        raise RuntimeError(f"No adjudication rows parsed from {adjudication_path}")
    return rows


def derive_weakness_profile(index_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    adjudication_path = EVALS_DIR / "session45_independent_adjudication.md"
    answer_audit_path = EVALS_DIR / "session45_answer_audit.json"
    adjudicated_rows = parse_independent_adjudication(adjudication_path)
    answer_audit = load_json(answer_audit_path)
    audit_rows = {row["questionId"]: row for row in answer_audit["rows"]}

    incorrect_rows = [row for row in adjudicated_rows if row["verdict"] == "incorrect"]
    weakness_evidence: list[dict[str, Any]] = []
    for row in incorrect_rows:
        qid = row["questionId"]
        index_row = index_by_id.get(qid)
        if not index_row:
            raise RuntimeError(f"Question {qid} missing from qbank_index.json")
        audit_row = audit_rows.get(qid)
        weakness_evidence.append(
            {
                "questionId": qid,
                "position": row["position"],
                "slot": row["slot"],
                "system": index_row["system"],
                "discipline": index_row["discipline"],
                "difficulty": index_row["difficulty"],
                "conceptFingerprint": index_row.get("concept_fingerprint"),
                "auditTitle": sanitize_audit_title(audit_row.get("title"))
                if audit_row
                else None,
                "selectedLetter": audit_row.get("selectedLetter")
                if audit_row
                else row["submittedAnswer"],
                "adjudicationNotes": row["notes"],
            }
        )

    systems = Counter(item["system"] for item in weakness_evidence)
    disciplines = Counter(item["discipline"] for item in weakness_evidence)
    difficulties = Counter(item["difficulty"] for item in weakness_evidence)

    def bounded_counter_weights(
        counter: Counter[str], *, increment: float, cap: float, min_count: int
    ) -> dict[str, float]:
        weighted: dict[str, float] = {}
        for key in sorted(counter):
            count = counter[key]
            if count < min_count:
                continue
            weighted[key] = round(1.0 + min(cap, count * increment), 2)
        return weighted

    system_weights = bounded_counter_weights(
        systems, increment=0.05, cap=0.20, min_count=2
    )
    discipline_weights = bounded_counter_weights(
        disciplines, increment=0.05, cap=0.20, min_count=2
    )
    difficulty_weights = bounded_counter_weights(
        difficulties, increment=0.03, cap=0.12, min_count=2
    )

    notes = [
        "Weakness weighting is intentionally bounded and only elevated for categories with at least two independently adjudicated misses.",
        "The profile is limited to independently adjudicated score-critical misses from session45:test2; it is not a claim about all 68 incorrect answers.",
    ]

    return {
        "user": USER_EMAIL,
        "sourceSessions": [TEST2_SESSION],
        "correctnessBasis": "independent_adjudication_only",
        "metadataBasis": [
            "artifacts/evals/session45_independent_adjudication.md",
            "artifacts/evals/session45_answer_audit.json",
            "vercel/uworld-api-deploy/qbank_index.json",
        ],
        "weights": {
            "systems": system_weights,
            "disciplines": discipline_weights,
            "difficulty": difficulty_weights,
        },
        "weakQuestionIds": [
            item["questionId"]
            for item in sorted(weakness_evidence, key=lambda item: item["position"])
        ],
        "weaknessEvidence": sorted(
            weakness_evidence, key=lambda item: item["position"]
        ),
        "evidenceCounts": {
            "systems": dict(sorted(systems.items())),
            "disciplines": dict(sorted(disciplines.items())),
            "difficulty": dict(sorted(difficulties.items())),
        },
        "notes": notes,
    }


def build_taken_exam_inventory() -> tuple[
    dict[str, Any], list[dict[str, Any]], dict[str, list[str]]
]:
    test1_path = EXPORTS_DIR / "test1_exam.json"
    test2_path = EXPORTS_DIR / "test2_exam.json"
    official_path = EXPORTS_DIR / "nbme120_official_sample_exam.json"

    test1_payload = load_json(test1_path)
    test2_payload = load_json(test2_path)
    official_payload = load_json(official_path)

    test1_ids = collect_exam_ids(test1_path)
    test2_ids = collect_exam_ids(test2_path)
    official_ids = collect_exam_ids(official_path)

    if test1_ids != test2_ids:
        raise RuntimeError(
            "Expected test1 to be an alias of test2, but question ID order differs"
        )

    excluded_taken_forms = list(
        test2_payload.get("exam", {}).get("excludedTakenForms", [])
    )
    if SESSION24_LABEL not in excluded_taken_forms:
        raise RuntimeError("Expected session24 label evidence in test2_exam.json")

    decision_log = [
        {
            "step": 1,
            "kind": "proven_taken_exam",
            "slug": "test2",
            "status": "proven_taken",
            "confidence": "high",
            "blocking": False,
            "evidence": [
                "artifacts/evals/session45_independent_adjudication.md",
                "artifacts/evals/session45_answer_audit.json",
                "artifacts/exports/test2_exam.json",
            ],
            "questionCount": len(test2_ids),
            "questionIdHash": qid_hash(test2_ids),
            "note": "Session 45 is explicit repo-local evidence that Nidhi took test2.",
        },
        {
            "step": 2,
            "kind": "alias_exam",
            "slug": "test1",
            "aliasOf": "test2",
            "status": "alias_not_distinct_inventory",
            "confidence": "high",
            "blocking": False,
            "evidence": [
                "artifacts/exports/test1_exam.json",
                "artifacts/exports/test2_exam.json",
            ],
            "questionCount": len(test1_ids),
            "questionIdHash": qid_hash(test1_ids),
            "note": "test1 carries the same frozen manifest and order as test2, so it is not a distinct exclusion inventory.",
        },
        {
            "step": 3,
            "kind": "inferred_exclusion_source",
            "slug": "nbme120_official",
            "status": "repo-local surrogate until live session inventory is available",
            "confidence": "medium",
            "blocking": False,
            "evidence": [
                "artifacts/exports/nbme120_official_sample_exam.json",
                "artifacts/exports/test2_exam.json.exam.excludedTakenForms",
            ],
            "questionCount": len(official_ids),
            "questionIdHash": qid_hash(official_ids),
            "note": "The official NBME sample is represented as an inferred exclusion source with concrete repo-local IDs.",
        },
        {
            "step": 4,
            "kind": "unresolved_label",
            "slug": SESSION24_LABEL,
            "status": "unresolved_label_only",
            "confidence": "low",
            "blocking": True,
            "evidence": [
                "artifacts/exports/test2_exam.json.exam.excludedTakenForms",
                "artifacts/manifests/june2026_nbme120_candidate.json.provenance.test2_parity_repair.excluded_taken_forms",
            ],
            "questionCount": None,
            "questionIdHash": None,
            "note": "Repo-local evidence proves the label exists, but no concrete repo-local question ID inventory was found.",
        },
    ]

    inventory = {
        "user": USER_EMAIL,
        "repoLocalOnly": True,
        "mode": DEFAULT_MODE,
        "examSets": [
            {
                "slug": "test2",
                "status": "proven_taken",
                "confidence": "high",
                "source": "artifacts/exports/test2_exam.json",
                "evidence": [
                    "artifacts/evals/session45_independent_adjudication.md",
                    "artifacts/evals/session45_answer_audit.json",
                ],
                "questionCount": len(test2_ids),
                "questionIdHash": qid_hash(test2_ids),
                "concreteQuestionIds": test2_ids,
            },
            {
                "slug": "test1",
                "status": "alias_not_distinct_inventory",
                "confidence": "high",
                "aliasOf": "test2",
                "source": "artifacts/exports/test1_exam.json",
                "evidence": [
                    "artifacts/exports/test1_exam.json",
                    "artifacts/exports/test2_exam.json",
                ],
                "questionCount": len(test1_ids),
                "questionIdHash": qid_hash(test1_ids),
                "concreteQuestionIds": [],
            },
            {
                "slug": "nbme120_official",
                "status": "repo-local surrogate until live session inventory is available",
                "confidence": "medium",
                "source": "artifacts/exports/nbme120_official_sample_exam.json",
                "evidence": [
                    "artifacts/exports/nbme120_official_sample_exam.json",
                    "artifacts/exports/test2_exam.json.exam.excludedTakenForms",
                ],
                "questionCount": len(official_ids),
                "questionIdHash": qid_hash(official_ids),
                "concreteQuestionIds": official_ids,
            },
            {
                "slug": SESSION24_LABEL,
                "status": "unresolved_label_only",
                "confidence": "low",
                "source": None,
                "evidence": [
                    "artifacts/exports/test2_exam.json.exam.excludedTakenForms",
                    "artifacts/manifests/june2026_nbme120_candidate.json.provenance.test2_parity_repair.excluded_taken_forms",
                ],
                "questionCount": None,
                "questionIdHash": None,
                "concreteQuestionIds": [],
            },
        ],
        "blockingUncertainties": [
            {
                "slug": SESSION24_LABEL,
                "reason": "No concrete repo-local question IDs found for the label-only simulation source.",
                "strictModeWouldFail": True,
            }
        ],
        "notes": [
            "test2 is the only prior Nidhi exam proven taken by direct repo-local session evidence.",
            "test1 is preserved as an alias annotation only, not as a separate exclusion inventory.",
            "The official sample export is usable as a concrete repo-local surrogate exclusion source.",
        ],
    }

    id_sources = {
        "test2": test2_ids,
        "nbme120_official": official_ids,
    }
    return inventory, decision_log, id_sources


def build_exclusion_set(
    index_by_id: dict[str, dict[str, Any]], id_sources: dict[str, list[str]]
) -> dict[str, Any]:
    excluded_question_ids = sorted({qid for ids in id_sources.values() for qid in ids})
    excluded_concept_fingerprints = sorted(
        {
            index_by_id[qid]["concept_fingerprint"]
            for qid in excluded_question_ids
            if qid in index_by_id and index_by_id[qid].get("concept_fingerprint")
        }
    )

    question_counts = {slug: len(ids) for slug, ids in sorted(id_sources.items())}
    fingerprint_counts = {
        slug: len(
            {
                index_by_id[qid]["concept_fingerprint"]
                for qid in ids
                if qid in index_by_id and index_by_id[qid].get("concept_fingerprint")
            }
        )
        for slug, ids in sorted(id_sources.items())
    }

    return {
        "user": USER_EMAIL,
        "mode": DEFAULT_MODE,
        "repoLocalOnly": True,
        "resolvedSources": ["test2", "nbme120_official"],
        "aliasSources": [{"slug": "test1", "aliasOf": "test2"}],
        "unresolvedSources": [SESSION24_LABEL],
        "strictModeWouldFail": True,
        "excludedQuestionIds": excluded_question_ids,
        "excludedQuestionIdCount": len(excluded_question_ids),
        "excludedConceptFingerprints": excluded_concept_fingerprints,
        "excludedConceptFingerprintCount": len(excluded_concept_fingerprints),
        "sourceQuestionCounts": question_counts,
        "sourceConceptFingerprintCounts": fingerprint_counts,
        "notes": [
            "Only sources with concrete repo-local question IDs contribute to the hard exclusion set.",
            "session24_nbme120_simulation is recorded as unresolved label-only evidence and contributes no concrete IDs in surrogate mode.",
            "test1 does not add new exclusions because it is an alias of test2 with identical question ordering.",
        ],
    }


def build_inputs(mode: str = DEFAULT_MODE) -> dict[str, Any]:
    if mode not in {"surrogate", "strict"}:
        raise ValueError(f"Unsupported mode: {mode}")

    index_by_id = load_qbank_index()
    inventory, decision_log, id_sources = build_taken_exam_inventory()
    exclusion_set = build_exclusion_set(index_by_id, id_sources)
    weakness_profile = derive_weakness_profile(index_by_id)

    inventory["mode"] = mode
    exclusion_set["mode"] = mode
    inventory["strictModeWouldFail"] = any(entry["blocking"] for entry in decision_log)

    if mode == "strict" and inventory["strictModeWouldFail"]:
        blocking_slugs = [entry["slug"] for entry in decision_log if entry["blocking"]]
        raise StrictModeBlocked(
            "Strict mode blocked by unresolved repo-local evidence: "
            + ", ".join(blocking_slugs)
        )

    return {
        "taken_exam_inventory": inventory,
        "exclusion_set": exclusion_set,
        "weakness_profile": weakness_profile,
        "decision_log": decision_log,
    }


def write_taken_exam_inventory(out_path: Path, payload: dict[str, Any]) -> None:
    write_json(out_path, payload)


def write_exclusion_set(out_path: Path, payload: dict[str, Any]) -> None:
    write_json(out_path, payload)


def write_weakness_profile(out_path: Path, payload: dict[str, Any]) -> None:
    write_json(out_path, payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic repo-local inputs for Nidhi TEST 3"
    )
    parser.add_argument(
        "--mode",
        choices=["surrogate", "strict"],
        default=DEFAULT_MODE,
        help="surrogate writes repo-local artifacts with explicit uncertainty; strict fails closed on unresolved evidence",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_inputs(mode=args.mode)
    write_taken_exam_inventory(
        RESEARCH_DIR / "nidhi_test3_taken_exam_inventory.json",
        payload["taken_exam_inventory"],
    )
    write_exclusion_set(
        RESEARCH_DIR / "nidhi_test3_exclusion_set.json", payload["exclusion_set"]
    )
    write_weakness_profile(
        RESEARCH_DIR / "nidhi_test3_weakness_profile.json", payload["weakness_profile"]
    )
    write_jsonl(
        RESEARCH_DIR / "nidhi_test3_decision-log.jsonl", payload["decision_log"]
    )


if __name__ == "__main__":
    main()
