# V21 Link-Gate Audit: 9um vs 14um

Date: 2026-07-20
Branch: `mitosis_hough_audit`

## Question

Should `cfar_max_link_distance_um` be raised from `9.0um` to `14.0um` to improve division candidate formation, given that the sparse GT audit showed all known GT parent-to-daughter distances are <= `13.529um`?

## Gate Identity

These are distinct gates:

- `cfar_max_link_distance_um` in `src/atabey/hybrid_config.py` is the candidate-formation and normal-linking distance gate. It is passed into `link_adjacent_timepoints_bipartite(...)` and used by the initial `motion_mutual` continuation assignment, candidate-parent eligibility, and local orphan inclusion.
- The `15.0um` daughter-separation bound is a separate hardcoded bipartite evaluation gate inside `src/atabey/tracking/nearest_neighbor.py`: `dist_primary_to_orphan > 15.0` rejects a local orphan after the parent and primary target have already been selected.

Changing `cfar_max_link_distance_um` is therefore broad and affects normal continuation tracking, not only division rescue.

## Sparse GT Distance Audit

Across all `199` train GEFF files:

- Known sparse GT divisions: `151`
- Parent-child GT edges: `302`

Parent-child edge distance:

| metric | value |
| --- | ---: |
| min | `0.406um` |
| median | `5.745um` |
| p90 | `9.066um` |
| max | `13.529um` |

Max parent-child distance per division:

| metric | value |
| --- | ---: |
| min | `2.844um` |
| median | `7.130um` |
| p90 | `10.050um` |
| max | `13.529um` |

Coverage by candidate-formation gate:

| gate | known GT divisions outside gate |
| ---: | ---: |
| `9um` | `30/151` |
| `10um` | `16/151` |
| `11um` | `10/151` |
| `12um` | `6/151` |
| `13um` | `2/151` |
| `14um` | `0/151` |

This made `14um` plausible from the label geometry alone. The bounded graph checks below show it is not safe as a global formation gate.

## Bounded Before/After: Missed `6bba_ebdf3b34` FN Window

Sample: `6bba_ebdf3b34`, `max_timepoints=20`.

| link gate | pre EdgeRecall | post-firewall EdgeRecall | pre Div TP/FP/FN | post Div TP/FP/FN | Track B accepted | known FN formed? |
| ---: | ---: | ---: | --- | --- | ---: | --- |
| `9um` | `0.707318` | `0.701220` | `0/1700/2` | `0/585/2` | `481` | `False` |
| `14um` | `0.658537` | `0.652439` | `0/2234/2` | `0/535/2` | `467` | `False` |

Result: raising the formation gate to `14um` did **not** recover the missed GT division.

Deeper inspection of the missed parent under `14um`:

- GT parent prediction: `6bba_ebdf3b34:t13:cf520`
- GT daughters: `t14:cf601`, `t14:cf555`
- Baseline primary remains the wrong target: `t14:cf31`
- Candidate orphan `cf601` is accepted with parent distance `5.992um`
- True second daughter `cf555` enters the 14um local range at parent distance `11.868um`, but fails the separate daughter-separation gate because its separation from wrong primary `cf31` is `16.061um > 15.0um`

So `14um` is insufficient by itself because the wrong primary is selected before orphan evaluation.

## Bounded Before/After: Previously Recovered TP Window

Sample: `6bba_05db0fb1`, `max_timepoints=32`.

| link gate | pre EdgeRecall | post-firewall EdgeRecall | pre Div TP/FP/FN | post Div TP/FP/FN | Track B accepted | known TP formed? |
| ---: | ---: | ---: | --- | --- | ---: | --- |
| `9um` | `0.765487` | `0.747788` | `1/3829/2` | `1/1127/2` | `1040` | `True` |
| `14um` | `0.694690` | `0.685841` | `0/4677/3` | `0/998/3` | `998` | `False` |

Result: raising the formation gate to `14um` broke an already-recovered TP and reduced post-firewall EdgeRecall by about `0.062` on this bounded window.

The known TP parent changed from the correct pair:

- `9um`: `cf17 + cf3` -> correct, TP formed.
- `14um`: `cf17 + cf206` -> wrong orphan, TP lost.

## Decision

Do **not** raise the global `cfar_max_link_distance_um` default from `9.0um` to `14.0um` based on the current evidence.

Why:

- `14um` does capture all sparse GT parent-daughter distances geometrically, but it also changes normal motion-mutual continuation and orphan competition.
- It did not recover the target `6bba_ebdf3b34` FN because the wrong primary target was selected first and the true daughter then failed the separate `15um` daughter-separation gate.
- It broke a previously validated `6bba_05db0fb1` TP by changing the orphan winner from the true daughter to a different candidate.
- Existing firewall filtering did remove additional noise, but it did not protect EdgeRecall or TP recovery in the bounded checks.

Next likely direction: a division-specific candidate-formation rescue path that can consider alternate primary/orphan pairings around matched or high-risk parents, without widening the global continuation link gate used by normal tracking.
