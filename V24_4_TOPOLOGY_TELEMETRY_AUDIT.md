# V24.4 Topology Telemetry Audit

Status: **complete; read-only analysis of the full-27 artifact**.

The audit consumes `v24_score_first_tracking_outputs (3).zip` and analyzes the
V24.2 shadow arm using the exact inflation definition from the V24.3 audit:

`shadow predicted nodes / V19 frozen reference predicted nodes`.

## Result

- The artifact contains all 27 samples and topology telemetry for all 27.
- The V24.2 shadow median node ratio is `1.29579`; `15/27` samples exceed
  the `1.25` ceiling under the complete cohort gate.
- Across samples, inflation has weak-to-moderate correlations with aggregate
  topology fractions: isolated `-0.3886`, degree-one `-0.1488`, degree-two
  `+0.2665`, continuation-support-zero `-0.3886`, and age-one `-0.3181`.
- Within `6bba`, the isolated correlation is `-0.3084`, degree-two is
  `+0.1910`, and age-one is `-0.2300`.
- The highest-ratio samples are connected-heavy `6bba` samples. Their pattern
  is not separable by the current aggregate histograms into weak versus
  legitimate nodes.

## Decision

Do not add a connected-node pruning rule from this audit. The telemetry proves
that isolated-node removal is not the remaining explanation, but its
per-sample distributions do not identify which connected nodes cause the
inflation.

The next measurement should be bounded per-node or per-stratum telemetry that
retains frame, age, degree, continuation support, and component identity, with
sample-level counts rather than raw coordinates. Any suppression rule must be
shadow-only, preregistered, and rescored on the complete 27-sample cohort.

The machine-readable report is `v24_4_topology_telemetry_27_report.json`.
Full-199 remains unauthorized.