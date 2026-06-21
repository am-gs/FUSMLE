#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = ROOT / "artifacts"
MANIFESTS_DIR = ARTIFACTS_DIR / "manifests"
EVALS_DIR = ARTIFACTS_DIR / "evals"
EXPORTS_DIR = ARTIFACTS_DIR / "exports"
RESEARCH_DIR = ARTIFACTS_DIR / "research"
RUNTIME_PATH = ROOT / "vercel" / "uworld-api-deploy" / "gold_runtime.json"
QBANK_INDEX_PATH = ROOT / "vercel" / "uworld-api-deploy" / "qbank_index.json"
INVENTORY_PATH = RESEARCH_DIR / "nidhi_test3_taken_exam_inventory.json"
EXCLUSION_PATH = RESEARCH_DIR / "nidhi_test3_exclusion_set.json"
WEAKNESS_PATH = RESEARCH_DIR / "nidhi_test3_weakness_profile.json"

EXAM_SLUG = "test3_nidhi_v1"
EXPORT_SLUG = "test3"
TITLE = "TEST 3 — Nidhi Personalized NBME-Style Reconstruction"
SOURCE_FORMS = ["NBME 27", "NBME 28", "NBME 29", "Form 30", "Form 31"]
SOURCE_PROXY_FORM = "NBME 120-style personalized five-form reconstruction"
TOTAL_QUESTIONS = 120
BLOCK_SIZES = [20, 20, 20, 20, 20, 20]
DIFFICULTY_TARGETS = {"easy": 23, "medium": 82, "hard": 15}
BLOCK_DIFFICULTY_TARGETS = [
    {"medium": 14, "easy": 5, "hard": 1},
    {"medium": 15, "easy": 3, "hard": 2},
    {"medium": 13, "easy": 3, "hard": 4},
    {"medium": 14, "easy": 5, "hard": 1},
    {"medium": 15, "easy": 3, "hard": 2},
    {"medium": 11, "easy": 4, "hard": 5},
]
BLOCK_IMAGE_TARGETS = [5, 5, 5, 5, 5, 5]
IMAGE_TARGET = sum(BLOCK_IMAGE_TARGETS)
BLUEPRINT = {
    "General Principles": 0.11,
    "Hemat/Lymph/Immune": 0.08,
    "Behavioral/Nervous & Special Senses": 0.11,
    "MSK/Skin": 0.08,
    "Cardiovascular": 0.09,
    "Respiratory": 0.08,
    "GI": 0.08,
    "Renal/Urinary": 0.06,
    "Reproductive/Endocrine": 0.12,
    "Multisystem": 0.19,
}
DEFAULT_MODE = "surrogate"

MANIFEST_PATH = MANIFESTS_DIR / f"{EXAM_SLUG}.json"
COVERAGE_PATH = MANIFESTS_DIR / f"{EXAM_SLUG}.coverage_report.json"
EXPLANATIONS_PATH = MANIFESTS_DIR / f"{EXAM_SLUG}.explanations.json"
EVAL_JSON_PATH = EVALS_DIR / f"{EXAM_SLUG}.json"
EVAL_MD_PATH = EVALS_DIR / f"{EXAM_SLUG}.md"
EXPORT_PATH = EXPORTS_DIR / "test3_exam.json"


class StrictModeBlocked(RuntimeError):
    pass


class SelectionFailed(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the deterministic frozen TEST 3 manifest and export for Nidhi"
    )
    parser.add_argument(
        "--mode",
        choices=["surrogate", "strict"],
        default=DEFAULT_MODE,
        help="surrogate honors the repo-local exclusion set with explicit uncertainty; strict fails closed on unresolved prior source labels",
    )
    return parser.parse_args()


def load_qbank_index() -> dict[str, dict[str, Any]]:
    payload = load_json(QBANK_INDEX_PATH)
    return {row["id"]: row for row in payload["questions"]}


def canonical_system(question: dict[str, Any]) -> str:
    return question.get("organ_system") or question.get("system") or "Multisystem"


def canonical_difficulty(question: dict[str, Any]) -> str:
    return question.get("difficulty_band") or "medium"


def has_image(question: dict[str, Any]) -> bool:
    return bool(
        question.get("image_url")
        or question.get("imageUrls")
        or question.get("image_assets")
    )


def option_letter(option: dict[str, Any], index: int) -> str:
    return option.get("letter") or chr(65 + index)


def option_text(option: dict[str, Any], index: int) -> str:
    text = option.get("text", "")
    letter = option_letter(option, index)
    prefix = f"{letter}) "
    if text.startswith(prefix):
        return text[len(prefix) :]
    return text


def image_urls(question: dict[str, Any]) -> list[str]:
    urls = question.get("imageUrls") or []
    if urls:
        return urls
    if question.get("image_url"):
        return [question["image_url"]]
    return []


def lower_source_form(question: dict[str, Any]) -> str:
    return str(question["id"]).split("_", 1)[0]


def load_inputs(mode: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    inventory = load_json(INVENTORY_PATH)
    exclusion = load_json(EXCLUSION_PATH)
    weakness = load_json(WEAKNESS_PATH)

    inventory["mode"] = mode
    exclusion["mode"] = mode

    strict_blocked = bool(
        inventory.get("strictModeWouldFail") or exclusion.get("strictModeWouldFail")
    )
    if mode == "strict" and strict_blocked:
        unresolved = exclusion.get("unresolvedSources") or [
            item.get("slug")
            for item in inventory.get("blockingUncertainties", [])
            if item.get("slug")
        ]
        raise StrictModeBlocked(
            "Strict mode blocked by unresolved repo-local source labels: "
            + ", ".join(sorted(unresolved))
        )

    return inventory, exclusion, weakness


def normalize_pool(
    exclusion: dict[str, Any],
    weakness: dict[str, Any],
    index_by_id: dict[str, dict[str, Any]],
    *,
    allow_excluded_fingerprints: bool,
) -> list[dict[str, Any]]:
    excluded_ids = set(exclusion["excludedQuestionIds"])
    excluded_fps = set(exclusion["excludedConceptFingerprints"])
    system_weights = weakness["weights"]["systems"]
    discipline_weights = weakness["weights"]["disciplines"]
    difficulty_weights = weakness["weights"]["difficulty"]

    runtime_questions = load_json(RUNTIME_PATH)
    pool: list[dict[str, Any]] = []
    for question in runtime_questions:
        if question.get("form") not in SOURCE_FORMS:
            continue
        if not question.get("exam_ready", True):
            continue
        if question["id"] in excluded_ids:
            continue

        fingerprint = question.get("concept_fingerprint")
        if (
            not allow_excluded_fingerprints
            and fingerprint
            and fingerprint in excluded_fps
        ):
            continue

        system = canonical_system(question)
        difficulty = canonical_difficulty(question)
        discipline = question.get("discipline")
        index_row = index_by_id.get(question["id"], {})
        system_weight = float(system_weights.get(system, 1.0))
        discipline_weight = float(discipline_weights.get(discipline, 1.0))
        difficulty_weight = float(difficulty_weights.get(difficulty, 1.0))

        normalized = dict(question)
        normalized.update(
            {
                "system": system,
                "difficulty": difficulty,
                "has_image": has_image(question),
                "difficulty_num": question.get("difficulty_1to5")
                or {"easy": 2, "medium": 3, "hard": 4}.get(difficulty, 3),
                "system_weight": system_weight,
                "discipline_weight": discipline_weight,
                "difficulty_weight": difficulty_weight,
                "weakness_weight": round(
                    system_weight * discipline_weight * difficulty_weight, 4
                ),
                "fingerprint_exclusion_fallback": bool(
                    allow_excluded_fingerprints
                    and fingerprint
                    and fingerprint in excluded_fps
                ),
                "source_pdf_page": index_row.get("source_pdf_page"),
                "pdf_verified": index_row.get("pdf_verified"),
            }
        )
        pool.append(normalized)

    return pool


def blueprint_base_targets() -> tuple[dict[str, float], dict[str, int]]:
    raw = {key: value * TOTAL_QUESTIONS for key, value in BLUEPRINT.items()}
    targets = {key: int(value) for key, value in raw.items()}
    remainder = TOTAL_QUESTIONS - sum(targets.values())
    for key, _ in sorted(
        raw.items(), key=lambda item: (-(item[1] - int(item[1])), item[0])
    )[:remainder]:
        targets[key] += 1
    return raw, targets


def compute_system_targets(
    availability_by_system: Counter[str],
) -> tuple[dict[str, int], dict[str, float], dict[str, int], list[dict[str, Any]]]:
    raw_targets, base_targets = blueprint_base_targets()
    adjusted_targets = dict(base_targets)
    adjustments: list[dict[str, Any]] = []

    for system in sorted(adjusted_targets):
        available = availability_by_system.get(system, 0)
        if adjusted_targets[system] > available:
            adjustments.append(
                {
                    "system": system,
                    "kind": "availability_cap",
                    "from": adjusted_targets[system],
                    "to": available,
                    "reason": "five-form post-exclusion pool cannot meet the pure blueprint-derived count",
                }
            )
            adjusted_targets[system] = available

    while sum(adjusted_targets.values()) < TOTAL_QUESTIONS:
        candidates = [
            system
            for system in adjusted_targets
            if adjusted_targets[system] < availability_by_system.get(system, 0)
        ]
        if not candidates:
            raise SelectionFailed(
                "Unable to redistribute capped blueprint targets back to 120 questions"
            )
        system = sorted(
            candidates,
            key=lambda key: (
                -(raw_targets[key] - adjusted_targets[key]),
                -(availability_by_system[key] - adjusted_targets[key]),
                key,
            ),
        )[0]
        before = adjusted_targets[system]
        adjusted_targets[system] += 1
        adjustments.append(
            {
                "system": system,
                "kind": "redistribution",
                "from": before,
                "to": adjusted_targets[system],
                "reason": "absorbs blueprint capacity displaced by capped systems while staying closest to raw Step 1 proportions",
            }
        )

    return adjusted_targets, raw_targets, base_targets, adjustments


def select_questions(
    pool: list[dict[str, Any]],
    system_targets: dict[str, int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    availability_by_system = Counter(question["system"] for question in pool)
    slots: list[str] = []
    for system, count in system_targets.items():
        slots.extend([system] * count)
    slots.sort(
        key=lambda system: (
            availability_by_system[system] - system_targets[system],
            availability_by_system[system],
            system,
        )
    )

    selected: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    used_fingerprints: set[str] = set()
    selected_difficulty = Counter()
    selected_forms = Counter()
    selected_images = 0

    for slot_system in slots:
        pick_index = len(selected) + 1
        desired_images_after_pick = round(IMAGE_TARGET * pick_index / TOTAL_QUESTIONS)
        candidates: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

        for question in pool:
            if question["id"] in used_ids:
                continue
            if question["system"] != slot_system:
                continue
            fingerprint = question.get("concept_fingerprint")
            if fingerprint and fingerprint in used_fingerprints:
                continue

            projected_images = selected_images + (1 if question["has_image"] else 0)
            difficulty = question["difficulty"]
            diff_penalty = (
                0
                if selected_difficulty[difficulty] < DIFFICULTY_TARGETS[difficulty]
                else 1
            )
            score = (
                diff_penalty,
                abs(projected_images - desired_images_after_pick),
                -question["weakness_weight"],
                selected_forms[question["form"]],
                question["difficulty_num"],
                question["id"],
            )
            candidates.append((score, question))

        candidates.sort(key=lambda item: item[0])
        if not candidates:
            raise SelectionFailed(
                f"No candidate available for system slot {slot_system}"
            )

        question = candidates[0][1]
        selected.append(question)
        used_ids.add(question["id"])
        fingerprint = question.get("concept_fingerprint")
        if fingerprint:
            used_fingerprints.add(fingerprint)
        selected_difficulty[question["difficulty"]] += 1
        selected_forms[question["form"]] += 1
        if question["has_image"]:
            selected_images += 1

    diagnostics = {
        "selectedDifficulty": dict(sorted(selected_difficulty.items())),
        "selectedForms": dict(sorted(selected_forms.items())),
        "selectedImageCount": selected_images,
    }
    return selected, slots_to_block_targets(system_targets), diagnostics


def slots_to_block_targets(system_targets: dict[str, int]) -> list[dict[str, int]]:
    block_targets = [Counter() for _ in range(6)]
    block_loads = [0] * 6
    for system, count in sorted(
        system_targets.items(), key=lambda item: (-item[1], item[0])
    ):
        for _ in range(count):
            block_index = min(
                range(6),
                key=lambda index: (
                    block_loads[index],
                    block_targets[index][system],
                    index,
                ),
            )
            block_targets[block_index][system] += 1
            block_loads[block_index] += 1
    return [dict(targets) for targets in block_targets]


def assign_blocks(
    selected_questions: list[dict[str, Any]],
    block_system_targets: list[dict[str, int]],
) -> list[list[dict[str, Any]]]:
    remaining = list(selected_questions)
    blocks: list[list[dict[str, Any]]] = []

    for block_index in range(6):
        block_questions: list[dict[str, Any]] = []
        block_difficulty = Counter()
        block_images = 0
        block_form_counts = Counter()

        slots: list[str] = []
        for system, count in block_system_targets[block_index].items():
            slots.extend([system] * count)
        slots.sort(
            key=lambda system: (
                sum(1 for question in remaining if question["system"] == system),
                system,
            )
        )

        for slot_system in slots:
            desired_images_after_pick = round(
                BLOCK_IMAGE_TARGETS[block_index] * (len(block_questions) + 1) / 20
            )
            candidates: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

            for question in remaining:
                if question["system"] != slot_system:
                    continue
                difficulty = question["difficulty"]
                diff_penalty = (
                    0
                    if block_difficulty[difficulty]
                    < BLOCK_DIFFICULTY_TARGETS[block_index][difficulty]
                    else 1
                )
                projected_images = block_images + (1 if question["has_image"] else 0)
                score = (
                    diff_penalty,
                    abs(projected_images - desired_images_after_pick),
                    -question["weakness_weight"],
                    block_form_counts[question["form"]],
                    question["difficulty_num"],
                    question["id"],
                )
                candidates.append((score, question))

            candidates.sort(key=lambda item: item[0])
            if not candidates:
                raise SelectionFailed(
                    f"Unable to fill block {block_index + 1} for system {slot_system}"
                )

            question = candidates[0][1]
            remaining.remove(question)
            block_questions.append(question)
            block_difficulty[question["difficulty"]] += 1
            block_form_counts[question["form"]] += 1
            if question["has_image"]:
                block_images += 1

        block_questions.sort(
            key=lambda question: (
                question["has_image"] is False,
                {"hard": 0, "medium": 1, "easy": 2}.get(question["difficulty"], 1),
                question["form"],
                question["id"],
            )
        )
        blocks.append(block_questions)

    if remaining:
        raise SelectionFailed(
            f"Block assignment left {len(remaining)} unassigned items"
        )
    return blocks


def question_selection_rationale(question: dict[str, Any]) -> str:
    if question["fingerprint_exclusion_fallback"]:
        return "concept-fingerprint-fallback"
    if question["weakness_weight"] > 1.0:
        return "weakness-weighted-blueprint-fit"
    return "blueprint-fit"


def question_selection_details(
    question: dict[str, Any], exam_position: int, block_item: int
) -> dict[str, Any]:
    return {
        "examPosition": exam_position,
        "blockItem": block_item,
        "form": question["form"],
        "broadSystem": question["system"],
        "difficultyBand": question["difficulty"],
        "difficulty1to5": question["difficulty_num"],
        "hasImage": question["has_image"],
        "discipline": question.get("discipline"),
        "conceptFingerprint": question.get("concept_fingerprint"),
        "pdfVerified": question.get("pdf_verified"),
        "sourcePdfPage": question.get("source_pdf_page"),
        "weaknessWeight": question["weakness_weight"],
        "weaknessComponents": {
            "system": question["system_weight"],
            "discipline": question["discipline_weight"],
            "difficulty": question["difficulty_weight"],
        },
        "fingerprintExclusionFallback": question["fingerprint_exclusion_fallback"],
    }


def build_manifest(
    blocks: list[list[dict[str, Any]]],
    inventory: dict[str, Any],
    exclusion: dict[str, Any],
    weak_profile: dict[str, Any],
    raw_blueprint_targets: dict[str, float],
    base_system_targets: dict[str, int],
    adjusted_system_targets: dict[str, int],
) -> dict[str, Any]:
    manifest_blocks: list[dict[str, Any]] = []
    absolute_index = 0

    for block_number, block in enumerate(blocks, start=1):
        rationale_by_question: dict[str, str] = {}
        detail_by_question: dict[str, Any] = {}
        for block_item, question in enumerate(block, start=1):
            absolute_index += 1
            rationale_by_question[question["id"]] = question_selection_rationale(
                question
            )
            detail_by_question[question["id"]] = question_selection_details(
                question, absolute_index, block_item
            )

        manifest_blocks.append(
            {
                "block": block_number,
                "timeLimitMinutes": 30,
                "questionIds": [question["id"] for question in block],
                "selection_rationale_by_question": rationale_by_question,
                "selection_details_by_question": detail_by_question,
            }
        )

    all_questions = [question for block in blocks for question in block]
    return {
        "exam_slug": EXAM_SLUG,
        "title": TITLE,
        "strategy": "deterministic_fixed_manifest",
        "manifest_version": 1,
        "mode": exclusion["mode"],
        "strict_mode_blocked_by_unresolved_sources": bool(
            exclusion.get("strictModeWouldFail")
        ),
        "source_forms": SOURCE_FORMS,
        "source_proxy_form": SOURCE_PROXY_FORM,
        "selection_basis": "personalized_blueprint_reconstruction",
        "selection_inputs": {
            "inventory_artifact": str(INVENTORY_PATH.relative_to(ROOT)),
            "exclusion_artifact": str(EXCLUSION_PATH.relative_to(ROOT)),
            "weakness_artifact": str(WEAKNESS_PATH.relative_to(ROOT)),
            "unresolved_sources": exclusion.get("unresolvedSources", []),
            "strict_mode_would_fail": bool(exclusion.get("strictModeWouldFail")),
        },
        "blueprint_targets": {
            "raw_counts": {
                key: round(value, 2) for key, value in raw_blueprint_targets.items()
            },
            "base_integer_targets": base_system_targets,
            "adjusted_targets": adjusted_system_targets,
            "difficulty_targets": DIFFICULTY_TARGETS,
            "block_difficulty_targets": BLOCK_DIFFICULTY_TARGETS,
            "block_image_targets": BLOCK_IMAGE_TARGETS,
        },
        "total_questions": len(all_questions),
        "block_sizes": [len(block) for block in blocks],
        "blocks": manifest_blocks,
    }


def build_explanations(blocks: list[list[dict[str, Any]]], mode: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    exam_position = 0
    for block_number, block in enumerate(blocks, start=1):
        for block_item, question in enumerate(block, start=1):
            exam_position += 1
            weakness_components = []
            if question["system_weight"] > 1.0:
                weakness_components.append(f"system {question['system']}")
            if question["discipline_weight"] > 1.0:
                weakness_components.append(f"discipline {question.get('discipline')}")
            if question["difficulty_weight"] > 1.0:
                weakness_components.append(f"difficulty {question['difficulty']}")

            if question["fingerprint_exclusion_fallback"]:
                summary = "Selected only as a documented concept-fingerprint fallback after the hard ID exclusions made the strict concept filter insufficient."
            elif weakness_components:
                summary = (
                    "Selected as a blueprint-fit item with bounded weakness weighting applied via "
                    + ", ".join(weakness_components)
                    + "."
                )
            else:
                summary = "Selected as a deterministic blueprint-fit item from the allowed five-form pool without needing concept fallback."

            items.append(
                {
                    "examPosition": exam_position,
                    "block": block_number,
                    "blockItem": block_item,
                    "questionId": question["id"],
                    "rationale": question_selection_rationale(question),
                    "summary": summary,
                    "system": question["system"],
                    "discipline": question.get("discipline"),
                    "difficulty": question["difficulty"],
                    "hasImage": question["has_image"],
                    "sourceForm": question["form"],
                    "conceptFingerprint": question.get("concept_fingerprint"),
                    "weaknessWeight": question["weakness_weight"],
                    "weaknessComponents": {
                        "system": question["system_weight"],
                        "discipline": question["discipline_weight"],
                        "difficulty": question["difficulty_weight"],
                    },
                    "fingerprintExclusionFallback": question[
                        "fingerprint_exclusion_fallback"
                    ],
                }
            )

    return {
        "exam_slug": EXAM_SLUG,
        "mode": mode,
        "notes": [
            "This artifact explains personalized blueprint-fit selection rationale only; it does not claim exact source recovery for any slot.",
            "Surrogate mode is acceptable for this repo-local build only because the unresolved prior simulation label is surfaced explicitly elsewhere in the artifacts.",
        ],
        "items": items,
    }


def find_duplicate_fingerprints(
    all_questions: list[dict[str, Any]],
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for question in all_questions:
        fingerprint = question.get("concept_fingerprint")
        if not fingerprint:
            continue
        grouped.setdefault(fingerprint, []).append(question["id"])
    return {
        fingerprint: ids for fingerprint, ids in sorted(grouped.items()) if len(ids) > 1
    }


def summarize_block(block: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "questionCount": len(block),
        "systemCounts": dict(sorted(Counter(q["system"] for q in block).items())),
        "difficultyCounts": dict(
            sorted(Counter(q["difficulty"] for q in block).items())
        ),
        "imageCount": sum(1 for question in block if question["has_image"]),
        "forms": dict(sorted(Counter(q["form"] for q in block).items())),
    }


def build_coverage_report(
    blocks: list[list[dict[str, Any]]],
    inventory: dict[str, Any],
    exclusion: dict[str, Any],
    weak_profile: dict[str, Any],
    pool_without_fallbacks: list[dict[str, Any]],
    pool_with_fallbacks: list[dict[str, Any]],
    raw_blueprint_targets: dict[str, float],
    base_system_targets: dict[str, int],
    adjusted_system_targets: dict[str, int],
    target_adjustments: list[dict[str, Any]],
    selection_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    all_questions = [question for block in blocks for question in block]
    all_ids = [question["id"] for question in all_questions]
    all_fingerprints = [
        question.get("concept_fingerprint")
        for question in all_questions
        if question.get("concept_fingerprint")
    ]
    duplicate_fingerprints = find_duplicate_fingerprints(all_questions)
    excluded_id_overlap = sorted(set(all_ids) & set(exclusion["excludedQuestionIds"]))
    excluded_fp_overlap = sorted(
        set(all_fingerprints) & set(exclusion["excludedConceptFingerprints"])
    )
    fallback_questions = [
        question["id"]
        for question in all_questions
        if question["fingerprint_exclusion_fallback"]
    ]

    system_counts = Counter(question["system"] for question in all_questions)
    difficulty_counts = Counter(question["difficulty"] for question in all_questions)
    form_counts = Counter(question["form"] for question in all_questions)
    image_count = sum(1 for question in all_questions if question["has_image"])
    pdf_verified_count = sum(
        1 for question in all_questions if question.get("pdf_verified")
    )
    weak_weighted_count = sum(
        1 for question in all_questions if question["weakness_weight"] > 1.0
    )

    availability_without_fallbacks = Counter(
        question["system"] for question in pool_without_fallbacks
    )
    availability_with_fallbacks = Counter(
        question["system"] for question in pool_with_fallbacks
    )

    integrity_checks = {
        "totalQuestionCount": len(all_questions) == TOTAL_QUESTIONS,
        "uniqueQuestionIds": len(set(all_ids)) == TOTAL_QUESTIONS,
        "blockSizes": [len(block) for block in blocks] == BLOCK_SIZES,
        "sourceFormsRestricted": all(
            question["form"] in SOURCE_FORMS for question in all_questions
        ),
        "excludedQuestionIdOverlap": len(excluded_id_overlap) == 0,
        "conceptFingerprintDuplicatesWithinManifest": len(duplicate_fingerprints) == 0,
        "excludedConceptFingerprintFallbackLogged": len(excluded_fp_overlap)
        == len(fallback_questions),
    }

    return {
        "exam_slug": EXAM_SLUG,
        "mode": exclusion["mode"],
        "selectionStatus": "surrogate_repo_local"
        if exclusion["mode"] == "surrogate"
        else "strict",
        "strictModeWouldFail": bool(exclusion.get("strictModeWouldFail")),
        "constraints": {
            "sourceForms": SOURCE_FORMS,
            "totalQuestions": TOTAL_QUESTIONS,
            "blockSizes": BLOCK_SIZES,
            "hardExcludedQuestionIds": exclusion.get("excludedQuestionIdCount"),
            "hardExcludedConceptFingerprints": exclusion.get(
                "excludedConceptFingerprintCount"
            ),
            "unresolvedPriorSourceLabels": exclusion.get("unresolvedSources", []),
            "weaknessProfileSourceSessions": weak_profile.get("sourceSessions", []),
        },
        "availability": {
            "postIdAndConceptExclusionPoolSize": len(pool_without_fallbacks),
            "postIdOnlyPoolSize": len(pool_with_fallbacks),
            "bySystemWithoutFallback": dict(
                sorted(availability_without_fallbacks.items())
            ),
            "bySystemWithFallback": dict(sorted(availability_with_fallbacks.items())),
        },
        "targets": {
            "rawBlueprintCounts": {
                key: round(value, 2) for key, value in raw_blueprint_targets.items()
            },
            "baseIntegerTargets": base_system_targets,
            "adjustedSystemTargets": adjusted_system_targets,
            "difficultyTargets": DIFFICULTY_TARGETS,
            "blockDifficultyTargets": BLOCK_DIFFICULTY_TARGETS,
            "blockImageTargets": BLOCK_IMAGE_TARGETS,
            "imageTarget": IMAGE_TARGET,
        },
        "adjustments": target_adjustments,
        "actual": {
            "systemCounts": dict(sorted(system_counts.items())),
            "difficultyCounts": dict(sorted(difficulty_counts.items())),
            "formCounts": dict(sorted(form_counts.items())),
            "imageCount": image_count,
            "pdfVerifiedCount": pdf_verified_count,
            "weaknessWeightedQuestionCount": weak_weighted_count,
            "selectionDiagnostics": selection_diagnostics,
            "perBlock": [summarize_block(block) for block in blocks],
        },
        "integrity": {
            "uniqueQuestionIdCount": len(set(all_ids)),
            "duplicateQuestionIdLeakage": TOTAL_QUESTIONS - len(set(all_ids)),
            "duplicateFingerprints": duplicate_fingerprints,
            "excludedQuestionIdOverlap": excluded_id_overlap,
            "excludedConceptFingerprintOverlap": excluded_fp_overlap,
            "conceptFingerprintFallbackQuestionIds": fallback_questions,
            "conceptFingerprintFallbackCount": len(fallback_questions),
            "strictModeBlockingLabels": inventory.get("blockingUncertainties", []),
            "checks": integrity_checks,
        },
        "notes": [
            "All 120 slots are personalized deterministic blueprint-fit selections from the allowed five-form pool; this artifact makes no exact-recovery claim for any slot.",
            "The starting Step 1 blueprint target was capped only where availability forced it, most notably Multisystem after the post-exclusion pool fell to 21 items.",
            "Any prior concept-fingerprint overlap would have been logged explicitly as a fallback. This build should remain at zero unless the five-form pool becomes insufficient.",
        ],
    }


def correct_answer_payload(question: dict[str, Any]) -> dict[str, Any]:
    correct_id = question.get("correct_answer")
    for index, option in enumerate(question.get("options", [])):
        if option.get("id") == correct_id:
            return {"index": correct_id, "letter": option_letter(option, index)}
    return {"index": correct_id, "letter": "?"}


def export_item(
    question: dict[str, Any], exam_position: int, block_item: int
) -> dict[str, Any]:
    return {
        "examPosition": exam_position,
        "blockItem": block_item,
        "id": question["id"],
        "sourceForm": lower_source_form(question),
        "subject": question.get("subject"),
        "system": question["system"],
        "discipline": question.get("discipline"),
        "difficulty": question["difficulty"],
        "stem": question.get("text", ""),
        "options": [
            {
                "letter": option_letter(option, index),
                "text": option.get("text", ""),
            }
            for index, option in enumerate(question.get("options", []))
        ],
        "correctAnswer": correct_answer_payload(question),
        "explanation": question.get("explanation", ""),
        "images": image_urls(question),
        "renderingFlag": None,
    }


def build_export(
    blocks: list[list[dict[str, Any]]], coverage_report: dict[str, Any]
) -> dict[str, Any]:
    all_questions = [question for block in blocks for question in block]
    system_counts = Counter(question["system"] for question in all_questions)
    difficulty_counts = Counter(question["difficulty"] for question in all_questions)
    form_counts = Counter(lower_source_form(question) for question in all_questions)

    export_blocks: list[dict[str, Any]] = []
    exam_position = 0
    for block_number, block in enumerate(blocks, start=1):
        items = []
        for block_item, question in enumerate(block, start=1):
            exam_position += 1
            items.append(export_item(question, exam_position, block_item))
        export_blocks.append(
            {
                "block": block_number,
                "blockSize": len(block),
                "questionIds": [question["id"] for question in block],
                "items": items,
            }
        )

    return {
        "exam": {
            "slug": EXPORT_SLUG,
            "title": TITLE,
            "manifestSlug": EXAM_SLUG,
            "manifestVersion": 1,
            "strategy": "deterministic_fixed_manifest",
            "sourceForms": SOURCE_FORMS,
            "sourceProxyForm": SOURCE_PROXY_FORM,
            "mode": coverage_report["mode"],
            "strictModeWouldFail": coverage_report["strictModeWouldFail"],
            "unresolvedSourceLabels": coverage_report["constraints"][
                "unresolvedPriorSourceLabels"
            ],
            "totalQuestions": TOTAL_QUESTIONS,
            "blockCount": 6,
            "blockSizes": BLOCK_SIZES,
            "timed": True,
        },
        "summary": {
            "totalQuestions": TOTAL_QUESTIONS,
            "uniqueQuestions": len({question["id"] for question in all_questions}),
            "imageQuestions": sum(
                1 for question in all_questions if question["has_image"]
            ),
            "flaggedQuestions": 0,
            "bySourceForm": dict(sorted(form_counts.items())),
            "byDifficulty": dict(sorted(difficulty_counts.items())),
            "bySystem": dict(sorted(system_counts.items())),
            "conceptFingerprintFallbackCount": coverage_report["integrity"][
                "conceptFingerprintFallbackCount"
            ],
        },
        "blocks": export_blocks,
    }


def build_eval_json(
    coverage_report: dict[str, Any],
    manifest: dict[str, Any],
    export_payload: dict[str, Any],
) -> dict[str, Any]:
    checks = [
        {
            "name": "manifest_slug",
            "passed": manifest["exam_slug"] == EXAM_SLUG,
            "actual": manifest["exam_slug"],
            "expected": EXAM_SLUG,
        },
        {
            "name": "block_sizes",
            "passed": manifest["block_sizes"] == BLOCK_SIZES,
            "actual": manifest["block_sizes"],
            "expected": BLOCK_SIZES,
        },
        {
            "name": "total_questions",
            "passed": manifest["total_questions"] == TOTAL_QUESTIONS,
            "actual": manifest["total_questions"],
            "expected": TOTAL_QUESTIONS,
        },
        {
            "name": "export_exam_slug",
            "passed": export_payload["exam"]["slug"] == EXPORT_SLUG,
            "actual": export_payload["exam"]["slug"],
            "expected": EXPORT_SLUG,
        },
        {
            "name": "excluded_question_overlap",
            "passed": not coverage_report["integrity"]["excludedQuestionIdOverlap"],
            "actual": coverage_report["integrity"]["excludedQuestionIdOverlap"],
            "expected": [],
        },
        {
            "name": "duplicate_fingerprints",
            "passed": not coverage_report["integrity"]["duplicateFingerprints"],
            "actual": coverage_report["integrity"]["duplicateFingerprints"],
            "expected": {},
        },
        {
            "name": "concept_fallback_count",
            "passed": coverage_report["integrity"]["conceptFingerprintFallbackCount"]
            == 0,
            "actual": coverage_report["integrity"]["conceptFingerprintFallbackCount"],
            "expected": 0,
        },
    ]

    passed = all(check["passed"] for check in checks)
    return {
        "exam_slug": EXAM_SLUG,
        "status": "pass" if passed else "fail",
        "mode": coverage_report["mode"],
        "strictModeWouldFail": coverage_report["strictModeWouldFail"],
        "checks": checks,
        "summary": {
            "systemCounts": coverage_report["actual"]["systemCounts"],
            "difficultyCounts": coverage_report["actual"]["difficultyCounts"],
            "imageCount": coverage_report["actual"]["imageCount"],
            "conceptFingerprintFallbackCount": coverage_report["integrity"][
                "conceptFingerprintFallbackCount"
            ],
            "unresolvedSourceLabels": coverage_report["constraints"][
                "unresolvedPriorSourceLabels"
            ],
        },
        "notes": [
            "This eval is artifact-level only; backend/frontend wiring is intentionally out of scope for Task 3.",
            "Surrogate mode is clearly labeled so later routing can decide whether to ship or gate on stricter evidence.",
        ],
    }


def build_eval_markdown(
    eval_json: dict[str, Any], coverage_report: dict[str, Any]
) -> str:
    lines = [
        f"# {EXAM_SLUG} eval",
        "",
        f"- Status: **{eval_json['status']}**",
        f"- Mode: `{eval_json['mode']}`",
        f"- Strict mode would fail: `{eval_json['strictModeWouldFail']}`",
        f"- Total questions: `{TOTAL_QUESTIONS}`",
        f"- Block sizes: `{BLOCK_SIZES}`",
        "",
        "## Constraint summary",
        "",
        f"- Source forms: {', '.join(SOURCE_FORMS)}",
        f"- Hard excluded question IDs: `{coverage_report['constraints']['hardExcludedQuestionIds']}`",
        f"- Hard excluded concept fingerprints: `{coverage_report['constraints']['hardExcludedConceptFingerprints']}`",
        f"- Unresolved prior source labels: `{coverage_report['constraints']['unresolvedPriorSourceLabels']}`",
        "",
        "## Distribution",
        "",
        f"- Systems: `{coverage_report['actual']['systemCounts']}`",
        f"- Difficulty: `{coverage_report['actual']['difficultyCounts']}`",
        f"- Images: `{coverage_report['actual']['imageCount']}`",
        f"- Forms: `{coverage_report['actual']['formCounts']}`",
        "",
        "## Integrity",
        "",
        f"- Duplicate question ID leakage: `{coverage_report['integrity']['duplicateQuestionIdLeakage']}`",
        f"- Duplicate concept fingerprints: `{len(coverage_report['integrity']['duplicateFingerprints'])}` groups",
        f"- Excluded question ID overlap: `{len(coverage_report['integrity']['excludedQuestionIdOverlap'])}`",
        f"- Prior concept-fingerprint fallback count: `{coverage_report['integrity']['conceptFingerprintFallbackCount']}`",
        "",
        "## Checks",
        "",
    ]
    for check in eval_json["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        lines.append(f"- {status} `{check['name']}`")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This build is a personalized deterministic reconstruction, not an exact named-form recovery.",
            "- The Step 1 blueprint was adjusted minimally after Multisystem availability dropped below the raw target in the post-exclusion five-form pool.",
            "- Any future non-zero concept fallback should be treated as a review trigger before routing is wired.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_artifacts(
    manifest: dict[str, Any],
    coverage_report: dict[str, Any],
    export_payload: dict[str, Any],
) -> None:
    if manifest["exam_slug"] != EXAM_SLUG:
        raise SelectionFailed("Manifest slug mismatch")
    if manifest["block_sizes"] != BLOCK_SIZES:
        raise SelectionFailed("Manifest block sizes are not 6x20")
    if manifest["total_questions"] != TOTAL_QUESTIONS:
        raise SelectionFailed("Manifest total question count is not 120")
    if export_payload["exam"]["slug"] != EXPORT_SLUG:
        raise SelectionFailed("Export slug mismatch")
    if coverage_report["integrity"]["excludedQuestionIdOverlap"]:
        raise SelectionFailed("Manifest leaked an excluded question ID")
    if coverage_report["integrity"]["duplicateFingerprints"]:
        raise SelectionFailed("Manifest leaked duplicate concept fingerprints")
    if coverage_report["integrity"]["duplicateQuestionIdLeakage"]:
        raise SelectionFailed("Manifest leaked duplicate question IDs")


def build_test3_manifest(mode: str = DEFAULT_MODE) -> dict[str, Any]:
    inventory, exclusion, weakness = load_inputs(mode)
    index_by_id = load_qbank_index()

    pool_without_fallbacks = normalize_pool(
        exclusion,
        weakness,
        index_by_id,
        allow_excluded_fingerprints=False,
    )
    pool_with_fallbacks = normalize_pool(
        exclusion,
        weakness,
        index_by_id,
        allow_excluded_fingerprints=True,
    )

    availability_by_system = Counter(
        question["system"] for question in pool_without_fallbacks
    )
    (
        adjusted_system_targets,
        raw_blueprint_targets,
        base_system_targets,
        target_adjustments,
    ) = compute_system_targets(availability_by_system)

    try:
        selected_questions, block_system_targets, selection_diagnostics = (
            select_questions(pool_without_fallbacks, adjusted_system_targets)
        )
    except SelectionFailed:
        selected_questions, block_system_targets, selection_diagnostics = (
            select_questions(pool_with_fallbacks, adjusted_system_targets)
        )

    blocks = assign_blocks(selected_questions, block_system_targets)
    manifest = build_manifest(
        blocks,
        inventory,
        exclusion,
        weakness,
        raw_blueprint_targets,
        base_system_targets,
        adjusted_system_targets,
    )
    explanations = build_explanations(blocks, mode)
    coverage_report = build_coverage_report(
        blocks,
        inventory,
        exclusion,
        weakness,
        pool_without_fallbacks,
        pool_with_fallbacks,
        raw_blueprint_targets,
        base_system_targets,
        adjusted_system_targets,
        target_adjustments,
        selection_diagnostics,
    )
    export_payload = build_export(blocks, coverage_report)
    eval_json = build_eval_json(coverage_report, manifest, export_payload)
    eval_markdown = build_eval_markdown(eval_json, coverage_report)

    validate_artifacts(manifest, coverage_report, export_payload)

    return {
        "manifest": manifest,
        "coverage_report": coverage_report,
        "explanations": explanations,
        "eval_json": eval_json,
        "eval_markdown": eval_markdown,
        "export_payload": export_payload,
    }


def export_test3_exam(mode: str = DEFAULT_MODE) -> dict[str, Any]:
    return build_test3_manifest(mode=mode)["export_payload"]


def main() -> None:
    args = parse_args()
    payload = build_test3_manifest(mode=args.mode)
    write_json(MANIFEST_PATH, payload["manifest"])
    write_json(COVERAGE_PATH, payload["coverage_report"])
    write_json(EXPLANATIONS_PATH, payload["explanations"])
    write_json(EVAL_JSON_PATH, payload["eval_json"])
    EVAL_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVAL_MD_PATH.write_text(payload["eval_markdown"])
    write_json(EXPORT_PATH, payload["export_payload"])


if __name__ == "__main__":
    main()
