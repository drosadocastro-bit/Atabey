# V21 Session Synthesis - 2026-07-22

Branch: `mitosis_hough_audit`

Status: documentation-only consolidation; no new experiment, graph mutation, detector change,
threshold tuning, or Track A/Track B change is authorized by this document

## Purpose

This document consolidates the evidence produced and reinterpreted during the July 22 session.
The work covered six related but distinct threads: official metric parity, ownership contention,
counterfactual pairing, constrained assignment, bead-free microscopy QC, and the conceptual Vela
Entropy Field note. The goal is to preserve what was actually measured, withdraw claims invalidated
by the corrected metric, and leave an explicit research boundary for the next session.

The corrected division evidence is bounded to the fixed Phase 1/2 windows. It is not a 199-sample
population estimate. Sparse-unsupported predictions remain unknown, not verified negatives and not
biologically valid divisions by default.

## Executive Synthesis

1. The local Division Jaccard evaluator was not equivalent to either the old exploitable host metric
   or the patched host metric. Official patched scoring is now called directly and parity-tested.
2. Under the corrected scorer, V19 contains four real division TPs and six evaluable FPs; V20 removes
   every one of those TPs. The former 91% division-FP-reduction claim is withdrawn.
3. Ownership contention is real in known wrong-winner events, but exclusivity alone is not a reliable
   biological division selector. The local Hungarian shadow improved aggregate ranking while causing
   three regressions and failing its pre-registered GO rule.
4. Future daughter continuity can reject known wrong pairs, but smooth unrelated tracks often look
   better than true daughters. Continuity is evidence, not a standalone selector.
5. A centralized assignment constraint layered over richer candidate scores remains a coherent
   architectural analogy from charged-particle tracking. It has not been validated for Atabey and
   has not been built.
6. The Sun Check analogy is useful for sample-state QC and routing research. It does not justify
   image correction, stage-drift compensation, or threshold adaptation.
7. Vela Entropy Field remains a conceptual uncertainty-pressure note only. It is related to, but
   must not be confused with, Track B's existing confidence router.

## 1. Official Division Metric Correction

### What was wrong

Atabey's previous local division evaluator matched neither historical host behavior:

- it was not the old weakly-connected-component implementation affected by the public exploit;
- it was not the patched implementation requiring the official directed division structure;
- it was a third, non-equivalent approximation.

Consequently, raw division FP totals and any precision/reduction claims derived from that local
implementation were not trustworthy representations of the competition score.

### What is now integrated

`src/atabey/evaluation/official_division_metric.py` converts Atabey graphs into
`tracksdata.InMemoryGraph` and calls the host's untouched `score_divisions` implementation.
No division-matching rule is reimplemented locally.

- Host repository: `royerlab/kaggle-cell-tracking-competition`
- Pinned host commit: `075fc5f5a52d11077f9dc2b074644618f26939e2`
- Public exploit-fix commit: `aa65e90aeb8a774ebb1b549e547787b87ac8a01c`
- Pinned `tracksdata` commit: `39dccf3a243e44274759468cb31b2ad9e7fc1d09`
- Official matching radius: `7 um`

Validation completed:

- official host patched division suite: **39/39 passed**;
- Atabey targeted adapter/adversarial/firewall/Track B suite: **16/16 passed**.

### Corrected bounded results

Across the fixed Phase 1 four plus Phase 2 ten evaluable division windows:

| Version | TP | FP | FN | Interpretation |
|---|---:|---:|---:|---|
| V19 raw bipartite | 4 | 6 | 10 | Four official divisions recovered; evaluable precision 0.40 |
| V20 bipartite + firewall | 0 | 0 | 14 | All four V19 TPs suppressed |

The fourth V19 TP is in `6bba_32db13fc`. The original three remain official TPs:

- `6bba_05db0fb1:t24:cf76`
- `6bba_b329af44:t82:cf38`
- `6bba_ebdf3b34:t84:cf39`

V19 produced `27,779` raw forks in these bounded graphs, but only six were official evaluable FPs.
Track B accepted `8,507` forks: three official TPs, two official FPs, and `8,502` unsupported/ignored
forks. Ignored does not mean correct; it means the sparse official evidence cannot score the fork.

### Claims formally withdrawn or preserved

Withdrawn:

- the claimed approximately 91% V19-to-V20 division-FP reduction as an official-metric result;
- raw-FP-per-sample interpretations based on the old evaluator;
- any Track B precision estimate using unsupported forks as ordinary false positives or negatives.

Preserved:

- EdgeRecall measurements, because they are a separate evaluation surface;
- zero-perturbation checks, because they compare graph identity rather than Division Jaccard;
- the existence of the original three recovered TPs;
- fixed-candidate kinematic, pairing, and ownership observations, with their population-level
  interpretation narrowed to the bounded cases actually measured.

Primary evidence: `OFFICIAL_DIVISION_METRIC_INTEGRATION.md` and
`OFFICIAL_DIVISION_RECALIBRATION.md`.

## 2. Ownership and Exclusivity Investigation

### Phase 1

The four known wrong-winner cases were audited read-only. In **4/4**, the wrong-winner cell had a
separate legitimate competing parent. The competing parent satisfied the same formation gate and
mutual-nearest conditions and was closer to that cell than the focal division parent. This confirmed
that the observed failures were genuine local ownership conflicts rather than merely isolated bad
scores.

### Phase 2

Twenty independent samples with known divisions were pre-registered. Ten were evaluable under the
sparse matching setup. Across the Phase 1 plus evaluable Phase 2 wrong-winner events, **12/12** showed
some competing-parent evidence, and **10/12** satisfied the strict full pattern.

The other ten Phase 2 samples were not hidden ownership failures. Across 12 missing GT nodes:

- seven were localization gaps between `7` and `14 um`;
- two were detection/localization gaps beyond `14 um`;
- two were recovered by a global distance-ordered matcher, demonstrating matcher-order artifacts;
- one involved one-to-one evaluator contention and also had a parent beyond `14 um`.

At sample level, eight of ten were primarily detection/localization failures and two were
matcher-order artifacts. Sparse centroid matching does not inspect lineage ownership, so a parent
outside the bounded graph cannot make a same-timepoint detection disappear from that evaluation.

### Local Hungarian shadow

The shadow solver reserved each focal daughter pair and solved assignment only among parents already
owning or mutually claiming those cells. It never performed frame-wide assignment and never mutated
Track A, Track B, graph edges, or candidate formation.

| Outcome | Result |
|---|---:|
| Correct-pair rank improved / flat / regressed | 9 / 2 / 3 |
| Top-1 correct pairs | 2/14 -> 6/14 |
| Median correct-pair rank | 6 -> 3 |
| Zero perturbation | 14/14 |

Decision: **NO-GO for broader rollout or integration.** The result was net-positive diagnostically,
but it failed the pre-registered requirement of no regressions and at least 10/14 top-1 recoveries.
The three regressions demonstrate the central limitation: real daughters can also be legitimate
continuations for competing parents. Exclusivity is informative but insufficient.

### Relationship to the four official TPs

All four official V19 TPs are already formed correctly in V19. On the exact officially credited
forks, **0/4** currently lose a daughter through the diagnosed ownership-contention mechanism.
`6bba_32db13fc` required a specific correction here: the official TP is the upstream fork
`t4:cf2 -> {t5:cf29, t5:cf5}`, not the later pair used by the original shadow-ranking row. The
officially credited fork has zero competing parents and zero disputed targets.

Therefore LSAP is not presently supported as a recovery mechanism for the small set of official TPs.
Any future assignment work must justify itself through a richer scorer and independent evidence,
not through the claim that these four TPs require exclusivity repair.

Primary evidence: `V21_LOCAL_ASSIGNMENT_SHADOW_AUDIT.md` and the corrected official-TP audit.

## 3. Counterfactual Pairing Audit

The Juracan-inspired audit held one matched daughter fixed, substituted nearby alternatives within a
diagnostic `14 um` radius, and followed existing continuations for four child frames. It measured
coverage, constant-velocity prediction error, branch-axis stability, and non-collapse. The production
`9 um` gate remained unchanged.

Findings:

- the correct pair beat each specifically known wrong pair under all three score profiles in the two
  cases where a wrong pair was pre-identified;
- no correct pair ranked in the top five;
- two of four correct pairs ranked in the top ten;
- two of four appeared on the Pareto front;
- unrelated nearby cells with smooth trajectories frequently outranked true daughters.

Decision: **NO-GO as a standalone daughter-pair selector.** Future continuity is useful negative or
supporting evidence, but individual daughter persistence does not establish shared parentage. A future
design needs independent parent-centered geometry or appearance evidence.

Primary evidence: `V21_COUNTERFACTUAL_PAIRING_AUDIT.md`.

## 4. Charged-Particle Tracking Parallel

The architectural reference is:

- Kortus et al., "Constrained Optimization of Charged Particle Tracking with Multi-Agent
  Reinforcement Learning," arXiv:2501.05113;
- the January 2026 Machine Learning: Science and Technology follow-up,
  DOI `10.1088/2632-2153/ae352b`.

Terminology correction: this is high-energy-physics charged-particle tracking for a proton-computed-
tomography detector, not an HL-LHC-specific reconstruction study. The transferable architectural
idea remains valid: richer local policies score candidate actions, then a centralized LSAP safety
layer projects those actions onto a uniquely assigned feasible solution. LSAP is a constraint layer,
not the semantic scorer.

Potential Atabey translation:

1. score parent-daughter hypotheses using parent-centered geometry, daughter continuity, appearance,
   and calibrated uncertainty;
2. apply local ownership constraints only to genuinely disputed cells;
3. preserve division capacity, because one biological parent may own two daughters. A vanilla
   one-to-one Hungarian formulation is insufficient; the formulation would need duplicated parent
   slots, capacitated matching, or an equivalent constrained representation;
4. retain an uncertain/abstain path rather than forcing every local conflict into a division.

Status: **architectural direction only; not implemented and not authorized.** Today's Hungarian
NO-GO shows that exclusivity cannot supply the missing semantic score. The official-TP audit further
shows that none of the four current TPs needs assignment repair.

References:

- https://arxiv.org/html/2501.05113v1
- https://iopscience.iop.org/article/10.1088/2632-2153/ae352b

## 5. Atabey Sun Check Bounded Audit

The WSR-88D Sun Check analogy was translated into a bead-free retrospective QC audit. Because the
competition data contain no calibration beads or instrument telemetry, every quantity was explicitly
treated as a self-consistency proxy rather than absolute gain, PSF, or stage drift.

The fixed panel contained six `44b6` and six `6bba` samples spanning components, local-maxima, and
CFAR routes; all four official V19 TP samples; a prior high-residual-noise case; and clean controls.
Five anchor frames plus their immediate successors were read per sample.

Key results:

- current image-only route agreed with the historical V20 detector class for **12/12** samples;
- CFAR route median background: `306`; median SNR proxy: `3.169`;
- components route median background: `77.5`; median SNR proxy: `10.619`;
- compact-object footprint ranges were narrow across the panel: Z `1.787-2.124 um`,
  Y `1.034-1.179 um`, X `1.002-1.179 um`;
- no sampled frame contained saturated `uint16` voxels;
- the full-panel temporal-intensity association with V20-minus-V13 EdgeRecall was
  `rho=-0.732`, `p=0.007`;
- inside the seven CFAR samples, the same association weakened to `rho=-0.536`, `p=0.215`.

The sensitivity check demonstrates route confounding. The full-panel correlation is not accepted as
a general effect. Bulk-shift estimates also mix acquisition displacement with real embryo motion and
do not justify stage-drift correction.

Decision: **GO for sample-state QC and routing research; NO-GO for correction, compensation, or
threshold adaptation.** A follow-up must use independent pre-registered samples within route and
must show value beyond the existing foreground-density profile.

Primary evidence: `ATABEY_SUN_CHECK_BOUNDED_AUDIT.md`.

## 6. Vela Entropy Field

Vela Entropy Field is recorded as a future research note: a generalized uncertainty-pressure signal
intended to summarize when local evidence is diffuse, contradictory, incomplete, or crowded. No
mathematical definition, implementation, fitted parameters, experiment, or validation exists in the
current checkout under this name.

### Scientific inspiration and naming provenance

The name comes from the Vela pulsar, PSR B0833-45, in the constellation Vela. Vela is a canonical
glitching neutron star: its otherwise regular spin-down is interrupted by sudden spin-ups, followed
by recoveries over multiple timescales. In vortex-mediated models, differential rotation and angular
momentum accumulate between the observed crust-coupled component and pinned superfluid regions;
catastrophic vortex unpinning transfers angular momentum, and post-glitch vortex creep governs part
of the recovery. Analyses of Vela's repeated glitches also describe persistent spin-up remnants and
discrete changes in internal torque.

Those observations motivated the **crustal memory analogy** used for Vela Entropy Field: a stressed,
partially coupled system carries consequences of accumulated prior state into a sudden transition and
its subsequent relaxation. This is path dependence, not memory in a cognitive or literal storage
sense.

The conceptual mapping to Atabey is:

| Vela glitch-system inspiration | Atabey research analogy |
|---|---|
| Accumulated differential rotation or stress | Unresolved local ambiguity, conflict, or missing evidence |
| Coupled regions with different response times | Detector, geometry, continuity, and ownership signals with different reliability |
| Threshold-crossing glitch | A routing, abstention, or review-priority transition |
| Post-glitch relaxation | Uncertainty pressure declining when later evidence resolves a conflict |
| Persistent rotational remnant | Residual uncertainty state that should remain visible rather than be silently erased |

This mapping is inspiration only. Atabey does not claim physical equivalence between cell tracking and
neutron-star interiors, and no glitch equation, vortex-creep parameter, entropy field, or crustal model
has been imported into the tracker.

The astrophysics literature does **not** appear to use "Vela Entropy Field" or establish a formal model
named "crustal memory hypothesis." Those are Atabey research terms. The underlying physical references
are glitch-driven state accumulation, release, recovery, coupling, and persistent remnants:

- Alpar, Anderson, Pines, and Shaham (1981), "Giant glitches and pinned vorticity in the Vela and other
  pulsars," *The Astrophysical Journal*, DOI `10.1086/183652`:
  https://ntrs.nasa.gov/citations/19820031117
- Alpar, Chau, Cheng, and Pines (1993), "Postglitch relaxation of the Vela pulsar after its first eight
  large glitches: A reevaluation with the vortex creep model," *The Astrophysical Journal*,
  DOI `10.1086/172668`: https://open.metu.edu.tr/handle/11511/67674
- Newton, Berger, and Haskell (2015), "Observational constraints on neutron star crust-core coupling
  during glitches," *Monthly Notices of the Royal Astronomical Society*, DOI `10.1093/mnras/stv2285`:
  https://academic.oup.com/mnras/article/454/4/4400/1002982

Its nearest existing Atabey mechanism is Track B's confidence router:

- calibrated high-confidence candidates may become division proposals;
- low-confidence or uncalibrated candidates remain extractive/flagged;
- the router controls disposition without mutating Track A.

Vela must not be treated as another confidence value or as evidence of biological truth. If developed,
it would be an upstream contextual pressure or review-priority signal that may inform the existing
router. It must preserve candidate provenance, mechanism identity, missing-feature state, and
abstention. It is documented here to prevent conceptual loss, not to authorize implementation.

## Prioritized Next Steps

### 1. Official-evaluator parity inventory - completed 2026-07-23

The inventory is complete in
[OFFICIAL_EVALUATOR_PARITY_INVENTORY.md](OFFICIAL_EVALUATOR_PARITY_INVENTORY.md). Official division,
per-sample tracking, node-count adjustment, and run-level aggregation now call the pinned host
directly. The executed host suites pass 39/39 division tests and 44/44 broader metric tests.

Sparse EdgeRecall, sparse node recall, nearest-centroid error, the historical 50/50 quality score,
multi-source agreement, and the V19 global-greedy matcher are classified as diagnostic or
experimental rather than competition-equivalent. Surviving division claims remain bounded and use
the official scorer.

### 2. Joint semantic scorer plus assignment constraint design - completed 2026-07-23

The design and pre-registered validation contract are complete in
[V21_JOINT_SEMANTIC_ASSIGNMENT_DESIGN.md](V21_JOINT_SEMANTIC_ASSIGNMENT_DESIGN.md).
The architecture scores parent-centered geometry, daughter continuity/divergence, explicit
missingness, and only independently validated appearance evidence before applying a local,
division-capable ownership constraint. Assignment is a safety layer, never a source of semantic
confidence, and low-margin constraint changes route to abstention.

The contract permanently includes the three Hungarian regressions, preserves the four official V19
TPs, and locks an independent 20-sample/39-division cohort before implementation. This completes the
design priority only. No scorer, solver, production graph mutation, or submission behavior has been
implemented or authorized.

### 3. Independent CFAR-only Sun Check follow-up - pre-registered 2026-07-23

The locked protocol is complete in
[SUN_CHECK_CFAR_FOLLOWUP_PREREGISTRATION.md](SUN_CHECK_CFAR_FOLLOWUP_PREREGISTRATION.md).
It fixes a primary cohort of 30 CFAR-routed samples balanced across both families, plus 12
non-CFAR route controls. Selection used frozen route metadata and deterministic hash ordering before
opening any Sun Check outcomes.

The primary endpoint is the official adjusted-edge-Jaccard difference between frozen V19 CFAR and
V13 adaptive graph copies. The confirmatory test asks whether temporal intensity adds out-of-sample
value beyond foreground density and component size. No measurement has been run, and no result can
authorize image correction, threshold adaptation, graph mutation, or production routing.

Vela remains behind the completed design and pre-registration priorities until it has a precise
problem statement and non-overlap argument relative to the confidence router.

## Closed

The following questions or approaches are closed unless new independent evidence justifies reopening:

- the previous local Division Jaccard implementation as a competition-equivalent evaluator;
- the approximately 91% division-FP-reduction claim derived from that evaluator;
- interpreting unsupported sparse-region forks as ordinary official FPs or verified negatives;
- Track A's current strict firewall as a division-recovery path. It suppresses all four official V19
  TPs in the fixed battery and will not be pursued further without structural redesign;
- loosening Track A thresholds as the next division strategy;
- short-horizon daughter continuity as a standalone selector;
- exclusivity-only local Hungarian ranking as a rollout candidate;
- LSAP as a standalone biological scorer;
- bead-free Sun Check measurements as authorization for image correction or drift compensation.

## Open

The following remain open research questions:

- how strongly each diagnostic sparse metric correlates with official score on independently held-out samples;
- why V20 removes each of the four already-correct official V19 forks;
- how to form and score parent-daughter alternatives without losing correct candidates upstream;
- whether parent-centered geometry, continuity, appearance, and calibrated uncertainty can jointly
  distinguish real divisions from legitimate neighboring continuations;
- whether a division-capable local assignment constraint improves an independently pre-registered
  official-metric battery after a richer scorer exists;
- whether Track B confidence can be calibrated with enough official positive and negative evidence;
- whether Sun Check proxies add within-route predictive value beyond foreground density;
- whether Vela Entropy Field can be defined without duplicating confidence, salience, or density and
  without turning uncertainty into implied evidence.

## Review Gate

This synthesis must be reviewed before any next implementation or experiment. Review should verify:

1. all corrected metric claims use the direct official scorer;
2. bounded evidence is not described as full-cohort generalization;
3. LSAP remains a constraint concept layered over richer evidence;
4. Track A remains frozen and parked pending redesign;
5. Sun Check and Vela remain diagnostic/conceptual and do not silently alter inference.
