from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from atabey.detection.baseline import (
    threshold_local_maxima,
    threshold_local_maxima_cfar,
    threshold_local_maxima_cfar_sidelobe,
)
from atabey.evaluation.sparse_ground_truth import evaluate_sparse_ground_truth
from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.tracking.nearest_neighbor import link_adjacent_timepoints
from atabey.types import Detection, LineageGraph


@dataclass(frozen=True)
class ExperimentRecord:
    sample_id: str
    strategy: str
    elapsed_seconds: float
    predicted_nodes: int
    predicted_edges: int
    sparse_nodes: int
    matched_sparse_nodes: int
    sparse_recall: float | None
    sparse_edge_recall: float | None
    predicted_to_estimated_node_ratio: float | None
    nodes_per_second: float
    edges_per_second: float
    matched_sparse_nodes_per_second: float
    quality_score: float
    quality_per_second: float


@dataclass(frozen=True)
class StrategySummary:
    strategy: str
    samples: int
    total_elapsed_seconds: float
    mean_elapsed_seconds: float
    total_predicted_nodes: int
    total_predicted_edges: int
    mean_sparse_recall: float | None
    mean_sparse_edge_recall: float | None
    mean_quality_score: float
    quality_per_second: float
    mean_nodes_per_second: float
    mean_edges_per_second: float


@dataclass(frozen=True)
class DetectorParams:
    threshold: float
    cfar_training_radius_voxels: tuple[int, int, int]
    cfar_guard_radius_voxels: tuple[int, int, int]
    cfar_k_sigma: float
    sidelobe_radius_voxels: tuple[int, int, int]
    sidelobe_floor_ratio: float
    max_detections_per_timepoint: int | None = None


DEFAULT_PARAMS = DetectorParams(
    threshold=0.50,
    cfar_training_radius_voxels=(1, 7, 7),
    cfar_guard_radius_voxels=(0, 1, 1),
    cfar_k_sigma=1.0,
    sidelobe_radius_voxels=(0, 2, 2),
    sidelobe_floor_ratio=0.85,
    max_detections_per_timepoint=None,
)


def _parse_int_tuple(spec: str) -> tuple[int, int, int]:
    parts = [part.strip() for part in str(spec).split(",") if part.strip()]
    if len(parts) != 3:
        raise ValueError(f"Expected three comma-separated integers, got: {spec!r}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def _parse_sweep_specs(specs: list[str] | None) -> list[DetectorParams]:
    if not specs:
        return [DEFAULT_PARAMS]

    parsed: list[DetectorParams] = []
    for spec in specs:
        # Format:
        # threshold|tz,ty,tx|gz,gy,gx|k_sigma|sz,sy,sx|sidelobe_floor
        parts = [part.strip() for part in spec.split("|")]
        if len(parts) != 6:
            raise ValueError(
                "Sweep spec must have 6 '|' separated fields: "
                "threshold|tz,ty,tx|gz,gy,gx|k_sigma|sz,sy,sx|sidelobe_floor"
            )
        parsed.append(
            DetectorParams(
                threshold=float(parts[0]),
                cfar_training_radius_voxels=_parse_int_tuple(parts[1]),
                cfar_guard_radius_voxels=_parse_int_tuple(parts[2]),
                cfar_k_sigma=float(parts[3]),
                sidelobe_radius_voxels=_parse_int_tuple(parts[4]),
                sidelobe_floor_ratio=float(parts[5]),
            )
        )
    return parsed


def build_graph_with_detector(
    *,
    sample_id: str,
    sample_path: Path,
    detector: str,
    detector_params: DetectorParams,
    max_timepoints: int | None = None,
) -> LineageGraph:
    array = open_competition_array(sample_path)
    total_timepoints = int(array.shape[0])
    if max_timepoints is not None:
        total_timepoints = min(total_timepoints, int(max_timepoints))

    graph = LineageGraph(sample_id=sample_id)
    previous: list[Detection] = []
    detections_by_node_id: dict[str, Detection] = {}
    predecessor_by_node_id: dict[str, Detection] = {}

    for t in range(total_timepoints):
        volume = read_timepoint(array, t)
        if detector == "local_maxima":
            current = threshold_local_maxima(
                sample_id,
                t,
                volume,
                threshold=max(0.65, detector_params.threshold),
                min_distance_voxels=(1, 5, 5),
                max_detections=detector_params.max_detections_per_timepoint,
            )
        elif detector == "cfar":
            current = threshold_local_maxima_cfar(
                sample_id,
                t,
                volume,
                threshold=detector_params.threshold,
                min_distance_voxels=(1, 5, 5),
                max_detections=detector_params.max_detections_per_timepoint,
                cfar_training_radius_voxels=detector_params.cfar_training_radius_voxels,
                cfar_guard_radius_voxels=detector_params.cfar_guard_radius_voxels,
                cfar_k_sigma=detector_params.cfar_k_sigma,
            )
        elif detector == "cfar_sidelobe":
            current = threshold_local_maxima_cfar_sidelobe(
                sample_id,
                t,
                volume,
                threshold=detector_params.threshold,
                min_distance_voxels=(1, 5, 5),
                max_detections=detector_params.max_detections_per_timepoint,
                cfar_training_radius_voxels=detector_params.cfar_training_radius_voxels,
                cfar_guard_radius_voxels=detector_params.cfar_guard_radius_voxels,
                cfar_k_sigma=detector_params.cfar_k_sigma,
                sidelobe_radius_voxels=detector_params.sidelobe_radius_voxels,
                sidelobe_floor_ratio=detector_params.sidelobe_floor_ratio,
            )
        else:
            raise ValueError(f"Unknown detector strategy: {detector}")

        for detection in current:
            graph.add_detection(detection)
            detections_by_node_id[detection.node_id] = detection

        edges = link_adjacent_timepoints(
            previous,
            current,
            9.0,
            strategy="motion_mutual",
            predecessor_by_node_id=predecessor_by_node_id,
        )
        for edge in edges:
            graph.add_edge(edge)
            predecessor_by_node_id[edge.target_id] = detections_by_node_id[edge.source_id]

        previous = current

    return graph


def _safe_rate(numerator: float, elapsed_seconds: float) -> float:
    elapsed = max(float(elapsed_seconds), 1e-9)
    return float(numerator) / elapsed


def _quality_score(sparse_recall: float | None, sparse_edge_recall: float | None) -> float:
    # Balanced local quality proxy used only for ranking calibration experiments.
    node_component = 0.0 if sparse_recall is None else float(sparse_recall)
    edge_component = 0.0 if sparse_edge_recall is None else float(sparse_edge_recall)
    return 0.5 * node_component + 0.5 * edge_component


def _mean_optional(values: list[float | None]) -> float | None:
    filtered = [float(value) for value in values if value is not None]
    if not filtered:
        return None
    return float(sum(filtered) / len(filtered))


def _build_strategy_summaries(records: list[ExperimentRecord]) -> list[StrategySummary]:
    grouped: dict[str, list[ExperimentRecord]] = {}
    for record in records:
        grouped.setdefault(record.strategy, []).append(record)

    summaries: list[StrategySummary] = []
    for strategy, items in grouped.items():
        total_elapsed = float(sum(item.elapsed_seconds for item in items))
        total_nodes = int(sum(item.predicted_nodes for item in items))
        total_edges = int(sum(item.predicted_edges for item in items))
        quality_total = float(sum(item.quality_score for item in items))
        summary = StrategySummary(
            strategy=strategy,
            samples=len(items),
            total_elapsed_seconds=round(total_elapsed, 2),
            mean_elapsed_seconds=round(total_elapsed / len(items), 2),
            total_predicted_nodes=total_nodes,
            total_predicted_edges=total_edges,
            mean_sparse_recall=_mean_optional([item.sparse_recall for item in items]),
            mean_sparse_edge_recall=_mean_optional([item.sparse_edge_recall for item in items]),
            mean_quality_score=quality_total / len(items),
            quality_per_second=_safe_rate(quality_total, total_elapsed),
            mean_nodes_per_second=sum(item.nodes_per_second for item in items) / len(items),
            mean_edges_per_second=sum(item.edges_per_second for item in items) / len(items),
        )
        summaries.append(summary)

    summaries.sort(key=lambda item: item.quality_per_second, reverse=True)
    return summaries


def run_experiment(
    *,
    train_dir: Path,
    sample_ids: list[str],
    output_json: Path,
    max_timepoints: int | None,
    sweep_specs: list[DetectorParams],
    output_summary_json: Path | None = None,
    top_k: int = 10,
) -> list[ExperimentRecord]:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    records: list[ExperimentRecord] = []
    strategies = [
        ("local_maxima_baseline", "local_maxima"),
        ("cfar", "cfar"),
        ("cfar_sidelobe", "cfar_sidelobe"),
    ]

    for params in sweep_specs:
        suffix = (
            f"thr{params.threshold:.2f}_"
            f"tr{params.cfar_training_radius_voxels[0]}-{params.cfar_training_radius_voxels[1]}-{params.cfar_training_radius_voxels[2]}_"
            f"gr{params.cfar_guard_radius_voxels[0]}-{params.cfar_guard_radius_voxels[1]}-{params.cfar_guard_radius_voxels[2]}_"
            f"k{params.cfar_k_sigma:.2f}_"
            f"sr{params.sidelobe_radius_voxels[0]}-{params.sidelobe_radius_voxels[1]}-{params.sidelobe_radius_voxels[2]}_"
            f"sf{params.sidelobe_floor_ratio:.2f}_"
            f"cap{params.max_detections_per_timepoint if params.max_detections_per_timepoint is not None else 'none'}"
        )
        for sample_id in sample_ids:
            sample_path = train_dir / f"{sample_id}.zarr"
            geff_path = train_dir / f"{sample_id}.geff"
            ground_truth = read_geff_graph(geff_path)
            for strategy_name, detector in strategies:
                start = time.perf_counter()
                graph = build_graph_with_detector(
                    sample_id=sample_id,
                    sample_path=sample_path,
                    detector=detector,
                    detector_params=params,
                    max_timepoints=max_timepoints,
                )
                elapsed = time.perf_counter() - start
                report = evaluate_sparse_ground_truth(graph, ground_truth, match_radius_um=7.0)
                quality_score = _quality_score(report.sparse_recall, report.sparse_edge_recall)
                record = ExperimentRecord(
                    sample_id=sample_id,
                    strategy=f"{strategy_name}|{suffix}",
                    elapsed_seconds=round(elapsed, 2),
                    predicted_nodes=report.predicted_nodes,
                    predicted_edges=report.predicted_edges,
                    sparse_nodes=report.sparse_ground_truth_nodes,
                    matched_sparse_nodes=report.matched_sparse_nodes,
                    sparse_recall=report.sparse_recall,
                    sparse_edge_recall=report.sparse_edge_recall,
                    predicted_to_estimated_node_ratio=report.predicted_to_estimated_node_ratio,
                    nodes_per_second=_safe_rate(report.predicted_nodes, elapsed),
                    edges_per_second=_safe_rate(report.predicted_edges, elapsed),
                    matched_sparse_nodes_per_second=_safe_rate(report.matched_sparse_nodes, elapsed),
                    quality_score=quality_score,
                    quality_per_second=_safe_rate(quality_score, elapsed),
                )
                records.append(record)
                print(json.dumps(asdict(record)), flush=True)

    output_json.write_text(json.dumps([asdict(record) for record in records], indent=2), encoding="utf-8")
    summaries = _build_strategy_summaries(records)
    top_ranked = summaries[: max(0, int(top_k))]
    print(
        json.dumps(
            {
                "quality_score_formula": "0.5*sparse_recall + 0.5*sparse_edge_recall",
                "ranking_metric": "quality_per_second",
                "top_ranked": [asdict(item) for item in top_ranked],
            }
        ),
        flush=True,
    )
    if output_summary_json is not None:
        output_summary_json.parent.mkdir(parents=True, exist_ok=True)
        output_summary_json.write_text(
            json.dumps(
                {
                    "quality_score_formula": "0.5*sparse_recall + 0.5*sparse_edge_recall",
                    "ranking_metric": "quality_per_second",
                    "strategies": [asdict(item) for item in summaries],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(json.dumps({"output_summary_json": str(output_summary_json)}), flush=True)
    print(json.dumps({"output_json": str(output_json), "records": len(records)}), flush=True)
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CFAR and side-lobe suppression detector experiments.")
    parser.add_argument(
        "--train-dir",
        default="train",
        help="Directory containing paired .zarr and .geff training samples.",
    )
    parser.add_argument(
        "--sample-ids",
        nargs="+",
        default=["44b6_40c45f5a", "44b6_18ced818", "6bba_05db0fb1"],
        help="Sample IDs (without extension) to evaluate.",
    )
    parser.add_argument(
        "--output-json",
        default="submissions/cfar_sidelobe_experiment.json",
        help="Where to write experiment records.",
    )
    parser.add_argument(
        "--max-timepoints",
        type=int,
        default=None,
        help="Optional timepoint limit for faster smoke runs.",
    )
    parser.add_argument(
        "--sweep-spec",
        action="append",
        default=[],
        help=(
            "Optional CFAR+sidelobe parameter set. Repeat for multiple sweeps. "
            "Format: threshold|tz,ty,tx|gz,gy,gx|k_sigma|sz,sy,sx|sidelobe_floor"
        ),
    )
    parser.add_argument(
        "--output-summary-json",
        default=None,
        help="Optional summary artifact with per-strategy quality-per-second ranking.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="How many top-ranked strategies to print to stdout.",
    )
    parser.add_argument(
        "--max-detections-per-timepoint",
        type=int,
        default=None,
        help="Optional cap on detections per timepoint after detector confidence ranking.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sweep_specs = _parse_sweep_specs(args.sweep_spec)
    if args.max_detections_per_timepoint is not None:
        sweep_specs = [
            DetectorParams(
                threshold=params.threshold,
                cfar_training_radius_voxels=params.cfar_training_radius_voxels,
                cfar_guard_radius_voxels=params.cfar_guard_radius_voxels,
                cfar_k_sigma=params.cfar_k_sigma,
                sidelobe_radius_voxels=params.sidelobe_radius_voxels,
                sidelobe_floor_ratio=params.sidelobe_floor_ratio,
                max_detections_per_timepoint=int(args.max_detections_per_timepoint),
            )
            for params in sweep_specs
        ]
    run_experiment(
        train_dir=Path(args.train_dir),
        sample_ids=list(args.sample_ids),
        output_json=Path(args.output_json),
        max_timepoints=args.max_timepoints,
        sweep_specs=sweep_specs,
        output_summary_json=Path(args.output_summary_json) if args.output_summary_json else None,
        top_k=args.top_k,
    )


if __name__ == "__main__":
    main()
