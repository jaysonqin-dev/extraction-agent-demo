import unittest

import helpers  # noqa: F401
from extraction_demo.normalize import (
    is_null_like,
    normalize_record,
    normalize_value,
    parse_date,
    parse_int,
    parse_rating,
)


class Ratings(unittest.TestCase):
    def test_formats_normalize_to_the_same_number(self):
        for raw in ("4.5", "4,5", "4.5/5", "4.5 / 5", "4,5 out of 5", 4.5, " 4.50 "):
            self.assertEqual(normalize_value("average_rating", raw), 4.5, raw)

    def test_scale_is_reported_but_never_converted(self):
        self.assertEqual(parse_rating("8.4/10"), (8.4, 10))
        self.assertEqual(normalize_value("average_rating", "8.4/10"), 8.4)

    def test_date_is_not_read_as_a_rating(self):
        self.assertIsNone(parse_rating("took place on 05/19/2025 with"))

    def test_unparseable_rating_stays_a_string(self):
        self.assertEqual(normalize_value("average_rating", "pretty good"), "pretty good")


class Counts(unittest.TestCase):
    def test_prose_and_words(self):
        self.assertEqual(parse_int("12 participants"), 12)
        self.assertEqual(parse_int("fifteen participants"), 15)
        self.assertEqual(parse_int(12.0), 12)

    def test_ambiguous_or_missing_counts_are_not_guessed(self):
        self.assertEqual(parse_int("12 to 15 testers"), "12 to 15 testers")
        self.assertEqual(parse_int("a handful"), "a handful")
        self.assertIsNone(parse_int("n/a"))

    def test_bool_is_left_alone(self):
        self.assertIs(parse_int(True), True)


class Dates(unittest.TestCase):
    def test_many_formats_to_iso(self):
        for raw in ("2025-03-14", "2025/03/14", "14 Mar 2025", "14 March 2025", "Mar 14, 2025",
                    "March 14, 2025", "14-Mar-2025", "03/14/2025", "14/03/2025", "March 14th, 2025"):
            self.assertEqual(parse_date(raw), "2025-03-14", raw)

    def test_slash_dates_are_month_first_when_ambiguous(self):
        self.assertEqual(parse_date("03/04/2025"), "2025-03-04")

    def test_invalid_date_stays_as_text(self):
        self.assertIsNone(parse_date("2025-02-30"))
        self.assertEqual(normalize_value("test_date", "next Tuesday"), "next Tuesday")


class NullsAndText(unittest.TestCase):
    def test_null_likes(self):
        for raw in (None, "", "  ", "n/a", "N/A", "None", "-", "null"):
            self.assertTrue(is_null_like(raw), repr(raw))
        self.assertFalse(is_null_like("Not applicable to wear tests"))
        self.assertFalse(is_null_like([]))

    def test_whitespace_and_case(self):
        self.assertEqual(normalize_value("product_name", "  Trail   JACKET X1 "), "trail jacket x1")
        self.assertEqual(normalize_value("style_code", " tjx1-25"), "TJX1-25")
        self.assertEqual(normalize_value("recommendation", "SHIP"), "ship")
        self.assertIsNone(normalize_value("notes", "N/A"))


class Lists(unittest.TestCase):
    def test_string_is_split_and_order_is_ignored(self):
        expected = ["kofi", "sofia"]
        for raw in ("Sofia, Kofi", "Kofi & Sofia", "Kofi and Sofia", ["Sofia", "Kofi"]):
            self.assertEqual(normalize_value("reviewer_names", raw), expected, raw)

    def test_names_containing_and_are_not_split(self):
        self.assertEqual(normalize_value("reviewer_names", ["Sandra"]), ["sandra"])

    def test_merged_names_inside_a_list_are_not_split(self):
        self.assertEqual(normalize_value("reviewer_names", ["Kofi and Sofia"]), ["kofi and sofia"])

    def test_bullets_are_stripped_from_findings(self):
        self.assertEqual(normalize_value("key_findings", "- b one\n* a two"), ["a two", "b one"])


class Records(unittest.TestCase):
    def test_unknown_fields_pass_through_generic_normalization(self):
        record = normalize_record({"price_tier": "  Premium ", "notes": "none", "tags": ["A  b"]})
        self.assertEqual(record, {"price_tier": "premium", "notes": None, "tags": ["a b"]})


if __name__ == "__main__":
    unittest.main()
