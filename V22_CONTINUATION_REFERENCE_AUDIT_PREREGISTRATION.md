# V22 Continuation-Reference Availability Audit Preregistration

Status: **PREREGISTERED READ-ONLY AUDIT; NO REAL-SAMPLE RESULTS OPENED**

## Question

Does the frozen 27-sample development split contain enough independent,
high-confidence V19 continuation references to support the planned weak
continuation-compatibility head without allowing a few dense samples, frames,
families, or routes to dominate it?

These references are weak compatibility evidence, not biological ground truth.
The audit does not fit a model, score a U-Net action, run assignment, or mutate a
graph.

## Frozen Population

The audit uses the same 27 samples and three sample-blocked folds as
`v22_joint_semantic_assignment_development_v1`. Every sample is rebuilt through
100 timepoints with the frozen V19 pre-firewall route. All 46 registered division
times are used only to exclude nearby references.

Results must be reported from the start by:

- fold;
- family (`44b6`, `6bba`);
- actual detector/link route;
- sample;
- parent frame.

Aggregate totals without these strata are insufficient.

Local-maxima is a transfer-only reporting stratum in this development split.
Because its only sample is in fold 3, folds 1 and 2 provide no held-out
local-maxima observation, while holding out fold 3 tests a route absent from
training. Every local-maxima metric must be separate and carry the caveat
**unproven generalization**; it cannot be hidden inside a pooled route-neutral
result.

## Reference Definition

A retained reference is one consecutive three-frame chain:

```text
anchor(t-1) -> parent(t) -> child(t+1)
```

All of the following are required:

1. both graph edges have relation `continuation`;
2. the anchor has exactly one outgoing edge;
3. the parent has exactly one incoming and one outgoing edge;
4. the child has exactly one incoming edge;
5. the child lies inside the frozen 14 um local action radius;
6. the central parent-to-child edge passes a route-neutral mutual-nearest test:
   - forward identity is the strict nearest child to the constant-velocity
     prediction from anchor through parent;
   - reverse identity is the strict nearest parent to the child in raw physical
     distance;
   - exact or near ties within 1e-6 um abstain;
7. none of the anchor, parent, or child frames lies within two frames of a
   registered division time.

The mutual-nearest test is recomputed independently for every route. An edge is
not accepted merely because V19 emitted it.

## Alternative Availability

For each retained reference, the audit counts:

- other child-frame detections within 14 um of the parent;
- other parent-frame detections within 14 um of the child.

These are local alternatives and ownership competitors, not negative labels.
The audit measures whether pairwise continuation ranking is feasible; it does not
convert alternatives into truth judgments.

## Concentration Contract

The audit reports reference counts and per-sample distributions for every fold,
family, and route. It also reports:

- largest sample and top-three sample share;
- effective sample size from per-sample counts;
- largest parent frame and top-three frame share;
- samples with zero references;
- references with at least one local alternative.

A GO to continuation-table construction requires:

- at least 1,000 total references;
- at least 200 references per fold;
- at least 100 references with alternatives per fold;
- at least 7 of 9 samples represented in every fold;
- at least 100 references per family;
- at least 25 references per observed route;
- largest sample share no greater than 20%;
- top-three sample share no greater than 45%;
- both families present;
- zero source-graph perturbation.

These thresholds are frozen before real-sample extraction. Passing them permits
only construction of a fold-safe weak-reference table. It does not validate the
continuation model, semantic ranker, assignment layer, or full 199-sample scope.

## Artifacts

- Machine contract:
  `tests/fixtures/v22_continuation_reference_audit.json`
- Extractor:
  `src/atabey/tracking/continuation_reference.py`
- Runner:
  `scripts/audit_v22_continuation_reference_availability.py`
- Generated shards:
  `v22_continuation_reference_audit/` (ignored by git)
- Aggregate summary:
  `v22_continuation_reference_audit_summary.json`