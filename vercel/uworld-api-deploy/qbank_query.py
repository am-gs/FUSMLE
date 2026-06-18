"""Fast, queryable view over the curated qbank.

Reads ``qbank_index.json`` (compact per-question metadata generated from
``gold_runtime.json``) so future exam assembly / analytics can filter and
aggregate without parsing the full 4 MB question file.

Usage (module):
    from qbank_query import QBankIndex
    idx = QBankIndex.load()
    cardio = idx.query(system="Cardiovascular", difficulty="medium", has_image=True)
    dist = idx.distribution("system")
    blueprint = idx.build_blueprint({"Cardiovascular": 12, "Respiratory": 10}, difficulty="medium")

Usage (CLI):
    python qbank_query.py counts
    python qbank_query.py query --system Cardiovascular --difficulty medium --has-image
    python qbank_query.py distribution --field difficulty
    python qbank_query.py provenance --id nbme28_q0005
"""
from __future__ import annotations

import json
import os
from collections import Counter
from typing import Dict, List, Optional

_DIR = os.path.dirname(__file__)
_INDEX_PATH = os.path.join(_DIR, "qbank_index.json")


class QBankIndex:
    def __init__(self, payload: Dict):
        self.generated = payload.get("generated")
        self.counts = payload.get("counts", {})
        self.questions: List[Dict] = payload.get("questions", [])
        self._by_id = {q["id"]: q for q in self.questions}

    @classmethod
    def load(cls, path: str = _INDEX_PATH) -> "QBankIndex":
        with open(path, "r", encoding="utf-8") as fh:
            return cls(json.load(fh))

    def get(self, qid: str) -> Optional[Dict]:
        return self._by_id.get(qid)

    def query(
        self,
        *,
        form: Optional[str] = None,
        system: Optional[str] = None,
        subject: Optional[str] = None,
        discipline: Optional[str] = None,
        difficulty: Optional[str] = None,
        high_yield: Optional[bool] = None,
        has_image: Optional[bool] = None,
        has_table: Optional[bool] = None,
        exam_ready: Optional[bool] = True,
        pdf_verified: Optional[bool] = None,
        exclude_ids: Optional[set] = None,
    ) -> List[Dict]:
        exclude_ids = exclude_ids or set()
        out = []
        for q in self.questions:
            if q["id"] in exclude_ids:
                continue
            if form is not None and q.get("form") != form:
                continue
            if system is not None and q.get("system") != system:
                continue
            if subject is not None and q.get("subject") != subject:
                continue
            if discipline is not None and q.get("discipline") != discipline:
                continue
            if difficulty is not None and q.get("difficulty") != difficulty:
                continue
            if high_yield is not None and bool(q.get("high_yield")) != high_yield:
                continue
            if has_image is not None and bool(q.get("has_image")) != has_image:
                continue
            if has_table is not None and bool(q.get("has_table")) != has_table:
                continue
            if exam_ready is not None and bool(q.get("exam_ready")) != exam_ready:
                continue
            if pdf_verified is not None and bool(q.get("pdf_verified")) != pdf_verified:
                continue
            out.append(q)
        return out

    def distribution(self, field: str, **filters) -> Dict[str, int]:
        rows = self.query(**filters) if filters else self.questions
        counter = Counter(q.get(field) for q in rows)
        return dict(sorted(counter.items(), key=lambda kv: -kv[1]))

    def build_blueprint(self, system_targets: Dict[str, int], **filters) -> Dict[str, List[str]]:
        """Return up to N question ids per system, honoring extra filters.

        Deterministic: ids are sorted so repeated calls return the same set.
        """
        selected: Dict[str, List[str]] = {}
        for system, n in system_targets.items():
            pool = sorted(q["id"] for q in self.query(system=system, **filters))
            selected[system] = pool[:n]
        return selected


def _main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Query the curated qbank index")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("counts")
    qp = sub.add_parser("query")
    qp.add_argument("--form")
    qp.add_argument("--system")
    qp.add_argument("--subject")
    qp.add_argument("--difficulty")
    qp.add_argument("--high-yield", action="store_true")
    qp.add_argument("--has-image", action="store_true")
    qp.add_argument("--has-table", action="store_true")
    qp.add_argument("--limit", type=int, default=20)
    dp = sub.add_parser("distribution")
    dp.add_argument("--field", required=True)
    pp = sub.add_parser("provenance")
    pp.add_argument("--id", required=True)
    args = ap.parse_args()

    idx = QBankIndex.load()
    if args.cmd == "counts":
        print(json.dumps(idx.counts, indent=2))
    elif args.cmd == "query":
        rows = idx.query(
            form=args.form,
            system=args.system,
            subject=args.subject,
            difficulty=args.difficulty,
            high_yield=True if args.high_yield else None,
            has_image=True if args.has_image else None,
            has_table=True if args.has_table else None,
        )
        print(f"{len(rows)} matches")
        for q in rows[: args.limit]:
            print(f"  {q['id']:18} {q.get('system','?'):26} {q.get('difficulty','?'):7} "
                  f"img={int(bool(q.get('has_image')))} hy={int(bool(q.get('high_yield')))}")
    elif args.cmd == "distribution":
        print(json.dumps(idx.distribution(args.field), indent=2))
    elif args.cmd == "provenance":
        q = idx.get(args.id)
        print(json.dumps(q, indent=2) if q else f"not found: {args.id}")


if __name__ == "__main__":
    _main()
