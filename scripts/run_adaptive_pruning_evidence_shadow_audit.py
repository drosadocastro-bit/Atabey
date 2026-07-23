from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.evaluation.official_tracking_metric import evaluate_official_tracking
from atabey.io.geff_reader import read_geff_graph
from atabey.tracking.adaptive_pruning_evidence_shadow import (
    compute_prediction_evidence_pruning_shadow,
)
from run_adaptive_pruning_shadow_audit import (
    DEFAULT_BATTERY,
    AuditRow,
    _build_v19,
    _delta,
    _signature,
    _write_rows,
)


def run_audit(args: argparse.Namespace) -> list[AuditRow]:
    train_dir = Path(args.train_dir)
    sample_ids = DEFAULT_BATTERY if args.sample_ids == ["battery"] else tuple(args.sample_ids)
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
        shadow = compute_prediction_evidence_pruning_shadow(
            graph,
            keep_fraction=args.keep_fraction,
            fragment_size_threshold=args.fragment_size_threshold,
            min_fragmented_node_fraction=args.min_fragmented_node_fraction,
            preserve_division_components=True,
            route_label=route_label,
            temporal_support_radius_um=args.temporal_support_radius_um,
            same_frame_duplicate_radius_um=args.same_frame_duplicate_radius_um,
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
            keep_fraction=float(args.keep_fraction),
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
        _write_rows(rows, output)
        print(
            f"  active={row.activated} frag={row.fragmented_node_fraction:.3f} "
            f"removed={row.removed_nodes} adj_delta={row.adjusted_edge_delta} "
            f"edge_tp_delta={row.edge_tp_delta} node_delta={row.node_recall_delta} "
            f"div_tp_delta={row.division_tp_delta} zero={source_zero_perturbation}",
            flush=True,
        )
        print(f"  checkpoint={output} rows={len(rows)}", flush=True)

    print(f"Saved {len(rows)} rows to {output}", flush=True)
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the frozen prediction-evidence pruning shadow audit."
    )
    parser.add_argument("--train-dir", default="train")
    parser.add_argument("--sample-ids", nargs="+", default=["battery"])
    parser.add_argument("--keep-fraction", type=float, default=0.97)
    parser.add_argument("--fragment-size-threshold", type=int, default=7)
    parser.add_argument("--min-fragmented-node-fraction", type=float, default=0.50)
    parser.add_argument("--temporal-support-radius-um", type=float, default=14.0)
    parser.add_argument("--same-frame-duplicate-radius-um", type=float, default=7.0)
    parser.add_argument("--max-timepoints", type=int, default=100)
    parser.add_argument(
        "--output",
        default="adaptive_pruning_evidence_shadow_battery_13.csv",
    )
    return parser.parse_args()


if __name__ == "__main__":
    run_audit(parse_args())
