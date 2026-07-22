# Cross-Repository Transfer Ideas for Atabey

Date: 2026-07-20
Branch reviewed: `mitosis_hough_audit`
Status: read-only research note; no mechanism in this document is approved for implementation

## Purpose

Project Atabey is an experimental lineage-tracking research scaffold created for the Kaggle
competition
[`Biohub - Cell Tracking During Development`](https://www.kaggle.com/competitions/biohub-cell-tracking-during-development).
The competition asks participants to reconstruct developing zebrafish cell lineages from
3D microscopy recorded over time. A valid solution must do more than detect cell-like objects:
it must associate detections across frames, preserve cell identity through motion and crowding,
represent parent-to-child relationships when cells divide, and export the resulting nodes and
edges in the competition's lineage-graph format. Evaluation emphasizes temporal edge quality and
also measures division recovery.

Atabey approaches this as a streaming signal-detection and data-association problem. It explores
interpretable, CPU-conscious mechanisms such as adaptive detection, physical-coordinate motion,
bipartite linking, track-local history, explicit lineage topology, and uncertainty-preserving
shadow candidates. The research question is not simply whether cells can be segmented in one
frame, but whether a bounded and inspectable pipeline can maintain plausible lineage continuity
through noisy, dense, and ambiguous 3D+time observations.

This repository and this note are for educational and personal research purposes only. Atabey is
competition-oriented experimental code, not a validated biological model, medical device,
clinical system, or source of authoritative claims about embryonic development. Its detections,
associations, state labels, and proposed divisions are computational hypotheses evaluated against
sparse competition annotations; they must not be interpreted as confirmed biological truth.

Within that scope, this note records engineering and research patterns found across the public
repositories at
[`drosadocastro-bit`](https://github.com/drosadocastro-bit?tab=repositories) that may help
Project Atabey. Its purpose is educational as well as practical: it explains not only what an
idea is, but why it may transfer from its original domain to cell-lineage tracking, where the
analogy stops, and what evidence would be required before adopting it.

The governing rule is:

> Borrow mechanisms only when the source and target share a measurable problem structure.
> Do not borrow claims, terminology, thresholds, or confidence merely because two projects
> sound conceptually similar.

## Current Atabey Context

The most relevant unresolved V21 problem is upstream candidate formation and pairing. In
several known true-division losses, the correct pair was never formed, so neither Track A's
firewall nor Track B's ranking could evaluate it. The clearest case is
`6bba_ebdf3b34`, where parent `t13:cf520` was paired with `t14:cf31` instead of the correct
alternative `t14:cf555`.

Other established constraints shape which ideas are useful:

- Track A is frozen and remains the topology-cleanup path.
- Track B is shadow-only and must not perturb Track A.
- The first Track B ranking was a NO-GO: a few true positives remained buried in thousands of
  false-positive candidates.
- Raising the global CFAR formation gate from `9 um` to `14 um` did not solve the pairing
  problem cleanly and regressed a known true positive.
- Sparse labels are calibration evidence, not exhaustive biological truth.
- A bounded three-sample check should precede any new full 199-sample run.

These findings favor mechanisms that preserve alternatives, compare future consistency, and
strengthen reproducibility. They argue against another global threshold change.

## How Transferability Is Judged

An idea is considered plausibly transferable only when all five questions have credible
answers:

1. **Shared structure:** Do the source and Atabey face the same kind of decision or failure?
2. **Observable evidence:** Can Atabey measure the signals the mechanism needs?
3. **Bounded output:** Can the idea run in shadow mode or behind an invariant before affecting
   lineage edges?
4. **Domain boundary:** Can we state clearly what does not transfer?
5. **Cheap falsification:** Is there a bounded experiment capable of showing that the idea does
   not help?

Conceptual resemblance alone is insufficient. A transfer should survive this test before it
becomes an implementation proposal.

## Priority Summary

| Priority | Source pattern | Atabey use | Current disposition |
| --- | --- | --- | --- |
| High | Juracan candidate-outcome simulation | Compare competing daughter pairings over a short future horizon | Best next read-only audit target |
| High | Agent K paired controls and severity caps | Protect true divisions and collision lookalikes together | Extend battery design when new cases are added |
| High | Manatuabon deterministic replay manifests | Make Colab and cohort experiments reproducible and resumable | Useful infrastructure candidate |
| Medium | BirdCLEF overlap-aware inference and raw-score retention | Test temporal-boundary losses and preserve pre-gate evidence | Audit boundary clustering first |
| Medium | Julia three-strike learning rule | Prevent single-sample promotion of permanent heuristics | Adopt as research governance, not runtime learning |
| Medium | Project Aria top-k alternatives and disagreement | Retain competing pair hypotheses for review | Useful only with genuinely distinct evidence sources |
| Existing | NIC confidence fallback and fixed adversarial suite | Separate proposals from uncertain extractive evidence | Already adapted in V21; continue calibration discipline |
| Low | Yucahu paired-seed gauntlets | Compare changes on matched sample/frame conditions | Useful evaluation discipline, not a new tracker mechanism |
| Low | Project Lumina state and memory concepts | Track-local history and latent candidates | Existing Atabey concepts already cover much of this space |
| Defer | Nemotron synthetic-data workflow | Synthetic division examples or learned models | Biological realism and label scarcity remain unresolved |

## 1. Juracan: Short-Horizon Counterfactual Pairing

### Source mechanism

Juracan does not select every apparently attractive action using a static score alone. Its
decision path applies a predicted-outcome check to competitive candidates, penalizes actions
whose target outcome fails, checks whether the source survives the action, and then revalidates
hard invariants before emitting the move.

Source:
[`Juracan/main.py`](https://github.com/drosadocastro-bit/Juracan/blob/main/main.py)

### Atabey analogue

For a possible division parent, retain several plausible daughter-pair hypotheses rather than
committing immediately to the first primary match. For each hypothesis, inspect a short future
horizon, such as the next two to four frames, and measure:

- whether both proposed daughters continue to plausible detections;
- whether their trajectories remain distinct instead of immediately crossing or collapsing;
- whether acceleration and separation evolution are physically plausible;
- whether choosing one pair causes obvious orphaning or identity conflicts nearby;
- whether the alternative preserves more consistent local topology.

The result should initially be diagnostic evidence only. It should not replace the linker or
modify Track A.

### Why it is transferable

Both systems must choose among mutually exclusive candidates whose consequences become more
observable shortly after the decision. In Juracan, the consequence is a simulated strategic
outcome. In Atabey, it is temporal trajectory consistency. The transferable mechanism is
"evaluate competing actions using bounded future consequences," not game strategy itself.

This directly addresses the `cf31` versus `cf555` failure: proximity may favor one candidate at
formation time, while subsequent frames may provide evidence that the other candidate forms a
more coherent daughter trajectory.

### Where the analogy breaks

Juracan's simulator operates under explicit game rules. Cell motion, detection, and sparse
labels are noisy and partially observed. A future-consistency score in Atabey cannot be treated
as proof of lineage identity. Missing detections could make a biologically correct pairing look
temporally weak.

### Cheapest falsification test

Run a read-only audit on the known upstream-loss cases. Enumerate the original winning pair and
the known correct alternative, calculate two-to-four-frame continuation evidence for both, and
ask whether the correct pair ranks higher without changing any graph. If it cannot improve the
known cases, or if nearby collision controls also prefer false alternatives, stop before
implementation.

## 2. Agent K: Paired Controls and Severity-Aware Promotion

### Source mechanism

Agent K uses deterministic dimensions, explicit flags, severity-based score caps, and a final
verdict derived from those bounded measurements. A severe failure can cap the aggregate rather
than being hidden by good averages.

Source:
[`Agent_K/scoring/aggregator.py`](https://github.com/drosadocastro-bit/Agent_K/blob/main/src/agent_k/scoring/aggregator.py)

### Atabey analogue

Every important adversarial-battery mechanism should include paired evidence:

- a positive case that must be preserved, such as a known true division;
- a structurally similar negative control that must remain rejected, such as nearby collision
  noise;
- an explicit `not_applicable` state when the evidence required by a rule is unavailable.

Promotion can also use severity gates. For example, a change that improves mean EdgeRecall but
destroys a known high-confidence true division should not pass merely because its average is
positive.

### Why it is transferable

Both projects combine several imperfect measurements and risk hiding a critical failure inside
an aggregate score. Paired controls test both sensitivity and specificity. Severity gates keep
one destructive topology regression visible.

### Where the analogy breaks

Agent K's dimensions are deterministic policy checks. Atabey's metrics depend on sparse and
possibly incomplete biological annotations. A missed sparse label can justify investigation,
but it should not automatically be interpreted as complete biological failure.

### Cheapest falsification test

For each known Atabey true positive, identify one matched collision or wrong-pair control from a
similar timepoint and density regime. Any proposed mechanism must move the positive and negative
in the intended opposite directions. If it raises both equally, it has not learned a useful
distinction.

## 3. Manatuabon: Deterministic Replay Manifests

### Source mechanism

Manatuabon runs declared worker steps over frozen input bundles and writes a reproducible output
package. Its manifest validates supported workers and input paths before execution, making the
experiment definition independent from a fragile live session.

Source:
[`Manatuabon/replay_manifest.py`](https://github.com/drosadocastro-bit/Manatuabon/blob/main/replay_manifest.py)

### Atabey analogue

An Atabey experiment manifest could declare:

- commit SHA and branch;
- sample IDs and timepoint bounds;
- detector and link strategy requested;
- actual detector and link strategy returned;
- relevant formation and evaluation parameters;
- expected invariants, including Track A edge hash or zero perturbation;
- output CSV/log paths and optional checksums;
- completed samples so an interrupted cohort can resume safely.

### Why it is transferable

Both projects run deterministic or mostly deterministic analysis over large frozen scientific
artifacts. The important common problem is provenance: knowing exactly which code, inputs, and
settings produced a result. This is especially valuable after repeated Colab runtime resets.

### Where the analogy breaks

A manifest makes a run reproducible; it does not make its scientific interpretation valid.
Hardware, dependency, and concurrency differences may still affect runtime or expose hidden
nondeterminism.

### Cheapest falsification test

Describe the bounded three-sample run in a small manifest, execute it twice on the same commit,
and compare per-sample strategy labels, metrics, and graph hashes. Any unexplained difference is
evidence that more determinism or provenance fields are needed.

## 4. BirdCLEF: Overlap-Aware Temporal Evidence

### Source mechanism

The BirdCLEF work used overlapping windows to reduce boundary effects and retained raw
probabilities so later calibration was not forced to operate only on early hard decisions.

Sources:

- [`cibuco-boriken`](https://github.com/drosadocastro-bit/cibuco-boriken)
- [`BirdClef2026`](https://github.com/drosadocastro-bit/BirdClef2026)

### Atabey analogue

Atabey could evaluate candidate divisions from overlapping temporal contexts. A branch near one
window boundary would also be evaluated in a shifted window where more pre- and post-division
history is available. Raw pairing evidence should be preserved before the firewall or confidence
route compresses it into a decision.

### Why it is transferable

Audio events and cell divisions are temporally localized phenomena whose evidence may be split
by arbitrary window boundaries. Overlap can reduce sensitivity to where processing begins and
ends. Raw evidence retention supports later calibration and forensic review.

### Where the analogy breaks

An audio window can often be shifted without changing the event. Cell tracking has graph state
and identity commitments that propagate across frames. Two overlapping tracking windows may
produce incompatible node identities, so reconciliation is harder than averaging probabilities.

### Cheapest falsification test

First measure whether known pairing losses are concentrated near bounded-run starts, ends, or
insufficient-history locations. If no boundary association exists, overlap is unlikely to solve
the current bottleneck. Do not build overlap machinery before this audit.

## 5. Julia: Three-Strike Research Governance

### Source mechanism

Julia records repeated failures under matching conditions. One or two failures remain active
corrections; the third identical failure can promote a persistent behavior change.

Source:
[`Julia/agentic/learner.py`](https://github.com/drosadocastro-bit/Julia/blob/main/julia/agentic/learner.py)

### Atabey analogue

Use a three-strike rule for research promotion, not online self-modification:

- one case creates a hypothesis;
- a second independent case justifies a bounded diagnostic;
- a third independent case with the same failure signature, plus paired negative controls,
  permits consideration of a frozen rule or structural change.

### Why it is transferable

Atabey repeatedly saw thresholds that looked conclusive on one sample and failed on larger
cohorts. Requiring recurrence under comparable conditions directly protects against
single-sample overfitting.

### Where the analogy breaks

"Identical conditions" are easy to hash in a controlled software system and difficult to define
for biological samples. Three cases are a governance minimum, not statistical validation, and
should never replace cohort analysis.

### Cheapest falsification test

Apply the rule retrospectively to the Hough, velocity-correction, firewall, and `14 um` gate
investigations. Record which premature changes would have been delayed and whether any useful
change would have been blocked unnecessarily.

## 6. Project Aria: Top-K Alternatives and Disagreement

### Source mechanism

Project Aria preserves alternative predictions, confidence, provenance, and fallback stages
rather than exposing only one opaque classification result.

Source:
[`Project-Aria`](https://github.com/drosadocastro-bit/Project-Aria)

### Atabey analogue

For ambiguous parents, retain the top few daughter-pair hypotheses and the evidence contributed
by motion, distance, branch geometry, local density, and future continuation. Disagreement among
independent evidence channels can prioritize a case for shadow review.

### Why it is transferable

Both tasks face ambiguous classifications where the top choice may be only marginally better
than an alternative. Preserving alternatives prevents early information loss and makes upstream
pairing failures inspectable.

### Where the analogy breaks

Several scores calculated from the same coordinates are correlated, not independent votes.
Calling their agreement "confidence" would be misleading. This approach becomes valuable only
when evidence provenance remains visible and calibration is empirical.

### Cheapest falsification test

Using existing candidate exports, reconstruct top-k pair alternatives for the known losses and
measure whether the correct pair was present near the top. If it was not generated at all,
top-k retention alone cannot solve candidate formation.

## 7. NIC: Confidence Routing and Accumulative Adversarial Testing

### Source mechanism already transferred

NIC separates sufficiently supported synthesis from a lower-confidence extractive fallback and
uses a fixed, version-controlled adversarial suite. Atabey has already adapted these ideas:

- uncalibrated Track B candidates route to `extractive_flagged` rather than fabricated
  confidence;
- the Atabey adversarial battery is fixed and append-only;
- Track B remains independent from Track A.

Source:
[`nova_rag_public`](https://github.com/drosadocastro-bit/nova_rag_public)

### Why the transfer remains valid

The shared mechanism is abstention under insufficient support. In NIC, extractive mode preserves
source-grounded text. In Atabey, the analogue preserves candidate IDs and measurable evidence
without committing division edges.

### Boundary to preserve

NIC's `0.60` threshold is not a biological constant. Atabey must not use it until Track B has a
calibrated probability model with enough positive and negative evidence. The current ranking
score is not such a probability.

## Supporting Evaluation Patterns

### Yucahu: matched comparisons

Yucahu's paired-seed and gauntlet discipline supports matched Atabey comparisons: the same
sample, timepoints, detections, and graph source should be evaluated with the candidate mechanism
active and shadowed. This reduces confounding but does not create causal certainty by itself.

Source: [`Yucahu`](https://github.com/drosadocastro-bit/Yucahu)

### Project Lumina: bounded state concepts

Lumina inspired track-local memory, latent candidates, and explicit state transitions already
described in Atabey's architecture. More memory or regulatory-state machinery is low priority
because it risks duplicating existing concepts before upstream pairing is understood.

Source: [`Project-Lumina`](https://github.com/drosadocastro-bit/Project-Lumina)

### Nemotron archive: synthetic experiment discipline

The Nemotron repository demonstrates experiment archiving and separation of large generated
artifacts from code. Synthetic division data might eventually help stress-test mechanics, but it
should be deferred until the simulation's biological realism can be evaluated. Synthetic success
must remain separate from validation on observed microscopy.

Source:
[`nvidianemotronchallenge2026`](https://github.com/drosadocastro-bit/nvidianemotronchallenge2026)

## Repository Coverage

The public profile review covered the following 13 visible repositories:

| Repository | Role in this audit |
| --- | --- |
| `nova_rag_public` | confidence fallback and adversarial-suite source |
| `Project-Aria` | top-k alternatives, confidence provenance, staged fallback |
| `nvidianemotronchallenge2026` | experiment archive and synthetic-data caution |
| `BirdClef2026` | overlap-aware temporal inference |
| `cibuco-boriken` | BirdCLEF implementation and lessons |
| `Manatuabon` | deterministic replay manifests and frozen evidence bundles |
| `Julia` | three-strike promotion discipline |
| `Yucahu` | matched gauntlets and comparison discipline |
| `Project-Lumina` | bounded conceptual source already represented in Atabey |
| `Juracan` | candidate prediction, short-horizon evaluation, hard invariants |
| `drosadocastro-bit` | profile-level research principles; no separate tracker mechanism |
| `Agent_K` | paired deterministic checks and severity-aware aggregation |
| `Atabey` | target repository, not an external transfer source |

Private or otherwise non-visible repositories are outside the evidence base of this audit.

## Recommended Learning Sequence

No new implementation is recommended before the pending bounded V21 run. After that result:

1. Perform the Juracan-inspired counterfactual pairing audit on known upstream losses.
2. Add paired positive/negative evidence whenever the adversarial battery gains a new mechanism.
3. Consider a Manatuabon-style replay manifest before another expensive Colab cohort run.
4. Audit temporal-boundary clustering before considering overlap-aware inference.
5. Apply the Julia three-strike rule before promoting any new permanent heuristic.
6. Preserve top-k pairing evidence only if the correct alternatives are actually being formed.

## Bottom Line

The most promising transfer is not another threshold. It is Juracan's bounded evaluation of
competing decisions using their short-horizon consequences, translated into a shadow-only test
of daughter-pair continuation. Manatuabon's reproducibility pattern and Agent K's paired controls
are the strongest supporting practices.

These ideas are transferable because they address structures Atabey genuinely shares with the
source projects: ambiguous alternatives, delayed evidence, costly runs, incomplete confidence,
and the danger of averages hiding critical failures. They remain hypotheses until bounded Atabey
evidence supports them.
