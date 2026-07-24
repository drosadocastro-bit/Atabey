# V22 Public Safe-Division Shadow Audit

Status: development-only read-only shadow; no threshold tuning or production mutation

## Frozen Rule

The shadow faithfully evaluates the public 0.902 notebook's post-link second-child rule:
one existing child, one unowned next-frame candidate, parent-candidate <= 4.66 um,
existing parent-child <= 7.65 um, sister separation <= 8.5 um, score equal to parent
distance plus 0.15 times sister distance, frame cap 0.0076, and global cap 0.00375.

## Coverage

- Completed samples: **27/27**.
- Known GT divisions: **46/46**.
- Raw eligible proposals: **17781**.
- Budget-selected second-child edges: **1089**.
- Source zero perturbation: **True**.

## Official Graph Impact

| Metric | Baseline | Shadow |
|---|---:|---:|
| Adjusted edge Jaccard | 0.350810015 | 0.350777724 |
| Division Jaccard | 0.000000000 | 0.000000000 |
| Division TP | 0 | 0 |
| Division FP | 403 | 424 |
| Division FN | 46 | 46 |

Adjusted-edge per-sample breakdown: improved 3, flat 14, regressed 10, not comparable 0.

Division per-sample breakdown: improved 0, flat 27, regressed 0, not comparable 0.

## Route Breakdown

| Route | Samples | Proposals | Selected | Division FP baseline | Division FP shadow | Edge I/F/R |
|---|---:|---:|---:|---:|---:|---:|
| `cfar_sidelobe/bipartite` | 7 | 3362 | 718 | 403 | 409 | 2/3/2 |
| `components/greedy` | 19 | 11581 | 328 | 0 | 15 | 1/10/8 |
| `local_maxima/motion_mutual` | 1 | 2838 | 43 | 0 | 0 | 0/1/0 |

Route counts are descriptive, not causal. `Edge I/F/R` means improved/flat/regressed.

## Structural Fidelity

The exact public rule selected more than one added child for **1** parent(s).
It enforces unique candidate ownership but does not cap each source parent at one added child.
The patched host consequently warned when a projected parent exceeded two total children and
retained only two outgoing edges for evaluation. This behavior was preserved rather than fixed
after outcomes were opened.

## Availability Contract

- Baseline official-positive availability reproduced: **13/13**.
- Baseline projected-invalid category reproduced: **8/8**.
- Previously available positives preserved: **13/13**.
- Projected-invalid divisions recovered: **0/8**.
- New actual official TPs: **0**.
- Lost actual official TPs: **0**.

## Decision

**NO-GO under the frozen rule:** at least one preregistered efficacy or safety gate failed.

The calibration split and locked independent validation cohort were not opened. Raw
proposal counts are geometric eligibility counts, not official FPs or biological labels.
The shadow does not address GT divisions whose parent or daughter detections are absent.
