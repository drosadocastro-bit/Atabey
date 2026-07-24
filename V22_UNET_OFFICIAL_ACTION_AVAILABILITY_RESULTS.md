# V22 U-Net Official-Action Availability Results

Decision: **GO_FOR_SEMANTIC_SCORE_DEVELOPMENT**

## Primary Results

- Official-positive divisions: **39/46**.
- Positive controls preserved: **12/13**.
- Newly available from the unavailable stratum: **21/25**.
- Official-positive families: **44b6, 6bba**.
- Source zero perturbation: **True**.
- Formed division actions: **268,822** total; median **1569**, p90 **21146**, maximum **48,686** per event.
- Registered geometric actions confirmed by the patched scorer: **64/64**.

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
| `DEV-44b6_5f15d135-t36-p125000000011` | `local_maxima/motion_mutual` | 271 | 6618 | 4 | 4 | True |
| `DEV-44b6_706092f0-t49-p446000000015` | `cfar_sidelobe/bipartite` | 277 | 4840 | 0 | 0 | False |
| `DEV-44b6_74d0c52e-t58-p296000000021` | `cfar_sidelobe/bipartite` | 73 | 628 | 2 | 2 | True |
| `DEV-44b6_aaf8b0ea-t61-p390000000000` | `cfar_sidelobe/bipartite` | 154 | 1539 | 0 | 0 | False |
| `DEV-44b6_c50204e0-t28-p171000000043` | `cfar_sidelobe/bipartite` | 502 | 17868 | 0 | 0 | False |
| `DEV-44b6_c50204e0-t65-p208000000033` | `cfar_sidelobe/bipartite` | 573 | 24424 | 1 | 1 | True |
| `DEV-6bba_2312ac41-t10-p11000190` | `components/greedy` | 201 | 2074 | 1 | 1 | True |
| `DEV-6bba_2312ac41-t19-p20000316` | `components/greedy` | 174 | 1599 | 1 | 1 | True |
| `DEV-6bba_2819ca14-t61-p62000719` | `components/greedy` | 46 | 60 | 1 | 1 | True |
| `DEV-6bba_3abfe10a-t81-p82001296` | `cfar_sidelobe/bipartite` | 690 | 28725 | 1 | 1 | True |
| `DEV-6bba_3c5691b6-t22-p23000172` | `components/greedy` | 49 | 74 | 1 | 1 | True |
| `DEV-6bba_3c5691b6-t6-p7000054` | `components/greedy` | 56 | 100 | 2 | 2 | True |
| `DEV-6bba_3fda6b25-t28-p29000542` | `components/greedy` | 93 | 405 | 1 | 1 | True |
| `DEV-6bba_57b7cc1e-t12-p13000378` | `cfar_sidelobe/bipartite` | 997 | 43211 | 6 | 6 | True |
| `DEV-6bba_57b7cc1e-t23-p24000720` | `cfar_sidelobe/bipartite` | 986 | 42983 | 1 | 1 | True |
| `DEV-6bba_57b7cc1e-t77-p78002270` | `cfar_sidelobe/bipartite` | 967 | 48686 | 2 | 2 | True |
| `DEV-6bba_5c039895-t10-p11000170` | `components/greedy` | 107 | 563 | 1 | 1 | True |
| `DEV-6bba_5c039895-t52-p53000762` | `components/greedy` | 86 | 291 | 1 | 1 | True |
| `DEV-6bba_5c039895-t58-p59000855` | `components/greedy` | 78 | 243 | 1 | 1 | True |
| `DEV-6bba_5c824876-t2-p3000057` | `components/greedy` | 187 | 2628 | 1 | 1 | True |
| `DEV-6bba_6321a359-t8-p9000094` | `components/greedy` | 40 | 38 | 2 | 2 | True |
| `DEV-6bba_67ebd073-t86-p87000772` | `components/greedy` | 66 | 241 | 1 | 1 | True |
| `DEV-6bba_7d3058ae-t32-p33000475` | `components/greedy` | 78 | 254 | 4 | 4 | True |
| `DEV-6bba_7d3058ae-t83-p84001401` | `components/greedy` | 86 | 244 | 1 | 1 | True |
| `DEV-6bba_87289e13-t77-p78001026` | `components/greedy` | 60 | 87 | 1 | 1 | True |
| `DEV-6bba_8b7818bf-t3-p4000023` | `components/greedy` | 56 | 107 | 1 | 1 | True |
| `DEV-6bba_8b7818bf-t33-p34000238` | `components/greedy` | 66 | 205 | 1 | 1 | True |
| `DEV-6bba_907271db-t96-p97001173` | `components/greedy` | 39 | 14 | 1 | 1 | True |
| `DEV-6bba_9e23430b-t89-p90001032` | `components/greedy` | 105 | 2040 | 1 | 1 | True |
| `DEV-6bba_cdcfe533-t28-p29000464` | `components/greedy` | 260 | 2892 | 1 | 1 | True |
| `DEV-6bba_cdcfe533-t48-p49000935` | `components/greedy` | 275 | 3737 | 1 | 1 | True |
| `DEV-6bba_cdcfe533-t52-p53001039` | `components/greedy` | 276 | 3923 | 1 | 1 | True |
| `DEV-6bba_cdcfe533-t86-p87002049` | `components/greedy` | 283 | 4524 | 0 | 0 | False |
| `DEV-6bba_d2b9fc0c-t72-p73000666` | `components/greedy` | 224 | 3534 | 2 | 2 | True |
| `DEV-6bba_d2b9fc0c-t78-p79000759` | `components/greedy` | 226 | 3547 | 4 | 4 | True |
| `DEV-6bba_d3da753b-t63-p64000722` | `components/greedy` | 120 | 834 | 1 | 1 | True |
| `DEV-6bba_debd7bfa-t12-p13000353` | `components/greedy` | 212 | 2749 | 1 | 1 | True |
| `DEV-6bba_debd7bfa-t26-p27000673` | `components/greedy` | 183 | 1960 | 6 | 6 | True |
| `DEV-6bba_debd7bfa-t36-p37000853` | `components/greedy` | 154 | 1486 | 1 | 1 | True |
| `DEV-6bba_debd7bfa-t37-p38000863` | `components/greedy` | 145 | 1511 | 1 | 1 | True |
| `DEV-6bba_ef7b4f7e-t14-p15000245` | `components/greedy` | 54 | 96 | 0 | 0 | False |
| `DEV-6bba_ef7b4f7e-t89-p90001375` | `components/greedy` | 65 | 264 | 1 | 1 | True |
| `DEV-6bba_fc5f39dc-t24-p25000064` | `cfar_sidelobe/bipartite` | 141 | 1696 | 2 | 2 | True |
| `DEV-6bba_fc5f39dc-t54-p55000245` | `cfar_sidelobe/bipartite` | 219 | 3424 | 0 | 0 | False |
| `DEV-6bba_fe670320-t0-p1000014` | `components/greedy` | 0 | 0 | 0 | 0 | False |
| `DEV-6bba_fe670320-t66-p67000712` | `components/greedy` | 140 | 1856 | 1 | 1 | True |

## Unavailable Cases

| Case | Cohort | Baseline status | Formed actions | Registered matches |
|---|---|---|---:|---:|
| `DEV-44b6_706092f0-t49-p446000000015` | `baseline_unavailable` | `no_parent_detection_within_7um` | 4840 | 0 |
| `DEV-44b6_aaf8b0ea-t61-p390000000000` | `baseline_unavailable` | `no_pair_inside_14um_formation_radius` | 1539 | 0 |
| `DEV-44b6_c50204e0-t28-p171000000043` | `baseline_nonofficial_action` | `projected_actions_not_official_tp` | 17868 | 0 |
| `DEV-6bba_cdcfe533-t86-p87002049` | `baseline_unavailable` | `fewer_than_two_daughter_lineages_within_7um` | 4524 | 0 |
| `DEV-6bba_ef7b4f7e-t14-p15000245` | `baseline_unavailable` | `no_parent_detection_within_7um` | 96 | 0 |
| `DEV-6bba_fc5f39dc-t54-p55000245` | `baseline_nonofficial_action` | `projected_actions_not_official_tp` | 3424 | 0 |
| `DEV-6bba_fe670320-t0-p1000014` | `positive_control` | `official_positive` | 0 | 0 |

The lost positive control at `t=0` has no prior frame and therefore no V19 `t-1`
anchor under this pre-registered formation rule. It is a structural anchor limitation,
not a detector-threshold failure.

## Interpretation Boundary

This audit measures whether an officially recognizable fork exists in the formed action set.
It does not select an action, estimate precision, fit confidence, solve ownership, or mutate
a tracking graph. Raw action counts are not official false positives.
