# V23 New Signal-Source Identification

Date: 2026-08-02
Status: completed bounded identification pass; no scorer authorized

## Question

Does V23 currently contain a GT-blind evidence source that was not already falsified by the V22/V23 semantic-ranking work and that can surface the three ownership-repair pairs supported by the oracle feasibility shadow?

## Sources Already Tested And Closed

- independent scalar patch contrast, mass, effective volume, and anisotropy;
- parent/daughter conservation and balance summaries;
- detector confidence;
- density and ownership counts;
- teacher-derived continuation features and mathematically redundant motion proxies;
- short-horizon daughter emergence, persistence, and scalar temporal conservation;
- E016 metadata ranking;
- CFAR-coordinate decoder logits and pooled embedding summaries;
- standalone continuity, counterfactual pairing, and exclusivity-only ranking.

These sources either failed generalization, failed specifically on CFAR/`44b6`, reconstructed V19 preferences, or could not retrieve registered actions from the unknown candidate pool.

## Genuinely New Candidate Tested

`candidate_axis_topology_change` preserves spatial image arrangement across time. For each proposed daughter pair, it measures whether the raw intensity profile along the pair axis changes from one parent-centered lobe at `t` to two endpoint-supported lobes with a central valley at `t+1`.

This is distinct from:

- Hough/bimodality, which tested parent-frame precursor morphology alone;
- V22 scalar temporal patches, which measured each location independently;
- geometry and continuation features, because distance, angle, velocity, prediction error, ownership, and rank do not enter the feature.

The frozen audit used three repairable events and three already-complete controls, balanced across `44b6` and `6bba`. Unknown alternatives remained unknown and no model was fitted.

## Result

Formal preregistered decision: **HOLD_CANDIDATE_AXIS_TOPOLOGY**.

- pooled median correct-pair percentile: `61.8%`;
- top-10 capture: `2/6`;
- rank improved/flat/regressed versus static endpoint support: `3/1/2`;
- family medians: `60.0%` for `44b6`, `63.6%` for `6bba`;
- zero perturbation: `6/6`.

The role split is the decisive diagnostic:

| Role | Correct-pair ranks | Top 10 |
|---|---|---:|
| Already-complete controls | `4, 6, 31` | `2/3` |
| Ownership-repair targets | `23, 25, 27` | `0/3` |

The feature detects some one-to-two image structure, but it does not surface the cases that actually require ownership repair. Two repairable cases improved substantially relative to static endpoint support, yet remained impractically deep in their local candidate pools. The third regressed.

## Conclusion

No currently tested Atabey feature source clears the evidence bar for another semantic ranker. The latest oracle feasibility GO establishes that a correct pair could be installed safely; it does not provide the missing GT-blind selector.

Candidate-axis topology remains a documented partial signal, not an active route. It must not be combined with failed V22/V23 features or tuned on these six cases to manufacture a GO.

A future reopening requires a genuinely independent source and a new preregistration. The clearest remaining class is a pair-conditioned spatiotemporal representation that retains the full local 3D field rather than scalar descriptors, trained and validated sample-blocked with sufficient official-positive availability. That is a materially larger experiment and should not begin until its label/availability contract demonstrates that it can test CFAR and both families independently.

## Guardrail

No scorer, fitted coefficient, threshold tuning, assignment integration, graph mutation, routing change, or full-cohort run is authorized by this identification pass.
