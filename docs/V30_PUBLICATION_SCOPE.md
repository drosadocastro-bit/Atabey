# V30 publication and reproducibility boundary

Danny authorized committing and pushing the completed V30 diagnostic before
starting V31. This publication preserves the original proposal, implementation
review, approved single-run receipt, source, tests, complete machine result,
all 199 compact per-sample summaries, terminal and independent verification,
derived readout, interpretation and execution closure manifest.

`v30_release_freeze_20260928.json` inventories the exact published bytes. The
historical PROPOSED, IMPLEMENTED_AWAITING_REVIEW and execution-time publication
authority flags are preserved verbatim. They describe earlier stages. The
separate execution and publication receipts record the subsequent approvals;
neither grants standing authority to retry scientific work.

The result is a **valid descriptive diagnostic**, not a model improvement,
independent validation or causal experiment. All 199 sample pairs reproduced
their final graph/export evidence; the independent audit verified serialized
stage signatures and output accounting without another graph reconstruction.
The V29A NO_GO decision and existing official metrics remain unchanged.

## Included and retained locally

The Git publication includes all candidate artifacts, preparation and
implementation preflight records, every compact diagnostic row, the full
result and original generated report, the independently checked completion
records, and the procedures used to prepare, audit and report the result.
The publication adds no new scientific execution or score.

The 199 compressed full-detail tables under
`outputs/v30_execution_20260928/samples/` remain local (about 359 MB). Their
paths, sizes and SHA-256 identities are preserved in the compact sample rows
and the original closure manifest. The large intermediate
`completed_payload.json` and transient console logs also remain local;
`result.json` is the published terminal result. Nothing was deleted or rewritten
to reduce publication size. Links to full-detail tables require those local files.

V29A's 398 saved coordinate arrays, microscopy images, GEFF ground truth,
checkpoint binaries and runtime dependencies are not added to Git. V30's
existing input inventory records their relevant identities and references.
An inventory entry alone does not prove that an absent file matches its hash.

A clone can inspect all 199 summary rows, the complete decision context,
approval chain, source and unit tests. With the required dependencies installed,
the tests exercise synthetic inputs only. Full independent evidence auditing
requires the omitted detailed tables and named local parent inputs. Scientific
replay additionally requires the pinned runtime, inputs and a new explicit
execution approval; the historical receipt is not reusable execution authority.

## Preserved boundaries

All original V28 and V29A release artifacts, including README.md and the root
.gitattributes, remain byte-identical. V30 artifacts already use LF line endings;
publication checks verify that staged Git blobs equal their frozen raw bytes.
No unrelated notebook changes, checkpoints, images, account logs or other local
work are included. The pre-existing modified V25 notebook is left untouched.

V31 is prospective work under its own contract. No V31 implementation or
execution belongs to this V30 release. No Kaggle submission or selection change
is performed as part of publication.
