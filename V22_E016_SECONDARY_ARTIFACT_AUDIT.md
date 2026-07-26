# V22 E016 Secondary Artifact Audit

Date: 2026-07-25\r\nStatus: **HOLD for development-shadow validation**

## Scope

This is a provenance and loadability audit only. No inference, graph mutation,
assignment, threshold tuning, or full-cohort run was performed.

The candidate artifact is the public [Biohub E016 dual-seed notebook](https://www.kaggle.com/code/buaaauto/biohub-e016-embryo-aware-dual-seed)
secondary model package `pilkwang/biohub-temporal-unet3d-seed314159-v1`.

## Checks passed

- Downloaded only the manifest, inference source, model config, training
  metadata, and `edge_predictor_best.pth` into `D:\Atabey-artifacts`, outside
  the repository and Git history.
- Checkpoint size: `8,363,159` bytes.
- Checkpoint SHA256:
  `9bac2fa0dadc4a6fc1899e0caf187f4b553e0a7cd90ba1261a68b35ffe9e305f`.
- The hash matches both the public `ARTIFACT_MANIFEST.json` and the E016
  notebook's published artifact record.
- Offline PyTorch load succeeded as a 136-entry state dictionary.
- Architecture/configuration matches the published TemporalUNet3D + node
  transformer description: layers `[32, 64, 128]`, downsample `[1, 4, 4]`,
  window size `2`, and `5.0` micrometer pooling kernel.
- Coordinate contract is explicit: `z, y, x` in original voxels, with
  scale `z=1.625` and `x=y=0.40625` micrometers per voxel.

## Blocking provenance finding

The artifact manifest identifies the training method as
`unet_transformer_alltrain_seed314159_v1` and reports:

- `train_datasets: 199`
- `validation_datasets: 40`
- seed `314159`
- split-0 training metadata

Our E016 development audit contains 46 labeled division events from 27 samples
drawn from that same 199-sample competition cohort. Therefore this checkpoint
cannot be used as an unbiased detector-shadow model for those events. The file
is authentic and loadable, but the training provenance violates the
preregistered requirement that development labels are not used to fit or select
the secondary artifact.

The public notebook's disjoint confirmation score is useful as external context,
but it does not remove this local label-overlap risk for the Atabey development
audit. No recovery claim is made from it here.

## Decision

**HOLD_ARTIFACT_TRAINED_ON_EVALUATION_COHORT**.

The E016 dual-seed shadow remains closed: `inference_enabled=false`,
`pairing_shadow_enabled=false`, `assignment_enabled=false`, and
`graph_mutation_enabled=false`. The next valid artifact must provide either:

1. a checkpoint trained without the 27 development samples and without their
   labels influencing model selection; or
2. a separately held-out labeled evaluation set that is disjoint from the
   artifact's 199-sample training cohort.

The audit helper is `scripts/audit_v22_e016_secondary_artifact.py`. It records
hashes, architecture metadata, offline loadability, and the cohort-overlap
decision without running inference.
