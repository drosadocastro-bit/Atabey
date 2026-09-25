"""Read-only, fixed-history census of V26A's filter/selection order discrepancy."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import platform
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import numpy as np
import scipy
from scipy.spatial import cKDTree

from atabey.provenance import canonical_text_sha256
from atabey.tracking.nearest_neighbor import (
    _predicted_position, link_adjacent_timepoints,
)
from atabey.tracking.v26_a_forward_ranking_shadow import link_step_ranked_motion_mutual
from atabey.tracking.v24_2_shadow import prune_interior_isolated_detections
from atabey.tracking.v24_3_shadow import prune_interior_short_fragments
from run_v26_a_forward_ranking_ablation import (
    _graph_signature_sha256, _read_record, _reconstruct_frozen_relink,
    _selection_subtypes, _sha256, _validate_contract,
)

RADIUS = 9.0


def inspect_frame(previous, current, predecessors):
    """Inspect decisions without updating histories or modifying graph objects."""
    rows = []
    if not previous:
        return rows
    current_positions = np.array([node.position_um for node in current], dtype=float)
    if current:
        forward_tree = cKDTree(current_positions)
        reverse_tree = cKDTree([node.position_um for node in previous])
        reverse = [int(reverse_tree.query(node.position_um, k=1)[1]) for node in current]
    for source_index, source in enumerate(previous):
        row = {
            "source_id": source.node_id, "source_t": source.t,
            "target_count": len(current), "feasible_count": 0,
            "global_motion_target_id": None,
            "baseline_accepted_target_id": None, "step_accepted_target_id": None,
            "gate_order_exposed": False, "motion_minimum_tie": False,
            "step_minimum_tie": False,
        }
        if current:
            predicted = _predicted_position(source, predecessors.get(source.node_id))
            errors = np.linalg.norm(current_positions - predicted, axis=1)
            steps = np.linalg.norm(current_positions - np.array(source.position_um), axis=1)
            distance, nearest = forward_tree.query(predicted, k=1)
            nearest = int(nearest)
            feasible = np.flatnonzero(
                np.isfinite(errors) & (errors <= RADIUS)
                & np.isfinite(steps) & (steps <= RADIUS)
            )
            original_passes = bool(np.isfinite(distance) and distance <= RADIUS
                                   and steps[nearest] <= RADIUS)
            row.update({
                "global_motion_target_id": current[nearest].node_id,
                "global_motion_error_um": float(distance),
                "global_motion_step_um": float(steps[nearest]),
                "original_prediction_gate_passes": bool(distance <= RADIUS),
                "original_step_gate_passes": bool(steps[nearest] <= RADIUS),
                "feasible_count": int(len(feasible)),
                "motion_minimum_tie": bool(np.count_nonzero(errors == errors[nearest]) > 1),
                "gate_order_exposed": bool(not original_passes and len(feasible)),
            })
            if original_passes and reverse[nearest] == source_index:
                row["baseline_accepted_target_id"] = current[nearest].node_id
            if len(feasible):
                selected = min((int(i) for i in feasible), key=lambda i: (float(steps[i]), i))
                row.update({
                    "step_selected_target_id": current[selected].node_id,
                    "step_selected_error_um": float(errors[selected]),
                    "step_selected_distance_um": float(steps[selected]),
                    "step_selected_reverse_source_id": previous[reverse[selected]].node_id,
                    "step_minimum_tie": bool(np.count_nonzero(steps[feasible] == steps[selected]) > 1),
                })
                if reverse[selected] == source_index:
                    row["step_accepted_target_id"] = current[selected].node_id
        rows.append(row)

    # Reverse ownership permits at most one source for each target; thus these
    # per-source decisions must agree with the executed greedy uniqueness layer.
    for key, edges in (
        ("baseline_accepted_target_id", link_adjacent_timepoints(
            previous, current, RADIUS, strategy="motion_mutual",
            predecessor_by_node_id=predecessors)),
        ("step_accepted_target_id", link_step_ranked_motion_mutual(
            previous, current, RADIUS, predecessors)),
    ):
        observed = {row["source_id"]: row[key] for row in rows if row[key] is not None}
        actual = {edge.source_id: edge.target_id for edge in edges}
        if observed != actual:
            raise RuntimeError(f"Frame-local analytical/executed decision mismatch: {key}")
    return rows


def audit_sample(record, graph, historical_v26a):
    before = _graph_signature_sha256(graph)
    nodes = {node.node_id: node for node in graph.detections}
    frames = defaultdict(list)
    for node in graph.detections:
        frames[node.t].append(node)
    predecessors = {edge.target_id: nodes[edge.source_id] for edge in graph.edges}
    counts = Counter({key: 0 for key in (
        "sources_before_final_frame", "sources_without_next_frame_targets",
        "sources_with_feasible_targets", "baseline_accepted", "step_local_accepted",
        "different_local_decision", "gate_order_exposed", "gate_order_exposed_step_accepted",
        "motion_minimum_ties", "step_minimum_ties",
    )})
    exposed = {}
    baseline_edges = set()
    for t in range(max(frames, default=0)):
        for row in inspect_frame(frames[t], frames[t + 1], predecessors):
            counts["sources_before_final_frame"] += 1
            counts["sources_without_next_frame_targets"] += int(row["target_count"] == 0)
            counts["sources_with_feasible_targets"] += int(row["feasible_count"] > 0)
            counts["baseline_accepted"] += int(row["baseline_accepted_target_id"] is not None)
            counts["step_local_accepted"] += int(row["step_accepted_target_id"] is not None)
            counts["different_local_decision"] += int(
                row["baseline_accepted_target_id"] != row["step_accepted_target_id"])
            counts["motion_minimum_ties"] += int(row["motion_minimum_tie"])
            counts["step_minimum_ties"] += int(row["step_minimum_tie"])
            if row["baseline_accepted_target_id"] is not None:
                baseline_edges.add((row["source_id"], row["baseline_accepted_target_id"]))
            if row["gate_order_exposed"]:
                exposed[row["source_id"]] = row
                counts["gate_order_exposed"] += 1
                counts["gate_order_exposed_step_accepted"] += int(row["step_accepted_target_id"] is not None)
    if baseline_edges != {(edge.source_id, edge.target_id) for edge in graph.edges}:
        raise RuntimeError("Full frozen edge replay differs from frame census")

    recovered = {tuple(edge) for edge in historical_v26a["transition_ledger"]["recovered_v19_credited_edges"]}
    subtypes = _selection_subtypes(record, graph)
    loss_counts = Counter()
    overlaps = []
    for loss in record["v19_credited_v24_3_lost_edges"]:
        edge = (loss["ground_truth_source_id"], loss["ground_truth_target_id"])
        mechanism = subtypes.get(edge, loss["failure_class"])
        loss_counts[f"all::{mechanism}"] += 1
        if edge in recovered:
            loss_counts[f"historically_recovered::{mechanism}"] += 1
        source_rows = [exposed[source] for source in loss["matched_e016_source_ids"] if source in exposed]
        if not source_rows:
            continue
        mapped_targets = set(loss["matched_e016_target_ids"])
        selected_mapped = any(row["step_accepted_target_id"] in mapped_targets for row in source_rows)
        loss_counts[f"exposed::{mechanism}"] += 1
        if selected_mapped:
            loss_counts[f"exposed_step_selects_mapped_target::{mechanism}"] += 1
        if edge in recovered:
            loss_counts[f"exposed_and_historically_recovered::{mechanism}"] += 1
        overlaps.append({
            "ground_truth_edge": list(edge), "v25_mechanism": mechanism,
            "exposed_source_ids": [row["source_id"] for row in source_rows],
            "step_local_selects_mapped_target": selected_mapped,
            "historically_recovered_in_v26a": edge in recovered,
        })
    if before != _graph_signature_sha256(graph):
        raise RuntimeError("Audit mutated frozen graph")
    return {
        "sample_id": record["sample_id"], "counts": dict(sorted(counts.items())),
        "loss_intersections": dict(sorted(loss_counts.items())),
        "gate_order_events": list(exposed.values()), "loss_overlap_events": overlaps,
        "graph_unchanged": True, "frame_decisions_match_existing_linkers": True,
    }


def run_audit(v25_archive, v26a_archive):
    contract_path = ROOT / "tests/fixtures/v26_a_forward_ranking_ablation.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    sample_ids = _validate_contract(contract, v25_archive)
    result_path = ROOT / "v26a_forward_ranking_ablation_results.json"
    original = json.loads(result_path.read_text(encoding="utf-8"))
    identity = original["source_archive"]
    if v26a_archive.stat().st_size != identity["bytes"] or _sha256(v26a_archive) != identity["sha256"]:
        raise RuntimeError("Frozen V26A result archive mismatch")
    samples = []
    with zipfile.ZipFile(v25_archive) as v25, zipfile.ZipFile(v26a_archive) as v26:
        for archive, prefix, expected_entries in (
            (v25, "run/samples/", contract["frozen_v25_archive"]["entries"]),
            (v26, "samples/", identity["entries"]),
        ):
            names = archive.namelist()
            actual = {name for name in names if name.startswith(prefix) and name.endswith(".json.gz")}
            expected = {f"{prefix}{sample_id}.json.gz" for sample_id in sample_ids}
            if len(names) != expected_entries or len(names) != len(set(names)) or actual != expected:
                raise RuntimeError("Archive entry/cohort mismatch")
        for index, sample_id in enumerate(sample_ids, 1):
            print(f"[{index}/16] {sample_id}: frozen-history audit", flush=True)
            record = _read_record(v25, sample_id)
            history = json.loads(gzip.decompress(v26.read(f"samples/{sample_id}.json.gz")))
            if record["sample_id"] != sample_id or history["sample_id"] != sample_id:
                raise RuntimeError("Sample identity mismatch")
            graph = _reconstruct_frozen_relink(record)
            v24_2 = prune_interior_isolated_detections(graph)
            v24_3 = prune_interior_short_fragments(v24_2)
            signatures = {}
            for name, stage in (("relink", graph), ("v24_2", v24_2), ("v24_3", v24_3)):
                signatures[name] = _graph_signature_sha256(stage)
                if signatures[name] != record["graph_signatures"][f"{name}_sha256"]:
                    raise RuntimeError(f"Frozen graph mismatch: {sample_id}/{name}")
            if signatures["v24_3"] != history["graph_signatures"]["baseline_v24_3_sha256"]:
                raise RuntimeError("V25/V26A baseline identity mismatch")
            result = audit_sample(record, graph, history)
            result["verified_graph_signatures"] = signatures
            samples.append(result)
    totals, intersections = Counter(), Counter()
    for sample in samples:
        totals.update(sample["counts"])
        intersections.update(sample["loss_intersections"])
    if totals["baseline_accepted"] != 86778 or sum(v for k, v in intersections.items() if k.startswith("all::")) != 1069:
        raise RuntimeError("Frozen audit denominators mismatch")
    sources = [
        "scripts/run_v26_a_gate_order_audit.py", "V26A_GATE_ORDER_AUDIT_PROTOCOL.md",
        "tests/fixtures/v26_a_forward_ranking_ablation.json",
        "v26a_forward_ranking_ablation_results.json",
        "src/atabey/constants.py", "src/atabey/types.py",
        *[value[0] for value in contract["sources"].values()],
    ]
    return {
        "status": "DESCRIPTIVE_GATE_ORDER_AUDIT_COMPLETE", "date": "2026-09-24",
        "history_policy": "Frozen V25 baseline predecessors; local decisions never propagated",
        "sample_count": len(samples), "verified_graph_signatures": 3 * len(samples),
        "input_archives": {
            "v25": {"sha256": _sha256(v25_archive), "bytes": v25_archive.stat().st_size},
            "v26a": {"sha256": _sha256(v26a_archive), "bytes": v26a_archive.stat().st_size},
        },
        "canonical_source_sha256": {path: canonical_text_sha256(ROOT / path) for path in sources},
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "counts": dict(sorted(totals.items())), "loss_intersections": dict(sorted(intersections.items())),
        "per_sample": samples,
        "boundaries": {
            "new_inference": False, "new_metric_execution": False, "graph_mutation": False,
            "recursive_gate_order_effect_quantified": False,
            "independent_validation": False, "production_tuning_authorized": False,
            "submission_authorized": False, "v26a_decision_preserved": original["decision"],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v25-archive", type=Path, default=ROOT / "v25_upstream_forensics_outputs.zip")
    parser.add_argument("--v26a-archive", type=Path, default=ROOT / "v26a_forward_ranking_ablation_outputs.zip")
    parser.add_argument("--output", type=Path, default=ROOT / "v26a_gate_order_audit_results.json")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Preserve existing audit output: {args.output}")
    result = run_audit(args.v25_archive, args.v26a_archive)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"counts": result["counts"], "loss_intersections": result["loss_intersections"]}, indent=2))


if __name__ == "__main__":
    main()
