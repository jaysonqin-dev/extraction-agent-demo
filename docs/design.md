# Design notes

This repo answers one question: is a replacement extractor safe to ship? The notes below explain the decisions behind the answer and where it stops being reliable.

## Why a golden set and a parity report, not eyeballing

Reading a few outputs and deciding they look fine does not scale and does not repeat. Two people read the same output differently, and the same person reads it differently on a Friday afternoon. A golden set fixes the expected answer once. A parity report then turns every candidate into the same comparable numbers, so a change of runtime, prompt, or model becomes a diff in a table rather than an opinion.

The golden records are hand-written from the source documents and validated against the schema, so the golden set cannot drift out of contract.

## Why normalize before comparing

Two outputs can disagree in text and agree in meaning: `4,5 out of 5` and `4.5`, `14 Mar 2025` and `2025-03-14`, `Revise` and `revise`. If the comparison is strict, those cosmetic differences dominate the report and hide the errors that matter. If the comparison is only normalized, the report hides a real contract problem, because a downstream consumer may not accept `4,5 out of 5`.

The report therefore keeps both views. `format_only` counts a field that is equal after normalization but different as written. Field accuracy counts it as correct; strict accuracy does not. The gap between the two numbers is the size of the contract cleanup still owed.

Normalization is deliberately conservative:

- It never converts rating scales. `8.4/10` normalizes to `8.4`, which then fails against `4.2` and fails the schema maximum. Silently rescaling would hide exactly the scale mix-up we want to catch.
- It never guesses an ambiguous count. `12 to 15 testers` stays as text and shows up as a `type` mismatch.
- Slash dates are read month-first and fall back to day-first when the month-first reading is impossible. `03/04/2025` is therefore 4 March, which is a stated convention rather than a fact about the data. A real deployment would pin the convention per source.
- Lists compare as order-insensitive collections. Reviewers and findings have no meaningful order in this schema. A merged entry such as `["Kofi and Sofia"]` is not split, so merging two reviewers is a value error.

Schema validity is reported twice, on the raw output and on the normalized output. Raw validity says how much cleanup a consumer would have to do. Normalized validity says whether the output is recoverable at all, and the gate requires it for every document.

## Why a mismatch taxonomy

A single accuracy number says how often the extractor is wrong, not how. The classes point at different fixes:

| Class | Meaning | Typical cause and response |
| --- | --- | --- |
| `match` | Identical as written | None |
| `format_only` | Equal after normalization, different as written | Output contract is loose; tighten the prompt or add a post-processor |
| `missing` | Golden has a value, candidate has none | Recall problem; check how the field is located in each document style |
| `extra` | Candidate has a value where golden has none, or a field outside the schema | Hallucination; the most expensive class to leave in production |
| `type` | Candidate value is not the expected kind after normalization | Output contract violation, such as prose in a numeric field |
| `value` | Right kind, wrong content | Comprehension error: wrong year, wrong scale, merged reviewers |

Absent keys and nulls are treated as equal, and null-like spellings such as `N/A` or `none` normalize to null. Fields in the candidate that are not in the golden record become their own comparison cells in an `unexpected` class, so a hallucinated field lowers accuracy rather than being ignored.

## Why the gate has thresholds per field class

One global accuracy threshold treats a wrong recommendation and a paraphrased finding as equal costs. They are not. The gate therefore has three kinds of check:

1. Overall field accuracy at or above a threshold (default 0.98, set with `--gate`).
2. Every document schema-valid after normalization.
3. A floor per field class. Identity, categorical, numeric and unexpected fields must be exact. Narrative fields (findings, notes) allow a floor of 0.90 because wording varies without changing meaning.

This is why a candidate can score 0.98 or better overall and still fail: one wrong `recommendation` in 12 documents breaks the categorical floor while barely moving the average. The test suite pins that behaviour.

All thresholds are illustrative. In a real setting they should come from the cost of each error class, agreed with the people who consume the data.

## Why a rule-based baseline

A deterministic regex extractor is the floor. It answers whether a candidate adds anything over code that costs nothing to run. It also exposes labelling and document-style problems: its misses here come from distractor values (an earlier round's date, a sub-score before the overall rating) and an unlisted phrasing for the participant count.

Two caveats matter. First, the baseline was written while looking at these same 12 documents, so its score is optimistic; on unseen documents it would be lower. Second, field accuracy alone ranks it close to the good candidate. Document-level exact match and the class floors separate them more clearly, and a candidate that scores below the baseline, as `candidate_b` does, should not ship regardless of how it is branded.

## Cost model

The model is parametric on purpose: it contains no prices. The caller supplies a per-call price for the metered option, and a fee plus calls per pack for the flat-capacity option, as well as documents per run, runs per month, calls per document and a retry rate.

- Metered: `docs_per_run * calls_per_doc * (1 + retry_rate) * price_per_call`, per run and per month.
- Flat capacity: `ceil(calls_per_month / calls_per_pack)` packs at the pack fee. The per-run figure is the monthly fee spread over runs.
- Break-even: the smallest runs per month at which one flat pack costs no more than metered. It is reported only when it falls inside one pack's capacity; beyond that the step function makes "break-even" ambiguous, so the function returns none rather than a misleading number.

Numbers in the README are illustrative placeholders to show the arithmetic, not real prices. The model leaves out latency, engineering time, and the cost of errors. A natural extension is cost per correct document, which joins this model to the parity report: a cheaper runtime that fails the gate is not cheaper.

## What would change with a real LLM

The fixtures here are hand-written; no model was called. With a live model the harness would need these additions:

- Sampling variance. Run each document N times (for example 5) and report per-field agreement across runs, not a single pass. A field that flips between runs is a reliability finding even if its majority answer is right. Gate on the worst run or on a lower confidence bound.
- A larger, stratified golden set. Twelve documents is enough to test the harness, not enough to estimate accuracy. One miss moves a field by 8 points. A real set needs a hundred or more documents, covering every house style and including known hard cases, with a held-out slice that prompts are never tuned on.
- Confidence intervals. Report Wilson intervals per class so a floor is compared with a bound rather than a point estimate.
- Pinned versions. Record the model, prompt, and schema version with every report so a regression can be traced.
- Constrained output. Schema-constrained decoding would shift errors from `type` and `format_only` towards `value`, which is easier to reason about.
- Narrative fields. Exact comparison of free text is harsh. A rubric or a second-model judge could grade it, with the judge itself checked against human labels.
- Drift monitoring. Re-run the gate on a sample of new documents on a schedule.

## Limits

- All data is synthetic: fictional products, names and dates.
- 12 documents and three house styles. Results do not generalize.
- The candidate outputs are hand-written fixtures built to be informative, not model output.
- The baseline is tuned to the same documents it is scored on.
- Gate thresholds and cost inputs are illustrative.
- Date ambiguity, order-insensitive lists, and casefolded comparison are conventions, not facts about any real pipeline.
