# V27 publication and reproducibility boundary

This publication records the V26A gate-order audit, the original failed V27A
execution, the V27A.1 amendment and fixed-history results, and the V27B recursive
history results. It does not change any frozen scientific source, contract,
approval, parameter or result, and does not authorize a new experiment.

The repository includes the implementations, regression tests, contracts,
implementation reviews, candidate and approved freeze records, result reports,
and machine-readable summaries and artifact inventories. The original V27A
failure stream, its failure record and freeze copy are included at their original
paths so that the real-failure regression witness remains verifiable. The
recorded validation XML files and V27B read-only artifact verifier are also
preserved. Candidate records and earlier validation attempts are historical
evidence; only the explicitly approved freeze records authorize their named run.

The complete V27A.1 and V27B output directories remain local under
`outputs/v27a1_frozen_20260924/` and `outputs/v27b_frozen_20260924/` (approximately
1.67 GB combined). Their byte identities and inventories are recorded in
`v27a1_association_decomposition_results.json` and
`v27b_recursive_history_results.json`. Upstream input archives, competition
volumes, model checkpoints and unrelated local logs are not included here.

A fresh clone can inspect the published records and run the included regression
tests after installing the project and test dependencies. It cannot independently
replay the cohort or perform the full artifact audit from Git alone: those steps
require the exact local inputs and outputs named by the frozen manifests, plus
the recorded runtime. Restoring a path with different bytes is not restoration
of the frozen evidence. Do not overwrite an existing run directory or regenerate
a pinned validation report as a substitute for the original.

V26A remains **NO_GO**, the original V27A remains **INVALID_EXECUTION**, and the
completed V27A.1 and V27B runs establish bounded mechanism observations. They do
not establish improved biological tracking accuracy or official Kaggle score.
