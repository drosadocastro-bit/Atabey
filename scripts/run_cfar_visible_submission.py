from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from atabey.detection.baseline import threshold_local_maxima_cfar_sidelobe
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.submission.writer import write_submission
from atabey.tracking.nearest_neighbor import link_adjacent_timepoints
from atabey.types import Detection, LineageGraph


@dataclass(frozen=True)
class VisibleRunRecord:
    sample_id: str
    sample_path: str
    elapsed_seconds: float
    predicted_nodes: int
    predicted_edges: int
    rows_written: int
    nodes_per_second: float
    edges_per_second: float
    link_strategy: str
    max_link_distance_um: float
    threshold: float
    cfar_training_radius_voxels: tuple[int, int, int]
    cfar_guard_radius_voxels: tuple[int, int, int]
    cfar_k_sigma: float
    sidelobe_radius_voxels: tuple[int, int, int]
    sidelobe_floor_ratio: float
    max_detections_per_timepoint: int | None
    max_timepoints: int | None


@dataclass(frozen=True)
class VisibleRunSummary:
    samples: int
    total_elapsed_seconds: float
    mean_elapsed_seconds: float
    total_predicted_nodes: int
    total_predicted_edges: int
    total_rows_written: int
    mean_nodes_per_second: float
    mean_edges_per_second: float


def _safe_rate(numerator: float, elapsed_seconds: float) -> float:
    elapsed = max(float(elapsed_seconds), 1e-9)
    return float(numerator) / elapsed


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
    link_strategy: str,
    max_link_distance_um: float,
    max_timepoints: int | None,
) -> LineageGraph:
    sample_id = _sample_id_from_path(sample_path)
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

    return graph


def run_visible_cfar_submission(
    *,
    input_dir: Path,
    output_csv: Path,
    report_json: Path,
    summary_json: Path | None,
    sample_ids: list[str] | None,
    max_samples: int | None,
    max_timepoints: int | None,
    threshold: float,
    cfar_training_radius_voxels: tuple[int, int, int],
    cfar_guard_radius_voxels: tuple[int, int, int],
    cfar_k_sigma: float,
    sidelobe_radius_voxels: tuple[int, int, int],
    sidelobe_floor_ratio: float,
    max_detections_per_timepoint: int | None,
    link_strategy: str,
    max_link_distance_um: float,
) -> tuple[list[VisibleRunRecord], VisibleRunSummary]:
    sample_paths = discover_zarr_samples(input_dir)
    if sample_ids:
        selected_ids = {str(sample_id) for sample_id in sample_ids}
        sample_paths = [path for path in sample_paths if _sample_id_from_path(path) in selected_ids]
        found_ids = {_sample_id_from_path(path) for path in sample_paths}
        missing_ids = sorted(selected_ids - found_ids)
        if missing_ids:
            raise FileNotFoundError(f"Requested sample IDs not found in {input_dir}: {missing_ids}")
    if max_samples is not None:
        sample_paths = sample_paths[: int(max_samples)]
    if not sample_paths:
        raise FileNotFoundError(f"No .zarr samples found in {input_dir}")

    records: list[VisibleRunRecord] = []
    graphs: list[LineageGraph] = []

    for sample_path in sample_paths:
        start = time.perf_counter()
        graph = build_graph_cfar_sidelobe(
            sample_path=sample_path,
            threshold=threshold,
            cfar_training_radius_voxels=cfar_training_radius_voxels,
            cfar_guard_radius_voxels=cfar_guard_radius_voxels,
            cfar_k_sigma=cfar_k_sigma,
            sidelobe_radius_voxels=sidelobe_radius_voxels,
            sidelobe_floor_ratio=sidelobe_floor_ratio,
            max_detections_per_timepoint=max_detections_per_timepoint,
            link_strategy=link_strategy,
            max_link_distance_um=max_link_distance_um,
            max_timepoints=max_timepoints,
        )
        elapsed = time.perf_counter() - start
        graphs.append(graph)

        predicted_nodes = len(graph.detections)
        predicted_edges = len(graph.edges)
        record = VisibleRunRecord(
            sample_id=graph.sample_id,
            sample_path=str(sample_path),
            elapsed_seconds=round(elapsed, 2),
            predicted_nodes=predicted_nodes,
            predicted_edges=predicted_edges,
            rows_written=predicted_nodes + predicted_edges,
            nodes_per_second=_safe_rate(predicted_nodes, elapsed),
            edges_per_second=_safe_rate(predicted_edges, elapsed),
            link_strategy=link_strategy,
            max_link_distance_um=max_link_distance_um,
            threshold=threshold,
            cfar_training_radius_voxels=cfar_training_radius_voxels,
            cfar_guard_radius_voxels=cfar_guard_radius_voxels,
            cfar_k_sigma=cfar_k_sigma,
            sidelobe_radius_voxels=sidelobe_radius_voxels,
            sidelobe_floor_ratio=sidelobe_floor_ratio,
            max_detections_per_timepoint=max_detections_per_timepoint,
            max_timepoints=max_timepoints,
        )
        records.append(record)
        print(json.dumps(asdict(record)), flush=True)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    report_json.parent.mkdir(parents=True, exist_ok=True)
    if summary_json is not None:
        summary_json.parent.mkdir(parents=True, exist_ok=True)

    output_csv_path = write_submission(graphs, output_csv)
    report_json.write_text(json.dumps([asdict(record) for record in records], indent=2), encoding="utf-8")

    total_elapsed = float(sum(record.elapsed_seconds for record in records))
    total_nodes = int(sum(record.predicted_nodes for record in records))
    total_edges = int(sum(record.predicted_edges for record in records))
    total_rows = int(sum(record.rows_written for record in records))
    summary = VisibleRunSummary(
        samples=len(records),
        total_elapsed_seconds=round(total_elapsed, 2),
        mean_elapsed_seconds=round(total_elapsed / len(records), 2),
        total_predicted_nodes=total_nodes,
        total_predicted_edges=total_edges,
        total_rows_written=total_rows,
        mean_nodes_per_second=sum(record.nodes_per_second for record in records) / len(records),
        mean_edges_per_second=sum(record.edges_per_second for record in records) / len(records),
    )

    if summary_json is not None:
        summary_json.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")

    print(json.dumps({"submission_csv": str(output_csv_path), "report_json": str(report_json)}), flush=True)
    if summary_json is not None:
        print(json.dumps({"summary_json": str(summary_json)}), flush=True)
    print(json.dumps({"summary": asdict(summary)}), flush=True)

    return records, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run bounded visible-test CFAR+sidelobe calibration and write submission artifacts."
    )
    parser.add_argument("--input-dir", default="test", help="Directory containing visible-test .zarr samples.")
    parser.add_argument(
        "--output-csv",
        default="submissions/visible_test_cfar_sidelobe_submission.csv",
        help="Output submission CSV path.",
    )
    parser.add_argument(
        "--report-json",
        default="submissions/visible_test_cfar_sidelobe_report.json",
        help="Per-sample runtime report output path.",
    )
    parser.add_argument(
        "--summary-json",
        default="submissions/visible_test_cfar_sidelobe_summary.json",
        help="Aggregate summary output path.",
    )
    parser.add_argument(
        "--sample-ids",
        nargs="+",
        default=None,
        help="Optional list of sample IDs (without .zarr) to run.",
    )
    parser.add_argument("--max-samples", type=int, default=None, help="Optional sample cap for smoke runs.")
    parser.add_argument(
        "--max-timepoints",
        type=int,
        default=None,
        help="Optional timepoint cap for bounded calibration.",
    )

    parser.add_argument("--threshold", type=float, default=0.52, help="Global normalized floor threshold.")
    parser.add_argument(
        "--cfar-training-radius",
        default="1,6,6",
        help="CFAR training radius as tz,ty,tx.",
    )
    parser.add_argument(
        "--cfar-guard-radius",
        default="0,1,1",
        help="CFAR guard radius as gz,gy,gx.",
    )
    parser.add_argument("--cfar-k-sigma", type=float, default=1.1, help="CFAR k-sigma multiplier.")
    parser.add_argument(
        "--sidelobe-radius",
        default="1,12,12",
        help="Sidelobe suppression radius as sz,sy,sx.",
    )
    parser.add_argument(
        "--sidelobe-floor",
        type=float,
        default=0.85,
        help="Sidelobe floor ratio.",
    )
    parser.add_argument(
        "--max-detections-per-timepoint",
        type=int,
        default=None,
        help="Optional cap on detections per timepoint after CFAR+sidelobe ranking.",
    )
    parser.add_argument(
        "--link-strategy",
        default="motion_mutual",
        choices=["greedy", "mutual", "motion", "motion_division", "motion_mutual", "motion_crowding", "motion_mutual_latent"],
        help="Linking strategy.",
    )
    parser.add_argument("--max-link-distance-um", type=float, default=9.0, help="Maximum link distance in microns.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_visible_cfar_submission(
        input_dir=Path(args.input_dir),
        output_csv=Path(args.output_csv),
        report_json=Path(args.report_json),
        summary_json=Path(args.summary_json) if args.summary_json else None,
        sample_ids=args.sample_ids,
        max_samples=args.max_samples,
        max_timepoints=args.max_timepoints,
        threshold=float(args.threshold),
        cfar_training_radius_voxels=_parse_int_tuple(args.cfar_training_radius),
        cfar_guard_radius_voxels=_parse_int_tuple(args.cfar_guard_radius),
        cfar_k_sigma=float(args.cfar_k_sigma),
        sidelobe_radius_voxels=_parse_int_tuple(args.sidelobe_radius),
        sidelobe_floor_ratio=float(args.sidelobe_floor),
        max_detections_per_timepoint=args.max_detections_per_timepoint,
        link_strategy=str(args.link_strategy),
        max_link_distance_um=float(args.max_link_distance_um),
    )


if __name__ == "__main__":
    main()
