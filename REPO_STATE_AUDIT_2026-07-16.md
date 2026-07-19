# Repo State Audit - 2026-07-16

Scope: read-only audit of the current `mitosis_hough_audit` branch before any further work on bipartite/division-firewall experiments. This document records verified repo state and current blockers from the actual checkout at `D:\Project-Atabey`.

## Executive Status

Do not interpret the last V20 bipartite/division-firewall metrics as validated yet.

The current branch is clean and tests pass, but the specific V20 bipartite + firewall integration path is not covered by tests and fails in a bounded direct reproduction. There is also a route-labeling/observability problem: `--cfar-link-strategy bipartite` is only active on CFAR-routed samples, while non-CFAR samples silently fall back to their baseline linker even if the run-level label says `V20 (Bipartite)`.

Very next action should be a small fix/verification pass, not threshold tuning:

1. Add explicit per-sample internal strategy/routing logging to `run_parallel_division_audit.py` and V20 ablation output.
2. Fix or replace `division_firewall.prune_invalid_divisions(...)` graph mutation, because it currently calls `LineageGraph.remove_edge(...)`, which does not exist.
3. Add a focused integration test for V20 `_build_v20_graph(..., cfar_link_strategy="bipartite")` on a tiny synthetic or capped sample path that exercises firewall pruning.
4. Only then rerun any V13/V19/V20 metric comparison.

## 1. Repo And Branch State

Verified commands:

- `git -C D:\Project-Atabey branch --show-current`
- `git -C D:\Project-Atabey status --short --branch`
- `git -C D:\Project-Atabey log --oneline --decorate -n 12`
- `git -C D:\Project-Atabey diff --name-status main...HEAD`

Findings:

- Current branch: `mitosis_hough_audit`
- Tracking: `origin/mitosis_hough_audit`
- Working tree: clean, no uncommitted/local-only files reported by git status.
- HEAD: `fb62b5b Implement division firewall`
- Recent branch commits:
  - `fb62b5b Implement division firewall`
  - `33caffc Fix NameError in evaluation script`
  - `6f4bb0d Fix bipartite solver guardrails and update evaluation output`
  - `d48ef4d Wire bipartite routing and audit script params`

Latest commit contents match the expected focus area:

- Added `src/atabey/tracking/division_firewall.py`
- Modified `src/atabey/tracking/nearest_neighbor.py`
- Modified `scripts/run_v20_quality_score_ablation.py`
- Modified `scripts/run_parallel_division_audit.py`
- Added diagnostic scripts: `diagnose_29000464.py`, `diagnose_collision_noise.py`, `diagnose_firewall.py`, `diagnose_signals.py`

Diff against `main` is very large and includes many accumulated experimental artifacts, docs, model files, logs, scripts, and source changes. This branch is not a narrow patch relative to main.

Notable tracked additions relative to main include:

- `.keras/.../weights_best.h5`
- `weights/smoke_cnn.pth`
- `weights/v20_cnn_best.pth`
- many audit logs and temporary diagnostic artifacts
- many new docs/scripts/tests from V14-V20 arcs

This is worth cleaning later, but not before the bipartite/firewall correctness issue is resolved.

## 2. Requested Docs: Missing Or Broken Links

Requested files were not present in the current checkout:

- `DIVISION_JACCARD_INVESTIGATION_SUMMARY.md`
- `HOUGH_MITOSIS_PRECURSOR_AUDIT.md`
- `DIVISION_TOPOLOGY_DESIGN.md`

Evidence:

- `rg --files D:\Project-Atabey | rg "DIVISION_JACCARD_INVESTIGATION_SUMMARY|HOUGH_MITOSIS_PRECURSOR_AUDIT|DIVISION_TOPOLOGY_DESIGN"` returned no matches.
- `README.md` links to `DIVISION_JACCARD_INVESTIGATION_SUMMARY.md` and `docs/RADAR_CONCEPTS_AND_ATABEY.md` references `HOUGH_MITOSIS_PRECURSOR_AUDIT.md` and `DIVISION_TOPOLOGY_DESIGN.md`, but those files are absent.

Available related docs read during this audit:

- `docs/RULE_BASED_CEILING_SUMMARY.md`
- `docs/V13_ARCHITECTURE_AUDIT.md`
- `docs/V19_CFAR_WATERSHED_GO.md`
- `README.md`

Documentation state is therefore internally inconsistent: the README claims a consolidated division-jaccard narrative exists, but the referenced file is missing from the checkout.

## 3. Current Tests

Command:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='D:\Project-Atabey\src'; python -m pytest -q
```

Result:

- `87 passed in 8.76s`

Important limitation:

- Passing tests do not validate the V20 bipartite + firewall integration path.
- Search evidence found no test directly covering `prune_invalid_divisions(...)` or `_build_v20_graph(..., cfar_link_strategy="bipartite")` with firewall pruning.

## 4. Strategy Propagation Findings

### 4.1 Route-gated behavior

`cfar_link_strategy` only affects the CFAR route. If `_should_use_cfar_route(...)` returns false, `_build_hybrid_graph(...)` and `_build_v20_graph(...)` fall back to adaptive baseline behavior and return the baseline link strategy instead.

Observed bounded check with `cfar_link_strategy='bipartite'`:

```text
44b6_24264f12, max_timepoints=3:
  detector_returned: components
  link_returned: greedy
  division_edges: 0

6bba_05db0fb1, max_timepoints=3:
  detector_returned: cfar_sidelobe
  link_returned: bipartite
  division_edges: 412
```

Interpretation:

- The CLI flag can be genuinely active, but only for routed CFAR samples.
- Run-level labels such as `V20 (Bipartite)` are misleading unless every per-sample record logs the actual returned detector/link strategy.
- This can explain many identical V13/V19/V20 rows on non-CFAR samples without requiring a lower-level dispatch bug.

### 4.2 Existing code returns link strategy, but parallel audit does not expose it

`_build_hybrid_graph(...)` and `_build_v20_graph(...)` return `(graph, profile, detector, link_strategy, reason, max_link_distance_um)`, but `scripts/run_parallel_division_audit.py` discards detector/link strategy and only prints metrics. That means the audit output cannot prove whether `bipartite` was active per sample.

This is likely the missing debug logging fix the prior session requested. It is not present in the current committed `run_parallel_division_audit.py` output.

## 5. Critical Reproduction: V20 Bipartite Firewall Fails

Bounded reproduction command called the real builders on `6bba_05db0fb1` with `max_timepoints=8` and `cfar_link_strategy='bipartite'`.

Observed results before V20 failure:

```text
V13:
  detector: local_maxima
  link: motion_mutual
  nodes: 3787
  edges: 2526
  division_edges: 0
  sparse_edge_recall: 0.7857142857142857
  division_jaccard: 0.0

V19:
  detector: cfar_sidelobe
  link: bipartite
  nodes: 5688
  edges: 4511
  division_edges: 1554
  sparse_edge_recall: 0.76
  division_jaccard: 0.0

V20:
  reached cfar_link_strategy == 'bipartite'
  crashed in division_firewall.prune_invalid_divisions(graph)
```

Traceback root cause:

```text
AttributeError: 'LineageGraph' object has no attribute 'remove_edge'
```

Current `src/atabey/types.py` defines `LineageGraph.add_detection(...)` and `LineageGraph.add_edge(...)`, but no `remove_edge(...)`. `division_firewall.py` calls `graph.remove_edge(edge)` in two places.

This is the top concrete bug found by the audit. It invalidates any claim that the current V20 bipartite firewall path has been verified end-to-end.

## 6. Existing Log Evidence

`parallel_audit.log` shows a prior parallel run did not complete cleanly:

- Several samples printed `V13`, `V19`, `V20` all with `TP:0 FP:0 FN:0`, often `J=None`.
- The run then crashed with `MemoryError` inside `compute_multi_source_agreement(...)`:

```text
row_ind, col_ind = zip(*pairs)
MemoryError
```

`audit_bipartite.log` shows many lines like:

```text
BIPARTITE: found N new division edges!
```

Interpretation:

- Bipartite can and did execute in at least some logged paths.
- Existing logs are not a clean final 199-sample proof of V20 behavior.
- A completed full-cohort metric table with per-sample actual link strategy is still needed.

## 7. Investigation Arc Reconstructed From Available Evidence

Because the requested canonical summary docs are absent, this is reconstructed from available docs and code only.

Current documented arc:

1. V13 established the frozen robust baseline: streaming Zarr, route-gated CFAR for merged 6bba-like samples, sigma CFAR, isotropic sidelobe suppression, `motion_mutual` linking.
2. V14-V18 explored bounded CFAR reformulation, correlation recovery, kinematic hard exclusion, and global optimization. The consolidated conclusion in `RULE_BASED_CEILING_SUMMARY.md` is that rule-based linking/scoring hit a ceiling because upstream detection/localization quality in dense ambiguous regions constrained all later logic.
3. V19 watershed refinement targeted upstream localization variance and was documented as a GO on the 66 CFAR-routed samples, with +0.0255 quality score and 57/66 improved in `V19_CFAR_WATERSHED_GO.md`.
4. README claims V20 moved from Hough/bimodality precursor work to a topological bipartite solver. `RADAR_CONCEPTS_AND_ATABEY.md` says Hough/bimodality had 1.0x enrichment and was rejected, but the detailed Hough and topology docs are absent.
5. Current branch adds a bipartite solver and multi-frame division firewall, but the V20 firewall integration is broken by missing `LineageGraph.remove_edge(...)` and per-sample strategy logging is insufficient.

## 8. Calibration Note For Future Agents

Treat all claims of “validated”, “conclusive”, “fully fixed”, or “no open questions” as hypotheses until backed by:

- sample count,
- route count,
- actual per-sample detector/link strategy,
- whether the result generalized beyond the calibration sample,
- whether the relevant integration path is covered by tests.

Specific caution from this audit:

- V19 watershed has stronger documentation and full 66-CFAR-sample evidence.
- V20 bipartite/firewall does not yet have a trustworthy completed evidence package in the current checkout.
- Identical metrics can come from route fallback or from a broken/aborted run; do not infer “bipartite had no effect” without per-sample actual strategy logs.
- Do not tune thresholds until the V20 path can run end-to-end and expose actual strategy per sample.

## 9. Next Action Checklist

Recommended next patch, in order:

1. Add `remove_edge(...)` to `LineageGraph` or refactor `prune_invalid_divisions(...)` to mutate `graph.edges` without assuming a missing method.
2. Add a regression test for `prune_invalid_divisions(...)` on a tiny graph with one valid/invalid two-child branch.
3. Add an integration test or bounded smoke for `_build_v20_graph(..., cfar_link_strategy='bipartite')` that verifies it completes and records returned `link_strategy == 'bipartite'` on a CFAR-routed case.
4. Update `run_parallel_division_audit.py` to print/store per-route returned detector and link strategy, not only run-level labels.
5. Rerun a small bounded sample set with both CFAR and non-CFAR samples.
6. Only after that rerun the full 199-sample comparison and interpret V13/V19/V20 deltas.
