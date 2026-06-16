import json
import pathlib
import sys
import unittest

API_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

from qbank_data import get_question_by_id
from qbank_data import load_questions


class ImageManifestContractTests(unittest.TestCase):
    def test_manifest_links_existing_questions_and_assets(self):
        manifest = json.loads((API_DIR / "image_manifest.json").read_text())
        question_ids = {q["id"] for q in load_questions()}

        self.assertTrue(manifest, "image manifest must not be empty")
        for question_id, assets in manifest.items():
            self.assertIn(question_id, question_ids)
            self.assertTrue(assets, f"{question_id} has no assets")
            for asset in assets:
                self.assertTrue(asset["url"].startswith("/api/images_crop/"))
                self.assertTrue(asset["url"].endswith(".webp"))
                self.assertGreater(asset.get("width", 0), 0)
                self.assertGreater(asset.get("height", 0), 0)
                path = API_DIR / "images_crop" / pathlib.Path(asset["url"]).name
                self.assertTrue(path.is_file(), f"missing image file: {path}")

    def test_questions_expose_all_manifest_image_urls(self):
        manifest = json.loads((API_DIR / "image_manifest.json").read_text())
        for question_id, assets in manifest.items():
            question = get_question_by_id(question_id)
            expected_urls = [asset["url"] for asset in assets]
            self.assertEqual(question["imageUrls"], expected_urls)
            self.assertEqual(question["image_url"], expected_urls[0])
            self.assertEqual(question["image_assets"], assets)

    def test_free120_manifest_assets_are_valid_webp_files(self):
        manifest = json.loads((API_DIR / "image_manifest.json").read_text())
        free120_entries = {key: value for key, value in manifest.items() if key.startswith("free120_2021_")}
        self.assertEqual(len(free120_entries), 12)
        for question_id, assets in free120_entries.items():
            self.assertRegex(question_id, r"^free120_2021_q\d{3}$")
            for asset in assets:
                path = API_DIR / "images_crop" / pathlib.Path(asset["url"]).name
                self.assertTrue(path.is_file(), f"missing Free 120 image file: {path}")


if __name__ == "__main__":
    unittest.main()
