# V23 Candidate Coordinate and Identity Audit

Read-only audit separating coordinate quality from graph ownership. No candidate, edge, or graph was changed.

| Sample | Role | Nearest candidate | Distance | Coordinate quality | Incoming claims | Outgoing claims |
|---|---|---|---:|---|---|---|
| 44b6_706092f0 t49 | parent | none | NA | no_candidate | - | - |
| 44b6_706092f0 t49 | daughter_1 | 44b6_706092f0:t50:cf186 | 1.625 | official_radius | - | - |
| 44b6_706092f0 t49 | daughter_2 | 44b6_706092f0:t50:cf186 | 5.203 | official_radius | - | - |
| 44b6_74d0c52e t58 | parent | 44b6_74d0c52e:t58:cf24 | 6.039 | official_radius | - | - |
| 44b6_74d0c52e t58 | daughter_1 | 44b6_74d0c52e:t59:cf3 | 8.044 | formation_radius_only | 44b6_74d0c52e:t58:cf1 | - |
| 44b6_74d0c52e t58 | daughter_2 | 44b6_74d0c52e:t59:cf13 | 6.551 | official_radius | 44b6_74d0c52e:t58:cf27 | - |
| 44b6_aaf8b0ea t61 | parent | 44b6_aaf8b0ea:t61:cf47 | 1.675 | official_radius | 44b6_aaf8b0ea:t60:cf10 | 44b6_aaf8b0ea:t62:cf33 |
| 44b6_aaf8b0ea t61 | daughter_1 | 44b6_aaf8b0ea:t62:cf33 | 3.300 | official_radius | 44b6_aaf8b0ea:t61:cf47 | - |
| 44b6_aaf8b0ea t61 | daughter_2 | 44b6_aaf8b0ea:t62:cf33 | 1.625 | official_radius | 44b6_aaf8b0ea:t61:cf47 | - |
| 6bba_57b7cc1e t23 | parent | 6bba_57b7cc1e:t23:cf46 | 7.963 | formation_radius_only | 6bba_57b7cc1e:t22:cf30 | - |
| 6bba_57b7cc1e t23 | daughter_1 | 6bba_57b7cc1e:t24:cf581 | 11.223 | formation_radius_only | - | - |
| 6bba_57b7cc1e t23 | daughter_2 | 6bba_57b7cc1e:t24:cf162 | 5.093 | official_radius | - | - |

Coordinate quality is measured against the registered GT position only for diagnosis. Incoming/outgoing claims describe the existing upstream graph and are not treated as truth labels.
