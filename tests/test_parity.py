import unittest

import helpers
from extraction_demo.parity import (
    EXTRA,
    FORMAT_ONLY,
    MATCH,
    MISSING,
    TYPE,
    VALUE,
    build_report,
    classify,
    compare_document,
    evaluate_gate,
)
from extraction_demo.schema import load_schema

GOLDEN = helpers.load_dir(helpers.DATA / "golden")
SCHEMA = load_schema()


def report_for(candidates):
    return build_report(GOLDEN, candidates, SCHEMA)


def perturbed(**changes):
    """Candidate set equal to golden except for the given fields of sb_01."""
    candidates = {name: dict(record) for name, record in GOLDEN.items()}
    candidates["sb_01"].update(changes)
    return candidates


class Classification(unittest.TestCase):
    def test_match(self):
        self.assertEqual(classify("participants", 12, 12), MATCH)

    def test_format_only(self):
        self.assertEqual(classify("participants", 12, "12 participants"), FORMAT_ONLY)
        self.assertEqual(classify("average_rating", 4.5, "4,5 out of 5"), FORMAT_ONLY)
        self.assertEqual(classify("test_date", "2025-03-14", "14 Mar 2025"), FORMAT_ONLY)

    def test_missing(self):
        self.assertEqual(classify("participants", 12, None), MISSING)
        self.assertEqual(classify("participants", 12, "n/a"), MISSING)

    def test_extra_when_golden_is_null(self):
        self.assertEqual(classify("notes", None, "invented"), EXTRA)

    def test_type(self):
        self.assertEqual(classify("participants", 12, "a handful"), TYPE)
        self.assertEqual(classify("reviewer_names", ["a"], 7), TYPE)

    def test_value(self):
        self.assertEqual(classify("recommendation", "ship", "revise"), VALUE)
        self.assertEqual(classify("reviewer_names", ["Kofi", "Sofia"], ["Kofi and Sofia"]), VALUE)

    def test_both_null_is_a_match_and_null_like_spelling_is_format_only(self):
        self.assertEqual(classify("notes", None, None), MATCH)
        self.assertEqual(classify("notes", None, "N/A"), FORMAT_ONLY)

    def test_unknown_candidate_field_is_extra(self):
        cells = compare_document("d", {"notes": None}, {"notes": None, "price_tier": "premium"})
        self.assertEqual([(c.field, c.status) for c in cells], [("notes", MATCH), ("price_tier", EXTRA)])

    def test_unknown_candidate_field_with_null_value_is_ignored(self):
        cells = compare_document("d", {"notes": None}, {"notes": None, "price_tier": None})
        self.assertEqual(len(cells), 1)

    def test_missing_candidate_document_is_all_missing(self):
        cells = compare_document("sb_01", GOLDEN["sb_01"], None)
        self.assertTrue(all(c.status == MISSING for c in cells))


class Aggregation(unittest.TestCase):
    def test_identical_candidate_is_perfect(self):
        report = report_for(GOLDEN)
        self.assertEqual(report.accuracy, 1.0)
        self.assertEqual(report.strict_accuracy, 1.0)
        self.assertEqual(report.documents_exact, 12)
        self.assertEqual(report.schema_valid_raw, 12)

    def test_format_only_counts_as_correct_but_not_strict(self):
        report = report_for(perturbed(participants="12 participants"))
        self.assertEqual(report.accuracy, 1.0)
        self.assertLess(report.strict_accuracy, 1.0)
        self.assertEqual(report.taxonomy()[FORMAT_ONLY], 1)
        self.assertEqual(report.schema_valid_raw, 11)
        self.assertEqual(report.schema_valid_normalized, 12)

    def test_per_field_and_doc_level(self):
        report = report_for(perturbed(recommendation="drop"))
        row = report.per_field()["recommendation"]
        self.assertEqual((row["total"], row[VALUE], row["accuracy"]), (12, 1, 11 / 12))
        self.assertEqual(report.documents_exact, 11)

    def test_extra_candidate_files_are_listed(self):
        candidates = dict(GOLDEN, stray={"notes": None})
        self.assertEqual(report_for(candidates).extra_documents, ["stray"])


class Gate(unittest.TestCase):
    def test_perfect_candidate_passes(self):
        self.assertTrue(evaluate_gate(report_for(GOLDEN)).passed)

    def test_threshold_is_applied_to_overall_accuracy(self):
        report = report_for(perturbed(notes="something else"))
        self.assertTrue(evaluate_gate(report, 0.98).passed)
        self.assertFalse(evaluate_gate(report, 0.999).passed)

    def test_decision_field_error_fails_even_when_overall_accuracy_is_high(self):
        report = report_for(perturbed(recommendation="drop"))
        gate = evaluate_gate(report, 0.90)
        self.assertGreater(report.accuracy, 0.99)
        self.assertFalse(gate.passed)
        failed = [c.name for c in gate.checks if not c.passed]
        self.assertEqual(failed, ["class floor: categorical"])

    def test_one_narrative_miss_is_tolerated(self):
        self.assertTrue(evaluate_gate(report_for(perturbed(key_findings=["paraphrase"]))).passed)

    def test_schema_invalid_after_normalization_fails(self):
        report = report_for(perturbed(rating_scale=10, average_rating=9.0))
        gate = evaluate_gate(report, 0.5)
        self.assertEqual(report.schema_valid_normalized, 11)
        self.assertIn("schema-valid after normalization", [c.name for c in gate.checks if not c.passed])

    def test_hallucinated_field_fails(self):
        candidates = perturbed(price_tier="premium")
        self.assertFalse(evaluate_gate(report_for(candidates)).passed)


if __name__ == "__main__":
    unittest.main()
