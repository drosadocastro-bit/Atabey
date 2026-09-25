# V27A.1 association decomposition results

Date: 2026-09-24

Status: **VALID_MECHANISM_RESULT — 16/16 frozen samples completed**.

Danny explicitly approved freezing and executing V27A.1. The approved payload
completed two identical passes per sample without a remaining validity failure.
The result separates local effects of operation order, ranking and forward tie
resolution on fixed baseline histories. It establishes no improvement in tracking
accuracy or official score. V26A remains **NO_GO**; the original V27A attempt
remains **INVALID_EXECUTION**.

## Design and unit of observation

The census contains **99,167 source decisions across 1,584 frame transitions**
(99 transitions in each of 16 samples). All arms consume the same frozen baseline
predecessors; alternate decisions never update the history used by later frames.
Both the prediction-error and physical-step gates remain inclusive at 9 microns.
Reverse physical cKDTree ownership, confidence and greedy uniqueness remain fixed.

| Arm | Selection order | Forward ranking and tie policy | Accepted local links |
|---|---|---|---:|
| H | Select, then gate | Historical motion cKDTree choice | 86,778 |
| M0 | Select, then gate | Motion error; original target index on exact ties | 86,763 |
| M1 | Filter, then select | Motion error; original target index on exact ties | 86,965 |
| S0 | Select, then gate | Physical step; original target index on exact ties | 87,450 |
| S1 | Filter, then select | Physical step; original target index on exact ties | 87,484 |

These are conditional local decisions, not recursively executed alternative
lineages. Repeated sources and frames are not independent biological evidence.

## Paired contrasts

| Contrast (before → after) | Selected target changed | Accepted outcome changed | Added edge identities | Removed edge identities | Net accepted links |
|---|---:|---:|---:|---:|---:|
| Forward tie resolution, H → M0 | 275 | 204 | 141 | 156 | -15 |
| Order with motion ranking, M0 → M1 | 4,739 | 202 | 202 | 0 | +202 |
| Order with step ranking, S0 → S1 | 4,630 | 34 | 34 | 0 | +34 |
| Ranking with select-first order, M0 → S0 | 2,470 | 1,608 | 1,533 | 846 | +687 |
| Ranking with filter-first order, M1 → S1 | 1,502 | 1,386 | 1,339 | 820 | +519 |

An accepted outcome is the accepted target identity or no accepted target. A
replacement counts once as a changed source outcome but contributes one removed
and one added edge. Selected-target changes also include an ineligible target
becoming no selection after prefiltering; they do not imply thousands of added
links. Added edges are not established true positives.

The aggregate acceptance interaction is
`(S1 - S0) - (M1 - M0) = 34 - 202 = -168`.
Equivalently, the ranking effect is +687 under select-first order and +519 under
filter-first order. Order and ranking therefore have non-additive local effects
in this cohort. At source level, the interaction is -1 for 199 decisions, +1 for
31, and zero for 98,937. These counts establish neither statistical independence
nor a preferred arm.

The historical exposure check reproduces **229** gate-failed H decisions with a
feasible alternative and **200** local S1 acceptances among them. This H-based
exposure is a different contrast from the controlled M0 → M1 order effect of
+202, because H and M0 use different forward tie policies.

## Exact ties and the amendment

H and M0 select the same target in **98,892** decisions. Their **275** different
selections are exact motion-error ties: **255** have the same eligibility and
**20** have different eligibility. The latter occur in seven samples. Across all
forward tie-resolution changes, 204 accepted outcomes change, with a net count
of -15 links. There are 824 decisions flagged with a forward tie overall; the
275 changed selections are a subset, not the total tie population.

All 20 differing-eligibility cases retain the original `h_m0_gate_mismatch` in
`parent_v27a_validity_failures`, with disposition
`RECORDED_TIE_MEDIATED_OUTCOME`. Each satisfies the explicit candidate-wise checks
in the [approved amendment](V27A1_TIE_GATE_AMENDMENT.md). No other parent failure
was observed, and no amended validity failure remains. The original failed run
and its known regression witness retain their original status and provenance.

## Verification and evidence

- The frozen pre-execution battery passed **93 tests**, with zero failures,
  errors or skips. No scientific code changed during this execution.
- The runner reproduced **48** graph signatures: relink, V24.2 and V24.3 for
  each sample. V19 hashes in sample metadata are historical references, not 16
  additional reproduced signatures.
- All **16 pairs of compressed frame streams** have identical SHA-256 hashes.
- Post-run artifact verification recomputed all sample and aggregate counts
  from first-pass rows using the frozen summarizer. It checked all 1,584 original
  observation digests after removing only amendment/runner annotations, and
  checked that each frame's before/after input digests agree.
- The **97 frozen source identities**, runtime, test evidence, input archives
  and parent failure artifacts still match the approved manifest. The saved
  `freeze_used.json` is byte-identical to that manifest.
- The raw run contains **50 files**, totaling **209,508,475 bytes**. Their paths,
  sizes and hashes, per-sample results and post-run checks are recorded in the
  [machine-readable result](v27a1_association_decomposition_results.json).

This is builder verification of execution integrity; it is not an independent
scientific review or a new human promotion decision. The earlier amendment and
implementation-review documents are preserved as historical pre-execution records;
this report records the subsequent approval and completed execution.

Approved manifest:
[v27a1_freeze_approved_20260924.json](v27a1_freeze_approved_20260924.json)

Manifest SHA-256:
`3598246e7aa9574a3a8a26d99bcc51eda910d32a004382a9e8256d972d597a19`

Payload SHA-256:
`2e95327df40245deb2a885265b5ccef88aafb44e52fe6fd32408e4a2bcd19913`

Raw output directory: `outputs/v27a1_frozen_20260924/`.

Executed command, recorded for provenance (the output directory now exists):

```powershell
.\.venv\Scripts\python.exe scripts/run_v27a1_association_decomposition.py run `
  --freeze v27a1_freeze_approved_20260924.json `
  --approved-freeze-sha256 3598246e7aa9574a3a8a26d99bcc51eda910d32a004382a9e8256d972d597a19 `
  --output-dir outputs/v27a1_frozen_20260924
```

## Interpretation and next research boundary

The V26A lesson is supported by this fixed-history decomposition: changing to
physical-step selection with prefiltering bundles mechanisms whose local effects
depend on each other. Forward tie resolution is also consequential, including
when the two candidates satisfy the same motion-error minimum but differ under
the physical-step gate.

A subsequent recursive-history experiment would require its own frozen contract,
explicit tie/order/ranking controls, evaluation boundaries and human authorization.
V27B has not been executed. This run performs no new model inference, official
rematching/scoring, production tuning or submission. More accepted links alone
do not justify promotion.
