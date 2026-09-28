# V29A lessons learned

V29A is a completed, reproducible research result with a **NO_GO promotion
decision**. It tested one intervention: the existing predictor's four-view XY
detection-logit average. V28's checkpoint, thresholds, physical linking, routing,
pruning and output schema stayed fixed. The result and its failed gates are
preserved without changing the contract after observing outcomes.

## Aggregate gain can coexist with unacceptable individual losses

The local official combined score rose from 0.721055749 to 0.735927590. All five
specified subgroup aggregates increased and 134 of 199 samples improved.
Nevertheless, 25 samples lost more than the permitted 0.020; the worst lost
0.106430206. The protected sample `6bba_76db78c1` lost 0.045537786 even though
the other three protected cases improved. Group averages did not establish
that every protected case was preserved.

The learned operational rule is to retain the aggregate, subgroup, individual
and protected-case results together. The two failed gates remain failures.
Their numeric limits were conservative choices fixed before the experiment,
not biological constants or independently calibrated thresholds. A different
future decision rule would need a separate prospective contract and authority;
it cannot retroactively make V29A pass.

## Exact implementation control does not imply fixed downstream history

Only `det_tta` changed in the predictor configuration. Different detections can
still change candidate ordering, exact ties, selected associations, pruning and
recursive track histories. V29A is therefore a detection intervention with
downstream effects, not a ranking-only or fixed-history mechanism experiment.
Reproducing V28 graphs and metrics establishes the control comparison; it does
not isolate which downstream mechanism produced each TTA gain or loss.

## Reproducibility, runtime and quality answer different questions

All 199 fresh baseline graphs and official metric records reproduced history.
The two TTA graph repeats and the official evaluation repeat passed. Both
runtime projections passed their fixed limit. These checks made the comparison
usable; they did not override the sample-level quality protections.

The GPU research run took 4 h 49 min and local evaluation about 17 minutes.
The 9 h 02 min projection is an extrapolation under the frozen hidden-workload
assumption, not a measurement of a TTA competition rerun. No V29A competition
submission was made, so there is no V29A leaderboard result.

## Opened development evidence remains opened

The 172 checkpoint-training and 27 checkpoint-held-out samples were already
opened. An aggregate gain on either group is useful development evidence, not
independent generalization. Sparse annotations also limit biological readings
of official false-positive counts. Both branches had zero official division
true positives; this intervention did not demonstrate division recovery.

## Delivery failures belong in the record

The initial test failure was a list-versus-tuple serialization expectation;
the original failing report is preserved alongside the corrected passing run.
Live-log transport connections ended prematurely while the GPU job continued.
An intentional local pause for travel did not cancel the remote experiment.
On return, output listing hit HTTP 429, and a larger page request was rejected
with HTTP 400. Paced supported pages recovered the files without rerunning
inference. These operational failures did not invalidate the verified scientific
outputs, and none was erased to make the process look cleaner.

For future packages, keep bulky installed dependencies outside the retained
output tree, preserve a compact result manifest, pace retrieval, and distinguish
remote execution state from local monitoring state. These are future delivery
improvements; the frozen V29A package and evidence remain unchanged.

## Closure

Publish the gain and the regressions as one result. Keep the V28 0.728 submission
and the V19 backup selected as observed at closure. No automatic fallback,
sample selector, threshold change or new experiment follows from V29A's outcome.
Full numbers and provenance are in [V29A_RESULTS.md](V29A_RESULTS.md).
