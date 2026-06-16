"""QBank backed by the curated gold pool (gold_runtime.json).
Falls back to legacy static_questions if the runtime file is absent.
"""
import copy, random, os, json
from typing import List, Dict, Optional

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
    from static_questions import QUESTIONS  # type: ignore
    from free120_questions import FREE120_QUESTIONS  # type: ignore
    ALL_QUESTIONS = [copy.deepcopy(q) for q in QUESTIONS] + list(FREE120_QUESTIONS)
    _BY_ID = {q["id"]: q for q in ALL_QUESTIONS}
    _SOURCE = "legacy_static"


def load_questions() -> List[Dict]:
    return ALL_QUESTIONS


def _ready() -> List[Dict]:
    return [q for q in ALL_QUESTIONS if q.get("exam_ready", True)]


def get_subject_counts() -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for q in _ready():
        s = q.get("organ_system") or q.get("subject", "Other")
        counts[s] = counts.get(s, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def get_system_counts() -> Dict[str, int]:
    return get_subject_counts()


def get_question_by_id(question_id: str) -> Optional[Dict]:
    q = _BY_ID.get(question_id)
    return copy.deepcopy(q) if q else None


def generate_test(total_questions: int, subjects: List[str] = None,
                  systems: List[str] = None) -> List[str]:
    pool = _ready()
    wanted = set()
    for grp in (subjects or [], systems or []):
        for s in grp:
            if s and s.strip():
                wanted.add(s.strip())
    if wanted:
        filt = [q for q in pool if (q.get("organ_system") in wanted) or (q.get("subject") in wanted)]
        if len(filt) >= min(total_questions, 5):
            pool = filt
    num = min(total_questions, len(pool))
    return [q["id"] for q in random.sample(pool, num)]


def get_user_progress_counts(user_id: int) -> Dict:
    return {"total_answered": 0, "correct_answers": 0, "accuracy": 0,
            "by_subject": {}, "by_system": {}}
