"""Unit tests for the nbme120 generator internals.

The contract suite validates the generator against the real gold pool. These
tests drive the internal selection logic with a synthetic pool so that the
dedupe-by-fingerprint, per-category backfill, exclude-ids, short-pool, and
``generate_test1`` code paths are all exercised deterministically.
"""
import pathlib
import sys
import unittest

API_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

import nbme120
from nbme120 import USMLE_TARGETS, _targets


def _make_pool():
    """Build a pool large enough to satisfy every blueprint category target,
    with distinct concept fingerprints and a spread of difficulties."""
    pool = []
    counter = 0
    for category, info in USMLE_TARGETS.items():
        # Provide well over the target so difficulty quotas + backfill are hit.
        for i in range(info["target"] + 6):
            counter += 1
            difficulty = ("easy", "medium", "hard")[i % 3]
            pool.append(
                {
                    "id": f"q{counter:04d}",
                    "_category": category,
                    "_difficulty": difficulty,
                    "concept_fingerprint": f"fp-{counter}",
                    "exam_ready": True,
                }
            )
    return pool


class TargetsTests(unittest.TestCase):
    def test_targets_sum_to_total(self):
        self.assertEqual(sum(_targets().values()), nbme120.TOTAL)

    def test_usmle_targets_mirror_targets(self):
        self.assertEqual({k: v["target"] for k, v in USMLE_TARGETS.items()}, _targets())


class GenerateNbme120Tests(unittest.TestCase):
    def setUp(self):
        self._saved = nbme120.load_questions
        self._pool = _make_pool()
        nbme120.load_questions = lambda: [dict(q) for q in self._pool]

    def tearDown(self):
        nbme120.load_questions = self._saved

    def test_produces_120_items_in_six_blocks(self):
        result = nbme120.generate_nbme120()
        self.assertEqual(result["format"], "nbme120")
        self.assertEqual(result["totalQuestions"], 120)
        self.assertEqual(len(result["blocks"]), 6)
        self.assertEqual([len(b["questionIds"]) for b in result["blocks"]], [20] * 6)
        flat = [qid for b in result["blocks"] for qid in b["questionIds"]]
        self.assertEqual(result["questionIds"], flat)
        self.assertEqual(len(set(flat)), 120)

    def test_respects_per_category_targets(self):
        result = nbme120.generate_nbme120()
        by_id = {q["id"]: q for q in self._pool}
        counts = {cat: 0 for cat in USMLE_TARGETS}
        for qid in result["questionIds"]:
            counts[by_id[qid]["_category"]] += 1
        self.assertEqual(counts, {cat: info["target"] for cat, info in USMLE_TARGETS.items()})

    def test_never_selects_duplicate_fingerprints(self):
        result = nbme120.generate_nbme120()
        by_id = {q["id"]: q for q in self._pool}
        fps = [by_id[qid]["concept_fingerprint"] for qid in result["questionIds"]]
        self.assertEqual(len(fps), len(set(fps)))

    def test_exclude_ids_are_never_chosen(self):
        excluded = {q["id"] for q in self._pool[:5]}
        result = nbme120.generate_nbme120(exclude_ids=excluded)
        self.assertTrue(excluded.isdisjoint(result["questionIds"]))

    def test_short_pool_backfills_but_cannot_exceed_available(self):
        small = self._pool[:30]
        nbme120.load_questions = lambda: [dict(q) for q in small]
        result = nbme120.generate_nbme120()
        self.assertEqual(result["totalQuestions"], 30)
        self.assertEqual(len(result["questionIds"]), 30)
        self.assertEqual(len(set(result["questionIds"])), 30)

    def test_shared_fingerprints_collapse_to_one_selection(self):
        # Two large groups that all share a single fingerprint each: only one
        # question per fingerprint may ever be selected.
        pool = []
        for cat in USMLE_TARGETS:
            for i in range(30):
                pool.append(
                    {
                        "id": f"{cat[:3]}-{i}",
                        "_category": cat,
                        "_difficulty": "medium",
                        "concept_fingerprint": f"shared-{cat}",
                        "exam_ready": True,
                    }
                )
        nbme120.load_questions = lambda: [dict(q) for q in pool]
        result = nbme120.generate_nbme120()
        # One unique fingerprint per category -> at most len(categories) items.
        self.assertEqual(result["totalQuestions"], len(USMLE_TARGETS))


class GenerateTest1Tests(unittest.TestCase):
    def setUp(self):
        self._saved_get = nbme120._get

    def tearDown(self):
        nbme120._get = self._saved_get

    def test_builds_six_blocks_and_skips_non_ready_items(self):
        def fake_get(qid):
            n = int(qid.split("_q")[1])
            # Mark item 5 as not exam_ready and item 10 as missing entirely.
            if n == 10:
                return None
            return {"id": qid, "exam_ready": n != 5}

        nbme120._get = fake_get
        result = nbme120.generate_test1()

        self.assertEqual(result["format"], "test1")
        self.assertTrue(result["timed"])
        self.assertEqual(len(result["blocks"]), 6)
        # 119 official items minus the skipped q005 and missing q010 -> 117.
        self.assertEqual(result["totalQuestions"], 117)
        self.assertEqual(len(result["questionIds"]), 117)
        self.assertNotIn("nbme120_q005", result["questionIds"])
        self.assertNotIn("nbme120_q010", result["questionIds"])
        # Block metadata reflects the official ranges.
        self.assertEqual(result["blocks"][0]["itemRange"], "1-20")
        self.assertEqual(result["blocks"][-1]["itemRange"], "101-119")
        self.assertEqual(result["blocks"][0]["timeLimit"], 30)

    def test_all_items_ready_yields_full_119(self):
        nbme120._get = lambda qid: {"id": qid, "exam_ready": True}
        result = nbme120.generate_test1()
        self.assertEqual(result["totalQuestions"], 119)
        self.assertEqual(result["questionIds"][0], "nbme120_q001")
        self.assertEqual(result["questionIds"][-1], "nbme120_q119")


if __name__ == "__main__":
    unittest.main()
