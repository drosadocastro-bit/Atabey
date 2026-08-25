# V24.3 Node-Inflation Decomposition

Status: **complete; read-only decomposition**.

V24.3 consumes the V24.2 full-27 Kaggle `per_sample.csv`. It separates the
nodes explicitly removed by V24.2 from the nodes that remain after pruning,
then summarizes the residual ratio by family and detector route.

## Result

- V24.2 removed `9,145` nodes across `19/27` samples.
- Every removal occurred in `6bba/components`; both `44b6` controls and all
  `cfar_sidelobe` samples were unchanged.
- The remaining shadow node ratio still exceeds `1.25` in `14/22` `6bba`
  samples and `14/19` `components` samples.
- `6bba` median shadow ratio is `1.34343`; overall median is `1.29579`.
- All recorded edge-set-preservation checks remain true.

The machine-readable report is
`v24_2_node_inflation_decomposition_27_report.json`.

## Interpretation Boundary

The CSV records removal counts, not node topology. Therefore the residual
nodes cannot be labeled as weak or legitimate from this audit. A further
suppression rule must first add node-level telemetry such as frame position,
track age, degree, and continuation support, then be preregistered and scored
against the complete cohort. Full-199 remains unauthorized.