import unittest

import helpers
from extraction_demo.baseline import extract, extract_dir
from extraction_demo.parity import build_report
from extraction_demo.schema import load_schema

GOLDEN = helpers.load_dir(helpers.DATA / "golden")
DOCS = helpers.DATA / "documents"


class Baseline(unittest.TestCase):
    def score(self, candidates):
        return build_report(GOLDEN, candidates, load_schema())

    def test_extraction_is_deterministic(self):
        self.assertEqual(extract_dir(DOCS), extract_dir(DOCS))
        self.assertEqual(self.score(extract_dir(DOCS)).accuracy, self.score(extract_dir(DOCS)).accuracy)

    def test_score_is_below_candidate_a(self):
        baseline = self.score(extract_dir(DOCS))
        candidate_a = self.score(helpers.load_dir(helpers.DATA / "candidates" / "candidate_a"))
        self.assertLess(baseline.accuracy, candidate_a.accuracy)
        self.assertLess(baseline.documents_exact, candidate_a.documents_exact)

    def test_form_style_document(self):
        record = extract((DOCS / "sb_01.txt").read_text(encoding="utf-8"))
        self.assertEqual(record["product_name"], "Trail Jacket X1")
        self.assertEqual(record["test_date"], "2025-03-14")
        self.assertEqual(record["participants"], 12)
        self.assertEqual(record["reviewer_names"], ["Maya", "Jonas", "Priya"])
        self.assertEqual(len(record["key_findings"]), 3)

    def test_memo_style_document_with_prose_values(self):
        record = extract((DOCS / "sb_08.txt").read_text(encoding="utf-8"))
        self.assertEqual(record["participants"], 9)
        self.assertEqual(record["average_rating"], 4.1)
        self.assertEqual(record["test_date"], "2025-06-17")
        self.assertEqual(record["recommendation"], "revise")
        self.assertIsNone(record["notes"])

    def test_compact_style_document(self):
        record = extract((DOCS / "sb_09.txt").read_text(encoding="utf-8"))
        self.assertEqual(record["style_code"], "HPH9-25")
        self.assertEqual(record["participants"], 14)
        self.assertEqual(record["reviewer_names"], ["Kofi", "Sofia"])

    def test_known_weaknesses_are_real_misses(self):
        earlier_round = extract((DOCS / "sb_06.txt").read_text(encoding="utf-8"))
        self.assertEqual(earlier_round["test_date"], "2025-05-12")
        unlisted_phrasing = extract((DOCS / "sb_11.txt").read_text(encoding="utf-8"))
        self.assertIsNone(unlisted_phrasing["participants"])
        sub_score = extract((DOCS / "sb_05.txt").read_text(encoding="utf-8"))
        self.assertEqual(sub_score["average_rating"], 5.0)


if __name__ == "__main__":
    unittest.main()
