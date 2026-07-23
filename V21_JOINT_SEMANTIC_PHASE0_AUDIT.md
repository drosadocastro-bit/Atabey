# V21 Joint Semantic Phase 0 Fixed-Battery Audit

Status: shadow evidence extraction only; no semantic score, assignment solve, or graph mutation

## Contract

The extractor enumerates continuation, division, termination, and abstention actions around
the registered focal parents. It records raw parent-centered geometry, daughter continuity,
appearance/mass diagnostics, feature availability, and missingness reasons. Every action
abstains. Only each registered correct pair is projected through the patched official scorer;
all other sparse candidates remain unlabeled rather than being treated as negatives.

## Results

- Raw evidence rows: **585** total, including **449** division actions.
- Registered correct pairs representable inside 14 um: **14/14**.
- Registered correct pairs labeled official TP in current ownership context: **7/14**.
- Registered correct pairs labeled official FP in current ownership context: **7/14**.
- Original official V19 TPs preserved: **4/4**.
- Prior Hungarian regression cases representable and still abstaining: **3/3**.
- Source zero perturbation: **14/14**.

| Case | Phase | Route | Actions | Division actions | Correct representable | Official projected label | Zero perturbation |
|---|---|---|---:|---:|---:|---|---:|
| `P2-12DF` | `phase2` | `local_maxima/motion_mutual` | 23 | 15 | True | `official_fp` | True |
| `P2-2A2E` | `phase2` | `cfar_sidelobe/bipartite` | 30 | 21 | True | `official_fp` | True |
| `P2-587A` | `phase2` | `components/greedy` | 12 | 6 | True | `official_fp` | True |
| `P2-D754` | `phase2` | `components/greedy` | 8 | 3 | True | `official_tp` | True |
| `P1-05DB` | `phase1` | `cfar_sidelobe/bipartite` | 30 | 21 | True | `official_tp` | True |
| `P2-207C` | `phase2` | `cfar_sidelobe/bipartite` | 47 | 36 | True | `official_fp` | True |
| `P2-32DB` | `phase2` | `cfar_sidelobe/bipartite` | 57 | 45 | True | `official_fp` | True |
| `P2-4FFD` | `phase2` | `cfar_sidelobe/bipartite` | 17 | 10 | True | `official_fp` | True |
| `P2-55B7` | `phase2` | `components/greedy` | 5 | 1 | True | `official_tp` | True |
| `P2-705E` | `phase2` | `components/greedy` | 23 | 15 | True | `official_tp` | True |
| `P1-B329` | `phase1` | `cfar_sidelobe/bipartite` | 80 | 66 | True | `official_tp` | True |
| `P1-EBDF-EARLY` | `phase1` | `cfar_sidelobe/bipartite` | 80 | 66 | True | `official_tp` | True |
| `P1-EBDF-LATE` | `phase1` | `cfar_sidelobe/bipartite` | 93 | 78 | True | `official_tp` | True |
| `P2-F8FF` | `phase2` | `cfar_sidelobe/bipartite` | 80 | 66 | True | `official_fp` | True |

## Boundary

A registered sparse pair and an official TP are not interchangeable labels. The projected
official result includes current local ownership and topology, so an `official_fp` here
does not prove that the biological pair is false. It proves that forming that fork alone
does not satisfy the patched competition metric in the current graph context.

This audit does not fit a model and cannot establish calibrated confidence. An official FP
label is not inferred from absence in sparse GT. Assignment remains disabled until semantic
evidence passes its own registered gate.
