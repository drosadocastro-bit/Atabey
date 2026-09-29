# Project Atabey

> Transfer principles. Test assumptions. Preserve the evidence.

**Competition research closed on September 29, 2026. Repository remains editable.**
Atabey closes this experimental cycle with **V28's recorded Kaggle public score of
0.728**, with V19 retained as the recorded backup. Later experiments remain part
of the research record, including rejected hypotheses and incomplete runs.
This is a documentary close, not a GitHub repository archive or a claim that the
competition's final private results have been published.

## Why this project existed

[Biohub — Cell Tracking During Development](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development)
asks participants to detect cells, connect their observations through 3D space
and time, and identify divisions to reconstruct cell lineages. Its microscopy
videos follow fluorescently labeled cells in developing zebrafish embryos.
Dense tissue, similar-looking neighbors, noise and cell division make manual
tracking laborious and automated association difficult. The benchmark aims to
reduce that manual effort and improve reproducible analysis of development.
Its combined metric evaluates temporal edges and division detection; finding
bright points alone does not solve the task.

Atabey used that challenge to ask an engineering question: **which principles
from radar and signal processing help with cell tracking, and where do their
assumptions stop applying?** We began with local signal/background estimation,
spatial peak suppression and geometric association. The work later incorporated
a learned detector, while retaining explicit linking, bounded interventions and
inspectable evaluation. The aim was a valid, understandable tracking pipeline,
with every claimed improvement tied to a specific experiment.

The reflection written during this work,
[What Radar Engineering Taught Me About Using AI in New Domains](https://apolitical.co/en/articles/what-radar-engineering-taught-me-about-using-ai-in-new-domains-510)
(Apolitical, August 31, 2026), explains the motivation: borrowing a useful
engineering principle does not establish that its statistical assumptions hold
in another domain. Its account of adaptive thresholds and rejected morphology
hypotheses complements the technical record below. The article is a reflection
on the process; experimental claims remain anchored to this repository's evidence.

## The result we kept: V28

| Frozen submission | Recorded public score | Recorded status | Exact notebook |
| --- | ---: | --- | --- |
| **V28: V24.3 policy delivery** | **0.728** | COMPLETE | [Version 353502941](https://www.kaggle.com/code/drakus74/atabey-v28-submission?scriptVersionId=353502941) |
| V19: backup | 0.515 | COMPLETE | [Version 334646717](https://www.kaggle.com/code/drakus74/atabey-adaptive-baseline?scriptVersionId=334646717) |

The public-score difference is **+0.213 points**. These are account observations
verified on September 28, 2026, not newly fetched results or final private scores.
The later V29A closure recorded both entries selected for final judging. No
selection was changed for this documentary close.

V28 delivered the frozen V24.3 policy:

1. Stream microscopy input and obtain detections from the **clean E016 temporal
   U-Net checkpoint**, without the later V29A four-view TTA intervention.
2. Convert positions to physical coordinates and link with the frozen
   **motion-mutual rule at a 9-micron gate**.
3. Apply isolated-node pruning followed by short-fragment pruning only on the
   frozen image-routed `6bba_` / `components` subset.
4. Export the resulting graph through the validated Kaggle CSV writer.

**CFAR and sidelobe suppression belong to Atabey's earlier detector research;
V28 did not use a CFAR detector.** The classical experiments informed our
questions and diagnostics, but the 0.728 result cannot be attributed to CFAR,
sidelobe suppression or any other component in isolation.

Offline delivery validation reproduced 199 route decisions, seven historical
graph signatures and a repeated inference. Submission-mode validation reproduced
the four visible graphs and a byte-identical 311,183-row CSV. Kaggle subsequently
reported the public score above. Visible parity verifies delivery consistency;
it does not establish independent biological validity. The 16 known local
regressions, including four protected severe cases, remain in the evidence.

See [V28's result](V28_KAGGLE_RESULT.md),
[delivery validation](V28_VALIDATION_RESULTS.md),
[submission receipt](V28_SUBMISSION_EXECUTION.md) and
[reproducibility boundary](docs/V28_PUBLICATION_SCOPE.md).

## How the radar-inspired approach developed

### CFAR: adapt to local background

The CFAR-style detector estimated local background mean and variance from a
3D training neighborhood, excluding a guard region around the candidate. It
retained local maxima meeting both a global intensity floor and a local
adaptive threshold. The `sigma` formulation used `background_mean + k *
background_std`. Candidate confidence measured contrast above that threshold,
rather than treating global brightness as certainty.

A separate classical CA-CFAR `pfa` formulation exposed a domain mismatch:
`alpha * background_mean` could exceed the normalized signal ceiling of 1.
No voxel could then pass. The false-alarm parameter was not a calibrated
biological false-positive probability. Bounded reformulations avoided collapse
in the evaluated windows, but did not recover useful quality and increased
runtime. Preventing an empty output was necessary, not sufficient.

Sources: [detector implementation](src/atabey/detection/baseline.py) and
[bounded-domain experiment and NO-GO](docs/CFAR_BOUNDED_REFORMULATION.md).

### Sidelobe suppression: control competing nearby peaks

We explored whether several local peaks could be redundant responses around a
stronger candidate. The implementation processed candidates in descending
CFAR-margin confidence and suppressed sufficiently weaker neighbors within a
configured voxel neighborhood, with isotropic and axial modes. This was a
spatial redundancy heuristic inspired by radar, not proof that microscopy
peaks were literal radar sidelobes or that the retained peak was a confirmed cell.
Dense neighboring cells made over-suppression a real hypothesis to test.

A read-only audit of **11 registered division events** compared the frozen
watershed-CFAR detector before and after suppression. Official geometric
availability was **4/11 in both views**, with no registered-role losses due to
suppression in those events. That finding localized those misses elsewhere;
it did not establish that suppression was harmless for every sample.
The subsequent seven-failure audit found upstream floor/threshold blockers and
one missing distinct-daughter pair; its narrower peak-footprint shadow recovered
**0/7** cases.

Sources: [pre/post suppression audit](V23_CFAR_PRE_POST_SIDELOBE_11_RESULTS.md) and
[upstream bottleneck audit](V23_RAW_CFAR_UPSTREAM_BOTTLENECK_AUDIT.md).

### Watershed: separate detection from localization

Raw peaks were used as markers inside a foreground mask. Marker-based watershed
partitioned connected regions, and each candidate moved to its region's geometric
centroid; candidates outside the mask retained their original positions. The
purpose was to improve localization without treating one merged bright region
as one cell. Watershed is a microscopy/image-processing mechanism, not a radar
algorithm.

The apparent systematic Z offset seen in a small preview did not survive the
full-cohort check: the median offset was zero. The problem was localization
variation, not evidence for a universal directional correction. Historical
watershed gains were measured with the **legacy sparse evaluator**, and must
not be relabeled as official Kaggle-score gains.

Sources: [watershed implementation](src/atabey/detection/cfar_watershed.py),
[Z-bias investigation](docs/V19_CFAR_Z_BIAS_ROOT_CAUSE.md) and
[historical V19 evaluation](docs/V19_CFAR_WATERSHED_GO.md).

### Association: geometry, competition and history

Detecting a candidate and assigning its successor were separate problems.
Atabey explored greedy, mutual, motion-based and constrained assignment paths.
Physical microns mattered because the voxels were anisotropic. Recursive motion
history also mattered: an accepted predecessor could affect the next decision.
Later audits separated candidate generation, gate order, ranking, exact ties,
reverse competition and pruning instead of calling every loss a ranking error.

The learned E016 detector was introduced after classical candidate-availability
work exposed limits. Its shadow evaluation tested whether required observations
were available before claiming that a tracking graph had improved. V28 eventually
combined that detector with the bounded classical linking/pruning path above.
The research did not establish reliable division recovery merely by observing
plausible shapes or adding forks to a graph.

Sources: [U-Net availability experiment](V22_UNET_DEVELOPMENT_46_RESULTS.md),
[upstream loss taxonomy](V25_FAILURE_TAXONOMY_AUDIT.md) and
[gate-order correction](V26A_GATE_ORDER_AUDIT_RESULTS.md).

## Research outcomes at closure

| Work | What the evidence supports | Disposition |
| --- | --- | --- |
| V19 / V20 division work | Corrected official scoring found 4 TP / 6 FP / 10 FN for raw V19 and 0 TP / 0 FP / 14 FN for the strict V20 firewall in the fixed bounded windows. | The earlier approximately 91% official division-FP reduction claim was withdrawn. |
| V24.3 → V28 | Full-199 local adjusted-edge Jaccard 0.721056; 183 improved and 16 regressed versus V19. Separately, V28 obtained public Kaggle score 0.728. | Retained submitted policy. Local and public metrics are distinct. |
| V26A / V27 | Gate order, ranking, ties, recursive history and fresh GT matching can change different parts of the result. V27C completed 480 retrospective evaluations. | V26A remained NO_GO; V27 selected no deployable winner. |
| V29A | Four-view TTA improved official local development score 0.721056 → 0.735928, but 25 samples lost more than 0.020 and one protected case regressed. | NO_GO under the frozen quality gates. |
| V30 / V31 | Completed coordinate/graph comparison across 199 pairs and factual association tracing on 28 focus pairs. | Diagnostic evidence; no new official score or promoted policy. |
| V32 | Reverse-population restriction changed frame-local acceptance on 28 focus pairs. Agreement under the restriction was expected by construction. | C was not deployed; mutual matching was not relaxed. |
| V33 | Stage A saved 175/199 pairs before its fixed 30-minute limit. Stage B never ran. | BUDGET_EXHAUSTED_INCOMPLETE; zero new official scores and no quality conclusion. |

Evidence: [official evaluator inventory](OFFICIAL_EVALUATOR_PARITY_INVENTORY.md),
[V24.3 full-cohort audit](V24_3_FULL_199_SCORE_VALIDATION_AUDIT.md),
[V27C](V27C_OFFICIAL_GRAPH_EVALUATION_RESULTS.md), [V29A](V29A_RESULTS.md),
[V30](V30_RESULTS.md). The later reports `V31_RESULTS.md`, `V32_RESULTS.md` and
`V33_RESULTS.md` are local, unpublished references for the summaries above;
this documentary publication does not include their full evidence or implementations.

## Lessons we are keeping

- **Transfer the question, then test the assumptions.** Local adaptation was a
  useful starting point; importing an incompatible probability model caused
  collapse. A familiar mechanism did not guarantee a useful detector.
- **Inspect the pipeline stage that actually failed.** More suppression tuning
  could not recover a candidate already lost to the global floor. Missing
  candidates, wrong associations and post-link pruning required different tests.
- **A small preview can mislead.** The apparent Z bias and the article's early
  morphology hypothesis illustrate why larger controlled comparisons matter.
- **Use the actual evaluator.** Replacing the local division approximation with
  the pinned host implementation changed conclusions and required withdrawals.
  Sparse annotation leaves some predictions unevaluated; it does not make them
  biologically true or false.
- **Freeze causal details, not just a method name.** Order, ties and recursive
  history belong in the contract. Equal edge totals do not mean equal targets;
  removing no edges during node pruning does not imply unchanged official matching.
- **Keep the regression tail visible.** V29A's aggregate gain did not erase its
  individual failures. Once observed, those failures were not permission to relax
  the predeclared gates or select per-case winners.
- **Opened data are development evidence.** All 199 labeled samples had been
  opened by the later experiments. More analysis of them did not create a new
  independent validation cohort.
- **Runtime is part of experimental feasibility.** V33's synthetic tests passed,
  but the real Stage A did not finish within its budget. We retained the failure
  rather than extending the deadline or scoring only the completed subset.
- **AI assistance does not transfer authority.** Tools helped implement, trace
  and audit hypotheses. Human review authorized each frozen execution and
  promotion; builder checks were not represented as independent review.

Further reading: [V26A lessons](docs/V26A_LESSONS_LEARNED.md),
[V29A lessons](V29A_LESSONS_LEARNED.md) and the
[documentary closure and provenance note](docs/ATABEY_DOCUMENTARY_CLOSURE_20260929.md).

## Reproducibility and repository use

The common research flow was:

```text
Zarr sample → streamed timepoints → candidate detection → physical coordinates
→ temporal association → lineage graph → bounded post-processing
→ pinned official evaluation / separately labeled diagnostics → submission CSV
```

Source modules live under [`src/atabey/`](src/atabey/), runners under
[`scripts/`](scripts/), and focused regression cases under [`tests/`](tests/).
The original longer research index is retained in the
[verbatim pre-closure README](docs/archive/README_before_documentary_close_20260929.md).
Its internal links retain their original repository-root context and its pending
statuses describe historical stages, not the final state above.

For a development environment (Python 3.10+):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e ".[official-metrics]"
python -m pytest -m "not slow"
```

Generic installation is not exact historical runtime reproduction. Use the
recorded package versions, source hashes, checkpoint identities and original
contracts for a particular experiment. Tests marked `slow` need local data or
weights; full cohort replay needs additional artifacts beyond a Git clone.
Consult the [V28 publication boundary](docs/V28_PUBLICATION_SCOPE.md),
[V29A publication boundary](docs/V29A_PUBLICATION_SCOPE.md) and
[V27 publication boundary](docs/V27_PUBLICATION_SCOPE.md).

Raw microscopy volumes, GEFF labels, checkpoint binaries and large generated
outputs are not bundled as a complete public dataset. Frozen manifests remain
unchanged. The former README bytes referenced by V29A are preserved separately;
that relocation does not make old path-based validators pass against the new
README. The closure note explains how to inspect the historical state.

Atabey is personal, educational research, not an official Biohub/Kaggle project,
a validated biological model or a diagnostic system. Detections and associations
remain tracking hypotheses. The durable result is both the submitted V28 and an
inspectable account of what we tried, rejected, corrected and could not finish.
