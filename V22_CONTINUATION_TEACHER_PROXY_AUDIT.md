# V22 Continuation Teacher-Proxy Audit

Status: **COMPLETED; TEACHER INDEPENDENCE NOT ESTABLISHED**

## Question

The mandatory teacher-feature ablation retained top-1 accuracy of 0.996281 after removing direct V19 teacher features. This audit asks whether the remaining geometric features provide independent continuation evidence or reconstruct teacher-equivalent information through correlated proxies.

## Scope And Weighting

The audit used the frozen 27-sample development table only:

- 1,207,532 candidate rows;
- 1,024,536 reference-versus-alternative pairs;
- all three sample-blocked folds;
- equal sample -> parent frame -> reference -> pair weighting;
- raw-candidate and pair-difference correlations reported separately;
- no fitting, assignment, graph mutation, locked validation, or full-199 evaluation.

Pair-difference correlations are the decision-relevant view because the logistic head learns reference-minus-alternative utilities. Features constant within a reference group have zero pair variance and therefore an undefined pairwise correlation.

## Deterministic Proxy

`prediction_error_um` is not independent of the retained geometry. Let:

- `a = anchor_parent_distance_um`;
- `b = parent_child_distance_um`;
- `theta = turn_angle_deg`.

Then the constant-velocity prediction error follows the law of cosines:

```text
prediction_error_um = sqrt(a^2 + b^2 - 2ab cos(theta))
```

Across 1,127,434 rows where the angle was available, reconstruction error was:

| Statistic | Absolute error (um) |
| --- | ---: |
| Weighted mean | 1.464662e-13 |
| Weighted median | 4.440892e-16 |
| Maximum | 4.214685e-08 |

This is numerical identity, not merely correlation. Removing `prediction_error_um` while retaining its three inputs does not remove its information.

## Correlation Evidence

### Raw candidate rows

| Removed teacher feature | Strongest retained proxy | Weighted Pearson r |
| --- | --- | ---: |
| prediction error | parent-child distance | +0.943129 |
| forward competitor margin | parent-child distance | -0.879009 |
| reverse competitor margin | parent-child distance | -0.866950 |
| forward local rank | local target count | +0.765407 |
| reverse local rank | local competing-source count | +0.768865 |

### Reference-minus-alternative pair differences

| Removed teacher feature | Strongest retained proxy | Weighted Pearson r |
| --- | --- | ---: |
| prediction error | parent-child distance / radial speed change | +0.749540 |
| forward competitor margin | parent-child distance / radial speed change | -0.671826 |
| reverse competitor margin | parent-child distance / radial speed change | -0.768976 |
| forward local rank | parent-child distance / radial speed change | +0.213692 |
| reverse local rank | local competing-source count | +0.353839 |

`parent_child_distance_um` and `radial_speed_change_um_per_frame` have identical pair differences because anchor-parent distance is constant within each reference group. This is another exact redundancy in the ranker's training representation.

## What The Ablated Head Actually Used

The four dominant coefficients were stable across all held-out folds:

| Feature | Fold 1 | Fold 2 | Fold 3 |
| --- | ---: | ---: | ---: |
| parent-child distance | -0.774077 | -0.776433 | -0.790580 |
| radial speed change | -0.757143 | -0.759140 | -0.767806 |
| step-distance ratio | -0.320754 | -0.295087 | -0.298102 |
| turn angle | -0.268400 | -0.278306 | -0.238540 |

The model therefore recovered V19 preferences primarily from redundant distance, speed, and angle encodings. Density and ownership-count coefficients were much smaller.

## Conclusion

The retained geometric features are highly informative for reproducing V19 preferences, but they are **not independent evidence**. The previous mandatory ablation proves redundancy and held-out teacher imitation, not independence from the V19 selection mechanism.

The formal preregistered result remains a GO for a weak-reference imitation head. It must not be cited as evidence that the head learned a distinct semantic continuation signal.

## Required Next Gate

Before joint semantic assignment shadow evaluation, preregister a proxy-resistant diagnostic that removes both direct teacher features and their deterministic motion reconstruction set:

- anchor-parent distance;
- parent-child distance;
- step-distance ratio;
- radial speed change;
- turn angle.

The remaining density/ownership-only evidence should be evaluated out of fold and compared with a simple nearest-distance baseline. This diagnostic may clarify whether any non-teacher signal remains, but it must not retroactively alter the already-opened thresholds or be promoted to biological validation.

No joint assignment shadow is authorized by this audit alone.
