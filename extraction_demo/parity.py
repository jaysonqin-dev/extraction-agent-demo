"""Field-level parity between candidate output and the golden set, plus the ship/no-ship gate."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .normalize import is_null_like, normalize_record, normalize_value
from .schema import SchemaError, validate

MATCH = "match"
FORMAT_ONLY = "format_only"
MISSING = "missing"
EXTRA = "extra"
TYPE = "type"
VALUE = "value"

STATUSES = (MATCH, FORMAT_ONLY, MISSING, EXTRA, TYPE, VALUE)
CORRECT = (MATCH, FORMAT_ONLY)

FIELD_CLASS = {
    "product_name": "identity",
    "style_code": "identity",
    "test_date": "identity",
    "reviewer_names": "identity",
    "test_type": "categorical",
    "rating_scale": "categorical",
    "recommendation": "categorical",
    "participants": "numeric",
    "average_rating": "numeric",
    "key_findings": "narrative",
    "notes": "narrative",
}
UNEXPECTED = "unexpected"

# Fields that drive a decision must be exact; narrative fields tolerate occasional paraphrase.
CLASS_FLOORS = {"identity": 1.0, "categorical": 1.0, "numeric": 1.0, "narrative": 0.9, UNEXPECTED: 1.0}
DEFAULT_GATE = 0.98


@dataclass(frozen=True)
class FieldResult:
    doc: str
    field: str
    status: str
    expected: Any
    actual: Any

    @property
    def field_class(self) -> str:
        return FIELD_CLASS.get(self.field, UNEXPECTED)


@dataclass(frozen=True)
class DocResult:
    name: str
    cells: List[FieldResult]
    raw_errors: List[SchemaError]
    normalized_errors: List[SchemaError]

    @property
    def exact(self) -> bool:
        return all(cell.status in CORRECT for cell in self.cells)


@dataclass(frozen=True)
class GateCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class GateResult:
    threshold: float
    checks: List[GateCheck]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


def classify(field: str, expected_raw: Any, actual_raw: Any) -> str:
    expected = normalize_value(field, expected_raw)
    actual = normalize_value(field, actual_raw)
    if expected is None and actual is None:
        return MATCH if expected_raw == actual_raw else FORMAT_ONLY
    if expected is None:
        return EXTRA
    if actual is None:
        return MISSING
    if type(expected) is not type(actual):
        return TYPE
    if expected != actual:
        return VALUE
    return MATCH if expected_raw == actual_raw else FORMAT_ONLY


def compare_document(name: str, golden: Dict[str, Any], candidate: Optional[Dict[str, Any]]) -> List[FieldResult]:
    """A missing candidate (None) is treated as an empty record, so every non-null field is `missing`."""
    candidate = candidate or {}
    fields = list(golden) + [key for key, value in candidate.items() if key not in golden and not is_null_like(value)]
    return [
        FieldResult(name, field, classify(field, golden.get(field), candidate.get(field)), golden.get(field), candidate.get(field))
        for field in fields
    ]


class Report:
    def __init__(self, docs: List[DocResult], extra_documents: List[str]) -> None:
        self.docs = docs
        self.extra_documents = extra_documents

    @property
    def cells(self) -> List[FieldResult]:
        return [cell for doc in self.docs for cell in doc.cells]

    def taxonomy(self) -> Dict[str, int]:
        counts = {status: 0 for status in STATUSES}
        for cell in self.cells:
            counts[cell.status] += 1
        return counts

    @property
    def accuracy(self) -> float:
        return _ratio(sum(1 for c in self.cells if c.status in CORRECT), len(self.cells))

    @property
    def strict_accuracy(self) -> float:
        return _ratio(sum(1 for c in self.cells if c.status == MATCH), len(self.cells))

    @property
    def documents_exact(self) -> int:
        return sum(1 for doc in self.docs if doc.exact)

    @property
    def schema_valid_raw(self) -> int:
        return sum(1 for doc in self.docs if not doc.raw_errors)

    @property
    def schema_valid_normalized(self) -> int:
        return sum(1 for doc in self.docs if not doc.normalized_errors)

    def per_field(self) -> Dict[str, Dict[str, Any]]:
        rows: Dict[str, Dict[str, Any]] = {}
        for cell in self.cells:
            row = rows.setdefault(cell.field, {"class": cell.field_class, "total": 0, **{s: 0 for s in STATUSES}})
            row["total"] += 1
            row[cell.status] += 1
        for row in rows.values():
            row["accuracy"] = _ratio(row[MATCH] + row[FORMAT_ONLY], row["total"])
        return rows

    def per_class(self) -> Dict[str, Dict[str, Any]]:
        totals: Dict[str, List[int]] = {}
        for cell in self.cells:
            correct_total = totals.setdefault(cell.field_class, [0, 0])
            correct_total[1] += 1
            correct_total[0] += cell.status in CORRECT
        return {
            name: {"total": total, "accuracy": _ratio(correct, total), "floor": CLASS_FLOORS[name]}
            for name, (correct, total) in totals.items()
        }

    def mismatches(self) -> List[FieldResult]:
        return [cell for cell in self.cells if cell.status not in CORRECT]

    def to_dict(self, gate: Optional[GateResult] = None) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "documents": len(self.docs),
            "cells": len(self.cells),
            "documents_exact": self.documents_exact,
            "accuracy": round(self.accuracy, 4),
            "strict_accuracy": round(self.strict_accuracy, 4),
            "schema_valid_raw": self.schema_valid_raw,
            "schema_valid_normalized": self.schema_valid_normalized,
            "taxonomy": self.taxonomy(),
            "per_class": self.per_class(),
            "per_field": self.per_field(),
            "mismatches": [
                {"doc": c.doc, "field": c.field, "status": c.status, "expected": c.expected, "actual": c.actual}
                for c in self.mismatches()
            ],
            "schema_errors": {
                doc.name: [error.to_dict() for error in doc.normalized_errors] for doc in self.docs if doc.normalized_errors
            },
            "extra_documents": self.extra_documents,
        }
        if gate is not None:
            data["gate"] = {
                "passed": gate.passed,
                "threshold": gate.threshold,
                "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in gate.checks],
            }
        return data


def build_report(
    golden: Dict[str, Dict[str, Any]],
    candidates: Dict[str, Dict[str, Any]],
    schema: Dict[str, Any],
) -> Report:
    docs = []
    for name, expected in golden.items():
        candidate = candidates.get(name)
        record = candidate or {}
        docs.append(
            DocResult(
                name=name,
                cells=compare_document(name, expected, candidate),
                raw_errors=validate(record, schema),
                normalized_errors=validate(normalize_record(record), schema),
            )
        )
    return Report(docs, sorted(set(candidates) - set(golden)))


def evaluate_gate(report: Report, threshold: float = DEFAULT_GATE) -> GateResult:
    checks = [
        GateCheck(
            "overall field accuracy",
            report.accuracy >= threshold,
            f"{report.accuracy:.3f} (need >= {threshold:.3f})",
        ),
        GateCheck(
            "schema-valid after normalization",
            report.schema_valid_normalized == len(report.docs),
            f"{report.schema_valid_normalized}/{len(report.docs)} documents (need all)",
        ),
    ]
    for name, stats in report.per_class().items():
        checks.append(
            GateCheck(
                f"class floor: {name}",
                stats["accuracy"] >= stats["floor"],
                f"{stats['accuracy']:.3f} (need >= {stats['floor']:.3f})",
            )
        )
    return GateResult(threshold, checks)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
