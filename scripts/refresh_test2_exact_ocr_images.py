#!/usr/bin/env python3
import json
import re
from pathlib import Path

from import_paddleocr_question_images import (
    IMAGES_CROP_DIR,
    GOLD_RUNTIME,
    IMAGE_MANIFEST,
    build_output_name,
    ffmpeg_convert_to_webp,
    ffprobe_dimensions,
    normalize_text,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST2_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "june2026_nbme120_candidate.json"
OCR_JSON = Path("/home/FORMS-27-33-REDUCED.pdf_by_PaddleOCR-VL-1.6.json")
DOWNLOAD_MANIFEST = REPO_ROOT / "artifacts" / "ocr_assets" / "download_manifest.json"
RAW_CACHE_DIR = Path("/home/ocr_download_cache/raw_1781770145")
REPORT_PATH = REPO_ROOT / "artifacts" / "qc" / "test2_exact_ocr_refresh_report.json"

MAX_REF_OVERRIDES = {
    "form31_page-96": 2,
}

FLAGGED_REVIEW_IDS = [
    "form31_page-43",
    "nbme28_q0156",
    "form31_page-100",
    "nbme29_q0193",
    "form31_page-117",
    "nbme27_page-106",
    "form31_page-104",
    "form31_page-96",
    "nbme29_q0025",
    "form31_page-12",
    "form30_page-105",
    "form30_page-12",
    "form31_page-158",
    "form31_page-42",
    "nbme27_page-127",
    "nbme27_page-158",
    "nbme28_q0014",
    "nbme29_q0072",
    "form31_page-107",
    "form31_page-127",
    "nbme27_page-135",
    "nbme29_q0092",
    "form31_page-171",
    "form31_page-25",
    "nbme29_q0128",
]


def build_download_lookup():
    manifest = json.loads(DOWNLOAD_MANIFEST.read_text())
    lookup = {}
    for entry in manifest["results"]:
        if entry.get("status") not in {"downloaded", "cached"} or not entry.get("path"):
            continue
        original = Path(entry["path"])
        candidates = [original, RAW_CACHE_DIR / original.name]
        for candidate in candidates:
            if candidate.is_file():
                lookup[entry["url"]] = candidate
                break
    return lookup


def extract_referenced_urls(row):
    markdown = row.get("markdown", {})
    image_map = markdown.get("images") or {}
    refs = re.findall(r'<img src="([^"]+)"', markdown.get("text", ""))
    urls = [image_map[ref] for ref in refs if ref in image_map]
    return urls


def build_test2_ids():
    manifest = json.loads(TEST2_MANIFEST.read_text())
    return [question_id for block in manifest["blocks"] for question_id in block["questionIds"]]


def find_exact_row_indices(ocr_rows):
    normalized_rows = [normalize_text(row.get("markdown", {}).get("text", "")) for row in ocr_rows]
    question_rows = {}
    questions = json.loads(GOLD_RUNTIME.read_text())
    question_by_id = {question["id"]: question for question in questions}
    for question_id in build_test2_ids():
        question = question_by_id[question_id]
        current_images = question.get("imageUrls") or ([question["image_url"]] if question.get("image_url") else [])
        if not current_images:
            continue
        needle = normalize_text(question.get("text", ""))[:140]
        hits = [idx for idx, row_text in enumerate(normalized_rows) if needle and needle in row_text]
        if len(hits) == 1:
            question_rows[question_id] = hits[0]
    return question_rows


def main():
    questions = json.loads(GOLD_RUNTIME.read_text())
    question_by_id = {question["id"]: question for question in questions}
    image_manifest = json.loads(IMAGE_MANIFEST.read_text())
    ocr_rows = json.loads(OCR_JSON.read_text())
    downloads = build_download_lookup()
    exact_rows = find_exact_row_indices(ocr_rows)

    refreshed = []
    flagged = []

    for question_id, row_idx in exact_rows.items():
        row = ocr_rows[row_idx]
        source_urls = extract_referenced_urls(row)
        if not source_urls:
            continue
        if question_id in MAX_REF_OVERRIDES:
            source_urls = source_urls[: MAX_REF_OVERRIDES[question_id]]

        assets = []
        for index, source_url in enumerate(source_urls):
            raw_path = downloads.get(source_url)
            if not raw_path or not raw_path.is_file():
                raise FileNotFoundError(f"missing OCR raw asset for {question_id}: {source_url}")
            output_name = build_output_name(question_id, index, len(source_urls))
            output_path = IMAGES_CROP_DIR / output_name
            ffmpeg_convert_to_webp(raw_path, output_path)
            width, height = ffprobe_dimensions(output_path)
            assets.append(
                {
                    "category": "ocr_exact_test2",
                    "label": f"exact_ocr_test2_asset_{index + 1}",
                    "ocr_row_index": row_idx,
                    "source_url": source_url,
                    "url": f"/api/images_crop/{output_name}",
                    "width": width,
                    "height": height,
                }
            )

        question = question_by_id[question_id]
        if question.get("imageUrls") != [asset["url"] for asset in assets]:
            question["imageUrls"] = [asset["url"] for asset in assets]
            question["image_url"] = assets[0]["url"]
            question["image_assets"] = assets
            image_manifest[question_id] = assets
            refreshed.append(
                {
                    "question_id": question_id,
                    "ocr_row_index": row_idx,
                    "asset_count": len(assets),
                    "urls": [asset["url"] for asset in assets],
                }
            )

    for question_id in FLAGGED_REVIEW_IDS:
        row_idx = exact_rows.get(question_id)
        source_urls = extract_referenced_urls(ocr_rows[row_idx]) if row_idx is not None else []
        flagged.append(
            {
                "question_id": question_id,
                "exact_ocr_row_index": row_idx,
                "exact_ocr_referenced_images": len(source_urls),
                "status": "refreshed" if any(item["question_id"] == question_id for item in refreshed) else "manual_review_needed",
            }
        )

    GOLD_RUNTIME.write_text(json.dumps(questions, indent=2))
    IMAGE_MANIFEST.write_text(json.dumps(image_manifest, indent=2))
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(
            {
                "refreshed_questions": refreshed,
                "flagged_questions": flagged,
                "summary": {
                    "refreshed_count": len(refreshed),
                    "flagged_count": len(flagged),
                    "still_flagged_count": sum(1 for item in flagged if item["status"] != "refreshed"),
                },
            },
            indent=2,
        )
    )
    print(json.dumps({"refreshed_count": len(refreshed), "still_flagged_count": sum(1 for item in flagged if item["status"] != "refreshed")}, indent=2))


if __name__ == "__main__":
    main()
