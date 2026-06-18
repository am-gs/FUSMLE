#!/usr/bin/env python3
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "vercel" / "uworld-api-deploy"
OCR_MARKDOWN = Path("/home/FORMS-27-33-REDUCED.pdf_by_PaddleOCR-VL-1.6.md")
DOWNLOAD_MANIFEST = REPO_ROOT / "artifacts" / "ocr_assets" / "download_manifest.json"
GOLD_RUNTIME = API_DIR / "gold_runtime.json"
IMAGE_MANIFEST = API_DIR / "image_manifest.json"
IMAGES_CROP_DIR = API_DIR / "images_crop"
REPORT_PATH = REPO_ROOT / "artifacts" / "qbank" / "paddleocr_image_import_report.json"
TARGET_PREFIXES = ("nbme27", "nbme28", "nbme29", "form30", "form31")
NEEDLE_WORDS = 18
MAX_IMAGES_PER_MATCH = 4


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = (
        text.replace("α", "a")
        .replace("β", "b")
        .replace("μ", "u")
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
    )
    text = re.sub(r"\$[^$]*\$", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_chunks(markdown_text: str):
    chunks = []
    for part in re.split(r"(?m)^(?=\d+\.\s)", markdown_text):
        match = re.match(r"(?m)^(\d+)\.\s", part)
        if not match:
            continue
        chunks.append(
            {
                "question_number": int(match.group(1)),
                "text": part,
                "normalized": normalize_text(part),
                "image_urls": re.findall(r'<img src="([^"]+)"', part),
            }
        )
    return chunks


def build_download_lookup():
    manifest = json.loads(DOWNLOAD_MANIFEST.read_text())
    return {
        entry["url"]: Path(entry["path"])
        for entry in manifest["results"]
        if entry.get("status") in {"downloaded", "cached"} and entry.get("path")
    }


def compute_prefix_windows(questions, chunks):
    windows = {}
    by_prefix = defaultdict(list)
    for question in questions:
        prefix = question["id"].split("_")[0]
        if prefix not in TARGET_PREFIXES:
            continue
        stem_words = normalize_text(question.get("text", "")).split()
        needle = " ".join(stem_words[:NEEDLE_WORDS])
        if not needle:
            continue
        hits = [idx for idx, chunk in enumerate(chunks) if needle in chunk["normalized"]]
        if len(hits) == 1:
            by_prefix[prefix].append(hits[0])
    for prefix, indices in by_prefix.items():
        windows[prefix] = (min(indices), max(indices))
    return windows


def ffmpeg_convert_to_webp(src: Path, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-vf",
            "format=rgba",
            str(dest),
        ],
        check=True,
    )


def ffprobe_dimensions(path: Path):
    output = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    data = json.loads(output)
    stream = (data.get("streams") or [{}])[0]
    return int(stream.get("width") or 0), int(stream.get("height") or 0)


def build_output_name(question_id: str, index: int, total: int):
    if total == 1:
        return f"{question_id}_ocr.webp"
    return f"{question_id}_ocr{index + 1:02d}.webp"


def main():
    questions = json.loads(GOLD_RUNTIME.read_text())
    question_by_id = {question["id"]: question for question in questions}
    image_manifest = json.loads(IMAGE_MANIFEST.read_text())
    chunks = build_chunks(OCR_MARKDOWN.read_text())
    downloads = build_download_lookup()
    prefix_windows = compute_prefix_windows(questions, chunks)

    report = {
        "source_markdown": str(OCR_MARKDOWN),
        "download_manifest": str(DOWNLOAD_MANIFEST),
        "chunk_count": len(chunks),
        "prefix_windows": prefix_windows,
        "updated_questions": [],
        "skipped_questions": [],
        "summary": {},
    }

    updated_count = 0
    imported_assets = 0
    existing_replacements = 0
    new_asset_questions = 0

    for question in questions:
        prefix = question["id"].split("_")[0]
        if prefix not in TARGET_PREFIXES or prefix not in prefix_windows:
            continue

        stem_words = normalize_text(question.get("text", "")).split()
        needle = " ".join(stem_words[:NEEDLE_WORDS])
        if not needle:
            report["skipped_questions"].append({"question_id": question["id"], "reason": "empty_stem"})
            continue

        start, end = prefix_windows[prefix]
        hits = [
            idx
            for idx in range(start, end + 1)
            if needle in chunks[idx]["normalized"]
        ]

        if len(hits) != 1:
            report["skipped_questions"].append(
                {
                    "question_id": question["id"],
                    "reason": "non_unique_chunk_match",
                    "hits": hits[:10],
                }
            )
            continue

        chunk_idx = hits[0]
        chunk = chunks[chunk_idx]
        if not chunk["image_urls"]:
            report["skipped_questions"].append(
                {"question_id": question["id"], "reason": "matched_chunk_has_no_images", "chunk_idx": chunk_idx}
            )
            continue

        if len(chunk["image_urls"]) > MAX_IMAGES_PER_MATCH:
            report["skipped_questions"].append(
                {
                    "question_id": question["id"],
                    "reason": "chunk_image_count_too_high",
                    "chunk_idx": chunk_idx,
                    "image_count": len(chunk["image_urls"]),
                }
            )
            continue

        assets = []
        for index, source_url in enumerate(chunk["image_urls"]):
            raw_path = downloads.get(source_url)
            if not raw_path or not raw_path.is_file():
                raise FileNotFoundError(f"missing downloaded OCR asset for {question['id']}: {source_url}")
            output_name = build_output_name(question["id"], index, len(chunk["image_urls"]))
            output_path = IMAGES_CROP_DIR / output_name
            ffmpeg_convert_to_webp(raw_path, output_path)
            width, height = ffprobe_dimensions(output_path)
            assets.append(
                {
                    "category": "ocr_extract",
                    "label": f"paddleocr_form_asset_{index + 1}",
                    "source_chunk_index": chunk_idx,
                    "source_question_number": chunk["question_number"],
                    "source_url": source_url,
                    "url": f"/api/images_crop/{output_name}",
                    "width": width,
                    "height": height,
                }
            )

        prior_asset_count = len(question.get("imageUrls") or [])
        if prior_asset_count:
            existing_replacements += 1
        else:
            new_asset_questions += 1

        question["imageUrls"] = [asset["url"] for asset in assets]
        question["image_url"] = assets[0]["url"]
        question["image_assets"] = assets
        image_manifest[question["id"]] = assets

        updated_count += 1
        imported_assets += len(assets)
        report["updated_questions"].append(
            {
                "question_id": question["id"],
                "chunk_idx": chunk_idx,
                "chunk_question_number": chunk["question_number"],
                "previous_asset_count": prior_asset_count,
                "new_asset_count": len(assets),
                "urls": [asset["url"] for asset in assets],
            }
        )

    for question_id, assets in image_manifest.items():
        question = question_by_id.get(question_id)
        if not question:
            continue
        question["imageUrls"] = [asset["url"] for asset in assets]
        question["image_url"] = assets[0]["url"] if assets else ""
        question["image_assets"] = assets

    GOLD_RUNTIME.write_text(json.dumps(questions, indent=2))
    IMAGE_MANIFEST.write_text(json.dumps(dict(sorted(image_manifest.items())), indent=2))
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report["summary"] = {
        "updated_questions": updated_count,
        "imported_assets": imported_assets,
        "replaced_existing_image_sets": existing_replacements,
        "added_new_image_sets": new_asset_questions,
        "skipped_questions": len(report["skipped_questions"]),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2))

    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        raise
