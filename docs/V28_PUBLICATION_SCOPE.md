# V28 publication and reproducibility boundary

This publication freezes the exact V28 version accepted by Kaggle with public
score 0.728, submission 56631581, script version 353502941. It adds delivery code,
tests, contracts, historical review/approval records, selected byte-pinned
evidence, an additive completed-result report and an updated README. It does not
change the frozen scientific policy or authorize another run.

The included original evidence covers the 21-artifact validation candidate,
the approved validation and submission dispatches, source bundle and manifest,
original unit-test reports, local route/graph parity, remote summaries and graph
records, API submission receipts, the live completed-score snapshot and the
83-test publication report. The release manifest enumerates the exact published
evidence; earlier inventories also name local files outside this publication.
Git attributes preserve raw bytes for V28 frozen artifacts, including original
CRLF line endings. Do not regenerate historical reports to satisfy their hashes.

Both notebooks under `notebooks/` remain review templates with `NOT_APPROVED`
receipts. The actual approved copies live under the original
`outputs/v28_validation_20260928/dispatch/` and
`outputs/v28_submission_20260928/dispatch/` paths. They contain historical
authorization for those specific executions, not standing permission to rerun.

A fresh clone can inspect the score/approval chain, validate published file
identities, inspect the embedded source bundle and run the focused unit tests
after installing the project's dependencies and pytest. Each notebook embeds
the source bundle and the pinned historical tracksdata replacement wheel. The
bundle is published separately as well, preserving its original identity.

Fresh GPU execution also requires Kaggle access, the competition data, support
pack version 10 (`pilkwang/biohub-tracking-support-pack-50ep-v1/10`), clean E016
checkpoint version 1 (`drakus74/v22-e016-clean-checkpoint/1`) and the recorded
runtime. Checkpoint and support-file hashes are in the manifest; their binary
datasets and full offline dependency wheel collection are not included in Git.
Building a new notebook from local inputs additionally needs the historical
archives and dataset-version records named by the builder. Exact replay cannot
be claimed from a Git clone alone.

The following remain local: full visible CSV files, historical cohort archives,
microscopy images, GEFF labels, checkpoint binaries, full raw output directories,
transient status polls and unselected account/runtime logs. Included inventories
record hashes and paths for some of these external artifacts; a missing local
artifact is not evidence of hash agreement. The post-run verification scripts
require the full corresponding downloaded outputs, including CSV files.

The complete hidden-evaluation output and timing were not retrieved. Kaggle's
COMPLETE status and public score are account observations; the visible CSV hash
must not be relabeled as a hidden-output hash. Final-selection state is not
established by this publication. V19 remains the accepted backup, and the
unrelated V25 notebook and other local work are not staged.
