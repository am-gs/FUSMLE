#!/usr/bin/env python3
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "artifacts" / "evals" / "session45_answer_audit.json"
EXAM_PATH = ROOT / "artifacts" / "exports" / "test2_exam.json"
ADJUDICATION_PATH = (
    ROOT / "artifacts" / "evals" / "session45_independent_adjudication.md"
)
OUT_JSON = ROOT / "artifacts" / "evals" / "session45_rescored_from_curated_key.json"
OUT_MD = ROOT / "artifacts" / "evals" / "session45_rescored_from_curated_key.md"

TABLE_ROW_RE = re.compile(
    r"^\|\s*(?P<position>\d+)\s*\|\s*B(?P<block>\d+)\.I(?P<blockItem>\d+)\s*\|\s*`(?P<questionId>[^`]+)`\s*\|\s*\*\*(?P<answer>[A-Z])\*\*\s*\|\s*(?P<her>[A-Z])\s*\|\s*\*\*(?P<verdict>Correct|Incorrect)\*\*\s*\|\s*(?P<notes>.*)\|\s*$"
)


def load_exam_items() -> list[dict]:
    payload = json.loads(EXAM_PATH.read_text())
    items = []
    for block in payload["blocks"]:
        items.extend(block["items"])
    assert len(items) == 120, len(items)
    return items


def load_manual_overrides() -> dict[int, dict]:
    overrides = {}
    for line in ADJUDICATION_PATH.read_text().splitlines():
        m = TABLE_ROW_RE.match(line.strip())
        if not m:
            continue
        position = int(m.group("position"))
        overrides[position] = {
            "position": position,
            "block": int(m.group("block")),
            "blockItem": int(m.group("blockItem")),
            "questionId": m.group("questionId"),
            "finalLetter": m.group("answer"),
            "manualVerdictForHer": m.group("verdict"),
            "notes": m.group("notes"),
        }
    return overrides


def normalize_final_key(
    audit_rows: list[dict], manual_overrides: dict[int, dict]
) -> list[dict]:
    final_rows = []
    for row in audit_rows:
        position = row["position"]
        override = manual_overrides.get(position)
        if override:
            final_letter = override["finalLetter"]
            source = "manual_independent_adjudication"
        else:
            final_letter = row.get("oeDisplayedLetter")
            source = "oe_displayed_letter"
        if not final_letter:
            raise ValueError(
                f"No final answer key for position {position} ({row['questionId']})"
            )
        final_rows.append(
            {
                "position": position,
                "questionId": row["questionId"],
                "finalLetter": final_letter,
                "keySource": source,
                "oeDisplayedLetter": row.get("oeDisplayedLetter"),
            }
        )
    return final_rows


def build_rescored_rows(
    audit_rows: list[dict],
    exam_items: list[dict],
    final_key_rows: list[dict],
    manual_overrides: dict[int, dict],
) -> list[dict]:
    exam_by_id = {item["id"]: item for item in exam_items}
    key_by_position = {row["position"]: row for row in final_key_rows}
    rows = []
    for audit in audit_rows:
        exam = exam_by_id.get(audit["questionId"])
        key = key_by_position[audit["position"]]
        exam_position = (
            exam.get("examPosition", audit["position"]) if exam else audit["position"]
        )
        assert audit["position"] == exam_position == key["position"]
        if exam:
            assert audit["questionId"] == exam["id"] == key["questionId"]
            option_letters = [opt["letter"] for opt in exam["options"]]
        else:
            assert audit["questionId"] == key["questionId"]
            option_letters = []
        selected_letter = audit.get("selectedLetter")
        final_letter = key["finalLetter"]
        manual = manual_overrides.get(audit["position"])
        rows.append(
            {
                "position": audit["position"],
                "block": audit["block"],
                "blockItem": audit["blockItem"],
                "questionId": audit["questionId"],
                "title": audit["title"],
                "selectedOption": audit["selectedOption"],
                "selectedLetter": selected_letter,
                "finalCorrectLetter": final_letter,
                "finalKeySource": key["keySource"],
                "oeDisplayedLetter": audit.get("oeDisplayedLetter"),
                "runtimeStoredIsCorrect": audit["runtimeStoredIsCorrect"],
                "runtimeCorrectLetter": audit.get("runtimeCorrectLetter"),
                "manifestLetter": audit.get("manifestLetter"),
                "isCorrectUnderFinalKey": selected_letter == final_letter,
                "manualOverrideApplied": manual is not None,
                "manualOverrideNotes": manual["notes"] if manual else None,
                "optionLetters": option_letters,
                "examExportMissing": exam is None,
            }
        )
    return rows


def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    correct = sum(1 for row in rows if row["isCorrectUnderFinalKey"])
    incorrect = total - correct
    manual_override_count = sum(1 for row in rows if row["manualOverrideApplied"])
    oe_key_count = sum(
        1 for row in rows if row["finalKeySource"] == "oe_displayed_letter"
    )
    runtime_disagreement_count = sum(
        1
        for row in rows
        if row["runtimeStoredIsCorrect"] != row["isCorrectUnderFinalKey"]
    )
    oe_override_disagreement_count = sum(
        1
        for row in rows
        if row["manualOverrideApplied"]
        and row.get("oeDisplayedLetter")
        and row["oeDisplayedLetter"] != row["finalCorrectLetter"]
    )
    return {
        "total": total,
        "correct": correct,
        "incorrect": incorrect,
        "manual_override_count": manual_override_count,
        "oe_key_count": oe_key_count,
        "runtime_disagreement_count": runtime_disagreement_count,
        "manual_override_vs_oe_disagreement_count": oe_override_disagreement_count,
    }


def build_markdown(summary: dict, rows: list[dict]) -> str:
    lines = []
    lines.append("# Session 45 / Test 2 — Curated Full-Exam Rescore")
    lines.append("")
    lines.append("## Final corrected score")
    lines.append("")
    lines.append(f"- Correct: **{summary['correct']} / {summary['total']}**")
    lines.append(f"- Incorrect: **{summary['incorrect']} / {summary['total']}**")
    lines.append(
        f"- Runtime disagreement count: **{summary['runtime_disagreement_count']}**"
    )
    lines.append(f"- Manual override count: **{summary['manual_override_count']}**")
    lines.append(
        f"- Manual override vs OE disagreement count: **{summary['manual_override_vs_oe_disagreement_count']}**"
    )
    lines.append("")
    lines.append("## Key method")
    lines.append("")
    lines.append(
        "- Baseline key: `oeDisplayedLetter` from `artifacts/evals/session45_answer_audit.json`"
    )
    lines.append(
        "- Override source: `artifacts/evals/session45_independent_adjudication.md`"
    )
    lines.append(
        "- User response source of truth: session `45` submitted `selectedLetter` / `selectedOption`"
    )
    lines.append("")
    lines.append("## User-requested items")
    lines.append("")
    for position in [35, 36, 42]:
        row = next(r for r in rows if r["position"] == position)
        verdict = "correct" if row["isCorrectUnderFinalKey"] else "incorrect"
        lines.append(
            f"- Q{position} / B{row['block']}.I{row['blockItem']} / `{row['questionId']}`: selected `{row['selectedLetter']}`, final key `{row['finalCorrectLetter']}` → **{verdict}**"
        )
    lines.append("")
    lines.append("## Manual overrides applied")
    lines.append("")
    lines.append(
        "| Q | Block.Item | Question ID | Final key | Selected | Result | Notes |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for row in rows:
        if not row["manualOverrideApplied"]:
            continue
        result = "Correct" if row["isCorrectUnderFinalKey"] else "Incorrect"
        lines.append(
            f"| {row['position']} | B{row['block']}.I{row['blockItem']} | `{row['questionId']}` | {row['finalCorrectLetter']} | {row['selectedLetter']} | {result} | {row['manualOverrideNotes']} |"
        )
    lines.append("")
    lines.append("## All incorrect items under final key")
    lines.append("")
    lines.append("| Q | Block.Item | Question ID | Selected | Final key | Key source |")
    lines.append("|---|---|---|---|---|---|")
    for row in rows:
        if row["isCorrectUnderFinalKey"]:
            continue
        lines.append(
            f"| {row['position']} | B{row['block']}.I{row['blockItem']} | `{row['questionId']}` | {row['selectedLetter']} | {row['finalCorrectLetter']} | {row['finalKeySource']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    audit_payload = json.loads(AUDIT_PATH.read_text())
    audit_rows = audit_payload["rows"]
    exam_items = load_exam_items()
    manual_overrides = load_manual_overrides()
    final_key_rows = normalize_final_key(audit_rows, manual_overrides)
    rows = build_rescored_rows(audit_rows, exam_items, final_key_rows, manual_overrides)
    summary = summarize(rows)
    payload = {
        "method": {
            "baseline": "oeDisplayedLetter from session45_answer_audit.json",
            "override": "independent manual adjudication table from session45_independent_adjudication.md",
            "notes": "This is a deterministic curated-key rescore that avoids known runtime off-by-one scoring corruption.",
        },
        "summary": summary,
        "rows": rows,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    OUT_MD.write_text(build_markdown(summary, rows))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
