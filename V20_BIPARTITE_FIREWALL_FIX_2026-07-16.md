# V20 Bipartite Firewall Fix - 2026-07-16

## Scope

Read-only threshold guardrail honored: no angle, drift, velocity, or detector thresholds were tuned in this pass.

The goal was to repair the broken V20 bipartite + division_firewall integration path, add regression coverage, expose true per-sample strategy routing, and run bounded verification before any full-cohort interpretation.

## Changes Made

- Added `LineageGraph.remove_edge(edge)` in `src/atabey/types.py`, matching the method expected by `prune_invalid_divisions()`.
- Added `tests/test_division_firewall.py`:
  - synthetic unit coverage for `prune_invalid_divisions()` with one valid two-child branch and one invalid branch.
  - local-data smoke coverage for `_build_v20_graph(..., cfar_link_strategy="bipartite")` on `6bba_05db0fb1`, asserting the builder completes and returns `link_strategy == "bipartite"`.
- Registered the `slow` pytest marker in `pyproject.toml`.
- Updated `scripts/run_parallel_division_audit.py`:
  - captures returned detector/link strategy for V13, V19, and V20 instead of discarding them.
  - prints per-sample detector/link strategy.
  - summarizes actual detector/link route counts.
  - adds `--max-timepoints` for bounded verification runs.
  - uses an absolute project-root V20 CNN weights path.

## Verification

Focused tests:

```text
python -m pytest D:\Project-Atabey\tests\test_division_firewall.py -q
2 passed in 29.40s
```

Full suite:

```text
python -m pytest -q
89 passed in 29.00s
```

Bounded audit command:

```text
python D:\Project-Atabey\scripts\run_parallel_division_audit.py --workers 1 --sample-ids 44b6_24264f12 6bba_05db0fb1 --cfar-link-strategy bipartite --max-timepoints 8
```

Bounded route results:

```text
44b6_24264f12:
  V13 detector=components link=greedy EdgeRecall=1.0
  V19 detector=components link=greedy EdgeRecall=1.0
  V20 (Bipartite) detector=components link=greedy EdgeRecall=1.0

6bba_05db0fb1:
  V13 detector=local_maxima link=motion_mutual DivJ=0.0 EdgeRecall=0.7857142857142857
  V19 detector=cfar_sidelobe link=bipartite DivJ=0.0 EdgeRecall=0.76
  V20 (Bipartite) detector=v20_firewall link=bipartite DivJ=0.0 EdgeRecall=1.0
```

Interpretation: the previous `LineageGraph.remove_edge()` crash is fixed. The CFAR-routed sample now completes through the actual `v20_firewall|bipartite` path. The non-CFAR sample correctly reports `components|greedy`, proving the audit can now distinguish true bipartite execution from non-applicable routing.

## Missing Docs Search

Searched for these referenced docs:

- `DIVISION_JACCARD_INVESTIGATION_SUMMARY.md`
- `HOUGH_MITOSIS_PRECURSOR_AUDIT.md`
- `DIVISION_TOPOLOGY_DESIGN.md`

Checks performed:

- `rg --files D:\Project-Atabey`
- `git -C D:\Project-Atabey log --all --name-only`
- `C:\Users\draku\OneDrive\Documents` recursive filename search
- narrowed `D:\` filename search excluding large/protected non-workspace folders

Result: no matching files were found. A full raw recursive `D:\` PowerShell search timed out after 120 seconds, so the result is best read as "not found in the repo, Git history, OneDrive workspace, or narrowed likely D: workspace search," not a proof that the names do not exist anywhere on disk.

## Next Step

The code path is now ready for a full 199-sample run with `--cfar-link-strategy bipartite`, but any metric interpretation should use the new per-sample detector/link route confirmation.
