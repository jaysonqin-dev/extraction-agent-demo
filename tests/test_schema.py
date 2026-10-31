import unittest

import helpers  # noqa: F401  (puts the repo root on sys.path)
from extraction_demo.schema import load_schema, validate


def codes(errors):
    return sorted((e.path, e.code) for e in errors)


class ValidatorRules(unittest.TestCase):
    def test_type_mismatch(self):
        self.assertEqual(codes(validate("x", {"type": "integer"})), [("$", "type")])

    def test_bool_is_not_an_integer_or_number(self):
        self.assertEqual(codes(validate(True, {"type": "integer"})), [("$", "type")])
        self.assertEqual(codes(validate(False, {"type": "number"})), [("$", "type")])

    def test_integer_is_a_number_but_float_is_not_an_integer(self):
        self.assertEqual(validate(3, {"type": "number"}), [])
        self.assertEqual(codes(validate(3.5, {"type": "integer"})), [("$", "type")])

    def test_null_requires_nullable(self):
        self.assertEqual(codes(validate(None, {"type": "string"})), [("$", "null_not_allowed")])
        self.assertEqual(validate(None, {"type": "string", "nullable": True}), [])

    def test_enum(self):
        schema = {"type": "string", "enum": ["a", "b"]}
        self.assertEqual(validate("a", schema), [])
        self.assertEqual(codes(validate("c", schema)), [("$", "enum")])

    def test_minimum_and_maximum(self):
        schema = {"type": "number", "minimum": 1, "maximum": 5}
        self.assertEqual(validate(1, schema), [])
        self.assertEqual(codes(validate(0.9, schema)), [("$", "minimum")])
        self.assertEqual(codes(validate(5.1, schema)), [("$", "maximum")])

    def test_pattern_and_min_length(self):
        schema = {"type": "string", "pattern": "^[A-Z]+$", "minLength": 2}
        self.assertEqual(validate("AB", schema), [])
        self.assertEqual(codes(validate("a", schema)), [("$", "minLength"), ("$", "pattern")])

    def test_date_format_rejects_impossible_dates(self):
        schema = {"type": "string", "format": "date"}
        self.assertEqual(validate("2025-02-28", schema), [])
        self.assertEqual(codes(validate("2025-02-30", schema)), [("$", "format")])
        self.assertEqual(codes(validate("14 Mar 2025", schema)), [("$", "format")])

    def test_array_bounds_and_item_paths(self):
        schema = {"type": "array", "minItems": 1, "maxItems": 2, "items": {"type": "string"}}
        self.assertEqual(codes(validate([], schema)), [("$", "minItems")])
        self.assertEqual(codes(validate(["a", "b", "c"], schema)), [("$", "maxItems")])
        self.assertEqual(codes(validate(["a", 2], schema)), [("$[1]", "type")])

    def test_object_required_and_additional_properties(self):
        schema = {
            "type": "object",
            "required": ["a"],
            "additionalProperties": False,
            "properties": {"a": {"type": "integer"}},
        }
        self.assertEqual(validate({"a": 1}, schema), [])
        self.assertEqual(codes(validate({}, schema)), [("$.a", "required")])
        self.assertEqual(codes(validate({"a": 1, "b": 2}, schema)), [("$.b", "additional_property")])

    def test_nested_paths(self):
        schema = {
            "type": "object",
            "properties": {
                "outer": {
                    "type": "object",
                    "properties": {"items": {"type": "array", "items": {"type": "integer"}}},
                }
            },
        }
        errors = validate({"outer": {"items": [1, "x"]}}, schema)
        self.assertEqual(codes(errors), [("$.outer.items[1]", "type")])
        self.assertIn("expected integer", errors[0].message)

    def test_type_failure_skips_dependent_rules(self):
        self.assertEqual(len(validate("x", {"type": "number", "minimum": 1})), 1)


class ShippedSchema(unittest.TestCase):
    def setUp(self):
        self.schema = load_schema()
        self.valid = helpers.load_dir(helpers.DATA / "golden")["sb_01"]

    def test_golden_records_are_valid(self):
        for name, record in helpers.load_dir(helpers.DATA / "golden").items():
            self.assertEqual(validate(record, self.schema), [], name)

    def test_shareback_rules_fire_with_field_paths(self):
        bad = dict(self.valid, style_code="tjx1", participants=0, average_rating=8.4, rating_scale=10)
        bad["key_findings"] = ["a"] * 6
        self.assertEqual(
            codes(validate(bad, self.schema)),
            [
                ("$.average_rating", "maximum"),
                ("$.key_findings", "maxItems"),
                ("$.participants", "minimum"),
                ("$.rating_scale", "enum"),
                ("$.style_code", "pattern"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
