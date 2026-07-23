from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.evaluation.official_tracking_metric import evaluate_official_tracking
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS as defaults
from atabey.io.geff_reader import read_geff_graph
from atabey.tracking.adaptive_pruning_shadow import compute_adaptive_pruning_shadow
from atabey.types import LineageGraph
from run_hybrid_train_evaluation import _build_hybrid_graph


DEFAULT_BATTERY = (
    "44b6_0113de3b",
    "44b6_0b24845f",
    "44b6_24264f12",
    "44b6_d754aa59",
    "44b6_12dfb391",
    "44b6_0c582fdc",
    "44b6_2a2eff9f",
    "6bba_05db0fb1",
    "6bba_32db13fc",
    "6bba_b329af44",
    "6bba_ebdf3b34",
    "6bba_ebff6e76",
    "6bba_55b7eebe",
)


@dataclass(frozen=True)
class AuditRow:
    sample_id: str
    detector: str
    link_strategy: str
    route_label: str
    keep_fraction: float
    activated: bool
    activation_reason: str
    fragmented_node_fraction: float
    component_count: int
    protected_components: int
    removed_components: int
    removed_nodes: int
    removed_edges: int
    baseline_nodes: int
    shadow_nodes: int
    estimated_total_nodes: int | None
    baseline_edge_tp: int
    shadow_edge_tp: int
    edge_tp_delta: int
    baseline_edge_fp: int
    shadow_edge_fp: int
    baseline_edge_fn: int
    shadow_edge_fn: int
    baseline_edge_jaccard: float | None
    shadow_edge_jaccard: float | None
    edge_jaccard_delta: float | None
    baseline_adjusted_edge_jaccard: float | None
    shadow_adjusted_edge_jaccard: float | None
    adjusted_edge_delta: float | None
    baseline_node_recall: float | None
    shadow_node_recall: float | None
    node_recall_delta: float | None
    baseline_division_tp: int
    shadow_division_tp: int
    division_tp_delta: int
    baseline_division_fp: int
    shadow_division_fp: int
    source_zero_perturbation: bool


def _delta(after: float | None, before: float | None) -> float | None:
    if after is None or before is None:
        return None
    return float(after - before)


def _signature(graph: LineageGraph) -> tuple:
    detections = tuple(
        (
            detection.node_id,
            detection.t,
            detection.z_um,
            detection.y_um,
            detection.x_um,
        )
        for detection in graph.detections
    )
    edges = tuple(
        (edge.source_id, edge.target_id, edge.confidence, edge.relation)
        for edge in graph.edges
    )
    return detections, edges


def _write_rows(rows: list[AuditRow], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(AuditRow.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def _build_v19(sample_path: Path, max_timepoints: int | None):
    return _build_hybrid_graph(
        sample_path=sample_path,
        max_timepoints=max_timepoints,
        cfar_threshold=defaults.cfar_threshold,
        cfar_training_radius_voxels=defaults.cfar_training_radius_voxels,
        cfar_guard_radius_voxels=defaults.cfar_guard_radius_voxels,
        cfar_threshold_mode=defaults.cfar_threshold_mode,
        cfar_k_sigma=defaults.cfar_k_sigma,
        cfar_pfa=defaults.cfar_pfa,
        sidelobe_mode=defaults.sidelobe_mode,
        sidelobe_radius_voxels=defaults.sidelobe_radius_voxels,
        sidelobe_axial_z_radius_voxels=defaults.sidelobe_axial_z_radius_voxels,
        sidelobe_axial_xy_tolerance_voxels=defaults.sidelobe_axial_xy_tolerance_voxels,
        sidelobe_floor_ratio=defaults.sidelobe_floor_ratio,
        max_detections_per_timepoint=defaults.max_detections_per_timepoint,
        cfar_link_strategy="bipartite",
        cfar_max_link_distance_um=defaults.cfar_max_link_distance_um,
        cfar_route_policy=defaults.cfar_route_policy,
        enable_watershed_refinement=True,
    )


def run_audit(args: argparse.Namespace) -> list[AuditRow]:
    train_dir = Path(args.train_dir)
    sample_ids = DEFAULT_BATTERY if args.sample_ids == ["battery"] else tuple(args.sample_ids)
    allowed_routes = (
        None if not args.allowed_routes else frozenset(args.allowed_routes)
    )
    rows: list[AuditRow] = []
    output = Path(args.output)

    for index, sample_id in enumerate(sample_ids, start=1):
        print(f"[{index}/{len(sample_ids)}] {sample_id}", flush=True)
        sample_path = train_dir / f"{sample_id}.zarr"
        gt_path = train_dir / f"{sample_id}.geff"
        if not sample_path.exists() or not gt_path.exists():
            raise FileNotFoundError(f"Missing paired sample inputs for {sample_id}")

        graph, _profile, detector, link_strategy, _reason, _distance = _build_v19(
            sample_path,
            args.max_timepoints,
        )
        route_label = f"{detector}/{link_strategy}"
        ground_truth = read_geff_graph(gt_path)
        before_signature = _signature(graph)
        baseline = evaluate_official_tracking(graph, ground_truth)

        for keep_fraction in args.keep_fractions:
            shadow = compute_adaptive_pruning_shadow(
                graph,
                keep_fraction=keep_fraction,
                fragment_size_threshold=args.fragment_size_threshold,
                min_fragmented_node_fraction=args.min_fragmented_node_fraction,
                preserve_division_components=True,
                route_label=route_label,
                allowed_routes=allowed_routes,
            )
            after = (
                evaluate_official_tracking(shadow.graph, ground_truth)
                if shadow.summary.activated
                else baseline
            )
            source_zero_perturbation = _signature(graph) == before_signature
            summary = shadow.summary
            row = AuditRow(
                sample_id=sample_id,
                detector=detector,
                link_strategy=link_strategy,
                route_label=route_label,
                keep_fraction=float(keep_fraction),
                activated=summary.activated,
                activation_reason=summary.activation_reason,
                fragmented_node_fraction=summary.fragmented_node_fraction,
                component_count=summary.component_count,
                protected_components=summary.protected_components,
                removed_components=summary.removed_components,
                removed_nodes=summary.removed_nodes,
                removed_edges=summary.removed_edges,
                baseline_nodes=baseline.predicted_nodes,
                shadow_nodes=after.predicted_nodes,
                estimated_total_nodes=baseline.estimated_total_nodes,
                baseline_edge_tp=baseline.edge_tp,
                shadow_edge_tp=after.edge_tp,
                edge_tp_delta=after.edge_tp - baseline.edge_tp,
                baseline_edge_fp=baseline.edge_fp,
                shadow_edge_fp=after.edge_fp,
                baseline_edge_fn=baseline.edge_fn,
                shadow_edge_fn=after.edge_fn,
                baseline_edge_jaccard=baseline.edge_jaccard,
                shadow_edge_jaccard=after.edge_jaccard,
                edge_jaccard_delta=_delta(after.edge_jaccard, baseline.edge_jaccard),
                baseline_adjusted_edge_jaccard=baseline.adjusted_edge_jaccard,
                shadow_adjusted_edge_jaccard=after.adjusted_edge_jaccard,
                adjusted_edge_delta=_delta(
                    after.adjusted_edge_jaccard,
                    baseline.adjusted_edge_jaccard,
                ),
                baseline_node_recall=baseline.node_recall,
                shadow_node_recall=after.node_recall,
                node_recall_delta=_delta(after.node_recall, baseline.node_recall),
                baseline_division_tp=baseline.division_tp,
                shadow_division_tp=after.division_tp,
                division_tp_delta=after.division_tp - baseline.division_tp,
                baseline_division_fp=baseline.division_fp,
                shadow_division_fp=after.division_fp,
                source_zero_perturbation=source_zero_perturbation,
            )
            rows.append(row)
            print(
                f"  keep={keep_fraction:.2f} active={row.activated} "
                f"frag={row.fragmented_node_fraction:.3f} removed={row.removed_nodes} "
                f"adj_delta={row.adjusted_edge_delta} edge_tp_delta={row.edge_tp_delta} "
                f"div_tp_delta={row.division_tp_delta} zero={source_zero_perturbation}",
                flush=True,
            )
        _write_rows(rows, output)
        print(f"  checkpoint={output} rows={len(rows)}", flush=True)

    _write_rows(rows, output)
    print(f"Saved {len(rows)} rows to {output}", flush=True)
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run official-metric adaptive component pruning as a read-only shadow audit."
    )
    parser.add_argument("--train-dir", default="train")
    parser.add_argument("--sample-ids", nargs="+", default=["battery"])
    parser.add_argument("--keep-fractions", nargs="+", type=float, default=[0.99, 0.97, 0.95])
    parser.add_argument("--fragment-size-threshold", type=int, default=7)
    parser.add_argument("--min-fragmented-node-fraction", type=float, default=0.50)
    parser.add_argument("--allowed-routes", nargs="*", default=None)
    parser.add_argument("--max-timepoints", type=int, default=100)
    parser.add_argument("--output", default="adaptive_pruning_shadow_13.csv")
    return parser.parse_args()


if __name__ == "__main__":
    run_audit(parse_args())
