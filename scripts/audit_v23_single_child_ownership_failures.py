"""Diagnose frozen single-child-anchor failures without changing the graph."""

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
from audit_v23_split_echo_paths import graph_signature, is_registered
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route


FORMATION_RADIUS_UM = 14.0


def distance(left, right) -> float:
    return float(np.linalg.norm(np.asarray(left, dtype=float) - np.asarray(right, dtype=float)))


def evaluate_case(train_dir: str, case: dict) -> dict:
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
        np.asarray(gt_nodes[int(child_id)].position_um, dtype=float)
        for child_id in case["gt_child_ids"]
    ]

    parent_candidates = [
        node for node in frame_nodes[t]
        if is_registered(np.asarray(node.position_um, dtype=float), gt_parent)
    ]
    parent_ids = {node.node_id for node in parent_candidates}
    parent_details = []
    for parent in parent_candidates:
        next_children = [
            target_id for target_id in outgoing.get(parent.node_id, [])
            if target_id in nodes and int(nodes[target_id].t) == t + 1
        ]
        child_details = []
        for child_id in next_children:
            child = nodes[child_id]
            child_position = np.asarray(child.position_um, dtype=float)
            child_details.append({
                "child_id": child_id,
                "distance_to_parent_um": distance(parent.position_um, child.position_um),
                "registered_daughter_indices": [
                    index for index, daughter in enumerate(gt_daughters)
                    if is_registered(child_position, daughter)
                ],
            })
        parent_details.append({
            "parent_id": parent.node_id,
            "distance_to_gt_parent_um": distance(parent.position_um, gt_parent),
            "next_frame_outgoing_count": len(next_children),
            "next_frame_children": child_details,
        })

    daughter_details = []
    for daughter_index, daughter in enumerate(gt_daughters):
        candidates = [
            node for node in frame_nodes[t + 1]
            if is_registered(np.asarray(node.position_um, dtype=float), daughter)
        ]
        candidates.sort(key=lambda node: (distance(node.position_um, daughter), node.node_id))
        candidate_details = []
        for child in candidates:
            owners = []
            for source_id in incoming.get(child.node_id, []):
                source = nodes.get(source_id)
                owners.append({
                    "parent_id": source_id,
                    "is_registered_gt_parent": source_id in parent_ids,
                    "distance_to_child_um": (
                        distance(source.position_um, child.position_um) if source else None
                    ),
                    "distance_to_gt_parent_um": (
                        distance(source.position_um, gt_parent) if source else None
                    ),
                    "plausible_owner_within_14um": bool(
                        source is not None
                        and int(source.t) == t
                        and distance(source.position_um, child.position_um) <= FORMATION_RADIUS_UM
                    ),
                })
            candidate_details.append({
                "child_id": child.node_id,
                "distance_to_gt_daughter_um": distance(child.position_um, daughter),
                "owners": owners,
                "ownership": (
                    "owned_by_registered_parent" if any(owner["is_registered_gt_parent"] for owner in owners)
                    else "owned_by_other_parent" if owners
                    else "unowned"
                ),
            })
        daughter_details.append({
            "daughter_index": daughter_index,
            "candidate_count": len(candidate_details),
            "candidates": candidate_details,
        })

    outgoing_counts = [item["next_frame_outgoing_count"] for item in parent_details]
    nearest_daughter_candidates = [
        item["candidates"][0] if item["candidates"] else None for item in daughter_details
    ]
    nearest_ownership = [
        item["ownership"] if item is not None else "missing_detection"
        for item in nearest_daughter_candidates
    ]
    distinct_nearest_daughters = bool(
        all(item is not None for item in nearest_daughter_candidates)
        and nearest_daughter_candidates[0]["child_id"] != nearest_daughter_candidates[1]["child_id"]
    )

    if not parent_candidates:
        diagnosis = "missing_parent_detection"
    elif any(count > 1 for count in outgoing_counts):
        diagnosis = "registered_parent_has_multiple_children"
    elif all(count == 0 for count in outgoing_counts):
        if "owned_by_other_parent" in nearest_ownership:
            diagnosis = "registered_parent_childless_daughter_claimed_elsewhere"
        elif "missing_detection" in nearest_ownership:
            diagnosis = "registered_parent_childless_missing_daughter_detection"
        else:
            diagnosis = "registered_parent_childless_daughters_unowned"
    else:
        diagnosis = "mixed_registered_parent_states"

    return {
        **case,
        "detector": detector,
        "link_strategy": link_strategy,
        "registered_parent_count": len(parent_candidates),
        "registered_parent_outgoing_counts": outgoing_counts,
        "parent_details": parent_details,
        "daughter_details": daughter_details,
        "nearest_daughter_ownership": nearest_ownership,
        "distinct_nearest_daughters": distinct_nearest_daughters,
        "diagnosis": diagnosis,
        "zero_perturbation": before == graph_signature(graph),
        "candidate_set_changed": False,
        "graph_mutated": False,
    }


def summarize(rows: list[dict]) -> dict:
    family = {}
    for name in ("44b6", "6bba"):
        subset = [row for row in rows if row["family"] == name]
        family[name] = {
            "events": len(subset),
            "diagnosis_counts": dict(Counter(row["diagnosis"] for row in subset)),
            "nearest_daughter_ownership_counts": dict(Counter(
                ownership for row in subset for ownership in row["nearest_daughter_ownership"]
            )),
        }
    return {
        "status": "read_only_v23_single_child_ownership_failures",
        "population": {"events": len(rows), "families": dict(Counter(row["family"] for row in rows))},
        "diagnosis_counts": dict(Counter(row["diagnosis"] for row in rows)),
        "nearest_daughter_ownership_counts": dict(Counter(
            ownership for row in rows for ownership in row["nearest_daughter_ownership"]
        )),
        "distinct_nearest_daughters": sum(row["distinct_nearest_daughters"] for row in rows),
        "family": family,
        "zero_perturbation_all": all(row["zero_perturbation"] for row in rows),
        "candidate_set_changed": False,
        "graph_mutation": False,
    }


def write_outputs(rows: list[dict], output: Path, summary_path: Path, report: Path) -> dict:
    rows = sorted(rows, key=lambda row: (row["family"], row["sample_id"], int(row["t"])))
    summary = summarize(rows)
    output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 Single-Child Ownership Failure Audit",
        "",
        "Decision: **READ-ONLY UPSTREAM DIAGNOSTIC**.",
        "",
        "Population: the eight frozen `missing_single_child_anchor` events from the independent parent-isolation audit. GT is used only to label parent/daughter identity after the unchanged V19 graph is built.",
        "",
        "| Event | Family | Registered parents | Outgoing counts | Nearest daughter ownership | Distinct daughters | Diagnosis |",
        "|---|---|---:|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['sample_id']} t{row['t']} | {row['family']} | "
            f"{row['registered_parent_count']} | {row['registered_parent_outgoing_counts']} | "
            f"{', '.join(row['nearest_daughter_ownership'])} | "
            f"{'yes' if row['distinct_nearest_daughters'] else 'no'} | {row['diagnosis']} |"
        )
    lines += [
        "",
        "## Aggregate",
        "",
        f"- Diagnoses: `{summary['diagnosis_counts']}`",
        f"- Nearest-daughter ownership states: `{summary['nearest_daughter_ownership_counts']}`",
        f"- Events with two distinct nearest daughter detections: {summary['distinct_nearest_daughters']}/{len(rows)}",
        "",
        "Guardrail: this audit is descriptive only. It did not change candidates, edges, graph topology, thresholds, or routing.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--parent-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    fixture = {
        (case["sample_id"], int(case["t"])): case
        for case in json.loads(args.fixture.read_text(encoding="utf-8"))["cases"]
    }
    parent_rows = json.loads(args.parent_audit.read_text(encoding="utf-8"))
    frozen_keys = {
        (row["sample_id"], int(row["t"]))
        for row in parent_rows
        if row["unevaluable_reason"] == "missing_single_child_anchor"
    }
    cases = [fixture[key] for key in sorted(frozen_keys)]
    if len(cases) != 8:
        raise RuntimeError(f"Expected exactly 8 frozen ownership failures, found {len(cases)}")

    completed = []
    if args.resume and args.output.exists():
        completed = json.loads(args.output.read_text(encoding="utf-8"))
    completed_keys = {(row["sample_id"], int(row["t"])) for row in completed}
    pending = [case for case in cases if (case["sample_id"], int(case["t"])) not in completed_keys]
    print(f"completed={len(completed)} pending={len(pending)} total={len(cases)}", flush=True)

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(evaluate_case, str(args.train_dir), case): case for case in pending
        }
        for future in as_completed(futures):
            row = future.result()
            completed.append(row)
            write_outputs(completed, args.output, args.summary, args.report)
            print(
                f"[{len(completed)}/{len(cases)}] {row['sample_id']} t{row['t']} "
                f"{row['diagnosis']}",
                flush=True,
            )

    print(json.dumps(write_outputs(completed, args.output, args.summary, args.report), indent=2), flush=True)


if __name__ == "__main__":
    main()
