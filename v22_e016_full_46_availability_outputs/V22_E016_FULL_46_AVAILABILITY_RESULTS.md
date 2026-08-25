# V22 U-Net Official-Action Availability Results

Decision: **GO_FOR_SEMANTIC_SCORE_DEVELOPMENT**

## Primary Results

- Official-positive divisions: **40/46**.
- Positive controls preserved: **12/13**.
- Newly available from the unavailable stratum: **20/25**.
- Official-positive families: **44b6, 6bba**.
- Source zero perturbation: **True**.
- Formed division actions: **211,328** total; median **1558**, p90 **20194**, maximum **24,351** per event.
- Registered geometric actions confirmed by the patched scorer: **55/55**.

## Gate Outcomes

- `complete`: **PASS**
- `official_positive_count`: **PASS**
- `positive_controls`: **PASS**
- `families`: **PASS**
- `zero_perturbation`: **PASS**
- `shadow_only`: **PASS**

## Cases

| Case | Route | Anchored parents | Division actions | GT-matched actions | Official TP actions | Available |
|---|---|---:|---:|---:|---:|---:|
| `DEV-44b6_5f15d135-t36-p125000000011` | `local_maxima/motion_mutual` | 427 | 11317 | 6 | 6 | True |
| `DEV-44b6_706092f0-t49-p446000000015` | `cfar_sidelobe/bipartite` | 572 | 19123 | 0 | 0 | False |
| `DEV-44b6_74d0c52e-t58-p296000000021` | `cfar_sidelobe/bipartite` | 271 | 5538 | 0 | 0 | False |
| `DEV-44b6_aaf8b0ea-t61-p390000000000` | `cfar_sidelobe/bipartite` | 231 | 4431 | 0 | 0 | False |
| `DEV-44b6_c50204e0-t28-p171000000043` | `cfar_sidelobe/bipartite` | 506 | 14033 | 1 | 1 | True |
| `DEV-44b6_c50204e0-t65-p208000000033` | `cfar_sidelobe/bipartite` | 682 | 21678 | 1 | 1 | True |
| `DEV-6bba_2312ac41-t10-p11000190` | `components/greedy` | 202 | 2033 | 1 | 1 | True |
| `DEV-6bba_2312ac41-t19-p20000316` | `components/greedy` | 174 | 1719 | 1 | 1 | True |
| `DEV-6bba_2819ca14-t61-p62000719` | `components/greedy` | 59 | 168 | 2 | 2 | True |
| `DEV-6bba_3abfe10a-t81-p82001296` | `cfar_sidelobe/bipartite` | 629 | 21392 | 1 | 1 | True |
| `DEV-6bba_3c5691b6-t22-p23000172` | `components/greedy` | 59 | 85 | 1 | 1 | True |
| `DEV-6bba_3c5691b6-t6-p7000054` | `components/greedy` | 55 | 75 | 2 | 2 | True |
| `DEV-6bba_3fda6b25-t28-p29000542` | `components/greedy` | 90 | 350 | 1 | 1 | True |
| `DEV-6bba_57b7cc1e-t12-p13000378` | `cfar_sidelobe/bipartite` | 850 | 24351 | 4 | 4 | True |
| `DEV-6bba_57b7cc1e-t23-p24000720` | `cfar_sidelobe/bipartite` | 843 | 24074 | 0 | 0 | False |
| `DEV-6bba_57b7cc1e-t77-p78002270` | `cfar_sidelobe/bipartite` | 756 | 21266 | 1 | 1 | True |
| `DEV-6bba_5c039895-t10-p11000170` | `components/greedy` | 131 | 805 | 1 | 1 | True |
| `DEV-6bba_5c039895-t52-p53000762` | `components/greedy` | 95 | 473 | 1 | 1 | True |
| `DEV-6bba_5c039895-t58-p59000855` | `components/greedy` | 96 | 424 | 1 | 1 | True |
| `DEV-6bba_5c824876-t2-p3000057` | `components/greedy` | 182 | 2334 | 1 | 1 | True |
| `DEV-6bba_6321a359-t8-p9000094` | `components/greedy` | 38 | 39 | 1 | 1 | True |
| `DEV-6bba_67ebd073-t86-p87000772` | `components/greedy` | 60 | 154 | 1 | 1 | True |
| `DEV-6bba_7d3058ae-t32-p33000475` | `components/greedy` | 64 | 137 | 2 | 2 | True |
| `DEV-6bba_7d3058ae-t83-p84001401` | `components/greedy` | 82 | 241 | 1 | 1 | True |
| `DEV-6bba_87289e13-t77-p78001026` | `components/greedy` | 56 | 80 | 1 | 1 | True |
| `DEV-6bba_8b7818bf-t3-p4000023` | `components/greedy` | 47 | 67 | 1 | 1 | True |
| `DEV-6bba_8b7818bf-t33-p34000238` | `components/greedy` | 61 | 134 | 1 | 1 | True |
| `DEV-6bba_907271db-t96-p97001173` | `components/greedy` | 50 | 48 | 1 | 1 | True |
| `DEV-6bba_9e23430b-t89-p90001032` | `components/greedy` | 88 | 967 | 1 | 1 | True |
| `DEV-6bba_cdcfe533-t28-p29000464` | `components/greedy` | 252 | 2749 | 1 | 1 | True |
| `DEV-6bba_cdcfe533-t48-p49000935` | `components/greedy` | 270 | 3343 | 1 | 1 | True |
| `DEV-6bba_cdcfe533-t52-p53001039` | `components/greedy` | 266 | 3618 | 1 | 1 | True |
| `DEV-6bba_cdcfe533-t86-p87002049` | `components/greedy` | 279 | 4403 | 1 | 1 | True |
| `DEV-6bba_d2b9fc0c-t72-p73000666` | `components/greedy` | 214 | 3196 | 1 | 1 | True |
| `DEV-6bba_d2b9fc0c-t78-p79000759` | `components/greedy` | 210 | 3226 | 2 | 2 | True |
| `DEV-6bba_d3da753b-t63-p64000722` | `components/greedy` | 112 | 724 | 1 | 1 | True |
| `DEV-6bba_debd7bfa-t12-p13000353` | `components/greedy` | 197 | 2135 | 1 | 1 | True |
| `DEV-6bba_debd7bfa-t26-p27000673` | `components/greedy` | 171 | 1696 | 2 | 2 | True |
| `DEV-6bba_debd7bfa-t36-p37000853` | `components/greedy` | 152 | 1421 | 1 | 1 | True |
| `DEV-6bba_debd7bfa-t37-p38000863` | `components/greedy` | 145 | 1347 | 1 | 1 | True |
| `DEV-6bba_ef7b4f7e-t14-p15000245` | `components/greedy` | 53 | 73 | 0 | 0 | False |
| `DEV-6bba_ef7b4f7e-t89-p90001375` | `components/greedy` | 60 | 198 | 2 | 2 | True |
| `DEV-6bba_fc5f39dc-t24-p25000064` | `cfar_sidelobe/bipartite` | 121 | 1247 | 2 | 2 | True |
| `DEV-6bba_fc5f39dc-t54-p55000245` | `cfar_sidelobe/bipartite` | 201 | 2679 | 1 | 1 | True |
| `DEV-6bba_fe670320-t0-p1000014` | `components/greedy` | 0 | 0 | 0 | 0 | False |
| `DEV-6bba_fe670320-t66-p67000712` | `components/greedy` | 152 | 1737 | 1 | 1 | True |

## Unavailable Cases

| Case | Cohort | Baseline status | Formed actions | Registered matches |
|---|---|---|---:|---:|
| `DEV-44b6_706092f0-t49-p446000000015` | `baseline_unavailable` | `no_parent_detection_within_7um` | 19123 | 0 |
| `DEV-44b6_74d0c52e-t58-p296000000021` | `baseline_unavailable` | `fewer_than_two_daughter_lineages_within_7um` | 5538 | 0 |
| `DEV-44b6_aaf8b0ea-t61-p390000000000` | `baseline_unavailable` | `no_pair_inside_14um_formation_radius` | 4431 | 0 |
| `DEV-6bba_57b7cc1e-t23-p24000720` | `baseline_unavailable` | `no_parent_detection_within_7um` | 24074 | 0 |
| `DEV-6bba_ef7b4f7e-t14-p15000245` | `baseline_unavailable` | `no_parent_detection_within_7um` | 73 | 0 |
| `DEV-6bba_fe670320-t0-p1000014` | `positive_control` | `official_positive` | 0 | 0 |

The lost positive control at `t=0` has no prior frame and therefore no V19 `t-1`
anchor under this pre-registered formation rule. It is a structural anchor limitation,
not a detector-threshold failure.

## Interpretation Boundary

This audit measures whether an officially recognizable fork exists in the formed action set.
It does not select an action, estimate precision, fit confidence, solve ownership, or mutate
a tracking graph. Raw action counts are not official false positives.
