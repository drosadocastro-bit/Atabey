# V23 Split Echo Paths Preregistration

Status: **development-only, read-only shadow diagnostic**.

## Purpose

Separate two upstream failure mechanisms that the pooled pair qualifier treated
as one problem:

1. **Parent-present / anchored completion:** a detected parent already owns one
   linked child. Preserve that edge and rank only one distinct echo candidate as
   the possible second daughter.
2. **Parent-missing / broken-track quarantine:** no detected parent is available
   at the division frame. Parent recovery and daughter completion remain a
   separate diagnostic and cannot contribute to the anchored-path decision.

This experiment does not emit detections, add edges, or mutate a graph.

## Frozen Population and Inputs

- The four events recovered by the frozen `K=1` proposal audit.
- V19/CFAR graph and low-confidence echo profile:
  `floor=0.35`, `k=0.80`, footprint `(1,3,3)`.
- Formation radius `14 um`, official registration radius `7 um`, and primary
  deduplication radius `3 um`.
- Existing graph edges determine whether a path is anchored or broken.

Ground truth is used only after proposal construction to locate the first
registered-valid hypothesis. It does not create a parent, child, echo, or score.

## Anchored Completion Path

Eligible seeds are detected frame-`t` parents with exactly one existing edge to
frame `t+1`. That child is immutable. The only proposed object is a distinct
low-confidence echo in frame `t+1` within `14 um` of the parent.

The fixed counterpart score reuses the preregistered pair evidence:

`score = 0.45 * midpoint_closeness`
`      + 0.25 * radial_balance`
`      + 0.15 * separation_support`
`      + 0.15 * echo_evidence`

- midpoint closeness compares the midpoint of the retained child and echo with
  the parent's motion prediction;
- radial balance compares both parent-to-daughter distances;
- separation support rejects only near-duplicate daughters and saturates at
  `3 um`;
- echo evidence is the clipped CFAR-margin evidence of the proposed counterpart.

No primary child may be replaced. No pair of two new echoes is allowed.

## Broken-Parent Quarantine

Broken endpoints at frame `t-1` may still be measured using the existing `K=1`
virtual-parent path, but their ranks are copied into a separate quarantine
section. They are not compared with anchored seeds and cannot change the
anchored decision. Any future release from quarantine requires its own contract
covering parent identity, temporal persistence, and compounded uncertainty.

## Echolocation Interpretation

The analogy is operationally bounded:

- track prediction is the directed query or beam;
- spatial residual is range delay;
- CFAR margin is return strength;
- persistence across adjacent frames is repeated-return consistency;
- competing ownership is multipath ambiguity.

Microscopy remains passive imaging. This language describes a track-conditioned
search and confidence model, not a new physical measurement.

## Measurements and Decision

For each anchored event report:

- rank of the registered-valid parent seed among all anchored seeds;
- rank of the registered-valid echo inside that seed;
- rank of the complete parent/retained-child/echo proposal globally;
- proposal population and zero perturbation.

Decision for the anchored path only:

- `GO_TO_ANCHORED_ASSIGNMENT_SHADOW`: all 3 known anchored events have parent
  rank at most 25 and counterpart rank at most 10, with both families covered.
- `HOLD_ANCHORED_PATH`: 2 of 3 satisfy both bounds.
- `NO_GO_ANCHORED_PATH`: fewer than 2 of 3 satisfy both bounds.

The parent-missing path always reports `QUARANTINED`; it has no GO threshold in
this experiment. No outcome authorizes graph mutation or a full-cohort run.
