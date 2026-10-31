"""Command line entry point: report, baseline, summary and cost."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import baseline as baseline_extractor
from .cost import FlatPricing, MeteredPricing, Volumes, break_even_runs
from .parity import DEFAULT_GATE, STATUSES, GateResult, Report, build_report, evaluate_gate
from .schema import SCHEMA_PATH, load_schema

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GOLDEN = ROOT / "data" / "golden"
DEFAULT_DOCUMENTS = ROOT / "data" / "documents"
DEFAULT_CANDIDATES = ROOT / "data" / "candidates"
MAX_LISTED_MISMATCHES = 20


class DataError(Exception):
    pass


def load_json_dir(directory: Path) -> Dict[str, Dict[str, Any]]:
    if not directory.is_dir():
        raise DataError(f"not a directory: {directory}")
    records = {}
    for path in sorted(directory.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise DataError(f"invalid JSON in {path}: {error}") from error
        if not isinstance(record, dict):
            raise DataError(f"{path} must contain a JSON object")
        records[path.stem] = record
    if not records:
        raise DataError(f"no .json files in {directory}")
    return records


def render_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> List[str]:
    cells = [[str(value) for value in row] for row in rows]
    widths = [max([len(headers[i])] + [len(row[i]) for row in cells]) for i in range(len(headers))]
    lines = ["  " + "  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))).rstrip()]
    for row in cells:
        lines.append("  " + "  ".join(row[i].ljust(widths[i]) for i in range(len(headers))).rstrip())
    return lines


def _short(value: Any, limit: int = 38) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _display(path: str) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path.cwd()))
    except ValueError:
        return path


def render_report(title: str, report: Report, gate: Optional[GateResult]) -> str:
    docs = len(report.docs)
    cells = len(report.cells)
    taxonomy = report.taxonomy()
    lines = [
        title,
        f"documents: {docs}   cells compared: {cells}",
        "",
        f"Doc-level exact match (normalized):   {report.documents_exact}/{docs}",
        f"Field accuracy (normalized):          {report.accuracy:.3f}  ({taxonomy['match'] + taxonomy['format_only']}/{cells})",
        f"Field accuracy (raw, strict):         {report.strict_accuracy:.3f}  ({taxonomy['match']}/{cells})",
        f"Schema-valid, raw output:             {report.schema_valid_raw}/{docs}",
        f"Schema-valid, after normalization:    {report.schema_valid_normalized}/{docs}",
        "",
        "Mismatch taxonomy",
    ]
    lines += render_table(
        ["class", "count", "share"],
        [[status, taxonomy[status], f"{taxonomy[status] / cells:.1%}" if cells else "n/a"] for status in STATUSES],
    )
    lines += ["", "Per-field breakdown"]
    lines += render_table(
        ["field", "class", "acc", "format_only", "missing", "extra", "type", "value"],
        [
            [name, row["class"], f"{row['accuracy']:.3f}", row["format_only"], row["missing"], row["extra"], row["type"], row["value"]]
            for name, row in report.per_field().items()
        ],
    )
    mismatches = report.mismatches()
    if mismatches:
        lines += ["", f"Mismatches ({len(mismatches)})"]
        lines += render_table(
            ["doc", "field", "class", "expected", "actual"],
            [[m.doc, m.field, m.status, _short(m.expected), _short(m.actual)] for m in mismatches[:MAX_LISTED_MISMATCHES]],
        )
        if len(mismatches) > MAX_LISTED_MISMATCHES:
            lines.append(f"  ... and {len(mismatches) - MAX_LISTED_MISMATCHES} more (use --json for the full list)")
    if report.extra_documents:
        lines += ["", "Candidate files with no golden record: " + ", ".join(report.extra_documents)]
    if gate is not None:
        lines += ["", f"Gate (threshold {gate.threshold:.3f}): {'PASS' if gate.passed else 'FAIL'}"]
        lines += [f"  [{'ok' if check.passed else 'FAIL'}] {check.name}: {check.detail}" for check in gate.checks]
    return "\n".join(lines)


def _emit(text: str, data: Dict[str, Any], as_json: bool) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False) if as_json else text)


def cmd_report(args: argparse.Namespace) -> int:
    golden = load_json_dir(Path(args.golden))
    candidates = load_json_dir(Path(args.candidate))
    report = build_report(golden, candidates, load_schema(Path(args.schema)))
    gate = evaluate_gate(report, args.gate)
    title = f"Parity report: {_display(args.candidate)} vs {_display(args.golden)}"
    _emit(render_report(title, report, gate), report.to_dict(gate), args.json)
    return 0 if gate.passed else 1


def cmd_baseline(args: argparse.Namespace) -> int:
    golden = load_json_dir(Path(args.golden))
    documents = Path(args.documents)
    if not documents.is_dir():
        raise DataError(f"not a directory: {documents}")
    report = build_report(golden, baseline_extractor.extract_dir(documents), load_schema())
    gate = evaluate_gate(report, args.gate) if args.gate is not None else None
    title = f"Baseline report: rule-based extractor on {_display(args.documents)} vs {_display(args.golden)}"
    _emit(render_report(title, report, gate), report.to_dict(gate), args.json)
    return 0 if gate is None or gate.passed else 1


def cmd_summary(args: argparse.Namespace) -> int:
    golden = load_json_dir(Path(args.golden))
    schema = load_schema()
    sources = {
        name: load_json_dir(Path(args.candidates) / name) for name in ("candidate_a", "candidate_b")
    }
    sources["rule-based baseline"] = baseline_extractor.extract_dir(Path(args.documents))
    lines = [
        f"| Source | Gate ({DEFAULT_GATE:.2f}) | Docs exact | Field accuracy | Strict accuracy | Schema-valid (normalized) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, candidate in sources.items():
        report = build_report(golden, candidate, schema)
        verdict = "PASS" if evaluate_gate(report).passed else "FAIL"
        lines.append(
            f"| {name} | {verdict} | {report.documents_exact}/{len(report.docs)} | {report.accuracy:.3f} "
            f"| {report.strict_accuracy:.3f} | {report.schema_valid_normalized}/{len(report.docs)} |"
        )
    print("\n".join(lines))
    return 0


def cmd_cost(args: argparse.Namespace) -> int:
    volumes = Volumes(args.docs_per_run, args.runs_per_month, args.calls_per_doc, args.retry_rate)
    metered = MeteredPricing(args.metered_price_per_call)
    flat = FlatPricing(args.flat_fee, args.flat_calls_per_pack)
    metered_month = metered.cost_per_month(volumes)
    flat_month = flat.cost_per_month(volumes)
    break_even = break_even_runs(volumes, metered, flat)
    data = {
        "calls_per_run": volumes.calls_per_run,
        "calls_per_month": volumes.calls_per_month,
        "metered": {"per_run": metered.cost_per_run(volumes), "per_month": metered_month},
        "flat": {
            "packs_needed": flat.packs_needed(volumes),
            "per_run_amortized": flat.cost_per_run(volumes),
            "per_month": flat_month,
        },
        "cheaper_at_this_volume": "flat" if flat_month < metered_month else "metered",
        "break_even_runs_per_month": break_even,
    }
    text = "\n".join(
        [
            "Cost model (prices are the values you passed in; units are whatever currency you used)",
            f"calls per run:    {volumes.calls_per_run:,.1f}",
            f"calls per month:  {volumes.calls_per_month:,.1f}",
            "",
            "Metered per-call",
            f"  per run:        {data['metered']['per_run']:,.2f}",
            f"  per month:      {metered_month:,.2f}",
            "",
            "Flat capacity",
            f"  packs needed:   {data['flat']['packs_needed']}",
            f"  per run:        {data['flat']['per_run_amortized']:,.2f}  (monthly fee spread over runs)",
            f"  per month:      {flat_month:,.2f}",
            "",
            f"Cheaper at this volume: {data['cheaper_at_this_volume']}",
            "Break-even: "
            + (
                f"flat is no more expensive from {break_even} runs/month (within one pack)"
                if break_even is not None
                else "none within one pack; metered is cheaper for every volume that fits"
            ),
        ]
    )
    _emit(text, data, args.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="extraction_demo", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    report = commands.add_parser("report", help="compare candidate output with the golden set and apply the gate")
    report.add_argument("--golden", default=str(DEFAULT_GOLDEN))
    report.add_argument("--candidate", required=True)
    report.add_argument("--schema", default=str(SCHEMA_PATH))
    report.add_argument("--gate", type=float, default=DEFAULT_GATE, help="minimum overall field accuracy")
    report.add_argument("--json", action="store_true")
    report.set_defaults(func=cmd_report)

    base = commands.add_parser("baseline", help="score the rule-based extractor against the golden set")
    base.add_argument("--golden", default=str(DEFAULT_GOLDEN))
    base.add_argument("--documents", default=str(DEFAULT_DOCUMENTS))
    base.add_argument("--gate", type=float, default=None, help="apply the gate; exit 1 on failure")
    base.add_argument("--json", action="store_true")
    base.set_defaults(func=cmd_baseline)

    summary = commands.add_parser("summary", help="markdown table of candidate_a, candidate_b and the baseline")
    summary.add_argument("--golden", default=str(DEFAULT_GOLDEN))
    summary.add_argument("--documents", default=str(DEFAULT_DOCUMENTS))
    summary.add_argument("--candidates", default=str(DEFAULT_CANDIDATES))
    summary.set_defaults(func=cmd_summary)

    cost = commands.add_parser("cost", help="compare metered and flat-capacity pricing; all prices are required")
    cost.add_argument("--docs-per-run", type=int, required=True)
    cost.add_argument("--runs-per-month", type=int, required=True)
    cost.add_argument("--calls-per-doc", type=float, default=1.0)
    cost.add_argument("--retry-rate", type=float, default=0.0, help="fraction of calls that are repeated")
    cost.add_argument("--metered-price-per-call", type=float, required=True)
    cost.add_argument("--flat-fee", type=float, required=True, help="fee for one pack of calls")
    cost.add_argument("--flat-calls-per-pack", type=int, required=True)
    cost.add_argument("--json", action="store_true")
    cost.set_defaults(func=cmd_cost)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (DataError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
