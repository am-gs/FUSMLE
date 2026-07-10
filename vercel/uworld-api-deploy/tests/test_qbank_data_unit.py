"""Unit tests for qbank_data pure helpers.

These target the module-level functions that the API contract suite does not
exercise directly: category/difficulty annotation, image-manifest binding,
subject/system counts, deterministic id lookups, and test generation.
"""
import copy
import pathlib
import sys
import unittest

API_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

import qbank_data


class AnnotateQuestionsTests(unittest.TestCase):
    def test_maps_legacy_system_to_canonical_blueprint_key(self):
        questions = [{"id": "a", "organ_system": "Gastrointestinal"}]
        qbank_data._annotate_questions(questions, {})
        self.assertEqual(questions[0]["_category"], "GI")

    def test_blueprint_key_passes_through_unchanged(self):
        questions = [{"id": "a", "organ_system": "Cardiovascular"}]
        qbank_data._annotate_questions(questions, {})
        self.assertEqual(questions[0]["_category"], "Cardiovascular")

    def test_unknown_system_falls_back_to_multisystem(self):
        questions = [
            {"id": "a", "organ_system": "Totally Made Up"},
            {"id": "b"},  # missing organ_system entirely
        ]
        qbank_data._annotate_questions(questions, {})
        self.assertEqual(questions[0]["_category"], "Multisystem")
        self.assertEqual(questions[1]["_category"], "Multisystem")

    def test_difficulty_defaults_to_medium_when_absent(self):
        questions = [
            {"id": "a"},
            {"id": "b", "difficulty_band": "hard"},
        ]
        qbank_data._annotate_questions(questions, {})
        self.assertEqual(questions[0]["_difficulty"], "medium")
        self.assertEqual(questions[1]["_difficulty"], "hard")

    def test_image_assets_bound_from_manifest(self):
        questions = [{"id": "with_img"}, {"id": "no_img"}]
        manifest = {
            "with_img": [
                {"url": "/api/images_crop/one.webp"},
                {"url": "/api/images_crop/two.webp"},
            ]
        }
        qbank_data._annotate_questions(questions, manifest)
        self.assertEqual(questions[0]["image_assets"], manifest["with_img"])
        self.assertEqual(
            questions[0]["imageUrls"],
            ["/api/images_crop/one.webp", "/api/images_crop/two.webp"],
        )
        self.assertEqual(questions[0]["image_url"], "/api/images_crop/one.webp")
        # A question absent from the manifest gets no image fields added.
        self.assertNotIn("image_assets", questions[1])


class LoadImageManifestTests(unittest.TestCase):
    def test_returns_empty_dict_when_manifest_missing(self):
        original = qbank_data._MANIFEST_PATH
        try:
            qbank_data._MANIFEST_PATH = str(API_DIR / "__does_not_exist__.json")
            self.assertEqual(qbank_data._load_image_manifest(), {})
        finally:
            qbank_data._MANIFEST_PATH = original


class _PatchedPoolMixin:
    """Swap the module-level question globals for a deterministic fixture."""

    FIXTURE = [
        {"id": "q1", "organ_system": "GI", "subject": "Path", "exam_ready": True},
        {"id": "q2", "organ_system": "GI", "subject": "Path", "exam_ready": True},
        {"id": "q3", "organ_system": "Cardiovascular", "subject": "Physio", "exam_ready": True},
        {"id": "q4", "organ_system": "Respiratory", "subject": "Physio", "exam_ready": True},
        {"id": "q5", "organ_system": "Respiratory", "subject": "Micro", "exam_ready": False},
    ]

    def setUp(self):
        self._saved_all = qbank_data.ALL_QUESTIONS
        self._saved_by_id = qbank_data._BY_ID
        fixture = [copy.deepcopy(q) for q in self.FIXTURE]
        qbank_data.ALL_QUESTIONS = fixture
        qbank_data._BY_ID = {q["id"]: q for q in fixture}

    def tearDown(self):
        qbank_data.ALL_QUESTIONS = self._saved_all
        qbank_data._BY_ID = self._saved_by_id


class SubjectCountsTests(_PatchedPoolMixin, unittest.TestCase):
    def test_counts_only_exam_ready_and_sorted_descending(self):
        counts = qbank_data.get_subject_counts()
        # q5 is not exam_ready so its Respiratory row is excluded.
        self.assertEqual(counts, {"GI": 2, "Cardiovascular": 1, "Respiratory": 1})
        # Highest count comes first.
        self.assertEqual(list(counts)[0], "GI")

    def test_get_system_counts_matches_subject_counts(self):
        self.assertEqual(qbank_data.get_system_counts(), qbank_data.get_subject_counts())


class GetQuestionByIdTests(_PatchedPoolMixin, unittest.TestCase):
    def test_returns_deep_copy_not_shared_reference(self):
        q = qbank_data.get_question_by_id("q1")
        self.assertEqual(q["id"], "q1")
        q["organ_system"] = "MUTATED"
        # The stored question must be unaffected by mutating the returned copy.
        self.assertEqual(qbank_data._BY_ID["q1"]["organ_system"], "GI")

    def test_returns_none_for_unknown_id(self):
        self.assertIsNone(qbank_data.get_question_by_id("does-not-exist"))


class GenerateTestTests(_PatchedPoolMixin, unittest.TestCase):
    def test_caps_result_at_available_ready_pool(self):
        ids = qbank_data.generate_test(100)
        # Only 4 exam_ready questions exist in the fixture.
        self.assertEqual(len(ids), 4)
        self.assertEqual(set(ids), {"q1", "q2", "q3", "q4"})

    def test_returns_requested_count_when_pool_is_larger(self):
        ids = qbank_data.generate_test(2)
        self.assertEqual(len(ids), 2)
        self.assertTrue(set(ids).issubset({"q1", "q2", "q3", "q4"}))

    def test_filters_by_system_when_enough_matches(self):
        # 2 GI questions >= min(total, 5) so the filter is honoured.
        ids = qbank_data.generate_test(2, systems=["GI"])
        self.assertEqual(set(ids), {"q1", "q2"})

    def test_filters_by_subject_value(self):
        ids = qbank_data.generate_test(2, subjects=["Physio"])
        self.assertEqual(set(ids), {"q3", "q4"})

    def test_falls_back_to_full_pool_when_filter_too_small(self):
        # "Cardiovascular" has a single ready match which is < min(total=5, 5),
        # so generate_test ignores the filter and draws from the whole pool.
        ids = qbank_data.generate_test(5, systems=["Cardiovascular"])
        self.assertEqual(set(ids), {"q1", "q2", "q3", "q4"})

    def test_blank_filters_are_ignored(self):
        ids = qbank_data.generate_test(4, systems=["", "  "])
        self.assertEqual(set(ids), {"q1", "q2", "q3", "q4"})


class MiscTests(_PatchedPoolMixin, unittest.TestCase):
    def test_load_questions_returns_module_pool(self):
        self.assertIs(qbank_data.load_questions(), qbank_data.ALL_QUESTIONS)

    def test_user_progress_counts_returns_zeroed_shape(self):
        result = qbank_data.get_user_progress_counts(user_id=42)
        self.assertEqual(
            result,
            {
                "total_answered": 0,
                "correct_answers": 0,
                "accuracy": 0,
                "by_subject": {},
                "by_system": {},
            },
        )


if __name__ == "__main__":
    unittest.main()
