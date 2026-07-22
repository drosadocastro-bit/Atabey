# Atabey Sun Check Bounded Audit

Status: read-only, 12-sample diagnostic; no image correction, detector tuning, or graph mutation

## Measurement Boundary

This audit adapts the WSR-88D external-reference idea to retrospective single-channel
fluorescence data. Because the competition volumes contain no bead field or instrument telemetry,
background, bulk shift, and compact-object width are explicitly treated as self-consistency
proxies. They are not absolute PSF, stage-drift, gain, or biological measurements.

Five anchor frames and their immediate successors are read from each sample. Track A, Track B,
the frozen 9 um formation gate, and all image voxels remain unchanged.

Scientific basis: NOAA solar scans use a known external source to measure antenna pointing,
beamwidth, and gain; fluorescence-microscopy QC uses sub-resolution beads to measure PSF geometry.
This dataset has neither reference, so the present measurements deliberately stop at shadow QC.

References:

- NOAA WSR-88D solar calibration: https://www.weather.gov/media/roc/Papers/PolarmetcirWXRadar_Cal_Using_SolarScans_AMTA2014_final.pdf
- Confocal PSF bead protocol: https://www.nature.com/articles/nprot.2011.407
- Fluorescence microscopy reproducibility guidance: https://www.nature.com/articles/s41592-021-01156-w
- Biohub Zebrahub light-sheet acquisition context: https://biohub.org/blog/zebrahub-tracks-zebrafish-development/

## Panel Results

| Sample | Role | Route | Background | SNR proxy | Drift um | Z spread | XY spread | q90 end/start |
|---|---|---|---:|---:|---:|---:|---:|---:|
| `44b6_0113de3b` | components control, high EdgeRecall | `components/greedy` | 94.000 | 7.011 | 0.935 | 0.485 | 1.088 | 1.031 |
| `44b6_24264f12` | components control, high EdgeRecall | `components/greedy` | 120.000 | 9.548 | 1.282 | 0.775 | 1.117 | 1.338 |
| `44b6_d754aa59` | components control, known Phase 2 division window | `components/greedy` | 36.000 | 11.691 | 4.086 | 0.194 | 1.414 | 1.577 |
| `44b6_12dfb391` | local-maxima non-CFAR, known Phase 2 division window | `local_maxima/motion_mutual_latent` | 367.000 | 4.397 | 0.306 | 0.931 | 0.385 | 1.727 |
| `44b6_0c582fdc` | atypical 44b6 CFAR route, strong V20 EdgeRecall gain | `cfar_sidelobe` | 257.000 | 9.630 | 1.215 | 0.350 | 2.307 | 0.788 |
| `44b6_2a2eff9f` | 44b6 CFAR route, V20 below V13 | `cfar_sidelobe` | 306.000 | 2.571 | 0.396 | 0.099 | 1.070 | 1.308 |
| `6bba_05db0fb1` | official V19 division TP | `cfar_sidelobe` | 603.000 | 3.169 | 1.590 | 0.628 | 0.669 | 1.020 |
| `6bba_32db13fc` | official V19 division TP | `cfar_sidelobe` | 139.000 | 7.937 | 0.857 | 1.426 | 1.599 | 0.534 |
| `6bba_b329af44` | official V19 division TP | `cfar_sidelobe` | 630.000 | 3.229 | 0.593 | 0.638 | 0.825 | 0.793 |
| `6bba_ebdf3b34` | official V19 division TP plus known FN | `cfar_sidelobe` | 257.000 | 2.949 | 0.953 | 0.815 | 0.952 | 1.005 |
| `6bba_ebff6e76` | prior high-residual division-noise case | `cfar_sidelobe` | 440.000 | 3.032 | 0.421 | 0.518 | 0.381 | 0.553 |
| `6bba_55b7eebe` | 6bba components/non-CFAR control | `components/greedy` | 61.000 | 12.693 | 0.549 | 1.112 | 1.477 | 0.914 |

## Cohort Summary

- `44b6` (n=6): background median=188.500, SNR proxy median=8.279, drift median=1.075 um, q90 end/start mean=1.295.
- `6bba` (n=6): background median=348.500, SNR proxy median=3.199, drift median=0.725 um, q90 end/start mean=0.803.

## Route Summary

- `cfar_sidelobe` (n=7): background median=306.000, SNR proxy median=3.169, drift median=0.857 um, q90 end/start mean=0.857.
- `components/greedy` (n=4): background median=77.500, SNR proxy median=10.619, drift median=1.109 um, q90 end/start mean=1.215.
- `local_maxima/motion_mutual_latent` (n=1): background median=367.000, SNR proxy median=4.397, drift median=0.306 um, q90 end/start mean=1.727.

## Main Findings

- Current image-only routing agrees with the historical V20 detector class for **12/12** samples.
- The CFAR group has higher background and lower SNR proxy than the components controls;
  this is coherent with the existing adaptive route but is not yet an independent predictor.
- Compact-object sigma ranges are narrow: Z `1.787-2.124` um, Y `1.034-1.179` um, and X `1.002-1.179` um. No large footprint outlier is visible.
- No sampled frame contains saturated uint16 voxels.
- Bulk-shift estimates are self-registration proxies and remain biologically confounded;
  they do not authorize stage-drift correction.

## Exploratory EdgeRecall Correlations

Spearman correlations use the reconstructed cohort's EdgeRecall delta (V20 minus V13).
With n=12, these are hypothesis-generating effect sizes, not validation or causal evidence.
The legacy division-FP field is retained in CSV only for provenance and must not be interpreted
after the official metric correction.

| Proxy | n | rho | p-value |
|---|---:|---:|---:|
| `q90_end_to_start_ratio` | 12 | -0.732 | 0.007 |
| `median_background` | 12 | 0.407 | 0.189 |
| `background_temporal_spread` | 12 | 0.341 | 0.278 |
| `median_drift_um` | 12 | 0.254 | 0.426 |
| `median_z_profile_spread` | 12 | 0.102 | 0.754 |
| `median_snr_proxy` | 12 | -0.073 | 0.823 |
| `median_xy_shading_spread` | 12 | -0.036 | 0.911 |
| `p90_drift_um` | 12 | 0.015 | 0.964 |

### CFAR-only sensitivity check

Restricting the same analysis to the seven CFAR-routed samples checks whether an apparent
relationship is driven by route composition rather than within-route behavior.

| Proxy | n | rho | p-value |
|---|---:|---:|---:|
| `median_snr_proxy` | 7 | 0.571 | 0.180 |
| `median_drift_um` | 7 | 0.536 | 0.215 |
| `q90_end_to_start_ratio` | 7 | -0.536 | 0.215 |
| `median_background` | 7 | -0.180 | 0.699 |
| `p90_drift_um` | 7 | 0.143 | 0.760 |
| `median_z_profile_spread` | 7 | -0.107 | 0.819 |
| `background_temporal_spread` | 7 | -0.071 | 0.879 |
| `median_xy_shading_spread` | 7 | 0.000 | 1.000 |

## Decision

**GO as a sample-state QC and routing research direction. NO-GO for image correction, drift
compensation, or threshold adaptation.** The route separation is coherent and the temporal
intensity range is large enough to justify an independent stratified shadow audit. However,
the strongest full-panel EdgeRecall association weakens inside the CFAR subset, demonstrating
route confounding. A follow-up must pre-register independent samples within each route and must
show value beyond the existing foreground-density profile before any production use.
