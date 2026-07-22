# V21 Counterfactual Pairing Audit

Date: 2026-07-21
Branch: `mitosis_hough_audit`
Status: shadow-only diagnostic; no graph, gate, Track A, or Track B change

## Method

For each known pairing failure, the audit holds one matched daughter fixed and substitutes nearby
detections from `t+1` inside a diagnostic 14 um radius. It follows existing outgoing graph edges for
four child frames and measures continuation coverage, constant-velocity prediction error, branch-axis
stability, and non-collapse. The 14 um radius only observes alternatives; the production 9 um gate is
unchanged.

Three deliberately different score profiles are reported as sensitivity analysis. They are not
probabilities or calibrated confidence. Pareto-front membership is also reported to avoid relying on
one arbitrary weighting.

## Results

| Case | Pair | Correct | Current | Coverage | Mean error | Max drift | Growth | Balanced rank | Pareto front |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `V21-FN-EBDF-PAIRING` | `cf555+cf601` | True | False | 0.875 | 5.034 | 12.582 | -2.237 | 6/21 | True |
| `V21-FN-EBDF-PAIRING` | `cf31+cf601` | False | True | 0.625 | 3.689 | NA | NA | 16/21 | False |
| `LINK-GATE-14-REGRESSION-05DB` | `cf17+cf3` | True | True | 0.500 | 5.723 | NA | NA | 6/11 | False |
| `LINK-GATE-14-REGRESSION-05DB` | `cf17+cf206` | False | False | 0.500 | 5.723 | NA | NA | 8/11 | False |
| `V19-TP-B329` | `cf298+cf309` | True | True | 0.875 | 2.551 | 11.213 | 1.854 | 11/21 | True |
| `V19-TP-EBDF` | `cf282+cf80` | True | True | 0.375 | 5.340 | NA | NA | 11/23 | False |

## Per-Case Interpretation

### V21-FN-EBDF-PAIRING

The 9 um graph forms cf31+cf601 and leaves the matched GT daughter cf555 unlinked.

- Alternatives evaluated: `21` matched substitution pairs.
- Correct pair beats the known wrong pair in `3/3` score profiles.
- Wrong ranks: coverage `16`, balanced `16`, stability `16`.
- Wrong Pareto front: `False`.
- Correct ranks: coverage `7`, balanced `6`, stability `6`.
- Correct Pareto front: `True`.
- Graph zero perturbation: `True`.

### LINK-GATE-14-REGRESSION-05DB

The 9 um graph forms cf17+cf3; a global 14 um gate replaced cf3 with cf206.

- Alternatives evaluated: `11` matched substitution pairs.
- Correct pair beats the known wrong pair in `3/3` score profiles.
- Wrong ranks: coverage `8`, balanced `8`, stability `8`.
- Wrong Pareto front: `False`.
- Correct ranks: coverage `6`, balanced `6`, stability `6`.
- Correct Pareto front: `False`.
- Graph zero perturbation: `True`.

### V19-TP-B329

V19 formed the sparse-GT-matched pair; V20 later lost the branch upstream.

- Alternatives evaluated: `21` matched substitution pairs.
- Correct ranks: coverage `9`, balanced `11`, stability `11`.
- Correct Pareto front: `True`.
- Graph zero perturbation: `True`.

### V19-TP-EBDF

V19 formed the sparse-GT-matched pair; the strict V20 fallback ratio rejected it.

- Alternatives evaluated: `23` matched substitution pairs.
- Correct ranks: coverage `11`, balanced `11`, stability `11`.
- Correct Pareto front: `False`.
- Graph zero perturbation: `True`.

## Aggregate Finding

- Correct-pair balanced ranks: `6/11`, `11/21`, `6/21`, and `11/23`.
- Correct pairs in the top 5: `0/4`; top 10: `2/4`.
- Correct pairs on the Pareto front: `2/4`.
- The correct pair beat the specifically known wrong pair under all three score profiles in `2/2` applicable cases.
- Zero perturbation held for all `3/3` rebuilt samples.

## GO/NO-GO Assessment

**NO-GO as an active daughter-pair selector. Partial positive evidence as a diagnostic signal.**

The future-continuation evidence consistently demoted the two known wrong pairings, but it did not
surface any correct pair in the top five and placed only half of the correct pairs on the Pareto
front. Nearby detections belonging to other smooth tracks frequently produced stronger continuation
evidence. Individual daughter persistence and smoothness therefore do not establish shared parentage.

A further pairing study would need an independent parent-centered signal, not another weighting of
the same daughter-continuation features. Possible evidence includes predecessor-conditioned split
symmetry, explicit local assignment competition, or validated appearance conservation. None is
authorized by this audit.

## Decision Rule

A future pairing mechanism is a GO candidate only if the correct pair consistently outranks the known
wrong pair across the scoring profiles, remains competitive against matched local controls, and the
same evidence does not elevate collision controls. Otherwise the short-horizon idea is insufficient
or requires a different evidence source.

This audit does not authorize graph mutation or parameter tuning.
