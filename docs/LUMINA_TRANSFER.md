# Lumina Transfer

Project Lumina started from a broad consciousness question, then became more useful as a
set of mechanical ideas about memory, pressure, dormant potential, and phase changes.
That is the part Atabey should borrow.

Atabey should not inherit Lumina's theatrical or consciousness-adjacent language without
translation into explicit tracking mechanics that can be tested against Kaggle outputs.

## Translation Rule

Borrow mechanisms, not claims.

If a Lumina concept cannot be restated as a bounded tracking rule, a diagnostic, or an
uncertainty label, it does not belong in Atabey.

## Concepts Worth Transferring

| Lumina concept | Atabey translation | Boundary |
| --- | --- | --- |
| Memory traces | Track-local history | Memory is not evidence of truth. |
| Dormant nodes | Latent cell candidates | Weak signals are preserved briefly, not confirmed. |
| Local pressure | Crowding, motion conflict, segmentation uncertainty | Pressure guides attention. |
| Phase transitions | Cell state transitions | State is an interpretive tracker label. |
| Predictive tension | Motion or lineage prediction error | Error is not biological proof. |
| Reflection layer | Review-oriented uncertainty note or report | Interpretation must not override measurable evidence. |

## Current Atabey Mapping

### Already implemented in working code

| Lumina concept | Atabey module | Current mechanic |
| --- | --- | --- |
| Memory traces | `src/atabey/tracking/nearest_neighbor.py` | Motion-based linking uses one-step predecessor history to predict the next position. |
| Local pressure | `src/atabey/tracking/nearest_neighbor.py` | `motion_crowding` applies a stricter identity gate only in contested neighborhoods. |
| Pressure-aware routing | `src/atabey/detection/adaptive.py` | Merged foreground profiles route to local maxima plus crowding-gated motion linking. |
| Review-oriented interpretation | `docs/BASELINE_RUNS.md` | Experimental outcomes are logged explicitly and treated as calibration rather than proof. |

### Present as scaffolding, but not yet driving the tracker

| Lumina concept | Atabey module | Current status |
| --- | --- | --- |
| Phase transitions | `src/atabey/state/cell_state.py` | State vocabulary exists, but it is not yet integrated into graph construction or evaluation. |
| Track memory | `src/atabey/state/cell_state.py` | A `CellTrackMemory` container exists, but it is not yet populated along real tracks. |
| Dormant potential | `docs/ADR-004-latent-cell-candidates.md` | The design is proposed, but no bounded latent-candidate lifecycle exists in code. |

### Still missing in a meaningful way

| Lumina concept | Atabey need | Why it matters |
| --- | --- | --- |
| Dormant nodes | Bounded latent retention and reactivation | This is the clearest path to recover short occlusions without pretending weak evidence is a confirmed cell. |
| Predictive tension | Per-track error accumulation and escalation | The tracker needs a persistent way to mark when motion predictions are degrading before links fail outright. |
| State transitions | Measured track-state updates | States should explain why a track is stable, uncertain, latent, or lost. |

## Concepts Not Transferred Directly

- consciousness or sentience framing
- narrative voice as evidence
- selfhood language
- poetic descriptions inside core tracking code
- product-like observability dashboards before baseline validity

Atabey's language should stay biological, computational, and uncertainty-aware.

## What Lumina Already Changed In Atabey

Lumina's strongest influence is not a single module. It is a design posture:

- preserve lineage history instead of treating each frame as isolated detection cleanup
- keep ambiguity visible instead of collapsing it into false certainty
- use local conflict as an attention signal
- allow interpretive layers only after the baseline submission path is valid

That posture is already visible in the move from `motion` to `motion_mutual` to
`motion_crowding`: the tracker is becoming more explicit about where identity is easy,
where it is contested, and where extra caution is justified.

## V11 Candidate: Latent Bridge

The strongest transferable Lumina mechanism that is not yet real in Atabey is dormant
potential. The clean Atabey version is a bounded latent bridge for short gaps.

### Proposal

When a previously stable track fails to link at `t+1`, do not immediately treat it as
gone. Instead:

1. move the track into a latent state for a short window such as 1 to 2 frames
2. keep a predicted position using recent motion history
3. allow a future weak or unmatched detection to reactivate the track only if it falls
   within strict distance and prediction-error bounds
4. expire the latent track if no bounded reactivation occurs

### Why this is the right next transfer

- `motion_crowding` already handles dense simultaneous ambiguity
- latent bridging targets a different failure mode: brief disappearance or partial
  detector failure
- the mechanism can improve continuity without claiming a missing cell was truly present

### Minimal implementation shape

- add a small latent-track store keyed by track id
- populate it only for tracks with enough prior history
- reactivation should require both physical proximity and acceptable prediction error
- write explicit report counters: latent entered, latent recovered, latent expired

### Safety boundaries

- latent is not confirmation
- latent tracks must expire quickly
- recovered links should remain identifiable in diagnostics
- leaderboard gain is required before expanding the mechanism

### Suggested experiment label

`v11_latent_bridge`

This should be implemented as a narrow experiment first, not as a broad state-system
rewrite.
