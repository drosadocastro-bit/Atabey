# ADR-003: Physical Voxel Distance Normalization

## Status

Accepted.

## Decision

All motion and linking distances should be computed in physical microns, not raw voxel
coordinates.

## Rationale

The seed TODO identifies anisotropic voxel sizes:

```text
z = 1.625 um / voxel
y = 0.40625 um / voxel
x = 0.40625 um / voxel
```

Nearest-neighbor tracking over raw voxel units would overstate lateral motion relative
to axial motion.

## Consequences

- Detections store both voxel and physical coordinates.
- Trackers consume physical coordinates.
- Any future state or division score must document whether it uses voxel or physical units.
