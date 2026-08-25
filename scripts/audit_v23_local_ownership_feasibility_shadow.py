"""Oracle-labeled local ownership feasibility shadow for four frozen V23 cases."""

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

from atabey.evaluation.official_division_metric import evaluate_official_divisions
from atabey.io.geff_reader import read_geff_graph
from atabey.tracking.local_assignment_shadow import _predecessors, _solve_assignment
from atabey.types import LineageEdge, LineageGraph
from audit_v23_split_echo_paths import graph_signature, is_registered
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route


ASSIGNMENT_GATE_UM = 9.0


def distance(left, right) -> float:
    return float(np.linalg.norm(np.asarray(left, dtype=float) - np.asarray(right, dtype=float)))


def complete_registered_fork(row: dict) -> bool:
    return any(
        {
            daughter_index
            for child in parent["next_frame_children"]
            for daughter_index in child["registered_daughter_indices"]
        }
        == {0, 1}
        for parent in row["parent_details"]
    )


def copy_with_oracle_fork(
    graph: LineageGraph,
    parent_id: str,
    child_ids: set[str],
) -> tuple[LineageGraph, list[tuple[str, str]], list[tuple[str, str]]]:
    nodes = {node.node_id: node for node in graph.detections}
    parent_t = int(nodes[parent_id].t)
    removed = []
    kept = []
    for edge in graph.edges:
        target = nodes.get(edge.target_id)
        remove_wrong_focal = (
            edge.source_id == parent_id
            and target is not None
            and int(target.t) == parent_t + 1
            and edge.target_id not in child_ids
        )
        remove_competing_owner = edge.target_id in child_ids and edge.source_id != parent_id
        if remove_wrong_focal or remove_competing_owner:
            removed.append((edge.source_id, edge.target_id))
        else:
            kept.append(edge)
    existing = {(edge.source_id, edge.target_id) for edge in kept}
    added = []
    for child_id in sorted(child_ids):
        if (parent_id, child_id) not in existing:
            kept.append(LineageEdge(parent_id, child_id, relation="division"))
            added.append((parent_id, child_id))
    return LineageGraph(graph.sample_id, list(graph.detections), kept), removed, added


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
    for node in graph.detections:
        frame_nodes[int(node.t)].append(node)
    for edge in graph.edges:
        incoming[edge.target_id].append(edge.source_id)

    ground_truth = read_geff_graph(Path(train_dir) / f"{sample_id}.geff")
    gt_nodes = {int(node.node_id): node for node in ground_truth.nodes}
    gt_parent_id = int(case["gt_parent_id"])
    gt_parent = np.asarray(gt_nodes[gt_parent_id].position_um, dtype=float)
    gt_daughters = [
        np.asarray(gt_nodes[int(child_id)].position_um, dtype=float)
        for child_id in case["gt_child_ids"]
    ]
    parents = [
        node for node in frame_nodes[t]
        if is_registered(np.asarray(node.position_um, dtype=float), gt_parent)
    ]
    focal = min(parents, key=lambda node: (distance(node.position_um, gt_parent), node.node_id)) if parents else None
    daughters = []
    for gt_daughter in gt_daughters:
        candidates = [
            node for node in frame_nodes[t + 1]
            if is_registered(np.asarray(node.position_um, dtype=float), gt_daughter)
        ]
        daughters.append(
            min(candidates, key=lambda node: (distance(node.position_um, gt_daughter), node.node_id))
            if candidates else None
        )
    distinct = bool(daughters[0] is not None and daughters[1] is not None and daughters[0].node_id != daughters[1].node_id)
    eligible = focal is not None and distinct

    row = {
        "sample_id": sample_id,
        "family": case["family"],
        "t": t,
        "gt_parent_id": gt_parent_id,
        "gt_child_ids": case["gt_child_ids"],
        "source_diagnosis": case["diagnosis"],
        "detector": detector,
        "link_strategy": link_strategy,
        "eligible": eligible,
        "focal_parent_id": focal.node_id if focal else None,
        "daughter_ids": [daughter.node_id if daughter else None for daughter in daughters],
        "zero_perturbation": False,
        "candidate_set_changed": False,
        "source_graph_mutated": False,
    }
    if not eligible:
        row.update({
            "status": "unavailable_missing_distinct_daughter_pair",
            "competing_parent_count": None,
            "assignment_safe": None,
            "official_target_before": None,
            "official_target_after": None,
        })
        row["zero_perturbation"] = before == graph_signature(graph)
        return row

    daughter_ids = {daughter.node_id for daughter in daughters}
    competitor_ids = {
        source_id
        for child_id in daughter_ids
        for source_id in incoming.get(child_id, [])
        if source_id != focal.node_id and source_id in nodes and int(nodes[source_id].t) == t
    }
    competitors = sorted((nodes[source_id] for source_id in competitor_ids), key=lambda node: node.node_id)
    targets = frame_nodes[t + 1]
    predecessors = _predecessors(graph, nodes)
    baseline_matched, baseline_cost = _solve_assignment(
        competitors,
        targets,
        predecessors,
        gate_um=ASSIGNMENT_GATE_UM,
        reserved_target_ids=set(),
    )
    constrained_matched, constrained_cost = _solve_assignment(
        competitors,
        targets,
        predecessors,
        gate_um=ASSIGNMENT_GATE_UM,
        reserved_target_ids=daughter_ids,
    )
    assignment_safe = constrained_matched == baseline_matched

    projected, removed, added = copy_with_oracle_fork(graph, focal.node_id, daughter_ids)
    baseline_official = evaluate_official_divisions(graph, ground_truth)
    projected_official = evaluate_official_divisions(projected, ground_truth)
    target_before = int(baseline_official.gt_scores.get(gt_parent_id, 0))
    target_after = int(projected_official.gt_scores.get(gt_parent_id, 0))
    row.update({
        "status": "oracle_fork_feasible" if assignment_safe else "oracle_fork_displaces_competitor",
        "competing_parent_ids": sorted(competitor_ids),
        "competing_parent_count": len(competitors),
        "baseline_competitors_matched": baseline_matched,
        "constrained_competitors_matched": constrained_matched,
        "baseline_assignment_cost_um": baseline_cost,
        "constrained_assignment_cost_um": constrained_cost,
        "assignment_cost_increase_um": max(0.0, constrained_cost - baseline_cost),
        "assignment_safe": assignment_safe,
        "shadow_edges_removed": removed,
        "shadow_edges_added": added,
        "official_target_before": target_before,
        "official_target_after": target_after,
        "official_tp_before": baseline_official.tp,
        "official_tp_after": projected_official.tp,
        "official_fp_before": baseline_official.fp,
        "official_fp_after": projected_official.fp,
        "official_fn_before": baseline_official.fn,
        "official_fn_after": projected_official.fn,
    })
    row["zero_perturbation"] = before == graph_signature(graph)
    return row


def summarize(rows: list[dict], controls: dict) -> dict:
    eligible = [row for row in rows if row["eligible"]]
    improved = [
        row for row in eligible
        if row["official_target_before"] == 0 and row["official_target_after"] == 1
    ]
    clean = [
        row for row in improved
        if row["assignment_safe"]
        and row["official_tp_after"] >= row["official_tp_before"]
        and row["official_fp_after"] <= row["official_fp_before"]
    ]
    protected_ok = controls["protected_complete_forks"] == 3
    decision = (
        "GO_TO_SEMANTIC_SCORER_RESEARCH_ONLY"
        if protected_ok and len(eligible) >= 2 and len(clean) == len(eligible)
        else "HOLD_LOCAL_OWNERSHIP_FEASIBILITY"
        if clean
        else "NO_GO_LOCAL_OWNERSHIP_FEASIBILITY"
    )
    return {
        "status": "read_only_v23_local_ownership_feasibility_shadow",
        "decision": decision,
        "population": {
            "target_cases": len(rows),
            "eligible_cases": len(eligible),
            "unavailable_cases": len(rows) - len(eligible),
            **controls,
        },
        "official_target_recovered": len(improved),
        "clean_feasible_recoveries": len(clean),
        "assignment_safe_cases": sum(bool(row["assignment_safe"]) for row in eligible),
        "family": {
            family: {
                "targets": sum(row["family"] == family for row in rows),
                "eligible": sum(row["family"] == family and row["eligible"] for row in rows),
                "clean": sum(row["family"] == family and row in clean for row in rows),
            }
            for family in ("44b6", "6bba")
        },
        "zero_perturbation_all": all(row["zero_perturbation"] for row in rows),
        "candidate_set_changed": False,
        "source_graph_mutation": False,
        "authorization": "semantic_scorer_research_only_not_assignment_integration",
    }


def write_outputs(rows: list[dict], controls: dict, output: Path, summary_path: Path, report: Path) -> dict:
    rows = sorted(rows, key=lambda row: (row["family"], row["sample_id"], int(row["t"])))
    summary = summarize(rows, controls)
    output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 Local Ownership Feasibility Shadow Results",
        "",
        f"Decision: **{summary['decision']}**.",
        "",
        "This is an oracle-labeled feasibility test, not a selector. GT identifies the desired fork only after the frozen V19 graph is built. Assignment is evaluated solely as a local ownership safety constraint.",
        "",
        f"Protected complete forks: {controls['protected_complete_forks']}/3. Detector-only quarantines: {controls['detector_only_quarantines']}. Mixed missing-detection targets remain explicit.",
        "",
        "| Event | Family | Eligible | Competitors | Safe | Target official 0->1 | TP delta | FP delta | Shadow edits |",
        "|---|---|---|---:|---|---|---:|---:|---|",
    ]
    for row in rows:
        official = (
            f"{row['official_target_before']}->{row['official_target_after']}"
            if row["eligible"] else "NA"
        )
        tp_delta = row["official_tp_after"] - row["official_tp_before"] if row["eligible"] else "NA"
        fp_delta = row["official_fp_after"] - row["official_fp_before"] if row["eligible"] else "NA"
        edits = (
            f"-{len(row['shadow_edges_removed'])}/+{len(row['shadow_edges_added'])}"
            if row["eligible"] else "none"
        )
        lines.append(
            f"| {row['sample_id']} t{row['t']} | {row['family']} | {row['eligible']} | "
            f"{row.get('competing_parent_count', 'NA')} | {row.get('assignment_safe', 'NA')} | "
            f"{official} | {tp_delta} | {fp_delta} | {edits} |"
        )
    lines += [
        "",
        "A GO authorizes only development of a GT-blind semantic scorer that proposes the pair before this constraint layer. It does not authorize edge mutation, assignment integration, routing changes, or a full-cohort run.",
        "",
        "Guardrail: all edits occurred only on copied graphs for official counterfactual scoring. Source graphs and candidate sets remained unchanged.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--ownership-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    source = json.loads(args.ownership_audit.read_text(encoding="utf-8"))
    protected = [row for row in source if complete_registered_fork(row)]
    detector_only = [
        row for row in source
        if row["diagnosis"] == "registered_parent_childless_missing_daughter_detection"
    ]
    targets = [
        row for row in source
        if not complete_registered_fork(row) and row not in detector_only
    ]
    if len(protected) != 3 or len(detector_only) != 1 or len(targets) != 4:
        raise RuntimeError(
            f"Frozen partition mismatch: protected={len(protected)} detector={len(detector_only)} targets={len(targets)}"
        )
    controls = {
        "protected_complete_forks": len(protected),
        "detector_only_quarantines": len(detector_only),
        "mixed_missing_detection_targets": sum(
            "missing_detection" in row["nearest_daughter_ownership"] for row in targets
        ),
    }

    completed = []
    if args.resume and args.output.exists():
        completed = json.loads(args.output.read_text(encoding="utf-8"))
    completed_keys = {(row["sample_id"], int(row["t"])) for row in completed}
    pending = [row for row in targets if (row["sample_id"], int(row["t"])) not in completed_keys]
    print(f"completed={len(completed)} pending={len(pending)} total={len(targets)}", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(evaluate_case, str(args.train_dir), row): row for row in pending
        }
        for future in as_completed(futures):
            row = future.result()
            completed.append(row)
            write_outputs(completed, controls, args.output, args.summary, args.report)
            print(
                f"[{len(completed)}/{len(targets)}] {row['sample_id']} t{row['t']} "
                f"status={row['status']} official={row['official_target_before']}->{row['official_target_after']}",
                flush=True,
            )
    print(json.dumps(write_outputs(completed, controls, args.output, args.summary, args.report), indent=2), flush=True)


if __name__ == "__main__":
    main()
