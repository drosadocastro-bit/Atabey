# V28 frozen Kaggle result: 0.728

Kaggle's authenticated account API confirms **COMPLETE** and a **public score
of 0.728** for submission **56631581**. The accepted V19 backup, **54622713**,
reports **COMPLETE / 0.515**. The public leaderboard increase is **0.213 points**.
The timestamp and original API fields are preserved in
[the live account snapshot](outputs/v28_release_20260928/submissions_live.json).

## Exact scored version

| Identity | Frozen value |
|---|---|
| Notebook | `drakus74/atabey-v28-submission` |
| Notebook version | 1 |
| Kernel ID | 136216285 |
| Scored script version ID | 353502941 |
| Competition submission | 56631581 |
| Submitted at | 2026-09-28 06:27:39.480 UTC |
| Filename | `submission.csv` |
| Public score | 0.728 |
| Kaggle status | COMPLETE |

[Exact scored notebook](https://www.kaggle.com/code/drakus74/atabey-v28-submission?scriptVersionId=353502941).
The latest fetched source still matches the approved executable cell for cell,
and its software-image digest matches the successful offline validation. No new
Kaggle version, inference run, submission or selection change was made to freeze
and publish this result.

Package-manifest SHA-256:
`fb7fde61dd8a1499cc68530cd0a0e3bc8293a803acfaf86edd2f4c67b5e097c3`

Submitted executable notebook SHA-256:
`336641397a41e819c810d3ccbdfd5b2598d43bcc6037807d893ceb89b9560acc`

The [release freeze](v28_release_freeze_20260928.json) binds the accepted result,
human publication approval, earlier execution freezes and published artifact
identities. Git tag **`v28-kaggle-0.728`** identifies this publication. It does not
replace either original execution approval or grant authority for a new run.

## What passed, and what the score means

The frozen V24.3 algorithm is unchanged: E016 detections, `motion_mutual` linking
in physical microns at 9 microns, followed by P2 then P3 pruning only on the
image-routed `6bba_` / `components` branch. V27 variants were not promoted.

Before submission, the offline validation matched 199 route decisions, seven
historical final-graph signatures and one repeated inference. The submitted
notebook's visible run then produced the same four final graphs and a byte-exact
311,183-row CSV in 186.142 seconds including setup. This publication reran the
focused regression battery: **83 tests passed**. The original validation and
fresh publication test reports are retained separately.

The visible CSV SHA-256 is:
`f9ed84aa3c55de186c7b750861d3e869d028107540e16d5e8ca1e77e01106924`.
It identifies the visible output, not the inaccessible hidden-evaluation CSV.
The API reports 234,937,107 bytes for the scored submission; those hidden output
bytes and their hash have not been downloaded or independently verified here.

The completed competition result establishes successful Kaggle evaluation of
this submitted version. The public score is not a final private leaderboard
score, biological ground truth or proof of generalization to every embryo.
V24.3's local adjusted-edge Jaccard of 0.721056 is a different evaluation record
and must not be treated as the same quantity as this competition score.

All 16 historical local regressions remain, including the four catastrophic
cases. Reproducing those cases established implementation parity, not a repair.
V26A remains NO_GO; V27 remains retrospective research; the lack of unopened
local labeled evidence remains. No leaderboard-driven tuning is part of this
release. The hidden run's exact duration and hardware telemetry are unavailable
in the account response; the earlier 5-hour projection remains an estimate.

## Publication and remaining competition step

Danny explicitly authorized freezing this version, updating the README and
pushing to GitHub. The publication includes V28 code, tests, contracts,
unapproved templates, approved dispatch copies, selected original evidence and
the current result receipt. Earlier documents retain their original PROPOSED or
PENDING wording as historical records; this additive report supplies the later
COMPLETE status.

See [the publication boundary](docs/V28_PUBLICATION_SCOPE.md) for what a fresh
clone can verify and what still requires external data. No weights, microscopy
volumes, ground-truth labels or full CSV outputs are added to Git. The unrelated
modified V25 notebook is excluded.

V19 remains the accepted backup, bound to script version **334646717**. Final
selection flags have not been verified or changed. Checking and recording the
final selections remains a separate competition-close step.
