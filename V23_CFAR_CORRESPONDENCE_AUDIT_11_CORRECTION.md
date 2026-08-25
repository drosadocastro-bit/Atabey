# V23 CFAR Correspondence Audit: 11-Event Correction

## Correction

The initial correspondence audit reported one official geometric candidate across the 11 CFAR events. That count was wrong.

The audit selected the candidate pair with the smallest daughter residual, then tested whether that pair's parent and daughters were all within 7 um. It did not check whether another pair in the same event satisfied all three bounds. This produced three false-negative event classifications.

The independent detector-stage pre/post sidelobe audit evaluates every distinct parent/daughter combination. It found four official geometric candidates both before and after sidelobe suppression:

- `44b6_c50204e0` at t28;
- `44b6_c50204e0` at t65;
- `6bba_57b7cc1e` at t12;
- `6bba_fc5f39dc` at t54.

Corrected geometric availability is therefore **4/11**, not **1/11**.

The correspondence script has been corrected to test all candidate pairs. The original generated report remains preserved as historical evidence and must be read together with this correction.

## Sidelobe Finding

Sidelobe suppression preserved all four official geometric candidates and removed zero registered roles from the 7 um radius. It reduced peak counts but did not cause an official geometric loss in this 11-event development subset.

## Guardrail

This correction concerns geometric candidate availability only. It does not establish an official Division Jaccard true positive, does not authorize graph mutation, and does not change the frozen CFAR configuration.
