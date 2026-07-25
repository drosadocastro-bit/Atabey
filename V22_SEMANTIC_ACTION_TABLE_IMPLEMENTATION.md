# V22 Semantic Action Table Implementation

Status: **BOUNDED IMPLEMENTATION VERIFIED; FULL 27-SAMPLE DEVELOPMENT BUILD NOT YET RUN**

## Purpose

This is the evidence-construction layer for the pre-registered V22 joint semantic
assignment experiment. It converts every frozen U-Net division action into a
fold-tagged, deterministic feature row while preserving the patched official
metric's three-state label boundary:

- `official_tp`: eligible supervised positive;
- `official_fp`: eligible supervised negative;
- `official_unsupported` or `not_evaluated`: excluded from supervised loss.

Sparse absence is never converted into a negative. This stage does not fit a
semantic model, run assignment, select graph edges, or mutate a graph.

## Implemented Surface

- `src/atabey/tracking/unet_semantic_features.py` builds parent-centered geometry,
  confidence, density, ownership-margin, and explicit missing-feature fields.
- `src/atabey/tracking/unet_semantic_dataset.py` implements deterministic,
  score-independent conflict and background sampling.
- `scripts/build_v22_semantic_action_table.py` verifies every pinned source hash,
  rebuilds the V19 source graph, enumerates all frozen actions, applies the patched
  official scorer only to the pre-registered label sample, and writes one atomic
  compressed shard plus one summary per sample.
- `src/atabey/tracking/unet_action_availability.py` now exposes the official
  `TP` / `FP` / `unsupported` label for an isolated candidate fork.

Every action row records its sample-blocked fold, event, route, selection reason,
label state, feature availability, source provenance, and disabled scoring,
assignment, and mutation fields. Resume accepts a checkpoint only when its shard,
contract, and peak-file hashes still match. The builder also asserts every
regenerated event against the pinned 268,822-action and 64-positive inventory.

## Bounded Verification

Focused tests: **12 passed** across official fork labels, deterministic action
features, deterministic sampling, and the frozen 39-positive fold inventory.

The two-family smoke covered one `44b6` sample and one `6bba` sample:

- 666 actions written;
- 4 `official_tp`;
- 27 `official_fp`;
- 133 `official_unsupported`;
- 502 `not_evaluated`;
- source zero perturbation: `true`;
- scoring, assignment, and graph mutation: `false`.

A fresh hardened rerun on `6bba_6321a359` produced 38 actions with 2 TP, 8 FP,
27 unsupported, and 1 not evaluated. A second invocation resumed from the
hash-verified checkpoint without rebuilding.

These are pipeline checks, not model-quality results. No retrieval, calibration,
or constrained-assignment claim is supported yet.

## Full Development Build

Run only the frozen 27-sample development split:

```powershell
python -u scripts/build_v22_semantic_action_table.py --resume
```

This is the verified command. Shards are written to `v22_semantic_action_shards/` and are
ignored by git. The compact aggregate summary is written to
`v22_semantic_action_table_summary.json`.

## Remaining Boundary

The separate weak continuation-reference head is not implemented in this pass.
The exported U-Net peaks cover registered event frames, while the pre-registration
excludes continuation references within two frames of a registered division.
A continuation extractor must therefore use independent V19 trajectories and
must document that domain boundary before those weak references can train a head.
It must not infer continuation negatives from sparse GT or reuse held-out fold
information.

The full 199-sample scope remains locked. The next valid step is the resumable
27-sample evidence build, followed by an inventory of official TP, FP,
unsupported, and not-evaluated rows by fold before any model fitting.