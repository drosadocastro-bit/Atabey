# V25 Upstream Association Forensics Preregistration

Date: 2026-08-30

Status: **OBSERVABILITY IMPLEMENTED; REAL-DATA TELEMETRY NOT EXECUTED**.

V25 starts by improving observability, not by improving score. Its first question
is: when frozen V24.3 regresses, did the correct association never enter the
E016 plus motion-mutual candidate set, or did it enter and lose?

## Prior-Version Boundary

- **V24.3 is the current frozen baseline.** Its checkpoint, predictor, full-199
  outputs, population identity, and audits are pinned in the machine contract.
  No V25 threshold, rule, or interpretation may be tuned against the opened 199.
- **V24.7 is closed as a documented NO-GO.** Preserve the route-90 null result
  and pre/post-pruning compatibility-boundary finding. Penalty or threshold
  rescue tuning is prohibited.
- **V24.8 remains blocked.** Preserve its graph-aligned concept only; no
  implementation or execution is authorized without genuinely independent
  labeled evidence.

## Scope

The first V25 phase is read-only mechanism research on the fixed 16 V24.3
regressions. Labels are already opened, so findings are descriptive and may not
support promotion, score, selector, or automatic-routing claims.

Instrument the unchanged E016 detections and motion-mutual decisions with:

- nearest and second-nearest prediction distance and margin;
- feasible candidate count for each source;
- forward/reverse mutuality conflicts and unmatched sources;
- accepted edge length, track velocity, and prediction error;
- local source and target density;
- sources competing for the same preferred target;
- candidate and accepted-edge survival through V24.2 and V24.3 pruning.

The observer must consume immutable graph/input views, reproduce no assignments,
and leave graph signatures unchanged. Candidate records are tracking hypotheses,
not confirmed identities.

## Failure Taxonomy

Each regression must receive exactly one evidence state:

1. `candidate_generation_failure`: a required detection is absent or the
   correct pair is absent from the frozen geometric candidate set;
2. `candidate_selection_ranking_failure`: the correct pair is present but is
   rejected by forward rank, mutuality, or assignment competition;
3. `post_link_pruning_interaction`: the correct pair is accepted and then
   removed by a frozen pruning stage;
4. `metric_node_adjustment_only_effect`: raw edge behavior improves while only
   the official node adjustment makes the sample regress;
5. `unresolved_insufficient_telemetry`: direct evidence is missing or ambiguous.

Aggregate TP/FP deltas alone may not distinguish the first three classes.

## V19 Comparison

For the same local frame regions, expose V19 `components + greedy` edges as a
separate visualization layer and compare them with E016 candidates, accepted
motion-mutual edges, and post-pruning survival. The goal is to isolate a
transferable mechanism, not to create a V19/V24 selector from opened labels.

## Visualization Contract

The read-only payload contains physical coordinates for source and target
detections, accepted and rejected candidate edges, ambiguity margins, a separate
V19 edge layer, and pruning survival. Rendering is downstream of this payload;
it may not alter graph state or write replacement predictions.

## Execution and Reporting

The first real-data run must use all 16 fixed regressions, complete sequences,
the frozen 9.0 um link radius, pinned V24.3 artifacts, deterministic output, and
raw denominators. Report catastrophic and mild strata, every taxonomy count,
candidate-present versus candidate-absent counts, V19/V24 divergence patterns,
pruning interactions, and negative findings.

Only after this audit is complete may a bounded intervention be designed. That
intervention requires a separate preregistration, default abstention, frozen
contract before execution, and genuinely independent evidence for any promotion.

Machine contract: `tests/fixtures/v25_upstream_association_forensics.json`.