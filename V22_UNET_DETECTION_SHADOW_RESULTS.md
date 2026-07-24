# V22 Temporal U-Net Detection-Availability Shadow Results

Date: 2026-07-24
Decision: **GO_TO_LARGER_SHADOW**

## Frozen Contract

The bounded screen used the public temporal 3D U-Net with:

- checkpoint SHA-256
  `12f6881ee3620a831697ca098ff8f48e687a24225f4e048b538deec3562fe771`;
- threshold `0.970`;
- 3.0 um peak suppression;
- eight-view XY D4 TTA;
- public two-frame temporal context;
- raw microscopy only.

No edge inference or graph mutation occurred.

## Results

- Target complete triplets: **6/9**; the gate required at least 3/9.
- `44b6` target recovery: **3/6**.
- `6bba` target recovery: **3/3**.
- Positive controls preserved: **3/3**.
- Recovered families: **44b6 and 6bba**.
- Graph mutation: **False**.
- Edge inference: **False**.

| baseline failure class | complete triplets |
|---|---:|
| no parent detection within 7 um | 2/3 |
| fewer than two daughter lineages within 7 um | 2/2 |
| no pair inside 14 um formation radius | 1/2 |
| projected actions not official TP | 1/2 |

## Residual Failures

Three target events remained incomplete:

- `44b6_706092f0:t49`: each daughter had a nearby candidate, but both roles
  resolved to the same peak, so no distinct daughter pair existed.
- `44b6_aaf8b0ea:t61`: the same merged-daughter ambiguity remained.
- `44b6_c50204e0:t28`: one daughter had no U-Net peak inside 7 um.

Every target event had at least one parent candidate after U-Net inference. The
residual failure mode therefore shifted from parent absence toward daughter
separation/availability.

## Candidate-Load Warning

The U-Net emitted substantially different frame loads across the bounded panel:

- `44b6` target frames averaged roughly 332 peaks per frame;
- `6bba` target frames averaged roughly 160 peaks per frame;
- individual `44b6` frames reached 579 peaks.

These counts are not automatically false positives, but they require a frozen V19
frame-count denominator before any integration decision.

## Interpretation

The result supports the upstream learned-detector hypothesis: the frozen U-Net
recovers complete role availability well above the pre-registered minimum without
disturbing existing controls.

It does not establish six official division TPs. A complete triplet means only that
one parent peak and two distinct daughter peaks are available within the official
spatial radius. Tracking, semantic division scoring, and official topology remain
separate unresolved stages.

The authorized next step is the pre-registered 46-division development shadow in
`V22_UNET_DEVELOPMENT_46_PREREGISTRATION.md`.
