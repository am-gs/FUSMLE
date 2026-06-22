"""QBank backed by the curated gold pool (gold_runtime.json).
Falls back to legacy static_questions if the runtime file is absent.
"""
import copy, random, os, json
from typing import List, Dict, Optional

_DIR = os.path.dirname(__file__)
_RUNTIME = os.path.join(_DIR, "gold_runtime.json")
_MANIFEST_PATH = os.path.join(_DIR, "image_manifest.json")

# Maps legacy / variant organ_system values to canonical USMLE blueprint keys
CATEGORY_MAP: Dict[str, str] = {
    "Musculoskeletal & Anatomy": "MSK/Skin",
    "Neurologic": "Behavioral/Nervous & Special Senses",
    "Renal & Urinary": "Renal/Urinary",
    "Behavioral & Psychiatry": "Behavioral/Nervous & Special Senses",
    "Gastrointestinal": "GI",
    "Biostatistics & Epidemiology": "General Principles",
    "Endocrine": "Reproductive/Endocrine",
    "Reproductive": "Reproductive/Endocrine",
    "Hematologic": "Hemat/Lymph/Immune",
    "Immunology": "Hemat/Lymph/Immune",
}

_BLUEPRINT_KEYS = {
    "General Principles", "Hemat/Lymph/Immune",
    "Behavioral/Nervous & Special Senses", "MSK/Skin",
    "Cardiovascular", "Respiratory", "GI",
    "Renal/Urinary", "Reproductive/Endocrine", "Multisystem",
}


def _load_runtime() -> List[Dict]:
    with open(_RUNTIME, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_image_manifest() -> Dict[str, List[Dict]]:
    try:
        with open(_MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _annotate_questions(questions: List[Dict], manifest: Dict[str, List[Dict]]) -> None:
    """Add _category, _difficulty, and manifest image fields in-place."""
    for q in questions:
        sys = q.get("organ_system") or "Multisystem"
        q["_category"] = CATEGORY_MAP.get(sys, sys if sys in _BLUEPRINT_KEYS else "Multisystem")
        q["_difficulty"] = q.get("difficulty_band") or "medium"
        qid = q.get("id", "")
        if qid in manifest:
            assets = manifest[qid]
            q["image_assets"] = assets
            q["imageUrls"] = [a["url"] for a in assets]
            q["image_url"] = assets[0]["url"] if assets else q.get("image_url")


try:
    ALL_QUESTIONS = _load_runtime()
    _IMAGE_MANIFEST = _load_image_manifest()
    _annotate_questions(ALL_QUESTIONS, _IMAGE_MANIFEST)
    _BY_ID = {q["id"]: q for q in ALL_QUESTIONS}
    _SOURCE = "gold_runtime"
except FileNotFoundError:  # legacy fallback
    from static_questions import QUESTIONS  # type: ignore
    from free120_questions import FREE120_QUESTIONS  # type: ignore
    ALL_QUESTIONS = [copy.deepcopy(q) for q in QUESTIONS] + list(FREE120_QUESTIONS)
    _IMAGE_MANIFEST = _load_image_manifest()
    _annotate_questions(ALL_QUESTIONS, _IMAGE_MANIFEST)
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
