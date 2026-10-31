# extraction-agent-demo

A team extracts structured fields from product-test "shareback" documents with an LLM step, and wants to swap that step for a cheaper or different runtime. The question is whether the new extractor is safe to ship. This repo answers it with an evaluation harness instead of a model call: a golden set, schema validation, normalization, a field-level parity report with a mismatch taxonomy, a pass/fail gate, a rule-based baseline as a floor, and a parametric cost model.

Everything is Python 3.9 standard library only. All data is synthetic, and the candidate outputs are hand-written fixtures standing in for model output; no live model calls are made.

## What this demonstrates

- Evaluation-driven development: the expected output is fixed first (12 golden records), and every candidate is judged by the same repeatable report.
- Schema-validated outputs: a small JSON-schema-style validator returns structured errors with paths and codes, and the shipped schema is the contract for both the golden set and the candidates.
- Normalization: cosmetic variation (`4,5 out of 5`, `14 Mar 2025`, `12 participants`, `N/A`) is separated from real errors, without hiding scale mix-ups or guessing ambiguous values.
- Parity gating: mismatches are classified as `missing`, `extra`, `type`, `value` or `format_only`, and the gate applies a threshold per field class, so one wrong recommendation fails a candidate even when overall accuracy looks high.
- Cost reasoning and honest limits: a parametric model compares metered and flat-capacity pricing with user-supplied prices, and the limits of a 12-document synthetic set are stated rather than hidden.

## Quickstart

No installation is needed. Run from the repository root.

```
python3 -m unittest discover -s tests
```

```
Ran 82 tests in 0.8s

OK
```

Report on the good candidate (exit code 0):

```
python3 -m extraction_demo report --golden data/golden --candidate data/candidates/candidate_a
```

<details>
<summary>Output</summary>

```
Parity report: data/candidates/candidate_a vs data/golden
documents: 12   cells compared: 132

Doc-level exact match (normalized):   11/12
Field accuracy (normalized):          0.992  (131/132)
Field accuracy (raw, strict):         0.856  (113/132)
Schema-valid, raw output:             3/12
Schema-valid, after normalization:    12/12

Mismatch taxonomy
  class        count  share
  match        113    85.6%
  format_only  18     13.6%
  missing      0      0.0%
  extra        0      0.0%
  type         0      0.0%
  value        1      0.8%

Per-field breakdown
  field           class        acc    format_only  missing  extra  type  value
  product_name    identity     1.000  1            0        0      0     0
  style_code      identity     1.000  1            0        0      0     0
  test_type       categorical  1.000  1            0        0      0     0
  test_date       identity     1.000  5            0        0      0     0
  participants    numeric      1.000  2            0        0      0     0
  average_rating  numeric      1.000  2            0        0      0     0
  rating_scale    categorical  1.000  0            0        0      0     0
  recommendation  categorical  1.000  2            0        0      0     0
  reviewer_names  identity     1.000  2            0        0      0     0
  key_findings    narrative    0.917  0            0        0      0     1
  notes           narrative    1.000  2            0        0      0     0

Mismatches (1)
  doc    field         class  expected                                actual
  sb_06  key_findings  value  ["Liner stayed in place during runs...  ["Liner stayed put during runs.", "...

Gate (threshold 0.980): PASS
  [ok] overall field accuracy: 0.992 (need >= 0.980)
  [ok] schema-valid after normalization: 12/12 documents (need all)
  [ok] class floor: identity: 1.000 (need >= 1.000)
  [ok] class floor: categorical: 1.000 (need >= 1.000)
  [ok] class floor: numeric: 1.000 (need >= 1.000)
  [ok] class floor: narrative: 0.958 (need >= 0.900)
```

</details>

Report on the candidate with realistic failure modes (exit code 1):

```
python3 -m extraction_demo report --golden data/golden --candidate data/candidates/candidate_b
```

<details>
<summary>Output</summary>

```
Parity report: data/candidates/candidate_b vs data/golden
documents: 12   cells compared: 133

Doc-level exact match (normalized):   4/12
Field accuracy (normalized):          0.932  (124/133)
Field accuracy (raw, strict):         0.902  (120/133)
Schema-valid, raw output:             7/12
Schema-valid, after normalization:    9/12

Mismatch taxonomy
  class        count  share
  match        120    90.2%
  format_only  4      3.0%
  missing      1      0.8%
  extra        2      1.5%
  type         1      0.8%
  value        5      3.8%

Per-field breakdown
  field           class        acc    format_only  missing  extra  type  value
  product_name    identity     1.000  0            0        0      0     0
  style_code      identity     1.000  0            0        0      0     0
  test_type       categorical  1.000  1            0        0      0     0
  test_date       identity     0.917  1            0        0      0     1
  participants    numeric      0.833  1            1        0      1     0
  average_rating  numeric      0.917  1            0        0      0     1
  rating_scale    categorical  0.917  0            0        0      0     1
  recommendation  categorical  0.917  0            0        0      0     1
  reviewer_names  identity     0.917  0            0        0      0     1
  key_findings    narrative    1.000  0            0        0      0     0
  notes           narrative    0.917  0            0        1      0     0
  price_tier      unexpected   0.000  0            0        1      0     0

Mismatches (9)
  doc    field           class    expected           actual
  sb_02  recommendation  value    "revise"           "ship"
  sb_03  price_tier      extra    null               "premium"
  sb_04  participants    missing  8                  null
  sb_05  average_rating  value    4.5                9.0
  sb_05  rating_scale    value    5                  10
  sb_06  test_date       value    "2025-05-19"       "2024-05-19"
  sb_08  notes           extra    null               "Reviewers noted no concerns."
  sb_09  reviewer_names  value    ["Kofi", "Sofia"]  ["Kofi and Sofia"]
  sb_10  participants    type     6                  "a handful"

Gate (threshold 0.980): FAIL
  [FAIL] overall field accuracy: 0.932 (need >= 0.980)
  [FAIL] schema-valid after normalization: 9/12 documents (need all)
  [FAIL] class floor: identity: 0.958 (need >= 1.000)
  [FAIL] class floor: categorical: 0.944 (need >= 1.000)
  [FAIL] class floor: numeric: 0.875 (need >= 1.000)
  [ok] class floor: narrative: 0.958 (need >= 0.900)
  [FAIL] class floor: unexpected: 0.000 (need >= 1.000)
```

</details>

Score the rule-based baseline against the same golden set (no gate unless `--gate` is given):

```
python3 -m extraction_demo baseline
```

<details>
<summary>Output</summary>

```
Baseline report: rule-based extractor on data/documents vs data/golden
documents: 12   cells compared: 132

Doc-level exact match (normalized):   9/12
Field accuracy (normalized):          0.977  (129/132)
Field accuracy (raw, strict):         0.977  (129/132)
Schema-valid, raw output:             12/12
Schema-valid, after normalization:    12/12

Mismatch taxonomy
  class        count  share
  match        129    97.7%
  format_only  0      0.0%
  missing      1      0.8%
  extra        0      0.0%
  type         0      0.0%
  value        2      1.5%

Per-field breakdown
  field           class        acc    format_only  missing  extra  type  value
  product_name    identity     1.000  0            0        0      0     0
  style_code      identity     1.000  0            0        0      0     0
  test_type       categorical  1.000  0            0        0      0     0
  test_date       identity     0.917  0            0        0      0     1
  participants    numeric      0.917  0            1        0      0     0
  average_rating  numeric      0.917  0            0        0      0     1
  rating_scale    categorical  1.000  0            0        0      0     0
  recommendation  categorical  1.000  0            0        0      0     0
  reviewer_names  identity     1.000  0            0        0      0     0
  key_findings    narrative    1.000  0            0        0      0     0
  notes           narrative    1.000  0            0        0      0     0

Mismatches (3)
  doc    field           class    expected      actual
  sb_05  average_rating  value    4.5           5.0
  sb_06  test_date       value    "2025-05-19"  "2025-05-12"
  sb_11  participants    missing  18            null
```

</details>

Add `--json` to `report` or `baseline` for machine-readable output.

### Results

Generated by `python3 -m extraction_demo summary`:

```
| Source | Gate (0.98) | Docs exact | Field accuracy | Strict accuracy | Schema-valid (normalized) |
| --- | --- | --- | --- | --- | --- |
| candidate_a | PASS | 11/12 | 0.992 | 0.856 | 12/12 |
| candidate_b | FAIL | 4/12 | 0.932 | 0.902 | 9/12 |
| rule-based baseline | FAIL | 9/12 | 0.977 | 0.977 | 12/12 |
```

Reading it: `candidate_a` passes. Its strict accuracy is low because most of its differences are formatting, which normalization absorbs; one paraphrased finding is tolerated by the narrative floor. `candidate_b` fails on several independent grounds and scores below the baseline. The baseline fails the gate on its numeric and identity floors even though its overall accuracy is 0.977. It was written while looking at these same 12 documents, so its score is optimistic.

### Cost model

All prices are inputs. The example below uses illustrative placeholders only, not real prices:

```
python3 -m extraction_demo cost --docs-per-run 200 --runs-per-month 20 --metered-price-per-call 0.01 --flat-fee 40 --flat-calls-per-pack 10000 --retry-rate 0.05
```

```
Cost model (prices are the values you passed in; units are whatever currency you used)
calls per run:    210.0
calls per month:  4,200.0

Metered per-call
  per run:        2.10
  per month:      42.00

Flat capacity
  packs needed:   1
  per run:        2.00  (monthly fee spread over runs)
  per month:      40.00

Cheaper at this volume: flat
Break-even: flat is no more expensive from 20 runs/month (within one pack)
```

## Honest limits

- All data is synthetic: 12 documents in three house styles, with fictional products, tester names and dates.
- The candidate outputs are hand-written fixtures built to show specific behaviours. No live model was called, and the fixtures say nothing about how any real model performs.
- Twelve documents can test the harness but cannot estimate real accuracy; one miss moves a field by about 8 points.
- The baseline was tuned on the same documents it is scored on.
- Gate thresholds and all cost figures are illustrative.
- With a real LLM the harness would also need repeated runs to measure sampling variance. See [docs/design.md](docs/design.md).

## Project layout

```
README.md
LICENSE
pyproject.toml
schema/shareback.schema.json   schema for the extracted fields
extraction_demo/
  schema.py                    schema-lite validator returning (path, code, message) errors
  normalize.py                 whitespace, case, ratings, counts, dates, null-likes, lists
  baseline.py                  deterministic regex extractor (the floor)
  parity.py                    comparison, mismatch taxonomy, aggregation, gate
  cost.py                      metered and flat-capacity cost model, break-even
  cli.py                       report, baseline, summary, cost
data/
  documents/                   12 synthetic documents
  golden/                      expected fields per document
  candidates/candidate_a/      fixtures: mostly correct, cosmetic differences
  candidates/candidate_b/      fixtures: realistic failure modes
tests/                         82 unittest tests
docs/design.md                 decisions, trade-offs, limits
```

## License

MIT. See [LICENSE](LICENSE).
