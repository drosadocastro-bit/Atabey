# V23 E016 Raw Patch-Descriptor Shadow Results

## Decision

**GO to the V23 positive-unlabeled ranker preregistration; HOLD production integration.**

This was a read-only detector-native feature-source preflight on the frozen
E016 development population. It did not fit a model, assign actions, mutate a
graph, change candidate formation, or evaluate the full 199-sample cohort.

## Population and integrity

| Quantity | Result |
|---|---:|
| Samples | 27 |
| Registered events | 46 |
| Detector peaks | 22,229 |
| Actions | 211,328 |
| Official TP actions | 55 |
| Official FP actions | 569 |
| Peak descriptor completeness | 100% |
| Official TP/FP descriptor completeness | 100% |
| Graph mutation | false |
| Full 199 authorized | false |

Unknown and unsupported actions remained excluded from discriminability
metrics; sparse absence was not treated as a negative label.

## Held-out evidence

The best confidence-only baseline was event-balanced AUC **0.5852**. The best
raw detector-native feature, `mean_daughter_contrast`, reached **0.8230**,
an advantage of **+0.2378** over that baseline. Feature-group best AUCs were:

| Group | AUC |
|---|---:|
| Contrast | 0.8230 |
| Shape | 0.7557 |
| Volume | 0.6892 |
| Mass | 0.6712 |

`mean_daughter_anisotropy` was the only feature marked stable by the frozen
feature-level stability check. This is encouraging evidence that detector
native appearance/shape information is not merely confidence metadata, but it
does not yet establish a reliable action scorer.

## Generalization cautions

| Stratum | Best raw AUC |
|---|---:|
| Fold 1 | 0.9298 |
| Fold 2 | 0.7797 |
| Fold 3 | 0.7594 |
| Family 44b6 | 0.4645 |
| Family 6bba | 0.8529 |
| CFAR/sidelobe + bipartite | 0.5161 |
| Components/greedy | 0.8928 |
| Local maxima/motion mutual | 0.8053 |

The CFAR route is effectively unproven at this stage, and 44b6 is below
chance for the best pooled raw feature. Local-maxima is descriptive only and
remains excluded from any pooled GO claim. The pooled result therefore cannot
be presented as route- or family-independent generalization.

## Interpretation and next gate

The result supports exporting detector-native evidence into a sample-blocked,
positive-unlabeled ranking experiment. The next experiment must keep the
current action population fixed, use fold-safe fitting, report fold/family/
route strata separately, and include the local ownership constraint as a
shadow-only assignment layer. It must not mutate Track A, alter candidate
formation, or use unsupported actions as easy negatives.

No decoder/bottleneck embedding hook is justified as a production change yet;
it is the next detector-native comparison only if the preregistered raw-patch
ranker fails or remains route-fragile.

## Reproducibility

- Contract: `tests/fixtures/v23_e016_raw_patch_descriptor_shadow.json`
- Entrypoint: `scripts/run_v23_raw_patch_descriptor_shadow.py`
- Compact summary: `v23_e016_patch_shadow_summary.json`
- Raw feature tables are local-only derived artifacts and are intentionally not
  committed to Git.
