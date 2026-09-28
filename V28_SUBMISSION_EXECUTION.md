# V28: frozen and submitted to Kaggle

**Submission registered; evaluation pending.** At 2026-09-28 06:27:59 UTC,
Kaggle reported `SubmissionStatus.PENDING` for submission **56631581**, with no
public score. Registration is not yet evidence of completed hidden execution,
successful scoring or final-selection status.

Danny approved the exact reviewed package with:

> acabo de leerlo amor, y esta solido y honesto, aprobado para congelacion y someter a kaggle

That authorization was recorded in a separate `V28_SUBMISSION` receipt. The
approved template was preserved; only its receipt line changed in the executable
copy. No scientific code, settings, thresholds, weights or policy changed.

## Submitted identity

| Item | Value |
|---|---|
| Competition submission | `56631581` |
| Submission time | 2026-09-28 06:27:39.480 UTC |
| Notebook | `drakus74/atabey-v28-submission` |
| Notebook version / kernel ID | 1 / 136216285 |
| Kaggle script version ID | 353502941 |
| Submitted filename | `submission.csv` |
| Execution cap | 39,600 seconds / 11 hours per execution |
| Accelerator / network | T4 / internet disabled |

[Exact submitted notebook](https://www.kaggle.com/code/drakus74/atabey-v28-submission?scriptVersionId=353502941)
and [competition submissions](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development/submissions).

Candidate payload SHA-256:
`217541a10e28652eda5ccc79c81683c7f9684ae28449a0559c9d7efb0e35e87d`

Package-manifest SHA-256:
`fb7fde61dd8a1499cc68530cd0a0e3bc8293a803acfaf86edd2f4c67b5e097c3`

Approved executable notebook SHA-256:
`336641397a41e819c810d3ccbdfd5b2598d43bcc6037807d893ceb89b9560acc`

Remote source cells match that executable. Kaggle also returned the exact image
used by the successful validation:

`gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461`

## Verification before submission

The visible notebook run completed in **186.142 seconds** including setup.
The downloaded output passed the frozen CSV validator: **311,183 rows** across
all four visible samples. Every recorded graph signature, export digest, node and
edge count, route decision and sample shape matched the preceding validation.
The CSV itself was byte-identical:

`f9ed84aa3c55de186c7b750861d3e869d028107540e16d5e8ca1e77e01106924`

Torch, CUDA, NumPy, SciPy, pandas, Zarr, tracksdata, scikit-image and the used GPU
identity matched the validation. All checked frozen source/test/package artifacts
remained intact. This was builder verification; Danny remains the reviewer and
authority. No new local inference or scoring was performed during verification.

The completed visible run increased the recorded quota usage by **204.588
seconds**, leaving **44.7897 hours** before the hidden rerun. This is a timed
account snapshot, not a statement of the later balance or allocated device count.
CPU-model and GPU-count telemetry gaps from validation remain disclosed.

## Backup, limits and remaining work

V19 submission **54622713** still reports `COMPLETE`, public score **0.515**.
The fresh account response binds it to script version **334646717**. It was not
modified. Its final-selection flag remains unverified.

The [official rules](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development/rules)
were read again: at most five submissions per day and up to two final selections.
The [official code requirements](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development/overview)
still require offline notebooks, `submission.csv`, all test datasets and at most
12 hours. The deadline remains September 29, 2026, 23:59 UTC. The authenticated
page responses are preserved with the evidence.

Next, inspect this submission's terminal result. If it succeeds, review that
result and the final-selection flags before the deadline. Final selection was
not changed by this action. No automatic retry, tuning or replacement candidate
is authorized by this execution record. The historical regressions and the
conditional hidden-runtime projection in [the validation report](V28_VALIDATION_RESULTS.md)
remain unchanged; no hidden score or generalization claim is inferred.

## Records

- [Approved submission freeze](v28_submission_freeze_approved_20260928.json).
- [Execution record and evidence hashes](v28_submission_execution_20260928.json).
- Raw receipts, API responses, notebook, metadata, logs and downloaded output:
  `outputs/v28_submission_20260928/`.
- Local visible-output verification:
  `outputs/v28_submission_20260928/visible_verification.json`.

The unrelated V25 notebook was preserved. No Git commit or push was performed.
