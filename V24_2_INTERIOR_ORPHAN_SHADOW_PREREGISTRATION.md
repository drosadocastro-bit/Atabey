# V24.2 Interior-Orphan Shadow Preregistration

Status: **approved; implementation-only checkpoint, scoring pending pinned predictor runtime**.

V24.1 localized node inflation to the `6bba/components` stratum but did not
justify global suppression. V24.2 tests one conservative post-link shadow
transform against the frozen E016 plus Atabey relink arm.

## Frozen Candidate Rule

Remove a detection only when all of the following hold:

- it has no incoming or outgoing continuation edge;
- it is not in the first or last observed frame;
- both adjacent frames contain at least one detection.

All connected detections and all existing edges are retained. The transform
returns a new graph and never mutates the frozen relink graph.

## Evaluation Contract

- Target stratum: `family=6bba` and `v19_reference_detector=components`.
- Controls: all other V24 samples remain reported unchanged.
- Cohort: the complete 27-sample V24 cohort, full sequences.
- Comparator: the exact V24 E016 plus Atabey relink arm.
- Primary metric: official adjusted edge Jaccard.
- Hard safety check: no edge may be removed or added by the transform.
- Promotion requires rerunning the complete V24 gate set; no smoke or local
  synthetic test can authorize full-199 evaluation.

The pinned public predictor runtime is required for scoring. Until that runtime
is available, this checkpoint provides only implementation and invariant tests,
not a score claim.