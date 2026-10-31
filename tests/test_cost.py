import unittest

import helpers  # noqa: F401
from extraction_demo.cost import FlatPricing, MeteredPricing, Volumes, break_even_runs


class Metered(unittest.TestCase):
    def test_per_run_and_month(self):
        volumes = Volumes(docs_per_run=100, runs_per_month=20)
        metered = MeteredPricing(price_per_call=0.02)
        self.assertAlmostEqual(metered.cost_per_run(volumes), 2.0)
        self.assertAlmostEqual(metered.cost_per_month(volumes), 40.0)

    def test_calls_per_doc_and_retries_multiply_calls(self):
        volumes = Volumes(docs_per_run=100, runs_per_month=10, calls_per_doc=2, retry_rate=0.1)
        self.assertAlmostEqual(volumes.calls_per_run, 220.0)
        self.assertAlmostEqual(volumes.calls_per_month, 2200.0)

    def test_zero_volume_costs_nothing(self):
        self.assertEqual(MeteredPricing(1.0).cost_per_month(Volumes(0, 0)), 0.0)


class Flat(unittest.TestCase):
    def test_single_pack(self):
        volumes = Volumes(docs_per_run=100, runs_per_month=20)
        flat = FlatPricing(fee_per_pack=50, calls_per_pack=5000)
        self.assertEqual(flat.packs_needed(volumes), 1)
        self.assertEqual(flat.cost_per_month(volumes), 50)
        self.assertAlmostEqual(flat.cost_per_run(volumes), 2.5)

    def test_exact_capacity_does_not_buy_a_second_pack(self):
        volumes = Volumes(docs_per_run=100, runs_per_month=50)
        self.assertEqual(FlatPricing(50, 5000).packs_needed(volumes), 1)

    def test_overflow_buys_another_pack(self):
        volumes = Volumes(docs_per_run=100, runs_per_month=51)
        flat = FlatPricing(50, 5000)
        self.assertEqual(flat.packs_needed(volumes), 2)
        self.assertEqual(flat.cost_per_month(volumes), 100)

    def test_float_noise_does_not_trigger_an_extra_pack(self):
        volumes = Volumes(docs_per_run=100, runs_per_month=10, retry_rate=0.05)
        self.assertEqual(FlatPricing(1, 1050).packs_needed(volumes), 1)


class BreakEven(unittest.TestCase):
    def test_break_even_runs(self):
        volumes = Volumes(docs_per_run=100, runs_per_month=1)
        metered = MeteredPricing(0.01)
        flat = FlatPricing(50, 5000)
        self.assertEqual(break_even_runs(volumes, metered, flat), 50)

    def test_break_even_is_the_crossing_point(self):
        volumes = Volumes(docs_per_run=100, runs_per_month=1)
        metered = MeteredPricing(0.03)
        flat = FlatPricing(50, 5000)
        runs = break_even_runs(volumes, metered, flat)
        self.assertEqual(runs, 17)
        below = Volumes(100, runs - 1)
        at = Volumes(100, runs)
        self.assertLess(metered.cost_per_month(below), flat.cost_per_month(below))
        self.assertGreaterEqual(metered.cost_per_month(at), flat.cost_per_month(at))

    def test_none_when_flat_pack_is_too_small_to_ever_win(self):
        volumes = Volumes(docs_per_run=100, runs_per_month=1)
        self.assertIsNone(break_even_runs(volumes, MeteredPricing(0.01), FlatPricing(500, 5000)))

    def test_none_when_metered_is_free(self):
        self.assertIsNone(break_even_runs(Volumes(10, 1), MeteredPricing(0.0), FlatPricing(5, 100)))


class Validation(unittest.TestCase):
    def test_negative_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            MeteredPricing(-1)
        with self.assertRaises(ValueError):
            Volumes(10, 10, retry_rate=-0.1)

    def test_pack_size_must_be_positive(self):
        with self.assertRaises(ValueError):
            FlatPricing(10, 0)


if __name__ == "__main__":
    unittest.main()
