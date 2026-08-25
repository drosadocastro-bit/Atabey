# V23 Range-Gated Echo Shadow Preregistration

Status: **development-only, read-only shadow**.

## Fixed components

- Frozen V19/CFAR graph supplies all router seeds and primary detections.
- Echo profile is fixed at global floor `0.35`, adaptive multiplier `0.80`, and local-maximum footprint `(1,3,3)`.
- Router radius is fixed at `14 um`.
- Echo peaks within `3 um` of an existing primary detection are treated as duplicates.

## Inference-only routing

The parent-frame echo channel opens only around velocity-predicted broken endpoints from `t-1`. The daughter-frame channel opens around under-resolved parents at `t`, their motion predictions, and the broken-endpoint predictions. GT coordinates never activate a window; they are used only afterward to measure registered 7 um / 14 um fork availability.

## Population and measurements

Run the fixed 11-event CFAR battery: seven failures and four production controls. Report:

- recovered fork geometry;
- new echo candidates admitted per event-frame;
- fraction of the full echo pool retained;
- approximate fraction of frame volume covered by the union of router windows;
- family and cohort breakdown;
- zero perturbation.

## Decision contract

- `NO_GO`: no failed events recover.
- `NO_GO_ROUTER_TOO_BROAD`: median router retention is at least 75% of the full echo pool.
- `HOLD_PARTIAL_RANGE_GATED_SIGNAL`: recovery exists and median retention is below 75%, but no production mutation is authorized.

A HOLD permits a later semantic/ownership filter over the admitted local candidates. It does not permit candidate emission, edge creation, or a full-cohort run.
