# V23 Split Echo Paths Results

Anchored decision: **NO_GO_ANCHORED_PATH**.

Upstream-quarantine decision: **QUARANTINED**.

The anchored path retained the graph's existing child and ranked only one distinct echo counterpart. The broken-parent path was excluded from all anchored metrics. GT was used only to identify registered-valid ranks after proposal construction.

The preregistered assumption of three anchored events was falsified: only two had a registered-valid parent, existing-child, and echo-counterpart hypothesis. `44b6_74d0c52e` had a detected parent but no registered existing-child anchor, while `6bba_57b7cc1e` had no registered parent detection.


## Parent-Present Anchored Completion

| Event | Family | Parent rank | Counterpart rank | Global proposal rank | Proposals |
|---|---|---:|---:|---:|---:|
| 44b6_aaf8b0ea t61 | 44b6 | 109 | 1 | 970 | 2153 |
| 6bba_fc5f39dc t24 | 6bba | 22 | 2 | 109 | 270 |

## Upstream Quarantine

| Event | Quarantine reason | Prior pooled source/rank | Status |
|---|---|---:|---|
| 44b6_74d0c52e t58 | detected_parent_has_no_registered_existing_child_anchor | primary_parent 241 / 7 | QUARANTINED |
| 6bba_57b7cc1e t23 | no_detected_parent_within_official_radius | echo_parent 349 / 83 | QUARANTINED |

Guardrail: both paths remained read-only. No candidate, edge, or graph was changed.
