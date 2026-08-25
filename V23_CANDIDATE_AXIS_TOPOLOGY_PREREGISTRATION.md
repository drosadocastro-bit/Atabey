# V23 Candidate-Axis Topology Audit Preregistration

Status: frozen raw-feature-source audit; no model fitting

## Hypothesis

A genuine division pair may show a candidate-conditioned image transition from one parent-centered lobe at frame `t` to two endpoint-supported lobes separated by a central valley at `t+1`. Unrelated nearby cells may be individually bright but should less consistently exhibit this shared one-to-two transition around the focal parent.

This is not the prior Hough/bimodality hypothesis. Hough tested whether the parent crop was already bimodal before division. This audit compares two frames along each proposed daughter-pair axis and retains the spatial profile rather than reducing each cell to an independent scalar patch.

## Frozen Population

Six CFAR/bipartite events from `v23_single_child_ownership_failures.json`:

- three safely repairable events from the local ownership feasibility shadow;
- three already-complete forks as protected positive controls;
- exactly three `44b6` and three `6bba` events.

Cases with a missing daughter detection are excluded as feature-unavailable, not counted as negatives. Unknown candidate pairs remain unknown.

## Feature

For each focal parent and every distinct daughter pair inside the unchanged 14 um formation radius:

1. sample nine points along the candidate daughter axis;
2. map that axis around the parent center in frame `t`;
3. sample the actual daughter axis in frame `t+1`;
4. normalize each frame using local 10th and 99.5th percentiles;
5. compute parent center dominance, daughter central-valley depth, and their sum: `candidate_axis_topology_change`.

`static_endpoint_support` is the preregistered comparator. No distance, angle, ownership count, detector confidence, GT distance, or fitted coefficient enters the feature.

GT is used only after enumeration to locate the registered correct pair and report its rank.

## Decision

`GO_TO_INDEPENDENT_TOPOLOGY_VALIDATION` requires:

- complete extraction for all six events;
- pooled median correct-pair percentile at least 0.75;
- median percentile at least 0.65 in both families;
- at least four of six correct pairs in the top 10;
- rank improvement over static endpoint support in at least four events;
- no more than one regression.

`HOLD` requires pooled median percentile at least 0.60, at least two top-10 events, and more improvements than regressions. Otherwise the result is `NO_GO`.

Even a GO authorizes only an independent sample-blocked validation of this feature source. It does not authorize a semantic ranker, assignment integration, graph mutation, threshold tuning, or a full 199-sample run.
