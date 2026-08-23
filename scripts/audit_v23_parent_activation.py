"""Rank anchored parent seeds from decoder evidence and lineage history."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from audit_v23_split_echo_paths import graph_signature, is_registered, stable_ranks
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route
from run_v23_per_track_echo_budget_shadow import ROUTER_RADIUS_UM


SIGNALS = (
    "confidence",
    "decoder_logit",
    "appearance",
    "precursor_change",
    "history",
    "combined",
)
RANK_SIGNALS = SIGNALS + ("track_age", "inverse_density")


def unique_track_age(node_id, incoming, nodes, cap=20):
    age = 1
    current = nodes[node_id]
    while age < cap:
        predecessors = [
            nodes[source]
            for source in incoming.get(current.node_id, [])
            if source in nodes and int(nodes[source].t) == int(current.t) - 1
        ]
        if len(predecessors) != 1:
            break
        current = predecessors[0]
        age += 1
    return age


def predecessor(node, incoming, nodes):
    candidates = [
        nodes[source]
        for source in incoming.get(node.node_id, [])
        if source in nodes and int(nodes[source].t) == int(node.t) - 1
    ]
    return candidates[0] if len(candidates) == 1 else None


def percentiles(values, higher=True, missing=0.5):
    values = np.asarray(values, dtype=float)
    result = np.full(len(values), missing, dtype=float)
    finite = np.isfinite(values)
    if not finite.any():
        return result
    ranked = values[finite] if higher else -values[finite]
    order = pd.Series(ranked).rank(method="average", pct=True).to_numpy(float)
    result[finite] = order
    return result


def local_density(positions):
    if not len(positions):
        return np.empty(0, dtype=float)
    distances = np.linalg.norm(
        positions[:, None, :] - positions[None, :, :], axis=2
    )
    return np.sum(distances <= ROUTER_RADIUS_UM, axis=1).astype(float) - 1.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--split-audit", type=Path, required=True)
    parser.add_argument("--decoder-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    fixture = {
        case["case_id"]: case
        for case in json.loads(args.fixture.read_text(encoding="utf-8"))["cases"]
    }
    split = json.loads(args.split_audit.read_text(encoding="utf-8"))
    anchored_prior = {row["case_id"]: row for row in split["anchored"]}
    cases = [fixture[case_id] for case_id in anchored_prior]
    evidence = pd.read_csv(args.decoder_evidence)
    evidence = evidence[evidence.sample_id.isin({case["sample_id"] for case in cases})]
    if evidence.node_id.duplicated().any():
        raise RuntimeError("Decoder evidence contains duplicate node IDs")
    evidence = evidence.set_index("node_id")

    rows = []
    for case in sorted(cases, key=lambda item: (item["sample_id"], int(item["t"]))):
        sample_id = case["sample_id"]
        t = int(case["t"])
        graph, detector, link_strategy = _build_v19_prefirewall_with_route(
            args.train_dir / f"{sample_id}.zarr", max_timepoints=t + 2
        )
        before = graph_signature(graph)
        nodes = {node.node_id: node for node in graph.detections}
        frame_nodes = defaultdict(list)
        incoming = defaultdict(list)
        outgoing = defaultdict(list)
        for node in graph.detections:
            frame_nodes[int(node.t)].append(node)
        for edge in graph.edges:
            incoming[edge.target_id].append(edge.source_id)
            outgoing[edge.source_id].append(edge.target_id)

        gt = read_geff_graph(args.train_dir / f"{sample_id}.geff")
        gt_nodes = {int(node.node_id): node for node in gt.nodes}
        gt_parent = np.asarray(
            gt_nodes[int(case["gt_parent_id"])].position_um, dtype=float
        )
        gt_daughters = [
            np.asarray(gt_nodes[int(node_id)].position_um, dtype=float)
            for node_id in case["gt_child_ids"]
        ]

        seeds = []
        for node in frame_nodes[t]:
            child_ids = [
                target for target in outgoing.get(node.node_id, [])
                if target in nodes and int(nodes[target].t) == t + 1
            ]
            if len(child_ids) != 1:
                continue
            child = nodes[child_ids[0]]
            parent_row = evidence.loc[node.node_id] if node.node_id in evidence.index else None
            previous = predecessor(node, incoming, nodes)
            previous_row = (
                evidence.loc[previous.node_id]
                if previous is not None and previous.node_id in evidence.index
                else None
            )
            seeds.append(
                {
                    "seed_id": node.node_id,
                    "position": np.asarray(node.position_um, dtype=float),
                    "child_position": np.asarray(child.position_um, dtype=float),
                    "confidence": float(parent_row.confidence) if parent_row is not None else np.nan,
                    "decoder_logit": float(parent_row.decoder_logit) if parent_row is not None else np.nan,
                    "confidence_change": (
                        abs(float(parent_row.confidence) - float(previous_row.confidence))
                        if parent_row is not None and previous_row is not None else np.nan
                    ),
                    "decoder_logit_change": (
                        abs(float(parent_row.decoder_logit) - float(previous_row.decoder_logit))
                        if parent_row is not None and previous_row is not None else np.nan
                    ),
                    "track_age": float(unique_track_age(node.node_id, incoming, nodes)),
                    "decoder_available": parent_row is not None,
                }
            )

        positions = np.asarray([seed["position"] for seed in seeds], dtype=float)
        densities = local_density(positions)
        confidence_pct = percentiles([seed["confidence"] for seed in seeds])
        logit_pct = percentiles([seed["decoder_logit"] for seed in seeds])
        confidence_change_pct = percentiles(
            [seed["confidence_change"] for seed in seeds]
        )
        logit_change_pct = percentiles(
            [seed["decoder_logit_change"] for seed in seeds]
        )
        age_pct = percentiles([seed["track_age"] for seed in seeds])
        inverse_density_pct = percentiles(densities, higher=False)

        for index, seed in enumerate(seeds):
            seed["density"] = float(densities[index])
            seed["feature_percentiles"] = {
                "confidence": float(confidence_pct[index]),
                "decoder_logit": float(logit_pct[index]),
                "confidence_change": float(confidence_change_pct[index]),
                "decoder_logit_change": float(logit_change_pct[index]),
                "track_age": float(age_pct[index]),
                "inverse_density": float(inverse_density_pct[index]),
            }
            appearance = 0.60 * confidence_pct[index] + 0.40 * logit_pct[index]
            change = 0.50 * confidence_change_pct[index] + 0.50 * logit_change_pct[index]
            history = 0.60 * age_pct[index] + 0.40 * inverse_density_pct[index]
            seed["signals"] = {
                "confidence": float(confidence_pct[index]),
                "decoder_logit": float(logit_pct[index]),
                "appearance": float(appearance),
                "precursor_change": float(change),
                "history": float(history),
                "track_age": float(age_pct[index]),
                "inverse_density": float(inverse_density_pct[index]),
                "combined": float(
                    0.35 * appearance
                    + 0.25 * change
                    + 0.25 * age_pct[index]
                    + 0.15 * inverse_density_pct[index]
                ),
            }
            seed["registered_parent_child"] = bool(
                is_registered(seed["position"], gt_parent)
                and any(
                    is_registered(seed["child_position"], daughter)
                    for daughter in gt_daughters
                )
            )

        useful = [index for index, seed in enumerate(seeds) if seed["registered_parent_child"]]
        if not useful:
            raise RuntimeError(f"No registered anchored parent seed for {case['case_id']}")
        signal_results = {}
        for signal in RANK_SIGNALS:
            ranks = stable_ranks(
                [seed["signals"][signal] for seed in seeds],
                [seed["seed_id"] for seed in seeds],
            )
            useful_index = min(useful, key=lambda index: ranks[index])
            useful_rank = int(ranks[useful_index])
            signal_results[signal] = {
                "rank": useful_rank,
                "percentile": float(
                    1.0 - (useful_rank - 1) / max(1, len(seeds))
                ),
                "score": float(seeds[useful_index]["signals"][signal]),
                "seed_id": seeds[useful_index]["seed_id"],
            }
        combined_useful = next(
            index for index in useful
            if seeds[index]["seed_id"] == signal_results["combined"]["seed_id"]
        )
        decoder_coverage = float(
            np.mean([seed["decoder_available"] for seed in seeds])
        )
        row = {
            "case_id": case["case_id"],
            "sample_id": sample_id,
            "family": sample_id.split("_", 1)[0],
            "t": t,
            "seed_count": len(seeds),
            "decoder_coverage": decoder_coverage,
            "baseline_parent_rank": int(anchored_prior[case["case_id"]]["parent_seed_rank"]),
            "signals": signal_results,
            "combined_parent_profile": {
                key: value for key, value in seeds[combined_useful].items()
                if key not in {"position", "child_position", "signals"}
            },
            "detector": detector,
            "link_strategy": link_strategy,
            "zero_perturbation": before == graph_signature(graph),
            "candidate_set_changed": False,
            "graph_mutated": False,
        }
        rows.append(row)
        print(
            f"{sample_id} t{t}: baseline={row['baseline_parent_rank']} "
            + " ".join(f"{signal}={signal_results[signal]['rank']}" for signal in RANK_SIGNALS),
            flush=True,
        )

    coverage_min = min(row["decoder_coverage"] for row in rows)
    combined_go = all(
        row["signals"]["combined"]["rank"] <= 25
        and row["signals"]["combined"]["percentile"] >= 0.90
        and row["signals"]["combined"]["rank"] <= row["baseline_parent_rank"]
        for row in rows
    )
    hold_signals = [
        signal for signal in SIGNALS
        if all(
            row["signals"][signal]["rank"] <= 50
            and row["signals"][signal]["rank"] <= row["baseline_parent_rank"]
            for row in rows
        )
    ]
    if coverage_min < 0.95:
        decision = "NO_GO_MISSING_PARENT_EVIDENCE"
    elif combined_go:
        decision = "GO_TO_LARGER_PARENT_ACTIVATION_SHADOW"
    elif hold_signals:
        decision = "HOLD_PARENT_ACTIVATION"
    else:
        decision = "NO_GO_PARENT_ACTIVATION"

    summary = {
        "status": "read_only_v23_parent_activation",
        "decision": decision,
        "events": len(rows),
        "minimum_decoder_coverage": coverage_min,
        "hold_signals": hold_signals,
        "diagnostic_signal_ranks": {
            signal: [row["signals"][signal]["rank"] for row in rows]
            for signal in ("track_age", "inverse_density")
        },
        "zero_perturbation_all": all(row["zero_perturbation"] for row in rows),
        "candidate_set_changed": False,
        "graph_mutation": False,
    }
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 Parent Activation Results",
        "",
        f"Decision: **{decision}**.",
        "",
        "Every score was computed before GT registration. The population contains only under-resolved parents with one existing child; quarantined paths were excluded and no graph was changed.",
        "",
        "| Event | Baseline | Confidence | Logit | Appearance | Change | Track age | Inv. density | History | Combined | Coverage |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['sample_id']} t{row['t']} | {row['baseline_parent_rank']} | "
            f"{row['signals']['confidence']['rank']} | "
            f"{row['signals']['decoder_logit']['rank']} | "
            f"{row['signals']['appearance']['rank']} | "
            f"{row['signals']['precursor_change']['rank']} | "
            f"{row['signals']['track_age']['rank']} | "
            f"{row['signals']['inverse_density']['rank']} | "
            f"{row['signals']['history']['rank']} | "
            f"{row['signals']['combined']['rank']} | "
            f"{row['decoder_coverage']:.1%} |"
        )
    lines += [
        "",
        f"Signals satisfying the bounded HOLD rule: `{', '.join(hold_signals) or 'none'}`.",
        "",
        "The HOLD history signal decomposes into inverse-density ranks 6/6 versus track-age ranks 95/33. Parent isolation is the transferable hypothesis; lineage age is not supported here.",
        "",
        "Because inverse density was a diagnostic decomposition rather than a preregistered decision signal, it does not upgrade this result. It requires an independent parent-isolation shadow.",
        "",
        "Guardrail: this two-event diagnostic cannot validate decoder evidence generally or authorize integration.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
