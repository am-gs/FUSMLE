"""QBank backed by the curated gold pool (gold_runtime.json).
Falls back to legacy static_questions if the runtime file is absent.
"""

import copy
import json
import os
import random
from typing import Dict, List, Optional

_DIR = os.path.dirname(__file__)
_RUNTIME = os.path.join(_DIR, "gold_runtime.json")


def _load_runtime() -> List[Dict]:
    with open(_RUNTIME, "r", encoding="utf-8") as f:
        return json.load(f)


try:
    ALL_QUESTIONS = _load_runtime()
    _BY_ID = {q["id"]: q for q in ALL_QUESTIONS}
    _SOURCE = "gold_runtime"
except FileNotFoundError:  # legacy fallback
    from free120_questions import FREE120_QUESTIONS  # type: ignore
    from static_questions import QUESTIONS  # type: ignore

    ALL_QUESTIONS = [copy.deepcopy(q) for q in QUESTIONS] + list(FREE120_QUESTIONS)
    _BY_ID = {q["id"]: q for q in ALL_QUESTIONS}
    _SOURCE = "legacy_static"


def load_questions() -> List[Dict]:
    return ALL_QUESTIONS


def is_exam_safe_question(question: Optional[Dict]) -> bool:
    if not isinstance(question, dict):
        return False
    if not bool(question.get("exam_ready", True)):
        return False
    if bool(question.get("option_parse_error")):
        return False
    options = question.get("options") or []
    if not isinstance(options, list) or not options:
        return False
    option_ids = {
        opt.get("id")
        for opt in options
        if isinstance(opt, dict) and isinstance(opt.get("id"), int)
    }
    correct_answer = question.get("correct_answer")
    return isinstance(correct_answer, int) and correct_answer in option_ids


def _ready() -> List[Dict]:
    return [q for q in ALL_QUESTIONS if is_exam_safe_question(q)]


def get_subject_counts() -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for q in _ready():
        s = q.get("organ_system") or q.get("subject", "Other")
        counts[s] = counts.get(s, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def get_system_counts() -> Dict[str, int]:
    return get_subject_counts()


def get_question_by_id(
    question_id: str, require_exam_safe: bool = False
) -> Optional[Dict]:
    q = _BY_ID.get(question_id)
    if not q:
        return None
    if require_exam_safe and not is_exam_safe_question(q):
        return None
    return copy.deepcopy(q)


def generate_test(
    total_questions: int,
    subjects: Optional[List[str]] = None,
    systems: Optional[List[str]] = None,
) -> List[str]:
    pool = _ready()
    wanted = set()
    for grp in (subjects or [], systems or []):
        for s in grp:
            if s and s.strip():
                wanted.add(s.strip())
    if wanted:
        filt = [
            q
            for q in pool
            if (q.get("organ_system") in wanted) or (q.get("subject") in wanted)
        ]
        if len(filt) >= min(total_questions, 5):
            pool = filt
    num = min(total_questions, len(pool))
    return [q["id"] for q in random.sample(pool, num)]


def get_user_progress_counts(user_id: int) -> Dict:
    return {
        "total_answered": 0,
        "correct_answers": 0,
        "accuracy": 0,
        "by_subject": {},
        "by_system": {},
    }
