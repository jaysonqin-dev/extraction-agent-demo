# Data

Everything in this directory is synthetic.

- `documents/`: 12 invented product-test shareback documents in three house styles. Products, style codes, tester first names and dates are fictional.
- `golden/`: the hand-written expected fields for each document, matching `schema/shareback.schema.json`.
- `candidates/candidate_a/` and `candidates/candidate_b/`: hand-written fixtures standing in for the output of a new extractor. No live model calls were made and no model produced them. `candidate_a` is written to be mostly correct with cosmetic differences; `candidate_b` is written to contain realistic failure modes.
