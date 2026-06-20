#!/usr/bin/env python3
"""Preview or apply a mechanical session backfill for repaired qbank answer keys.

This script is intentionally narrow:
- scope = sessions whose recorded answers intersect repaired question IDs
- key source = current `gold_runtime.json`
- recompute = `selected_option == current correct_answer`

It does NOT apply manual/adjudicated overrides such as the curated session-45
52/120 correction; that requires a separate explicit override path.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "vercel" / "uworld-api-deploy"
ARTIFACTS_DIR = ROOT / "artifacts" / "evals"
RUNTIME_PATH = API_DIR / "gold_runtime.json"
NBME28_REPAIR_PATH = ARTIFACTS_DIR / "nbme28_answerkey_repair_2026-06-19.json"

sys.path.insert(0, str(API_DIR))

from database import (  # type: ignore
    USE_SUPABASE,
    _eq,
    _supabase_request,
    get_db_connection,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write recomputed is_correct values back to the configured database.",
    )
    parser.add_argument(
        "--session-id",
        type=int,
        action="append",
        default=[],
        help="Limit backfill to one or more specific test session IDs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ARTIFACTS_DIR
        / f"impacted_session_backfill_{date.today().isoformat()}.json",
        help="Where to write the preview/apply summary artifact.",
    )
    return parser.parse_args()


def load_runtime_by_id() -> dict[str, dict[str, Any]]:
    rows = json.loads(RUNTIME_PATH.read_text())
    return {str(row["id"]): row for row in rows}


def load_repaired_question_ids() -> set[str]:
    payload = json.loads(NBME28_REPAIR_PATH.read_text())
    return {str(row["question_id"]) for row in payload.get("applied", [])}


def fetch_all_test_answers() -> list[dict[str, Any]]:
    if USE_SUPABASE:
        rows = _supabase_request(
            "GET", "test_answers", query="order=test_session_id.asc,id.asc"
        )
        return rows or []
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, test_session_id, user_id, question_id, selected_option, is_correct, time_spent, answered_at FROM test_answers ORDER BY test_session_id ASC, id ASC"
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def fetch_test_sessions_by_ids(session_ids: set[int]) -> dict[int, dict[str, Any]]:
    if not session_ids:
        return {}
    if USE_SUPABASE:
        sessions: dict[int, dict[str, Any]] = {}
        for session_id in sorted(session_ids):
            rows = _supabase_request(
                "GET", "test_sessions", query=f"id={_eq(session_id)}&limit=1"
            )
            if rows:
                sessions[int(session_id)] = rows[0]
        return sessions
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        placeholders = ",".join("?" for _ in session_ids)
        cursor.execute(
            f"SELECT id, user_id, mode, question_ids, total_questions, current_question, score, completed, created_at, completed_at FROM test_sessions WHERE id IN ({placeholders})",
            tuple(sorted(session_ids)),
        )
        return {int(row["id"]): dict(row) for row in cursor.fetchall()}
    finally:
        conn.close()


def patch_test_answer(session_id: int, question_id: str, is_correct: bool) -> None:
    if USE_SUPABASE:
        _supabase_request(
            "PATCH",
            "test_answers",
            {"is_correct": bool(is_correct)},
            query=f"test_session_id={_eq(session_id)}&question_id={_eq(question_id)}",
            select=False,
        )
        return
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE test_answers SET is_correct = ? WHERE test_session_id = ? AND question_id = ?",
            (bool(is_correct), int(session_id), str(question_id)),
        )
        conn.commit()
    finally:
        conn.close()


def patch_test_session_score(session_id: int, score: int) -> None:
    if USE_SUPABASE:
        _supabase_request(
            "PATCH",
            "test_sessions",
            {"score": int(score)},
            query=f"id={_eq(session_id)}",
            select=False,
        )
        return
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE test_sessions SET score = ? WHERE id = ?",
            (int(score), int(session_id)),
        )
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    args = parse_args()
    runtime_by_id = load_runtime_by_id()
    repaired_ids = load_repaired_question_ids()
    all_answers = fetch_all_test_answers()

    impacted_answers = [
        row for row in all_answers if str(row.get("question_id")) in repaired_ids
    ]
    if args.session_id:
        requested = {int(v) for v in args.session_id}
        impacted_answers = [
            row
            for row in impacted_answers
            if int(row.get("test_session_id")) in requested
        ]

    impacted_session_ids = {int(row["test_session_id"]) for row in impacted_answers}
    sessions_by_id = fetch_test_sessions_by_ids(impacted_session_ids)

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in impacted_answers:
        grouped[int(row["test_session_id"])].append(row)

    session_summaries: list[dict[str, Any]] = []
    total_answer_rows_changed = 0

    for session_id in sorted(grouped):
        rows = grouped[session_id]
        changed_rows: list[dict[str, Any]] = []
        for row in rows:
            question_id = str(row["question_id"])
            runtime_question = runtime_by_id.get(question_id)
            if not runtime_question:
                continue
            correct_answer = runtime_question.get("correct_answer")
            if not isinstance(correct_answer, int):
                continue
            selected_option = row.get("selected_option")
            recomputed = bool(selected_option == correct_answer)
            prior = bool(row.get("is_correct"))
            if recomputed != prior:
                changed_rows.append(
                    {
                        "questionId": question_id,
                        "selectedOption": selected_option,
                        "storedIsCorrect": prior,
                        "recomputedIsCorrect": recomputed,
                        "correctAnswer": correct_answer,
                    }
                )
                if args.apply:
                    patch_test_answer(session_id, question_id, recomputed)

        session_payload = sessions_by_id.get(session_id) or {}
        answer_rows_for_session = [
            row for row in all_answers if int(row.get("test_session_id")) == session_id
        ]
        corrected_answer_rows = []
        changed_by_qid = {row["questionId"]: row for row in changed_rows}
        for row in answer_rows_for_session:
            qid = str(row["question_id"])
            if qid in changed_by_qid:
                corrected_answer_rows.append(changed_by_qid[qid]["recomputedIsCorrect"])
            else:
                corrected_answer_rows.append(bool(row.get("is_correct")))
        recomputed_score = sum(1 for value in corrected_answer_rows if value)
        if args.apply:
            patch_test_session_score(session_id, recomputed_score)

        total_answer_rows_changed += len(changed_rows)
        session_summaries.append(
            {
                "sessionId": session_id,
                "userId": session_payload.get("user_id"),
                "mode": session_payload.get("mode"),
                "impactedQuestionCount": len(rows),
                "changedAnswerRows": len(changed_rows),
                "storedSessionScore": session_payload.get("score"),
                "recomputedSessionScore": recomputed_score,
                "changedRows": changed_rows,
            }
        )

    payload = {
        "mode": "apply" if args.apply else "preview",
        "databaseBackend": "supabase" if USE_SUPABASE else "sqlite",
        "runtimePath": str(RUNTIME_PATH.relative_to(ROOT)),
        "repairArtifact": str(NBME28_REPAIR_PATH.relative_to(ROOT)),
        "repairedQuestionCount": len(repaired_ids),
        "impactedSessionCount": len(session_summaries),
        "changedAnswerRowCount": total_answer_rows_changed,
        "sessionSummaries": session_summaries,
        "notes": [
            "This script performs a mechanical rescore using current runtime correct_answer values.",
            "It does not apply manual/adjudicated overrides such as the curated 52/120 session-45 correction.",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "mode": payload["mode"],
                "impactedSessionCount": payload["impactedSessionCount"],
                "changedAnswerRowCount": payload["changedAnswerRowCount"],
                "output": str(args.output.relative_to(ROOT)),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
