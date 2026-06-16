import pathlib
import sys
import unittest

API_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

from nbme120 import USMLE_TARGETS, generate_nbme120
from static_questions import QUESTIONS


class Nbme120ContractTests(unittest.TestCase):
    def test_usmle_targets_intentionally_sum_to_120(self):
        self.assertEqual(sum(info["target"] for info in USMLE_TARGETS.values()), 120)

    def test_nbme120_has_six_unique_ordered_blocks(self):
        result = generate_nbme120()
        block_ids = [qid for block in result["blocks"] for qid in block["questionIds"]]

        self.assertEqual(result["format"], "nbme120")
        self.assertEqual(result["totalQuestions"], 120)
        self.assertEqual(len(result["blocks"]), 6)
        self.assertEqual([len(block["questionIds"]) for block in result["blocks"]], [20, 20, 20, 20, 20, 20])
        self.assertEqual(len(result["questionIds"]), 120)
        self.assertEqual(len(set(result["questionIds"])), 120)
        self.assertEqual(result["questionIds"], block_ids)

    def test_nbme120_respects_category_targets_and_difficulty_balance(self):
        result = generate_nbme120()
        questions_by_id = {q["id"]: q for q in QUESTIONS}

        category_counts = {category: 0 for category in USMLE_TARGETS}
        difficulty_counts = {"easy": 0, "medium": 0, "hard": 0}
        for question_id in result["questionIds"]:
            question = questions_by_id[question_id]
            category_counts[question["_category"]] += 1
            difficulty_counts[question["_difficulty"]] += 1

        expected_targets = {category: info["target"] for category, info in USMLE_TARGETS.items()}
        self.assertEqual(category_counts, expected_targets)
        self.assertGreaterEqual(difficulty_counts["easy"], 18)
        self.assertLessEqual(difficulty_counts["easy"], 30)
        self.assertGreaterEqual(difficulty_counts["medium"], 60)
        self.assertLessEqual(difficulty_counts["medium"], 84)
        self.assertGreaterEqual(difficulty_counts["hard"], 18)
        self.assertLessEqual(difficulty_counts["hard"], 30)


if __name__ == "__main__":
    unittest.main()
