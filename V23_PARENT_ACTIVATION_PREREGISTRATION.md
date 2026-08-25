# V23 Parent Activation Preregistration

Status: **development-only, read-only ranking diagnostic**.

## Purpose

Test whether parent-centered appearance and pre-division lineage history can
identify the correct anchored parent before second-daughter echo completion.
This follows two negative temporal audits: generic `t+2` return availability was
nearly universal, and parent-velocity inheritance failed across families.

## Prior Evidence and Guardrail

The earlier CFAR decoder role audit found only weak pooled parent separation:
confidence AUC `0.6323` and decoder-logit AUC `0.5901`. This experiment therefore
tests decoder evidence only as one bounded component in a narrower population.
It must not be interpreted as validating the decoder as a general ranker.

## Frozen Population

- The two anchored events in `v23_split_echo_paths.json`.
- Eligible seeds are V19/CFAR frame-`t` detections with exactly one existing
  frame-`t+1` child.
- Link-identity and missing-parent failures remain quarantined.
- Decoder evidence comes from the frozen
  `v23_cfar_decoder_evidence.csv.gz` table.
- Existing candidates, children, edges, and graphs remain unchanged.

Ground truth is used only after every seed feature and score exists to identify
the registered parent/retained-child seed and measure its rank.

## Inference-Only Features

- parent CFAR confidence and decoder logit;
- absolute confidence and decoder-logit change from the unique predecessor;
- unique-predecessor track age, capped at 20 frames;
- inverse local parent density inside `14 um`.

Every feature is converted to an event-local percentile. Missing predecessor
change receives neutral percentile `0.5`; missing decoder evidence is reported
and cannot silently receive a favorable score.

## Frozen Signals

- `confidence`: parent-confidence percentile;
- `decoder_logit`: parent-logit percentile;
- `appearance`: `0.60 confidence + 0.40 decoder_logit`;
- `precursor_change`: equal mean of confidence-change and logit-change
  percentiles;
- `history`: `0.60 track_age + 0.40 inverse_density`;
- `combined`: `0.35 appearance + 0.25 precursor_change + 0.25 track_age +
  0.15 inverse_density`.

Weights are fixed from prior directional evidence and are not fitted on these
events.

## Measurements

- correct-parent rank for every signal, by event and family;
- comparison with the frozen anchored-pair parent ranks (`109` and `22`);
- correct-parent event-local percentile and feature profile;
- decoder-evidence coverage;
- zero perturbation.

## Decision Contract

- Evidence coverage below 95% is `NO_GO_MISSING_PARENT_EVIDENCE`.
- `GO_TO_LARGER_PARENT_ACTIVATION_SHADOW`: combined rank is top 25 in both
  events, reaches at least the 90th percentile, and does not regress against the
  anchored-pair parent rank.
- `HOLD_PARENT_ACTIVATION`: at least one frozen signal puts both parents in the
  top 50 without regressing either baseline rank.
- `NO_GO_PARENT_ACTIVATION`: neither condition is met.

No outcome authorizes graph mutation, model fitting, threshold tuning, or a
full-cohort run.
