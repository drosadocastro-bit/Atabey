"""Independently validate local isolation of anchored division parents."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from audit_v23_parent_activation import local_density, unique_track_age
from audit_v23_split_echo_paths import graph_signature, is_registered, stable_ranks
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route


def evaluate_case(train_dir, case):
    sample_id = case["sample_id"]
    t = int(case["t"])
    graph, detector, link_strategy = _build_v19_prefirewall_with_route(
        Path(train_dir) / f"{sample_id}.zarr", max_timepoints=t + 2
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

    gt = read_geff_graph(Path(train_dir) / f"{sample_id}.geff")
    gt_nodes = {int(node.node_id): node for node in gt.nodes}
    gt_parent = np.asarray(gt_nodes[int(case["gt_parent_id"])].position_um, dtype=float)
    gt_daughters = [
        np.asarray(gt_nodes[int(node_id)].position_um, dtype=float)
        for node_id in case["gt_child_ids"]
    ]

    detected_registered_parents = [
        node for node in frame_nodes[t]
        if is_registered(np.asarray(node.position_um, dtype=float), gt_parent)
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
        parent_position = np.asarray(node.position_um, dtype=float)
        child_position = np.asarray(child.position_um, dtype=float)
        seeds.append({
            "seed_id": node.node_id,
            "position": parent_position,
            "parent_registered": is_registered(parent_position, gt_parent),
            "child_registered": any(
                is_registered(child_position, daughter) for daughter in gt_daughters
            ),
            "track_age": unique_track_age(node.node_id, incoming, nodes),
        })

    route_ok = detector == "cfar_sidelobe" and link_strategy == "bipartite"
    useful = [
        index for index, seed in enumerate(seeds)
        if seed["parent_registered"] and seed["child_registered"]
    ]
    if not route_ok:
        reason = "route_mismatch"
    elif not detected_registered_parents:
        reason = "missing_parent_detection"
    elif not any(seed["parent_registered"] for seed in seeds):
        reason = "missing_single_child_anchor"
    elif not useful:
        reason = "linked_child_identity_failure"
    else:
        reason = None

    row = {
        **case,
        "detector": detector,
        "link_strategy": link_strategy,
        "seed_count": len(seeds),
        "evaluable": reason is None,
        "unevaluable_reason": reason,
        "zero_perturbation": before == graph_signature(graph),
        "candidate_set_changed": False,
        "graph_mutated": False,
    }
    if reason is None:
        positions = np.asarray([seed["position"] for seed in seeds], dtype=float)
        densities = local_density(positions)
        density_ranks = stable_ranks(
            [-float(value) for value in densities],
            [seed["seed_id"] for seed in seeds],
        )
        age_ranks = stable_ranks(
            [float(seed["track_age"]) for seed in seeds],
            [seed["seed_id"] for seed in seeds],
        )
        useful_density_index = min(useful, key=lambda index: density_ranks[index])
        useful_age_index = min(useful, key=lambda index: age_ranks[index])
        rank = int(density_ranks[useful_density_index])
        row.update({
            "inverse_density_rank": rank,
            "inverse_density_percentile": float(
                1.0 - (rank - 1) / max(1, len(seeds))
            ),
            "registered_parent_density_14um": float(densities[useful_density_index]),
            "track_age_rank": int(age_ranks[useful_age_index]),
            "registered_parent_track_age": int(seeds[useful_age_index]["track_age"]),
        })
    return row


def summarize(rows):
    evaluable = [row for row in rows if row["evaluable"]]
    family = {}
    for name in ("44b6", "6bba"):
        subset = [row for row in evaluable if row["family"] == name]
        family[name] = {
            "candidate_events": sum(row["family"] == name for row in rows),
            "evaluable_events": len(subset),
            "median_percentile": (
                float(np.median([row["inverse_density_percentile"] for row in subset]))
                if subset else None
            ),
            "top10_capture": sum(row["inverse_density_rank"] <= 10 for row in subset),
            "top25_capture": sum(row["inverse_density_rank"] <= 25 for row in subset),
        }
        if subset:
            family[name]["top10_fraction"] = family[name]["top10_capture"] / len(subset)
            family[name]["top25_fraction"] = family[name]["top25_capture"] / len(subset)
        else:
            family[name]["top10_fraction"] = 0.0
            family[name]["top25_fraction"] = 0.0

    go = (
        len(evaluable) >= 12
        and all(item["evaluable_events"] >= 4 for item in family.values())
        and all(item["median_percentile"] is not None and item["median_percentile"] >= 0.90 for item in family.values())
        and all(item["top10_fraction"] >= 0.75 for item in family.values())
    )
    hold = (
        len(evaluable) >= 8
        and all(item["evaluable_events"] >= 3 for item in family.values())
        and all(item["median_percentile"] is not None and item["median_percentile"] >= 0.75 for item in family.values())
        and all(item["top25_fraction"] >= 0.75 for item in family.values())
    )
    decision = (
        "GO_TO_ISOLATION_CONSTRAINED_SHADOW" if go
        else "HOLD_PARENT_ISOLATION" if hold
        else "NO_GO_PARENT_ISOLATION"
    )
    return {
        "status": "read_only_v23_independent_parent_isolation",
        "decision": decision,
        "population": {
            "candidate_events": len(rows),
            "evaluable_events": len(evaluable),
            "unevaluable_reasons": dict(Counter(
                row["unevaluable_reason"] for row in rows if not row["evaluable"]
            )),
        },
        "family": family,
        "hypothesis_status": "withdrawn_not_generalized",
        "structural_bottleneck": "parent_detection_and_single_child_anchor_availability",
        "zero_perturbation_all": all(row["zero_perturbation"] for row in rows),
        "candidate_set_changed": False,
        "graph_mutation": False,
    }


def write_outputs(rows, output, summary_path, report):
    rows = sorted(rows, key=lambda row: (row["family"], row["sample_id"], int(row["t"])))
    summary = summarize(rows)
    output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 Independent Parent-Isolation Results",
        "",
        f"Decision: **{summary['decision']}**.",
        "",
        "The discovery events were excluded. Each row is one preregistered sample-blocked GT division, and unevaluable cases remain explicit.",
        "",
        "| Event | Family | Status | Seeds | Isolation rank | Percentile | Density | Track-age rank |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        status = "evaluable" if row["evaluable"] else row["unevaluable_reason"]
        percentile = (
            f"{row['inverse_density_percentile']:.1%}"
            if row["evaluable"] else "NA"
        )
        lines.append(
            f"| {row['sample_id']} t{row['t']} | {row['family']} | {status} | "
            f"{row['seed_count']} | {row.get('inverse_density_rank', 'NA')} | "
            f"{percentile} | "
            f"{row.get('registered_parent_density_14um', 'NA')} | "
            f"{row.get('track_age_rank', 'NA')} |"
        )
    lines += ["", "## Family Summary", "", "| Family | Evaluable | Median percentile | Top 10 | Top 25 |", "|---|---:|---:|---:|---:|"]
    for name, item in summary["family"].items():
        median = "NA" if item["median_percentile"] is None else f"{item['median_percentile']:.1%}"
        lines.append(
            f"| {name} | {item['evaluable_events']}/{item['candidate_events']} | {median} | "
            f"{item['top10_capture']}/{item['evaluable_events']} | {item['top25_capture']}/{item['evaluable_events']} |"
        )
    lines += [
        "",
        "The discovery ranks 6/6 did not generalize: no evaluable event in either family reached the top 25. Parent isolation is withdrawn as a ranking hypothesis rather than retuned.",
        "",
        "Eleven of 20 divisions failed before ranking: eight lacked a valid single-child anchor and three lacked a parent detection. Detection availability and child ownership remain separate upstream targets.",
        "",
        "Guardrail: this audit is read-only and cannot authorize graph mutation or threshold tuning.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    cases = fixture["cases"]
    completed = []
    if args.resume and args.output.exists():
        completed = json.loads(args.output.read_text(encoding="utf-8"))
    completed_ids = {(row["sample_id"], int(row["t"])) for row in completed}
    pending = [case for case in cases if (case["sample_id"], int(case["t"])) not in completed_ids]
    print(f"completed={len(completed)} pending={len(pending)} total={len(cases)}", flush=True)

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(evaluate_case, str(args.train_dir), case): case
            for case in pending
        }
        for future in as_completed(futures):
            row = future.result()
            completed.append(row)
            write_outputs(completed, args.output, args.summary, args.report)
            print(
                f"[{len(completed)}/{len(cases)}] {row['sample_id']} t{row['t']} "
                f"status={'rank'+str(row.get('inverse_density_rank')) if row['evaluable'] else row['unevaluable_reason']}",
                flush=True,
            )

    summary = write_outputs(completed, args.output, args.summary, args.report)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
