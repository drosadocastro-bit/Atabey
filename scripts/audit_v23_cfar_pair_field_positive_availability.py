"""Census patched-official division-action availability on the frozen CFAR route."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from atabey.detection.cfar_watershed import threshold_local_maxima_cfar_sidelobe_watershed
from atabey.evaluation.official_division_metric import evaluate_official_divisions
from atabey.evaluation.semantic_positive_availability import gt_division_window
from atabey.hybrid_config import DEFAULT_GUARDRAIL_SETTINGS, DEFAULT_HYBRID_FROZEN_DEFAULTS
from atabey.io.geff_reader import GroundTruthNode, read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.types import Detection, LineageEdge, LineageGraph


MATCH_RADIUS_UM = 7.0
FORMATION_RADIUS_UM = 14.0
PAIR_FIELD_HALF_EXTENT_UM = 16.0
VOXEL_SCALE_UM = np.asarray((1.625, 0.40625, 0.40625), dtype=float)


@dataclass(frozen=True)
class EventSpec:
    sample_id: str
    gt_parent_id: int
    gt_child_1_id: int
    gt_child_2_id: int
    family: str
    fold: int


def _distance(left, right) -> float:
    return float(np.linalg.norm(np.asarray(left, dtype=float) - np.asarray(right, dtype=float)))


def _detect(sample_id: str, t: int, volume: np.ndarray) -> list[Detection]:
    settings = DEFAULT_HYBRID_FROZEN_DEFAULTS
    return threshold_local_maxima_cfar_sidelobe_watershed(
        sample_id,
        t,
        volume,
        threshold=settings.cfar_threshold,
        min_distance_voxels=(1, 5, 5),
        max_detections=settings.max_detections_per_timepoint,
        cfar_training_radius_voxels=settings.cfar_training_radius_voxels,
        cfar_guard_radius_voxels=settings.cfar_guard_radius_voxels,
        cfar_threshold_mode=settings.cfar_threshold_mode,
        cfar_k_sigma=settings.cfar_k_sigma,
        cfar_pfa=settings.cfar_pfa,
        sidelobe_mode=settings.sidelobe_mode,
        sidelobe_radius_voxels=settings.sidelobe_radius_voxels,
        sidelobe_axial_z_radius_voxels=settings.sidelobe_axial_z_radius_voxels,
        sidelobe_axial_xy_tolerance_voxels=settings.sidelobe_axial_xy_tolerance_voxels,
        sidelobe_floor_ratio=settings.sidelobe_floor_ratio,
    )


def _nearby(detections: list[Detection], node: GroundTruthNode) -> list[tuple[Detection, float]]:
    found = [(item, _distance(item.position_um, node.position_um)) for item in detections]
    return sorted(
        ((item, distance) for item, distance in found if distance <= MATCH_RADIUS_UM),
        key=lambda item: (item[1], item[0].node_id),
    )


def _crop_coverage(position_um, spatial_shape) -> float:
    high_domain = (np.asarray(spatial_shape, dtype=float) - 1.0) * VOXEL_SCALE_UM
    position = np.asarray(position_um, dtype=float)
    low = position - PAIR_FIELD_HALF_EXTENT_UM
    high = position + PAIR_FIELD_HALF_EXTENT_UM
    overlap = np.maximum(0.0, np.minimum(high, high_domain) - np.maximum(low, 0.0))
    return float(np.prod(overlap / (2.0 * PAIR_FIELD_HALF_EXTENT_UM)))


def _official_tp(parent: Detection, child_1: Detection, child_2: Detection, ground_truth, gt_parent_id: int) -> bool:
    graph = LineageGraph(
        sample_id=parent.sample_id,
        detections=[parent, child_1, child_2],
        edges=[
            LineageEdge(parent.node_id, child_1.node_id, relation="division"),
            LineageEdge(parent.node_id, child_2.node_id, relation="division"),
        ],
    )
    result = evaluate_official_divisions(graph, gt_division_window(ground_truth, gt_parent_id))
    return result.gt_scores.get(int(gt_parent_id), 0) == 1 and parent.node_id in result.tp_fork_ids


def _process_sample(train_dir: str, specs: list[dict]) -> list[dict]:
    events = [EventSpec(**item) for item in specs]
    sample_id = events[0].sample_id
    train = Path(train_dir)
    ground_truth = read_geff_graph(train / f"{sample_id}.geff")
    gt_nodes = {int(node.node_id): node for node in ground_truth.nodes}
    array = open_competition_array(train / f"{sample_id}.zarr")
    required_frames = sorted({gt_nodes[event.gt_parent_id].t + offset for event in events for offset in (0, 1)})
    detections = {t: _detect(sample_id, t, read_timepoint(array, t)) for t in required_frames}
    spatial_shape = tuple(int(value) for value in array.shape[1:])

    rows = []
    for event in events:
        parent_gt = gt_nodes[event.gt_parent_id]
        child_1_gt = gt_nodes[event.gt_child_1_id]
        child_2_gt = gt_nodes[event.gt_child_2_id]
        parent_candidates = _nearby(detections[parent_gt.t], parent_gt)
        child_1_candidates = _nearby(detections[child_1_gt.t], child_1_gt)
        child_2_candidates = _nearby(detections[child_2_gt.t], child_2_gt)
        specs_by_ids = {}
        for parent, parent_distance in parent_candidates:
            for child_1, child_1_distance in child_1_candidates:
                for child_2, child_2_distance in child_2_candidates:
                    if child_1.node_id == child_2.node_id:
                        continue
                    if _distance(parent.position_um, child_1.position_um) > FORMATION_RADIUS_UM:
                        continue
                    if _distance(parent.position_um, child_2.position_um) > FORMATION_RADIUS_UM:
                        continue
                    ordered = sorted((child_1, child_2), key=lambda item: item.node_id)
                    key = (parent.node_id, ordered[0].node_id, ordered[1].node_id)
                    role_distance = parent_distance + child_1_distance + child_2_distance
                    if key not in specs_by_ids or role_distance < specs_by_ids[key][0]:
                        specs_by_ids[key] = (role_distance, parent, ordered[0], ordered[1])

        official_actions = []
        for role_distance, parent, child_1, child_2 in sorted(specs_by_ids.values(), key=lambda item: (item[0], item[1].node_id, item[2].node_id, item[3].node_id)):
            if _official_tp(parent, child_1, child_2, ground_truth, event.gt_parent_id):
                official_actions.append((role_distance, parent, child_1, child_2))

        if not parent_candidates:
            status = "no_parent_detection_within_7um"
        elif not child_1_candidates or not child_2_candidates:
            status = "missing_daughter_detection_within_7um"
        elif not any(left.node_id != right.node_id for left, _ in child_1_candidates for right, _ in child_2_candidates):
            status = "no_distinct_daughter_pair"
        elif not specs_by_ids:
            status = "no_pair_inside_14um_formation_radius"
        elif not official_actions:
            status = "projected_actions_not_official_tp"
        else:
            status = "official_positive"

        canonical = official_actions[0] if official_actions else None
        coverage = _crop_coverage(canonical[1].position_um, spatial_shape) if canonical else None
        rows.append({
            **asdict(event),
            "t": int(parent_gt.t),
            "parent_candidate_count": len(parent_candidates),
            "daughter_1_candidate_count": len(child_1_candidates),
            "daughter_2_candidate_count": len(child_2_candidates),
            "distinct_formed_action_count": len(specs_by_ids),
            "official_tp_action_count": len(official_actions),
            "status": status,
            "canonical_parent_id": canonical[1].node_id if canonical else None,
            "canonical_child_1_id": canonical[2].node_id if canonical else None,
            "canonical_child_2_id": canonical[3].node_id if canonical else None,
            "canonical_role_distance_um": canonical[0] if canonical else None,
            "pair_field_unpadded_crop_coverage": coverage,
            "pair_field_available": canonical is not None,
            "graph_mutated": False,
        })
    return rows


def _assign_folds(sample_ids: list[str]) -> dict[str, int]:
    assignments = {}
    for family in ("44b6", "6bba"):
        family_ids = [sample_id for sample_id in sample_ids if sample_id.startswith(family + "_")]
        family_ids.sort(key=lambda sample_id: hashlib.sha256(f"v23-cfar-pair-field|{sample_id}".encode()).hexdigest())
        for index, sample_id in enumerate(family_ids):
            assignments[sample_id] = index % 3 + 1
    return assignments


def _load_specs(distance_csv: Path, routes_json: Path) -> list[EventSpec]:
    routes = json.loads(routes_json.read_text(encoding="utf-8"))["records"]
    cfar_ids = {row["sample_id"] for row in routes if row["route"] == "cfar_sidelobe/bipartite"}
    raw = [row for row in csv.DictReader(distance_csv.open(newline="", encoding="utf-8")) if row["sample_id"] in cfar_ids]
    folds = _assign_folds(sorted({row["sample_id"] for row in raw}))
    return [
        EventSpec(
            sample_id=row["sample_id"],
            gt_parent_id=int(row["gt_parent_id"]),
            gt_child_1_id=int(row["gt_child_1_id"]),
            gt_child_2_id=int(row["gt_child_2_id"]),
            family=row["sample_id"].split("_", 1)[0],
            fold=folds[row["sample_id"]],
        )
        for row in raw
    ]


def _summarize(rows: list[dict]) -> dict:
    positive = [row for row in rows if row["status"] == "official_positive"]
    def count(subset):
        return {
            "events": len(subset),
            "samples": len({row["sample_id"] for row in subset}),
            "official_tp_actions": sum(row["official_tp_action_count"] for row in subset),
        }
    strata = {
        "family": {family: count([row for row in positive if row["family"] == family]) for family in ("44b6", "6bba")},
        "fold": {str(fold): count([row for row in positive if row["fold"] == fold]) for fold in (1, 2, 3)},
    }
    fold_support = {}
    for fold in (1, 2, 3):
        train = [row for row in positive if row["fold"] != fold]
        test = [row for row in positive if row["fold"] == fold]
        fold_support[str(fold)] = {
            "training": {family: count([row for row in train if row["family"] == family]) for family in ("44b6", "6bba")},
            "heldout": {family: count([row for row in test if row["family"] == family]) for family in ("44b6", "6bba")},
        }
    coverage = [row["pair_field_unpadded_crop_coverage"] for row in positive]
    gates = {
        "cfar_positive_samples_min_6": count(positive)["samples"] >= 6,
        "each_family_positive_samples_min_3": all(strata["family"][family]["samples"] >= 3 for family in ("44b6", "6bba")),
        "each_fold_training_events_per_family_min_4": all(item["training"][family]["events"] >= 4 for item in fold_support.values() for family in ("44b6", "6bba")),
        "each_fold_heldout_events_per_family_min_2": all(item["heldout"][family]["events"] >= 2 for item in fold_support.values() for family in ("44b6", "6bba")),
        "pair_field_representation_availability_min_99pct": len(positive) > 0 and all(row["pair_field_available"] for row in positive),
    }
    decision = "GO_TO_CFAR_PAIR_FIELD_EXTRACTION_CONTRACT" if all(gates.values()) else "NO_GO_CFAR_PAIR_FIELD_TRAINING"
    return {
        "status": "read_only_v23_cfar_native_official_positive_availability",
        "decision": decision,
        "source_population": {
            "events": len(rows),
            "samples": len({row["sample_id"] for row in rows}),
            "formed_candidate_actions": sum(row["distinct_formed_action_count"] for row in rows),
        },
        "official_positive": count(positive),
        "status_counts": {status: sum(row["status"] == status for row in rows) for status in sorted({row["status"] for row in rows})},
        "strata": strata,
        "fold_support": fold_support,
        "pair_field_crop_coverage": {"min": min(coverage) if coverage else None, "median": float(np.median(coverage)) if coverage else None, "p10": float(np.quantile(coverage, 0.1)) if coverage else None},
        "gates": gates,
        "detector_contract": {
            "route": "cfar_sidelobe/bipartite",
            "watershed_refinement": True,
            "match_radius_um": MATCH_RADIUS_UM,
            "division_formation_radius_um": FORMATION_RADIUS_UM,
            "max_detections_per_timepoint": DEFAULT_HYBRID_FROZEN_DEFAULTS.max_detections_per_timepoint,
            "spike_guardrail_unreachable": DEFAULT_HYBRID_FROZEN_DEFAULTS.max_detections_per_timepoint < DEFAULT_GUARDRAIL_SETTINGS.min_absolute_count,
        },
        "model_fitted": False,
        "crops_extracted": False,
        "graph_mutation": False,
        "unsupported_candidates_labeled_negative": False,
        "full_199_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--distance-audit", type=Path, default=ROOT / "v21_gt_division_distance_audit.csv")
    parser.add_argument("--routes", type=Path, default=ROOT / "v22_route_prevalence_199.json")
    parser.add_argument("--output-csv", type=Path, default=ROOT / "v23_cfar_pair_field_positive_availability.csv")
    parser.add_argument("--summary", type=Path, default=ROOT / "v23_cfar_pair_field_positive_availability_summary.json")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    specs = _load_specs(args.distance_audit, args.routes)
    grouped = {}
    for spec in specs:
        grouped.setdefault(spec.sample_id, []).append(asdict(spec))
    print(f"Frozen CFAR population: {len(specs)} events across {len(grouped)} samples", flush=True)
    rows = []
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(_process_sample, str(args.train_dir), sample_specs): sample_id for sample_id, sample_specs in grouped.items()}
        for index, future in enumerate(as_completed(futures), start=1):
            sample_id = futures[future]
            sample_rows = future.result()
            rows.extend(sample_rows)
            print(f"[{index}/{len(futures)}] {sample_id}: {sum(row['status'] == 'official_positive' for row in sample_rows)}/{len(sample_rows)} available", flush=True)
    rows.sort(key=lambda row: (row["sample_id"], row["t"], row["gt_parent_id"]))
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = _summarize(rows)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
