# V22 Proxy-Resistant Continuation Gate Preregistration

Status: **PREREGISTERED; RESULTS NOT OPENED**

## Objective

Determine whether density and local ownership features contribute fold-stable information beyond geometric imitation of V19. This gate follows the finding that the first teacher ablation retained deterministic proxies for prediction error and strong proxies for margins and ranks.

## Frozen Feature Sets

The density-only head removes all five direct teacher features and the complete retained motion-reconstruction set: anchor-parent distance, parent-child distance, step-distance ratio, radial speed change, and turn angle.

Its only features are parent density, child density, local target count, and local competing-source count. Parent density and local target count are expected to be constant within a reference group; they remain in the audit for transparency but cannot create pairwise ranking utility by themselves.

## Three Required Comparisons

1. **Density-only:** a sample-blocked pairwise logistic head using only the four density/ownership features.
2. **Nearest-distance baseline:** fixed score `-parent_child_distance_um`, with strict ties counted as failures.
3. **Distance plus density:** the same nested out-of-fold logistic procedure using parent-child distance plus the four density/ownership features.

The third comparison is decisive. Density-only need not replace geometry to be independent; it must add stable out-of-fold value over the fixed nearest-distance baseline.

## Validation

All fitted models use the existing three sample-blocked folds, inner two-fold swap for `C` selection, train-only preprocessing, equal sample -> frame -> reference -> pair weighting, and strict `1e-12` ties. CFAR and components are evaluated independently. Local-maxima remains zero-shot, unproven, and excluded from every decision.

The distance-plus-density head must pass every existing hard fold and route gate and fire no existing generalization warning.

## Incremental GO Gates

A GO additionally requires:

- pooled top-1 improvement over nearest distance of at least 0.005;
- pooled pairwise improvement of at least 0.0025;
- no fold or route top-1 delta below -0.0025;
- positive top-1 delta in at least two of three folds;
- nonnegative top-1 delta in both decision routes;
- density-only pairwise accuracy of at least 0.60;
- density-only top-1 at least 0.05 above the equal-sample random-within-group expectation.

No value is rounded into passing.

## Decision States

- **GO_INDEPENDENT_INCREMENTAL_DENSITY_SIGNAL:** every generalization and incremental gate passes.
- **HOLD_WEAK_OR_UNSTABLE_INCREMENTAL_SIGNAL:** pooled improvement is positive, but a practical-size or stability gate fails.
- **NO_GO_INDEPENDENT_DENSITY_SIGNAL:** pooled improvement is nonpositive or an existing hard generalization gate fails.

## Boundary

Even a GO would establish incremental prediction of weak V19 references, not biological truth. It would authorize only the bounded development joint-assignment shadow. Production graph mutation, locked validation, and full-199 evaluation remain prohibited.
