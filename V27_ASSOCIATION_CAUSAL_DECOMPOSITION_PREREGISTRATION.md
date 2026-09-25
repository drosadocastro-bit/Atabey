# V27 association decision decomposition — proposed preregistration

Date: 2026-09-24

Status: **PROPOSED; NOT FROZEN; NOT IMPLEMENTED; NOT EXECUTED**.

The user requested that V26A's gate-order finding become a lesson learned and
the basis for V27. This document proposes a reviewable experiment. It does not
claim execution approval, a completed freeze, or a superior tracker.

## Question

On the same immutable source, target and predecessor evidence, what local
decision changes follow from operation order, what changes follow from ranking,
and where do these factors interact?

Here a causal contrast means an intervention on a deterministic decision
procedure conditional on recorded inputs. It does not establish biological
causation, independent generalization or the effect of a recursively applied
tracker. The opened 16-sample V25 cohort is retrospective mechanism evidence.

V24.3 stays the frozen reference, V26A stays NO-GO, and V24.8's independent-data
block remains in place. Existing scientific artifacts must not be rewritten.

## V27A: local decisions under frozen baseline histories

For every source before the final frame, use exactly the predecessor in the
archived V25 baseline graph. Use all detections in the next frame in their
original order. No arm's output may become another frame's predecessor input.
The full cohort is required; the 229 exposed sources are an audit stratum, not
a subset selected for experimentation.

Definitions:

- `motion_error`: distance to the frozen one-step predicted position in microns.
- `physical_step`: source-to-target distance in microns.
- `feasible`: both distances finite and at most 9.0 um, inclusive.
- `SELECT_THEN_GATE`: choose from all targets using the stated rank key; apply
  both gates to that one target; if it fails, abstain without trying another.
- `FILTER_THEN_SELECT`: first retain feasible targets, then choose using the
  stated rank key; if none remain, abstain.
- Controlled forward ties: ascending original target index for exactly equal
  rank distances, with no epsilon, jitter, rounding or index renumbering.

| Arm | Operation order | Ranking | Forward ties | Purpose |
| --- | --- | --- | --- | --- |
| H | Exact existing baseline function | Motion | Existing SciPy cKDTree | Historical reference |
| M0 | SELECT_THEN_GATE | Motion | Original target index | Controlled reference |
| M1 | FILTER_THEN_SELECT | Motion | Original target index | Order at fixed motion ranking |
| S0 | SELECT_THEN_GATE | Physical step | Original target index | Ranking at fixed original order |
| S1 | FILTER_THEN_SELECT | Physical step | Original target index | Combined condition; existing V26A locally |

All four controlled arms must consume the same computed distance tables and
unchanged input order. Reverse raw-nearest ownership continues to use the same
SciPy cKDTree over the previous detections, including its existing tie behavior
and inclusive 9 um limit. Reverse ties are observed, not intervened on.
The existing greedy uniqueness rule and prediction-error confidence definition
remain common. Keep selected, gate-eligible and finally accepted targets distinct.

The H/M0 comparison checks forward tie normalization. Do not label a discrepancy
as a tie effect merely because cKDTree and an array implementation disagree:
verify equality of the tied rank distances and unchanged gate outcomes. Any
non-tie selection, gate or confidence discrepancy is a numerical/implementation
mismatch that blocks this attribution and must be preserved before remediation.
Do not introduce an epsilon after observing such a failure. H must remain the
exact historical function regardless of the result of this check.

## Prespecified contrasts

| Contrast | Paired arms | What is controlled |
| --- | --- | --- |
| Order under motion ranking | M1 versus M0 | Ranking, ties and history |
| Order under step ranking | S1 versus S0 | Ranking, ties and history |
| Ranking with select-before-gate | S0 versus M0 | Order, ties and history |
| Ranking with pre-filtering | S1 versus M1 | Order, ties and history |
| Forward tie normalization at historical order/ranking | M0 versus H | Requires the tie-only equivalence check |

Report each contrast at both the selected-target and accepted-target stages.
For each source, record the categorical before/after target IDs (including
abstention), added/removed edge identities and rejection reasons. A symmetric
difference count does not identify a signed improvement.

For the binary accepted-edge indicator Y, the interaction is
`(Y_S1 - Y_S0) - (Y_M1 - Y_M0)`. Report its per-source distribution and sum.
Also retain the complete target tuples: equal acceptance counts can conceal
different target identities. Do not claim that signed acceptance or more edges
means improved tracking. The main factorial holds ties fixed; the H contrast
does not estimate all possible tie-policy interactions.

## Evidence and outputs

Inputs are the previously validated V25 archive, historical V26A result archive,
V26A gate-order audit JSON and pinned code references. The machine proposal
records exact cohort IDs, archive identities and canonical source hashes.

Required outputs per sample and in aggregate:

- denominators for source decisions, available/feasible targets and accepted links;
- source/frame/node IDs, predecessor ID, candidate index and distances;
- all five arms' selected, gate-eligible, reverse-owner and accepted decisions;
- exact forward and reverse distance ties, including target ordering;
- all five prespecified paired contrasts and the acceptance interaction;
- descriptive strata for no predecessor, gate-order exposure, ties and archived
  V25 loss subtype; preserve overlapping memberships rather than double-counting;
- optional descriptive intersections with the fixed archived V26A recovery and
  unmatched-edge ledgers, clearly identified as historical intersections;
- graph/input signatures before and after observation, source/runtime identities,
  validation failures and deterministic replay evidence.

No new official metric or node/edge rematching is performed in V27A. A selected
target with an archived mapping is not a newly measured TP. No image inference,
training, threshold search, blending, sample selector, routing or submission is
part of this phase. Do not assemble the local arm outputs into a new scored
whole-sequence tracker or feed them to pruning.

## Freeze and validity checks

The machine file is currently **PROPOSED**, with null implementation, review
and freeze records. A fixture-shaped file or completed checklist is not a lock.

Before any real-data V27 run:

1. Review this scope and the exact contrasts with the human authority.
2. Implement one bounded shadow decision surface extending existing association
   audit machinery; do not introduce a second production linker hierarchy.
3. Validate synthetic cases for both order directions, two feasible targets with
   opposing ranks, inclusive gates, no targets, absent history, forward/reverse
   ties, reverse rejection, and confidence/uniqueness. Include cases with only
   one feasible alternative and with step-nearest targets failing prediction.
4. Review implementation against the decision table. Pin final implementation,
   test, protocol and dependency identities in an immutable freeze manifest,
   recording the reviewed revision and human execution authorization. The
   current working-tree proposal and audit have no assumed committed identity.
5. Require the runner to reject a proposal, absent/mismatched freeze record,
   artifact mismatch or unapproved revision. Preserve failed attempts.

Execution validity then requires:

- full 16-sample membership and both archive identities;
- the existing 48 baseline/pruning signatures and 86,778 baseline edge identities;
- exact H agreement with the existing baseline and exact local S1 agreement
  with existing V26A, including edge confidences;
- reproduction of the prior audit's 99,167 sources, 229 exposed sources and 200
  local S1 acceptances at exposed sources as integrity checks, not efficacy gates;
- the H/M0 tie-only equivalence check described above;
- unchanged frozen graph/input signatures and two deterministic scientific replays.

Use `VALID_MECHANISM_RESULT` only when every validity check passes; use
`INVALID_EXECUTION` on any failure, keeping partial evidence. A valid null result
is a useful outcome. Neither status means GO for production, and no arm is
automatically selected by the count of recoveries or accepted links.

## Recursive history: separate future phase

V27B is a prospective question, not an executable phase in this proposal. A
separate contract would compare local frozen-history decisions with recursive
versions of explicitly fixed arms, separating raw linking, unchanged-code
pruning responses and official rematching. It must be fixed before that run;
V27A labels must not be used to silently select a winning arm or thresholds.
No recursive effect or independent validation follows from V27A alone.

## Lessons and references

- [V26A lessons learned](docs/V26A_LESSONS_LEARNED.md)
- [Gate-order evidence](V26A_GATE_ORDER_AUDIT_RESULTS.md)
- [Original V26A result and NO-GO](V26A_FORWARD_RANKING_ABLATION_RESULTS.md)
- Machine proposal: `tests/fixtures/v27_association_causal_decomposition.json`
