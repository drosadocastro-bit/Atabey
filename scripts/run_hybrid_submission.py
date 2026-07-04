from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median

from atabey.baseline import build_baseline_graph
from atabey.detection.adaptive import ForegroundProfile, choose_settings_for_sample
from atabey.detection.baseline import threshold_local_maxima, threshold_local_maxima_cfar_sidelobe
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.submission.writer import write_submission
from atabey.tracking.nearest_neighbor import link_adjacent_timepoints
from atabey.types import Detection, LineageGraph


@dataclass(frozen=True)
class HybridRunRecord:
    sample_id: str
    sample_path: str
    route: str
    elapsed_seconds: float
    predicted_nodes: int
    predicted_edges: int
    rows_written: int
    detector: str
    threshold: float
    min_volume: int
    peak_min_distance_voxels: tuple[int, int, int]
    link_strategy: str
    max_link_distance_um: float
    median_largest_component_voxels: float
    median_foreground_fraction: float
    reason: str
    cfar_training_radius_voxels: tuple[int, int, int] | None
    cfar_guard_radius_voxels: tuple[int, int, int] | None
    cfar_k_sigma: float | None
    sidelobe_radius_voxels: tuple[int, int, int] | None
    sidelobe_floor_ratio: float | None
    max_detections_per_timepoint: int | None
    cfar_spike_fallback_count: int | None
    max_timepoints: int | None


@dataclass(frozen=True)
class HybridRunSummary:
    samples: int
    total_elapsed_seconds: float
    mean_elapsed_seconds: float
    total_predicted_nodes: int
    total_predicted_edges: int
    total_rows_written: int
    route_counts: dict[str, int]


def _parse_int_tuple(spec: str) -> tuple[int, int, int]:
    parts = [part.strip() for part in str(spec).split(",") if part.strip()]
    if len(parts) != 3:
        raise ValueError(f"Expected three comma-separated integers, got: {spec!r}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def discover_zarr_samples(input_dir: str | Path) -> list[Path]:
    root = Path(input_dir)
    return sorted(
        (path for path in root.iterdir() if path.is_dir() and path.name.endswith(".zarr")),
        key=lambda path: path.name,
    )


def _sample_id_from_path(sample_path: Path) -> str:
    return sample_path.name.removesuffix(".zarr")


def _is_profile_6bba_like_for_cfar(profile: ForegroundProfile) -> bool:
    """Heuristic route gate for dim/dense merged profiles seen in 6bba-like samples."""

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


def build_graph_cfar_sidelobe(
    *,
    sample_path: Path,
    threshold: float,
    cfar_training_radius_voxels: tuple[int, int, int],
    cfar_guard_radius_voxels: tuple[int, int, int],
    cfar_k_sigma: float,
    sidelobe_radius_voxels: tuple[int, int, int],
    sidelobe_floor_ratio: float,
    max_detections_per_timepoint: int | None,
    guardrail_spike_multiplier: float,
    guardrail_min_history: int,
    guardrail_history_window: int,
    guardrail_min_absolute_count: int,
    guardrail_fallback_threshold: float,
    guardrail_fallback_max_detections: int | None,
    link_strategy: str,
    max_link_distance_um: float,
    max_timepoints: int | None,
) -> tuple[LineageGraph, int]:
    sample_id = _sample_id_from_path(sample_path)
    array = open_competition_array(sample_path)
    total_timepoints = int(array.shape[0])
    if max_timepoints is not None:
        total_timepoints = min(total_timepoints, int(max_timepoints))

    graph = LineageGraph(sample_id=sample_id)
    previous: list[Detection] = []
    detections_by_node_id: dict[str, Detection] = {}
    predecessor_by_node_id: dict[str, Detection] = {}
    recent_counts: list[int] = []
    spike_fallback_count = 0

    for t in range(total_timepoints):
        volume = read_timepoint(array, t)
        current = threshold_local_maxima_cfar_sidelobe(
            sample_id,
            t,
            volume,
            threshold=threshold,
            min_distance_voxels=(1, 5, 5),
            max_detections=max_detections_per_timepoint,
            cfar_training_radius_voxels=cfar_training_radius_voxels,
            cfar_guard_radius_voxels=cfar_guard_radius_voxels,
            cfar_k_sigma=cfar_k_sigma,
            sidelobe_radius_voxels=sidelobe_radius_voxels,
            sidelobe_floor_ratio=sidelobe_floor_ratio,
        )

        use_guardrail = False
        if len(recent_counts) >= int(guardrail_min_history):
            recent_window = recent_counts[-int(guardrail_history_window) :]
            baseline_count = float(median(recent_window))
            spike_limit = max(
                int(guardrail_min_absolute_count),
                int(round(baseline_count * float(guardrail_spike_multiplier))),
            )
            use_guardrail = len(current) > spike_limit

        if use_guardrail:
            current = threshold_local_maxima(
                sample_id,
                t,
                volume,
                threshold=guardrail_fallback_threshold,
                min_distance_voxels=(1, 5, 5),
                max_detections=guardrail_fallback_max_detections,
            )
            spike_fallback_count += 1

        recent_counts.append(len(current))

        for detection in current:
            graph.add_detection(detection)
            detections_by_node_id[detection.node_id] = detection

        edges = link_adjacent_timepoints(
            previous,
            current,
            max_link_distance_um,
            strategy=link_strategy,
            predecessor_by_node_id=predecessor_by_node_id,
        )
        for edge in edges:
            graph.add_edge(edge)
            predecessor_by_node_id[edge.target_id] = detections_by_node_id[edge.source_id]

        previous = current

    return graph, spike_fallback_count


def build_hybrid_graph_for_sample(
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
) -> tuple[LineageGraph, HybridRunRecord]:
    profile, settings = choose_settings_for_sample(sample_path)
    use_cfar = _should_use_cfar_route(
        profile=profile,
        adaptive_detector=settings.detector,
        cfar_route_policy=cfar_route_policy,
    )
    route = "cfar_sidelobe" if use_cfar else "adaptive_baseline"

    start = time.perf_counter()
    if use_cfar:
        graph, cfar_spike_fallback_count = build_graph_cfar_sidelobe(
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
        detector = "cfar_sidelobe"
        threshold = cfar_threshold
        min_volume = settings.min_volume
        peak_min_distance_voxels = settings.peak_min_distance_voxels
        link_strategy = cfar_link_strategy
        max_link_distance_um = cfar_max_link_distance_um
        cfar_training = cfar_training_radius_voxels
        cfar_guard = cfar_guard_radius_voxels
        cfar_sigma = cfar_k_sigma
        sidelobe_radius = sidelobe_radius_voxels
        sidelobe_floor = sidelobe_floor_ratio
    else:
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
        detector = settings.detector
        threshold = settings.threshold
        min_volume = settings.min_volume
        peak_min_distance_voxels = settings.peak_min_distance_voxels
        link_strategy = baseline_link_strategy
        max_link_distance_um = settings.max_link_distance_um
        cfar_training = None
        cfar_guard = None
        cfar_sigma = None
        sidelobe_radius = None
        sidelobe_floor = None
        cfar_spike_fallback_count = None
        if settings.detector == "local_maxima":
            route = "v9_style_adaptive"
    elapsed = time.perf_counter() - start

    predicted_nodes = len(graph.detections)
    predicted_edges = len(graph.edges)
    record = HybridRunRecord(
        sample_id=graph.sample_id,
        sample_path=str(sample_path),
        route=route,
        elapsed_seconds=round(elapsed, 2),
        predicted_nodes=predicted_nodes,
        predicted_edges=predicted_edges,
        rows_written=predicted_nodes + predicted_edges,
        detector=detector,
        threshold=threshold,
        min_volume=min_volume,
        peak_min_distance_voxels=peak_min_distance_voxels,
        link_strategy=link_strategy,
        max_link_distance_um=max_link_distance_um,
        median_largest_component_voxels=profile.median_largest_component_voxels,
        median_foreground_fraction=profile.median_foreground_fraction,
        reason=settings.reason,
        cfar_training_radius_voxels=cfar_training,
        cfar_guard_radius_voxels=cfar_guard,
        cfar_k_sigma=cfar_sigma,
        sidelobe_radius_voxels=sidelobe_radius,
        sidelobe_floor_ratio=sidelobe_floor,
        max_detections_per_timepoint=max_detections_per_timepoint if use_cfar else None,
        cfar_spike_fallback_count=cfar_spike_fallback_count,
        max_timepoints=max_timepoints,
    )
    return graph, record


def run_hybrid_submission(
    *,
    input_dir: Path,
    output_csv: Path,
    report_json: Path,
    summary_json: Path | None,
    max_samples: int | None,
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
) -> tuple[list[HybridRunRecord], HybridRunSummary]:
    sample_paths = discover_zarr_samples(input_dir)
    if max_samples is not None:
        sample_paths = sample_paths[: int(max_samples)]
    if not sample_paths:
        raise FileNotFoundError(f"No .zarr samples found in {input_dir}")

    graphs: list[LineageGraph] = []
    records: list[HybridRunRecord] = []
    for sample_path in sample_paths:
        graph, record = build_hybrid_graph_for_sample(
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
        graphs.append(graph)
        records.append(record)
        print(json.dumps(asdict(record)), flush=True)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    report_json.parent.mkdir(parents=True, exist_ok=True)
    if summary_json is not None:
        summary_json.parent.mkdir(parents=True, exist_ok=True)

    output_path = write_submission(graphs, output_csv)
    report_json.write_text(json.dumps([asdict(record) for record in records], indent=2), encoding="utf-8")

    route_counts: dict[str, int] = {}
    for record in records:
        route_counts[record.route] = route_counts.get(record.route, 0) + 1

    total_elapsed = float(sum(record.elapsed_seconds for record in records))
    total_nodes = int(sum(record.predicted_nodes for record in records))
    total_edges = int(sum(record.predicted_edges for record in records))
    total_rows = int(sum(record.rows_written for record in records))
    summary = HybridRunSummary(
        samples=len(records),
        total_elapsed_seconds=round(total_elapsed, 2),
        mean_elapsed_seconds=round(total_elapsed / len(records), 2),
        total_predicted_nodes=total_nodes,
        total_predicted_edges=total_edges,
        total_rows_written=total_rows,
        route_counts=route_counts,
    )

    if summary_json is not None:
        summary_json.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")

    print(json.dumps({"submission_csv": str(output_path), "report_json": str(report_json)}), flush=True)
    if summary_json is not None:
        print(json.dumps({"summary_json": str(summary_json)}), flush=True)
    print(json.dumps({"summary": asdict(summary)}), flush=True)
    return records, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run hybrid adaptive baseline + selective CFAR+sidelobe submission.")
    parser.add_argument("--input-dir", default="test", help="Directory containing .zarr samples.")
    parser.add_argument("--output-csv", default="submissions/hybrid_submission.csv", help="Output submission CSV path.")
    parser.add_argument("--report-json", default="submissions/hybrid_report.json", help="Per-sample report path.")
    parser.add_argument("--summary-json", default="submissions/hybrid_summary.json", help="Aggregate summary path.")
    parser.add_argument("--max-samples", type=int, default=None, help="Optional sample limit for smoke tests.")
    parser.add_argument("--max-timepoints", type=int, default=None, help="Optional timepoint limit for bounded calibration.")
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
    parser.add_argument(
        "--cfar-link-strategy",
        default="motion_mutual",
        choices=["greedy", "mutual", "motion", "motion_division", "motion_mutual", "motion_crowding", "motion_mutual_latent"],
        help="Linking strategy for CFAR-routed samples.",
    )
    parser.add_argument("--cfar-max-link-distance-um", type=float, default=9.0, help="CFAR route link distance.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_hybrid_submission(
        input_dir=Path(args.input_dir),
        output_csv=Path(args.output_csv),
        report_json=Path(args.report_json),
        summary_json=Path(args.summary_json) if args.summary_json else None,
        max_samples=args.max_samples,
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
