# Adaptive Component Pruning Shadow Audit

Status: full-cohort audit paused; prediction-evidence rank is a fixed-battery NO-GO

## Purpose

This experiment tests whether sample-level component pruning can improve Atabey's official adjusted
edge Jaccard by removing likely fragmented detections without damaging matched edges, node recall, or
officially recognized divisions. It is inspired by Amer's Kaggle notebook
[`Biohub Cell Tracking | Adaptive Pruning`](https://www.kaggle.com/code/amerhu/biohub-cell-tracking-adaptive-pruning),
but its `0.95` budget and learned edge probabilities are not assumed to transfer to Atabey.

This is a shadow post-processing experiment. It does not alter V19, V20, Track A, Track B, detector
routing, candidate formation, or submission generation.

## Why This Is Plausible

The pinned official evaluator applies the predicted-node-count adjustment after sparse edge matching.
An unsupported component can leave edge TP/FP/FN unchanged while increasing `T_pred`, which lowers
the adjusted edge score. Direct adapter tests now cover that exact behavior.

The four visible V19 submission graphs show that the problem is not uniform:

| Sample | Atabey V19 nodes | Notebook min7 nodes | Atabey nodes in components smaller than 7 |
|---|---:|---:|---:|
| `44b6_0113de3b` | 20,904 | 25,127 | 25.89% |
| `44b6_0b24845f` | 74,519 | 21,823 | 84.58% |
| `6bba_05b6850b` | 4,431 | 6,168 | 26.77% |
| `6bba_05db0fb1` | 64,254 | 68,803 | 42.83% |

The external notebook is not ground truth. Its counts are used only to expose the scale and
sample-specific nature of Atabey's fragmentation. A universal five-percent trim is therefore not
pre-approved.

## Official Metric Boundary

`src/atabey/evaluation/official_tracking_metric.py` converts Atabey graphs to `tracksdata` and calls
the pinned host functions `evaluate`, `node_recall`, and `per_sample_metrics` directly. Atabey does
not reimplement matching or adjusted-edge arithmetic in this path.

The adapter reports:

- edge TP, FP, FN, and Jaccard;
- official adjusted edge Jaccard;
- matched-node recall;
- predicted and estimated total-node counts;
- official division TP, FP, FN, and Jaccard;
- the combined per-sample score where defined.

## Shadow Mechanism

`compute_adaptive_pruning_shadow()`:

1. clones the input graph;
2. identifies undirected connected components;
3. measures node count, temporal span, edge count, mean available edge confidence, missing
   confidence count, and division presence;
4. computes the fraction of all nodes lying in components smaller than seven nodes;
5. abstains unless that fragmented-node fraction is at least `0.50`;
6. ranks eligible components by shortest size and then lowest available edge confidence;
7. treats missing confidence explicitly rather than fabricating a learned probability;
8. protects every component containing an out-degree-two fork or a division-labelled edge;
9. removes whole components toward the requested node budget without overshooting it; and
10. returns the shadow graph, component evidence, and a complete removal summary.

The activation decision uses prediction-side structure and optional route labels only. Ground truth,
official metric outcomes, and `estimated_number_of_nodes` are forbidden as pruning inputs.

## Pre-Registered Battery

The fixed 13-sample battery reuses already characterized cases so the experiment is cheap and
adversarial:

- hyper-fragmented target: `44b6_0b24845f`;
- components controls: `44b6_0113de3b`, `44b6_24264f12`, `44b6_d754aa59`, `6bba_55b7eebe`;
- local-maxima control: `44b6_12dfb391`;
- 44b6 CFAR contrasts: `44b6_0c582fdc`, `44b6_2a2eff9f`;
- four official V19 division TPs: `6bba_05db0fb1`, `6bba_32db13fc`, `6bba_b329af44`,
  `6bba_ebdf3b34`;
- prior high-noise case: `6bba_ebff6e76`.

The target sample was always part of the stated hypothesis and was run first, but it was omitted
from the initial default tuple while transcribing the earlier 12-sample Sun Check battery. The tuple
was corrected to 13 before the broader run. This correction is scope bookkeeping, not an
outcome-selected sample addition.

The first budget sweep is frozen at:

- `0.99` retained nodes;
- `0.97` retained nodes;
- `0.95` retained nodes.

The fragmentation threshold is frozen at component size `<7`, and the activation gate is frozen at
fragmented-node fraction `>=0.50`. No threshold is changed while inspecting this battery.

## Decision Contract

A configuration is a bounded **GO** only when all conditions hold:

1. every source graph passes zero-perturbation identity checks;
2. official adjusted edge Jaccard improves in aggregate across activated samples;
3. aggregate official edge TP does not decrease;
4. no one of the four known official V19 division TPs is lost;
5. median node-recall delta across activated samples is no worse than `-0.01`;
6. the result is not carried entirely by one sample or one detector route; and
7. inactive/control samples remain unchanged.

The experiment is a **NO-GO** if adjusted score is flat or negative, any known division TP is lost,
edge TP declines in aggregate, or the apparent gain depends on GT-derived routing information.

A result that helps only the hyper-fragmented subgroup is not automatically a NO-GO. It supports a
targeted route if the subgroup can be identified from prediction-side evidence alone and independent
samples reproduce the benefit.

## Execution

```powershell
python -u scripts/run_adaptive_pruning_shadow_audit.py `
  --sample-ids battery `
  --keep-fractions 0.99 0.97 0.95 `
  --max-timepoints 100 `
  --output adaptive_pruning_shadow_13.csv
```

The eight-timepoint `44b6_0b24845f` smoke check activated as expected with a fragmented-node fraction
of `0.947` and preserved source identity for all three budgets. Because that window contained no
matched sparse edges, its metric deltas are not treated as validation evidence.

The first full 100-frame `44b6_0b24845f` run produced a metric trade-off, not a GO. Budgets `0.99`,
`0.97`, and `0.95` improved official adjusted edge Jaccard by `0.000243`, `0.000731`, and `0.001217`
without losing an edge TP or division TP. However, all three reduced sparse node recall from `0.4314`
to `0.3922`. This violates the current node-recall guardrail when considered alone and must remain
visible during the full battery interpretation.

## Full Battery Results

The corrected fixed battery produced 39 rows: 13 samples by three frozen budgets. The prediction-side
fragmentation gate activated on 3/13 samples and abstained on 10/13. The activated samples covered both
`local_maxima/motion_mutual` and `components/greedy` routes, so activation was not equivalent to a
hard-coded detector route. All four samples containing known official V19 division TPs remained
inactive, preserving one TP apiece. Every run reported source zero perturbation.

| Keep | Removed nodes | Active-sample host-weighted adjusted delta | Full-13 host-weighted adjusted delta | Edge TP delta | Division TP delta | Median active node-recall delta | Decision |
|---:|---:|---:|---:|---:|---:|---:|---|
| `0.99` | 914 | +0.000211 | +0.000008 | 0 | 0 | -0.00435 | Passes bounded contract |
| `0.97` | 2,743 | +0.000634 | +0.000024 | 0 | 0 | -0.00435 | Shadow-only GO |
| `0.95` | 4,572 | +0.009225 | +0.000355 | +2 | 0 | -0.01389 | NO-GO: recall guardrail failed |

For every budget, all three activated samples improved and none regressed in official adjusted edge
Jaccard. Cohort edge TP was `3,539` before pruning and remained `3,539` at `0.99` and `0.97`; it rose to
`3,541` at `0.95` because removing decoy nodes changed the official sparse node assignment on
`44b6_d754aa59`. Official division TP remained `4` at every budget.

The score gain must not hide the principal risk. On hyper-fragmented `44b6_0b24845f`, even the `0.99`
budget removed a sparse-GT-matched fragment and reduced node recall from `0.4314` to `0.3922`. The
official adjusted edge score rewards removing unsupported predicted nodes, but that does not prove each
removed component is biologically false.

### Decision

Advance `0.97` only to a pre-registered independent shadow validation on 15-20 samples. It gives a
larger bounded gain than `0.99` with the same observed median and worst-case recall losses, while `0.95`
fails the frozen median node-recall guardrail despite its larger score gain. This is not approval for
production pruning, submission generation, or a full-cohort run. The independent cohort must reproduce
the adjusted-edge benefit without division loss or worse node-recall behavior before promotion is
reconsidered.

The complete bounded evidence is stored in `adaptive_pruning_shadow_13.csv`.

## Independent Validation Pre-Registration

The promoted configuration is frozen at `keep_fraction=0.97`, component size `<7`, and fragmented-node
activation fraction `>=0.50`. The independent cohort contains 20 samples not used in the 13-sample
battery, balanced across the two sample families. Selection used ascending SHA-256 order of
`adaptive-pruning-independent-v1:<sample_id>` within each family; no metric, route, fragmentation, or
ground-truth outcome influenced inclusion.

- `44b6_`: `44b6_d2f34f90`, `44b6_0db75fae`, `44b6_a2bb48bb`, `44b6_cf8fed6b`,
  `44b6_5740d24b`, `44b6_2f31fc2f`, `44b6_a21120c2`, `44b6_d78e09d9`,
  `44b6_8f5ab931`, `44b6_deabac95`.
- `6bba_`: `6bba_907271db`, `6bba_67ebd073`, `6bba_0c7fa718`, `6bba_74686d6a`,
  `6bba_91951b3a`, `6bba_2819ca14`, `6bba_afb141ff`, `6bba_268e1230`,
  `6bba_6479435d`, `6bba_f8ffd5e7`.

The original decision contract remains unchanged. Results checkpoint after each sample to
`adaptive_pruning_shadow_independent_20.csv`. No threshold changes or sample substitutions are
permitted after execution starts.

## Independent Validation Results

The frozen run completed all 20 pre-registered samples. The prediction-side gate activated on 8/20
and abstained on 12/20. Activations covered both `local_maxima/motion_mutual` and
`components/greedy`; the third observed route, `cfar_sidelobe/bipartite`, abstained. All 20 source
graphs passed zero-perturbation identity checks.

| Measure | Independent result |
|---|---:|
| Activated samples improved / flat / regressed | 8 / 0 / 0 |
| Removed nodes across activated samples | 5,607 |
| Official edge TP | 5,358 -> 5,373 (+15) |
| Official division TP | 0 -> 0 |
| Official division FP | 286 -> 286 |
| Median activated node-recall delta | -0.00216 |
| Worst activated node-recall delta | -0.01442 |
| Active-sample host-weighted adjusted-edge delta | +0.00646 |
| Full-20 host-weighted adjusted-edge delta | +0.00211 |

The independent cohort reproduces the bounded GO contract: adjusted edge Jaccard improved on every
activated sample, aggregate edge TP did not decline, median node-recall loss remained above the
frozen `-0.01` floor, two detector/link routes contributed, controls were unchanged, and routing used
prediction-side evidence only. This cohort contained no official division TPs at baseline, so it adds
no new positive-case evidence for division preservation; the original four-TP battery remains the
relevant division guardrail.

The worst-case node-recall loss occurred on `44b6_a2bb48bb` (`-0.01442`) while adjusted edge
Jaccard rose by `+0.01266` and edge TP rose by five. This is a real metric/coverage trade-off and
prevents interpreting pruning as proof that removed components are biologically false.

### Promotion Decision

Promote the frozen `0.97` configuration to a full-199 **shadow audit only**. Production graph
mutation and submission generation remain prohibited. The full-cohort pass should measure route- and
family-stratified activation, adjusted-edge improvement, edge TP, node-recall tails, and official
division preservation before any production decision.

The complete independent evidence is stored in
`adaptive_pruning_shadow_independent_20.csv`.

## Prediction-Evidence Ranking Audit

The independent validation's worst node-recall case, `44b6_a2bb48bb`, exposed a defect in the legacy
rank: 2,107 singleton components had no edge confidence, so exact ties fell through to lexicographic
component ids. That removed whole lexical time blocks (`t0-t2`, then `t10-t30`) and eliminated six
otherwise unmatched official sparse-GT node matches.

A separate shadow implementation leaves the frozen legacy path unchanged and ranks singleton
components using prediction-only evidence:

1. fewer supported adjacent-frame sides first, within a 14 um prediction-space radius;
2. proximity to an already-linked detection in the same frame;
3. lower detector confidence;
4. SHA-256 only for exact ties.

Unavailable sides outside the observed time range are neutral rather than unsupported, preventing
`t0` and `t99` from being penalized. Ground truth and metric outcomes are not ranking inputs.

| Measure | Baseline | Legacy 0.97 | Evidence-ranked 0.97 |
|---|---:|---:|---:|
| Removed nodes / edges | 0 / 0 | 2,107 / 0 | 2,107 / 0 |
| Official edge TP | 162 | 167 | 175 |
| Official edge FP | 123 | 119 | 111 |
| Adjusted edge Jaccard | 0.29912 | 0.31179 | 0.33174 |
| Node recall | 0.77644 | 0.76202 | 0.76923 |
| Node-recall delta | 0 | -0.01442 | -0.00721 |

Evidence-ranked removals covered all 100 frames, with 158-230 removals per decade and only 24/27 at
the two boundary frames. The original source graph remained unchanged and no graph edge or division
was removed.

This is a **bounded GO for fixed-battery validation**, not a full-199 GO. The sample was selected
because it exposed the failure and therefore serves as calibration evidence. The full-cohort audit
remains paused until the exact frozen evidence rank is tested without tuning on the existing
adversarial battery and independent controls.

### Fixed-Battery Evidence-Rank Pre-Registration

The next run reuses the original 13 samples without substitution. The configuration is frozen at
`keep_fraction=0.97`, component size `<7`, activation fraction `>=0.50`, temporal-support radius
`14 um`, and same-frame duplicate radius `7 um`. No feature, radius, budget, or sample may change
after execution starts.

The evidence rank advances beyond this battery only if source zero perturbation holds everywhere,
aggregate adjusted edge Jaccard and edge TP are no worse than legacy `0.97`, all four official
division TPs remain preserved, median activated node-recall delta remains at least `-0.01`, and the
node-recall distribution is no worse than the legacy rank. Output checkpoints after each sample to
`adaptive_pruning_evidence_shadow_battery_13.csv`.

## Fixed-Battery Evidence-Rank Results

The frozen 13-sample run completed without substitution or tuning. The activation set remained the same
three samples because the prediction-side gate was unchanged. All source graphs passed zero
perturbation, all four official division TPs were preserved, and no edge TP was lost.

| Measure | Legacy 0.97 | Evidence-ranked 0.97 |
|---|---:|---:|
| Activated samples | 3 | 3 |
| Removed nodes | 2,743 | 2,743 |
| Adjusted-edge delta, active host-weighted | +0.000634 | +0.000634 |
| Edge TP delta | 0 | 0 |
| Division TP total | 4 -> 4 | 4 -> 4 |
| Median activated node-recall delta | -0.00435 | -0.01389 |
| Worst activated node-recall delta | -0.03922 | -0.03922 |

Adjusted-edge outcomes were numerically identical because both ranks removed the same node count and
neither changed the official edge confusion matrix on these three samples. Removal identity therefore
appeared only in node recall. The evidence rank was equal on `44b6_0b24845f`, lost one additional
sparse match on `44b6_24264f12`, and lost one sparse match on `44b6_d754aa59` where legacy lost none.

### Fixed-Battery Decision

The prediction-evidence rank is a **NO-GO as a general replacement**. It fails the pre-registered
`-0.01` median node-recall floor and is worse than legacy on two of three activated battery samples.
Its strong result on `44b6_a2bb48bb` is retained as valid calibration evidence for a bounded subgroup,
but it did not generalize across the fixed adversarial battery.

The full-199 shadow audit remains paused. Neither the temporally biased legacy tie-break nor this
non-generalizing evidence rank is approved for cohort-wide execution or production pruning.

The completed battery evidence is stored in
`adaptive_pruning_evidence_shadow_battery_13.csv`.

## Guardrails

- No production graph mutation.
- No submission generation from shadow graphs.
- No threshold tuning during the completed 13-sample run.
- No use of the notebook's `0.95` value as evidence by itself.
- No claim that short components are biologically false tracks.
- No threshold tuning before the independent shadow cohort is evaluated.
- No full 199-sample run until the independent cohort reproduces the bounded GO.
