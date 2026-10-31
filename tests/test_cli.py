import json
import unittest

import helpers

A = "data/candidates/candidate_a"
B = "data/candidates/candidate_b"


class Report(unittest.TestCase):
    def test_candidate_a_passes_with_exit_zero(self):
        result = helpers.run_cli("report", "--golden", "data/golden", "--candidate", A)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Gate (threshold 0.980): PASS", result.stdout)

    def test_candidate_b_fails_with_exit_one_and_shows_taxonomy(self):
        result = helpers.run_cli("report", "--golden", "data/golden", "--candidate", B)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Gate (threshold 0.980): FAIL", result.stdout)
        for label in ("missing", "extra", "type", "value", "format_only"):
            self.assertIn(label, result.stdout)

    def test_gate_threshold_can_be_tightened(self):
        result = helpers.run_cli("report", "--golden", "data/golden", "--candidate", A, "--gate", "0.999")
        self.assertEqual(result.returncode, 1)

    def test_json_output_is_machine_readable(self):
        result = helpers.run_cli("report", "--golden", "data/golden", "--candidate", B, "--json")
        data = json.loads(result.stdout)
        self.assertFalse(data["gate"]["passed"])
        self.assertEqual(data["documents"], 12)
        self.assertEqual(sum(data["taxonomy"].values()), data["cells"])

    def test_missing_directory_is_a_usage_error(self):
        result = helpers.run_cli("report", "--golden", "data/golden", "--candidate", "data/nope")
        self.assertEqual(result.returncode, 2)
        self.assertIn("not a directory", result.stderr)


class Baseline(unittest.TestCase):
    def test_baseline_prints_a_score_and_exits_zero_without_a_gate(self):
        result = helpers.run_cli("baseline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Field accuracy (normalized)", result.stdout)

    def test_baseline_with_a_gate_can_fail(self):
        self.assertEqual(helpers.run_cli("baseline", "--gate", "0.999").returncode, 1)

    def test_summary_table_lists_all_sources(self):
        result = helpers.run_cli("summary")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 5)
        self.assertIn("candidate_a | PASS", lines[2])
        self.assertIn("candidate_b | FAIL", lines[3])


class Cost(unittest.TestCase):
    ARGS = (
        "cost", "--docs-per-run", "100", "--runs-per-month", "20",
        "--metered-price-per-call", "0.02", "--flat-fee", "50", "--flat-calls-per-pack", "5000",
    )

    def test_cost_output(self):
        result = helpers.run_cli(*self.ARGS, "--json")
        data = json.loads(result.stdout)
        self.assertAlmostEqual(data["metered"]["per_month"], 40.0)
        self.assertEqual(data["flat"]["per_month"], 50)
        self.assertEqual(data["cheaper_at_this_volume"], "metered")
        self.assertEqual(data["break_even_runs_per_month"], 25)

    def test_prices_are_required(self):
        result = helpers.run_cli("cost", "--docs-per-run", "100", "--runs-per-month", "20")
        self.assertEqual(result.returncode, 2)

    def test_invalid_input_is_reported(self):
        args = [a if a != "0.02" else "-1" for a in self.ARGS]
        result = helpers.run_cli(*args)
        self.assertEqual(result.returncode, 2)
        self.assertIn("negative", result.stderr)


class DataIntegrity(unittest.TestCase):
    def test_every_document_has_a_golden_record_and_both_candidates(self):
        docs = sorted(p.stem for p in (helpers.DATA / "documents").glob("*.txt"))
        self.assertEqual(len(docs), 12)
        for directory in ("golden", "candidates/candidate_a", "candidates/candidate_b"):
            self.assertEqual(sorted(helpers.load_dir(helpers.DATA / directory)), docs, directory)


if __name__ == "__main__":
    unittest.main()
