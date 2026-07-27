# V22 E016 Candidate-Formation Audit

Date: 2026-07-27
Scope: six E016 cases without a patched-official positive action
Status: read-only diagnostic; no thresholds, graph mutation, or assignment

## Result

The six misses are not one failure mode. The detector action table was
exhaustively regenerated from the frozen E016 peaks, so an event with zero
official TP actions means the correct official fork was not represented by the
formed action set.

| Case | Route | Formation evidence | Diagnosis |
| --- | --- | --- | --- |
| `44b6_706092f0:t49` | CFAR/bipartite | 19,123 actions; one parent candidate, no GT daughter candidates within 7 um | Genuine daughter-formation loss after a parent was found |
| `44b6_74d0c52e:t58` | CFAR/bipartite | 5,538 actions; no GT parent candidate, only one daughter role candidate | Genuine parent-formation loss |
| `44b6_aaf8b0ea:t61` | CFAR/bipartite | 4,431 actions; one parent and one candidate in each daughter role, but no distinct pair inside the 14 um formation radius | Genuine pair-formation loss |
| `6bba_57b7cc1e:t23` | CFAR/bipartite | 24,074 actions; two parent candidates, zero candidates for one GT daughter role | Genuine daughter-formation loss despite parent alternatives |
| `6bba_ef7b4f7e:t14` | components/greedy | 73 actions; detector reports a complete geometric triplet, but zero official TP actions and four scored FP actions | Triplet exists, but the correct official fork was not formed; this is pairing/identity failure, not simple availability |
| `6bba_fe670320:t0` | components/greedy | zero anchors and zero actions | Structural first-frame anchor limitation; not a detector threshold failure |

## Evidence Boundary

The E016 detector shadow reported `complete_triplet=True` for the later
`6bba_ef7b4f7e:t89` event, but that event is not one of the six misses in this
audit because it has an official positive action in the regenerated action set.
The `t14` case is different: a geometric triplet was available, but the
patched official scorer found no true fork among the enumerated actions.

The action counts are candidate-pool sizes, not false-positive counts. Most
actions remain unevaluated or unsupported under the patched metric and must not
be interpreted as negative evidence.

## Decision

Candidate formation remains a real upstream target, but it is not sufficient
for all six cases. The next feature-source experiment should therefore preserve
the full 14 um action set and export detector-native evidence for every parent
and daughter peak. It must distinguish:

1. missing role detection;
2. wrong daughter identity among available peaks;
3. first-frame anchor absence; and
4. correct action present but poorly ranked.

No formation-radius change is authorized by this audit alone.
