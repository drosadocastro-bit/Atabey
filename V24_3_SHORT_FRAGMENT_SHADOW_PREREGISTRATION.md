# V24.3 Short-Fragment Shadow Preregistration

Status: **full-27 gates passed; frozen full-199 score validation authorized**.

The authoritative result and provenance are recorded in
`V24_3_SHORT_FRAGMENT_SHADOW_FULL_27_AUDIT.md`. This authorization remains
limited to score validation; production mutation and submission are not
authorized.

This is a single shadow-only post-link rule applied after the V24.2
interior-isolated detection shadow. It does not alter detection thresholds,
model weights, native edges, production graphs, or the official evaluator.

## Frozen Rule

Remove an entire connected component only when all conditions hold:

1. The component has exactly two detections.
2. Its earliest frame is after the graph's global first frame.
3. Its latest frame is before the graph's global last frame.
4. No edge incident to either detection has relation `division`.

Components of size one are handled only by V24.2. Components of size three or
larger are retained. Components touching the first or last observed frame are
retained. The filtered graph preserves every edge whose endpoints remain.

## Evaluation Contract

- Cohort: the frozen complete 27-sample held-out cohort.
- New arm: `e016_atabey_relink_v24_3_short_fragment_shadow`.
- Comparison arms: V19 reference, E016 relink, E016 native, and V24.2 shadow.
- Primary endpoint: official adjusted edge Jaccard with the existing pooled,
  family, fold, regression, determinism, and node-inflation gates.
- Full-199 score validation is authorized only after the complete gate set
    passes; the authoritative full-27 artifact satisfied that condition.

The minimum node reductions calculated from the prior V24.2 artifact are
feasibility context only. They do not authorize selecting components to hit a
target count. The rule must be evaluated as frozen across the complete cohort.