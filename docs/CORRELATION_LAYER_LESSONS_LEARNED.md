# Correlation Layer Track-Continuity — Lessons Learned and Close-Out

Date: 2026-07-05
Status: Closed as documented experimental history (final NO-GO for submission candidacy).

This document consolidates the full correlation-layer thread in one place:

- Motivation and hypothesis from OSS diagnostics.
- Phase 1 shadow validation.
- Phase 2 naive active injection NO-GO.
- Phase 3 merge-gate mechanism fix (qualified GO in harness).
- Real-pipeline integration verdict (final NO-GO).

The intent is archival clarity, not rollback or deletion. This history remains part of the repository as a reusable decision record.

## Canonical References

- [CORRELATION_LAYER.md](CORRELATION_LAYER.md)
- [CORRELATION_LAYER_PHASE2.md](CORRELATION_LAYER_PHASE2.md)
- [CORRELATION_LAYER_MERGE_GATE.md](CORRELATION_LAYER_MERGE_GATE.md)
- [OSS_DIAGNOSTICS.md](OSS_DIAGNOSTICS.md)

## 1) Consolidated Timeline

1. Starting hypothesis (from OSS diagnostics):
- OSS showed CFAR-collapse-prone samples were Type A recoverable and not Type B blind spots.
- At-risk cohort classification: 51/51 Type A, 0/51 Type B.
- Interpretation: leverage should be in track continuity/recovery, not detector-threshold retuning.

2. Phase 1 (shadow-only, feasibility):
- Track-gap continuity signal was abundant on the routed cohort.
- Recovery potential was strong and runtime cost was negligible.
- Decision: GO to active-injection validation.

3. Phase 2 (naive active injection, ground-truth scored):
- Confirmed real node recovery (synthetic matches on GT nodes, 0 displaced node matches).
- At-risk node recall improved, but at-risk edge recall regressed (identity-collision/double-target failure).
- Decision: QUALIFIED NO-GO for naive injection.

4. Phase 3 (merge gate, identity de-dup in isolation harness):
- Merge gate suppressed synthetic candidates near real detections and resolved the identity-collision mechanism.
- At-risk edge regression was reduced by 77% in isolation.
- Decision: QUALIFIED GO on the experimental harness (mechanism-level fix validated).

5. Real-pipeline integration (production runners, opt-in only):
- Recovery integrated behind explicit flag `--enable-correlation-recovery`, default OFF.
- Gain compressed on the real scoring path: overall delta positive but small.
- Target at-risk cohort was essentially flat, and two outside-cohort regressions appeared.
- Decision: FINAL NO-GO for submission candidacy.

## 2) Three Root Causes Identified

1. Wrong-edge second cause (distinct from identity collision):
- Synthetic candidates can land in genuine gaps correctly, but their extrapolated beacon-derived edge can still be wrong versus the true lineage edge.
- This is a motion-model/extrapolation limitation.
- Merge gate should not and does not solve this, because no nearby real detection exists to suppress against.

2. Target-cohort dilution:
- The mechanism was intended to improve the at-risk cohort identified by diagnostics.
- In real-pipeline scoring, at-risk aggregate gain was approximately flat, while the net positive overall delta came mostly from outside the target group.
- Result: benefit concentration did not align with the original hypothesis target.

3. Outside-cohort regression / trigger over-reach:
- Track-gap triggering still activates in some non-at-risk samples.
- Those activations produced measurable regressions in part of the outside cohort.
- Result: trigger specificity is insufficient for safe promotion.

## 3) What Must Change Before Any Revisit

Any future attempt must satisfy two independent fixes at the same time.

1. Better lineage-edge model for synthetic candidates:
- Not just linear/velocity extrapolated edge attachment.
- Must improve edge correctness when filling genuine gaps.
- Prefer methods that attach synthetic continuity using stronger evidence than pure prediction.

2. Tighter trigger condition:
- Narrower and more precise than the current track-gap heuristic.
- Activation should be constrained to truly at-risk conditions and avoid non-at-risk over-reach.

Without both fixes holding together, this line is expected to repeat the same failure pattern.

## 4) CNN-Advisor Connection (Explicitly Separate Future Branch)

Reasoning captured during this branch:

- A CNN-based detector used as an advisor (not an arbiter) could provide real detected positions in high-background regions.
- That could address wrong-edge behavior by reducing reliance on purely extrapolated synthetic placement/edge linkage.

Scope boundary:

- This is architecturally different from beacon-extrapolated correlation recovery.
- It should be handled as a separate future initiative branch, not as a patch continuation of the current correlation-layer branch.
- Rationale: avoid stacking new diagnostic uncertainty on top of three already-completed NO-GO/qualified-go iterations.

## 5) Final State Confirmation

1. Safety and baseline protection:
- `--enable-correlation-recovery` and related correlation flags remain default OFF in both runners.
- `run.py` kernel defaults and the protected V13 submission path remain untouched.

2. Verification state:
- Full test suite remains green at close-out (70 passed).

3. Branch disposition:
- This branch is either merged as documented experiment history with no production default impact, or archived as a reference branch.
- Final disposition is a project/maintainer decision (Danny), not a code-path decision.

## Close-Out Statement

Correlation-layer track-continuity work delivered real technical learning and isolated a true mechanism-level fix (identity-collision merge gate), but did not meet promotion criteria on the real pipeline path for submission candidacy. The outcome is a documented, high-value NO-GO history retained for future design decisions.