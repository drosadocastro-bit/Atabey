# V24.7 ROOT-Inspired Commitment plus ILP Combined Shadow

## Status

Completed locally on the two cached 12-timepoint E016 samples. This is a pure
shadow composition. It does not mutate a graph, authorize an assignment,
select an arm, tune a threshold, or alter a submission.

## Direct Comparison

| Method | Question answered | Main strength | Main limitation |
|---|---|---|---|
| ROOT-inspired predecessor intervention | Does removing one accepted history contribution change later linking? | Localizes path dependence and distinguishes persistent from reconverging perturbations | Does not choose or validate an alternative assignment |
| Bounded ILP | Is there a lower-cost feasible joint assignment under ownership and intervention constraints? | Compares multiple paths jointly and can abstain through an explicit rewrite charge | Depends on a kinematic surrogate and can propose unsupported extensions without eligibility guards |
| Combined funnel | Do intervention-sensitive windows also contain a contained joint alternative? | Uses causal sensitivity for scope and ILP only for bounded adjudication | Evidence remains local, objective-dependent, and non-biological |

The combined funnel is more promising mechanistically than either method alone.
ROOT-inspired intervention is the better trigger; ILP is the better constrained
adjudicator. Neither is sufficient evidence of tracking correctness.

## Frozen Combined Contract

- commitment horizon: 2 frames
- commitment candidates: 64 ambiguity-ranked accepted edges per sample
- ILP enrollment: every commitment record with at least one changed assignment
- ILP ordering: persistent first, then margin and stable node IDs
- maximum ILP windows: 16 per sample
- baseline edge-change penalty: `2.0 um` per symmetric-difference edge
- minimum contained improvement: `0.5 um`
- maximum binary variables: 512 per window
- solver time limit: 5 seconds per window
- zero-penalty ILP: mechanism diagnostic only

## Funnel Result

| Sample | ROOT changed | ROOT persistent | ILP evaluated | Primary rewrites | Zero-penalty rewrites |
|---|---:|---:|---:|---:|---:|
| `6bba_2646afc7` | 2 | 1 | 2 | 0 | 1 |
| `6bba_3c5691b6` | 4 | 0 | 4 | 0 | 0 |
| **Total** | **6** | **1** | **6** | **0** | **1** |

All solves were optimal and used 8 to 23 binary variables. Input graph
signatures remained unchanged.

## Proposal Classification

The one persistent ROOT-sensitive window is also the only zero-penalty ILP
ownership rewrite:

- sample: `6bba_2646afc7`
- trigger: `n00000654 -> n00000723`
- unpenalized kinematic gain: `6.896161 um`
- proposal: remove one edge and add three edges
- contained primary result: keep baseline

Two reconverging ROOT windows had positive unpenalized objective gains but did
not produce ownership rewrites:

- `6bba_2646afc7`, trigger source `n00000217`: add-only proposal
  `n00000289 -> n00000361`, gain `4.878890 um`
- `6bba_3c5691b6`, trigger source `n00000387`: add-only proposal
  `n00000458 -> n00000532`, gain `2.050896 um`

The eligibility rule rejected both add-only extensions. The other three
reconverging windows retained the exact baseline even at zero penalty.

## Interpretation

Within this tiny opened-label probe, persistence is more selective than mere
perturbability:

- persistent commitment windows with an ILP rewrite: 1 of 1
- reconverging commitment windows with an ILP rewrite: 0 of 5

That separation is promising as a precision funnel, not as efficacy evidence.
The sample is too small to estimate enrichment, and no proposed graph was
officially scored. The primary containment contract still recommends zero
changes, which is the correct operational result at this evidence level.

The add-only proposals expose an important objective boundary: kinematic cost
alone can reward extra continuity. Keeping rewrite eligibility separate from
raw solver gain prevents that diagnostic behavior from becoming an implicit
recovery mechanism.

A defensible continuation is a fixed-cohort shadow replay with the same
contract, reporting persistent/reconverging overlap, proposal class, objective
gain, intervention size, budget failures, and retrospective official metric
deltas. No penalty should be changed from these two samples.

## Reproduction

```powershell
python scripts/run_v24_7_commitment_ilp_shadow.py
```

Machine-readable evidence is in
`outputs/v24_7_commitment_ilp_shadow_local_2/summary.json`.