from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from atabey.baseline import build_baseline_graph
from atabey.detection.adaptive import ForegroundProfile, choose_settings_for_sample
from atabey.evaluation.sparse_ground_truth import evaluate_sparse_ground_truth
from atabey.io.geff_reader import read_geff_graph
from run_hybrid_submission import build_graph_cfar_sidelobe


@dataclass(frozen=True)
class TrainHybridEvalRecord:
    sample_id: str
    route: str
    elapsed_seconds: float
    predicted_nodes: int
    predicted_edges: int
    sparse_nodes: int
    matched_sparse_nodes: int
    sparse_recall: float | None
    sparse_edge_recall: float | None
    predicted_to_estimated_node_ratio: float | None
    quality_score: float
    quality_per_second: float
    detector: str
    link_strategy: str
    median_largest_component_voxels: float
    median_foreground_fraction: float
    reason: str
    max_detections_per_timepoint: int | None
    max_timepoints: int | None


@dataclass(frozen=True)
class TrainHybridEvalSummary:
    route: str
    samples: int
    total_elapsed_seconds: float
    mean_elapsed_seconds: float
    total_predicted_nodes: int
    total_predicted_edges: int
    mean_sparse_recall: float | None
    mean_sparse_edge_recall: float | None
    mean_quality_score: float
    quality_per_second: float


def _parse_int_tuple(spec: str) -> tuple[int, int, int]:
    parts = [part.strip() for part in str(spec).split(",") if part.strip()]
    if len(parts) != 3:
        raise ValueError(f"Expected three comma-separated integers, got: {spec!r}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def _safe_rate(numerator: float, elapsed_seconds: float) -> float:
    return float(numerator) / max(float(elapsed_seconds), 1e-9)


def _quality_score(sparse_recall: float | None, sparse_edge_recall: float | None) -> float:
    node_component = 0.0 if sparse_recall is None else float(sparse_recall)
    edge_component = 0.0 if sparse_edge_recall is None else float(sparse_edge_recall)
    return 0.5 * node_component + 0.5 * edge_component


def _mean_optional(values: list[float | None]) -> float | None:
    filtered = [float(value) for value in values if value is not None]
    if not filtered:
        return None
    return float(sum(filtered) / len(filtered))


def _is_profile_6bba_like_for_cfar(profile: ForegroundProfile) -> bool:
    return (
        profile.median_largest_component_voxels >= 100_000
        and profile.median_largest_component_voxels <= 600_000
        and profile.median_foreground_fraction >= 0.05
        and profile.median_foreground_fraction <= 0.20
    )


def _should_use_cfar_route(*, profile: ForegroundProfile, adaptive_detector: str, cfar_route_policy: str) -> bool:
    if adaptive_detector != "local_maxima":
        return False
    if cfar_route_policy == "merged_all":
        return True
    if cfar_route_policy == "merged_6bba_only":
        return _is_profile_6bba_like_for_cfar(profile)
    raise ValueError(f"Unknown CFAR route policy: {cfar_route_policy}")


def _build_v9_style_graph(sample_path: Path, max_timepoints: int | None):
    profile, settings = choose_settings_for_sample(sample_path)
    link_strategy = "motion_mutual" if settings.detector == "local_maxima" else settings.link_strategy
    reason = settings.reason.replace(" with a bounded one-frame latent recovery bridge", "")
    graph = build_baseline_graph(
        sample_path,
        max_timepoints=max_timepoints,
        threshold=settings.threshold,
        min_volume=settings.min_volume,
        max_link_distance_um=settings.max_link_distance_um,
        link_strategy=link_strategy,
        detector=settings.detector,
        peak_min_distance_voxels=settings.peak_min_distance_voxels,
    )
    return graph, profile, settings.detector, link_strategy, reason


def _build_hybrid_graph(
    *,
    sample_path: Path,
    max_timepoints: int | None,
    cfar_threshold: float,
    cfar_training_radius_voxels: tuple[int, int, int],
    cfar_guard_radius_voxels: tuple[int, int, int],
    cfar_k_sigma: float,
    sidelobe_radius_voxels: tuple[int, int, int],
    sidelobe_floor_ratio: float,
    max_detections_per_timepoint: int | None,
    cfar_link_strategy: str,
    cfar_max_link_distance_um: float,
    cfar_route_policy: str,
):
    profile, settings = choose_settings_for_sample(sample_path)
    if _should_use_cfar_route(
        profile=profile,
        adaptive_detector=settings.detector,
        cfar_route_policy=cfar_route_policy,
    ):
        graph, _ = build_graph_cfar_sidelobe(
            sample_path=sample_path,
            threshold=cfar_threshold,
            cfar_training_radius_voxels=cfar_training_radius_voxels,
            cfar_guard_radius_voxels=cfar_guard_radius_voxels,
            cfar_k_sigma=cfar_k_sigma,
            sidelobe_radius_voxels=sidelobe_radius_voxels,
            sidelobe_floor_ratio=sidelobe_floor_ratio,
            max_detections_per_timepoint=max_detections_per_timepoint,
            guardrail_spike_multiplier=1.8,
            guardrail_min_history=6,
            guardrail_history_window=12,
            guardrail_min_absolute_count=1200,
            guardrail_fallback_threshold=0.65,
            guardrail_fallback_max_detections=max_detections_per_timepoint,
            link_strategy=cfar_link_strategy,
            max_link_distance_um=cfar_max_link_distance_um,
            max_timepoints=max_timepoints,
        )
        return graph, profile, "cfar_sidelobe", cfar_link_strategy, settings.reason

    baseline_link_strategy = "motion_mutual" if settings.detector == "local_maxima" else settings.link_strategy
    graph = build_baseline_graph(
        sample_path,
        max_timepoints=max_timepoints,
        threshold=settings.threshold,
        min_volume=settings.min_volume,
        max_link_distance_um=settings.max_link_distance_um,
        link_strategy=baseline_link_strategy,
        detector=settings.detector,
        peak_min_distance_voxels=settings.peak_min_distance_voxels,
    )
    reason = settings.reason.replace(" with a bounded one-frame latent recovery bridge", "")
    return graph, profile, settings.detector, baseline_link_strategy, reason


def _record_for_graph(
    *,
    route: str,
    elapsed_seconds: float,
    graph,
    ground_truth,
    profile,
    detector: str,
    link_strategy: str,
    reason: str,
    max_detections_per_timepoint: int | None,
    max_timepoints: int | None,
) -> TrainHybridEvalRecord:
    report = evaluate_sparse_ground_truth(graph, ground_truth, match_radius_um=7.0)
    quality_score = _quality_score(report.sparse_recall, report.sparse_edge_recall)
    return TrainHybridEvalRecord(
        sample_id=graph.sample_id,
        route=route,
        elapsed_seconds=round(elapsed_seconds, 2),
        predicted_nodes=report.predicted_nodes,
        predicted_edges=report.predicted_edges,
        sparse_nodes=report.sparse_ground_truth_nodes,
        matched_sparse_nodes=report.matched_sparse_nodes,
        sparse_recall=report.sparse_recall,
        sparse_edge_recall=report.sparse_edge_recall,
        predicted_to_estimated_node_ratio=report.predicted_to_estimated_node_ratio,
        quality_score=quality_score,
        quality_per_second=_safe_rate(quality_score, elapsed_seconds),
        detector=detector,
        link_strategy=link_strategy,
        median_largest_component_voxels=profile.median_largest_component_voxels,
        median_foreground_fraction=profile.median_foreground_fraction,
        reason=reason,
        max_detections_per_timepoint=max_detections_per_timepoint,
        max_timepoints=max_timepoints,
    )


def _build_summaries(records: list[TrainHybridEvalRecord]) -> list[TrainHybridEvalSummary]:
    routes = sorted({record.route for record in records})
    summaries: list[TrainHybridEvalSummary] = []
    for route in routes:
        items = [record for record in records if record.route == route]
        total_elapsed = float(sum(item.elapsed_seconds for item in items))
        quality_total = float(sum(item.quality_score for item in items))
        summaries.append(
            TrainHybridEvalSummary(
                route=route,
                samples=len(items),
                total_elapsed_seconds=round(total_elapsed, 2),
                mean_elapsed_seconds=round(total_elapsed / len(items), 2),
                total_predicted_nodes=int(sum(item.predicted_nodes for item in items)),
                total_predicted_edges=int(sum(item.predicted_edges for item in items)),
                mean_sparse_recall=_mean_optional([item.sparse_recall for item in items]),
                mean_sparse_edge_recall=_mean_optional([item.sparse_edge_recall for item in items]),
                mean_quality_score=quality_total / len(items),
                quality_per_second=_safe_rate(quality_total, total_elapsed),
            )
        )
    summaries.sort(key=lambda summary: summary.route)
    return summaries


def run_train_evaluation(
    *,
    train_dir: Path,
    sample_ids: list[str],
    output_json: Path,
    output_summary_json: Path | None,
    max_timepoints: int | None,
    cfar_threshold: float,
    cfar_training_radius_voxels: tuple[int, int, int],
    cfar_guard_radius_voxels: tuple[int, int, int],
    cfar_k_sigma: float,
    sidelobe_radius_voxels: tuple[int, int, int],
    sidelobe_floor_ratio: float,
    max_detections_per_timepoint: int | None,
    cfar_link_strategy: str,
    cfar_max_link_distance_um: float,
    cfar_route_policy: str,
) -> list[TrainHybridEvalRecord]:
    records: list[TrainHybridEvalRecord] = []
    for sample_id in sample_ids:
        sample_path = train_dir / f"{sample_id}.zarr"
        ground_truth = read_geff_graph(train_dir / f"{sample_id}.geff")

        start = time.perf_counter()
        graph, profile, detector, link_strategy, reason = _build_v9_style_graph(sample_path, max_timepoints)
        elapsed = time.perf_counter() - start
        record = _record_for_graph(
            route="v9_style_adaptive",
            elapsed_seconds=elapsed,
            graph=graph,
            ground_truth=ground_truth,
            profile=profile,
            detector=detector,
            link_strategy=link_strategy,
            reason=reason,
            max_detections_per_timepoint=None,
            max_timepoints=max_timepoints,
        )
        records.append(record)
        print(json.dumps(asdict(record)), flush=True)

        start = time.perf_counter()
        graph, profile, detector, link_strategy, reason = _build_hybrid_graph(
            sample_path=sample_path,
            max_timepoints=max_timepoints,
            cfar_threshold=cfar_threshold,
            cfar_training_radius_voxels=cfar_training_radius_voxels,
            cfar_guard_radius_voxels=cfar_guard_radius_voxels,
            cfar_k_sigma=cfar_k_sigma,
            sidelobe_radius_voxels=sidelobe_radius_voxels,
            sidelobe_floor_ratio=sidelobe_floor_ratio,
            max_detections_per_timepoint=max_detections_per_timepoint,
            cfar_link_strategy=cfar_link_strategy,
            cfar_max_link_distance_um=cfar_max_link_distance_um,
            cfar_route_policy=cfar_route_policy,
        )
        elapsed = time.perf_counter() - start
        record = _record_for_graph(
            route="hybrid_cfar_sidelobe",
            elapsed_seconds=elapsed,
            graph=graph,
            ground_truth=ground_truth,
            profile=profile,
            detector=detector,
            link_strategy=link_strategy,
            reason=reason,
            max_detections_per_timepoint=max_detections_per_timepoint if detector == "cfar_sidelobe" else None,
            max_timepoints=max_timepoints,
        )
        records.append(record)
        print(json.dumps(asdict(record)), flush=True)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps([asdict(record) for record in records], indent=2), encoding="utf-8")

    summaries = _build_summaries(records)
    if output_summary_json is not None:
        output_summary_json.parent.mkdir(parents=True, exist_ok=True)
        output_summary_json.write_text(json.dumps([asdict(summary) for summary in summaries], indent=2), encoding="utf-8")
        print(json.dumps({"output_summary_json": str(output_summary_json)}), flush=True)
    print(json.dumps({"output_json": str(output_json), "records": len(records), "summaries": [asdict(summary) for summary in summaries]}), flush=True)
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare v9-style adaptive routing against hybrid CFAR+sidelobe on sparse train labels.")
    parser.add_argument("--train-dir", default="train", help="Directory containing .zarr/.geff train pairs.")
    parser.add_argument("--sample-ids", nargs="+", default=["44b6_40c45f5a", "6bba_05db0fb1"], help="Sample IDs to evaluate.")
    parser.add_argument("--output-json", default="submissions/train_slice_hybrid_eval.json", help="Output record JSON path.")
    parser.add_argument("--output-summary-json", default="submissions/train_slice_hybrid_eval_summary.json", help="Output summary JSON path.")
    parser.add_argument("--max-timepoints", type=int, default=100, help="Optional timepoint cap.")
    parser.add_argument("--cfar-threshold", type=float, default=0.50, help="CFAR global normalized floor threshold.")
    parser.add_argument("--cfar-training-radius", default="1,6,6", help="CFAR training radius as tz,ty,tx.")
    parser.add_argument("--cfar-guard-radius", default="0,1,1", help="CFAR guard radius as gz,gy,gx.")
    parser.add_argument("--cfar-k-sigma", type=float, default=1.1, help="CFAR k-sigma multiplier.")
    parser.add_argument("--sidelobe-radius", default="1,12,12", help="Sidelobe suppression radius as sz,sy,sx.")
    parser.add_argument("--sidelobe-floor", type=float, default=0.85, help="Sidelobe floor ratio.")
    parser.add_argument("--max-detections-per-timepoint", type=int, default=900, help="CFAR route detection cap.")
    parser.add_argument(
        "--cfar-route-policy",
        default="merged_all",
        choices=["merged_all", "merged_6bba_only"],
        help=(
            "Which adaptive local-maxima samples should be routed through CFAR+sidelobe; "
            "merged_6bba_only uses profile-based gating (dim/dense merged foreground), not sample prefixes."
        ),
    )
    parser.add_argument("--cfar-link-strategy", default="motion_mutual", help="CFAR route link strategy.")
    parser.add_argument("--cfar-max-link-distance-um", type=float, default=9.0, help="CFAR route link distance.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_train_evaluation(
        train_dir=Path(args.train_dir),
        sample_ids=list(args.sample_ids),
        output_json=Path(args.output_json),
        output_summary_json=Path(args.output_summary_json) if args.output_summary_json else None,
        max_timepoints=args.max_timepoints,
        cfar_threshold=float(args.cfar_threshold),
        cfar_training_radius_voxels=_parse_int_tuple(args.cfar_training_radius),
        cfar_guard_radius_voxels=_parse_int_tuple(args.cfar_guard_radius),
        cfar_k_sigma=float(args.cfar_k_sigma),
        sidelobe_radius_voxels=_parse_int_tuple(args.sidelobe_radius),
        sidelobe_floor_ratio=float(args.sidelobe_floor),
        max_detections_per_timepoint=args.max_detections_per_timepoint,
        cfar_link_strategy=str(args.cfar_link_strategy),
        cfar_max_link_distance_um=float(args.cfar_max_link_distance_um),
        cfar_route_policy=str(args.cfar_route_policy),
    )


if __name__ == "__main__":
    main()
