from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from atabey.baseline import build_baseline_graph
from atabey.detection.adaptive import choose_settings_for_sample
from atabey.submission.writer import write_submission
from atabey.types import LineageGraph


@dataclass(frozen=True)
class SampleRunRecord:
    sample_id: str
    sample_path: str
    elapsed_seconds: float
    predicted_nodes: int
    predicted_edges: int
    detector: str
    threshold: float
    min_volume: int
    peak_min_distance_voxels: tuple[int, int, int]
    link_strategy: str
    max_link_distance_um: float
    median_largest_component_voxels: float
    median_foreground_fraction: float
    reason: str


def discover_zarr_samples(input_dir: str | Path) -> list[Path]:
    root = Path(input_dir)
    return sorted((path for path in root.iterdir() if path.is_dir() and path.name.endswith(".zarr")), key=lambda path: path.name)


def build_graph_for_sample(sample_path: Path, max_timepoints: int | None = None) -> tuple[LineageGraph, SampleRunRecord]:
    profile, settings = choose_settings_for_sample(sample_path)
    start = time.perf_counter()
    graph = build_baseline_graph(
        sample_path,
        max_timepoints=max_timepoints,
        threshold=settings.threshold,
        min_volume=settings.min_volume,
        max_link_distance_um=settings.max_link_distance_um,
        link_strategy=settings.link_strategy,
        detector=settings.detector,
        peak_min_distance_voxels=settings.peak_min_distance_voxels,
    )
    elapsed = time.perf_counter() - start
    record = SampleRunRecord(
        sample_id=graph.sample_id,
        sample_path=str(sample_path),
        elapsed_seconds=round(elapsed, 2),
        predicted_nodes=len(graph.detections),
        predicted_edges=len(graph.edges),
        detector=settings.detector,
        threshold=settings.threshold,
        min_volume=settings.min_volume,
        peak_min_distance_voxels=settings.peak_min_distance_voxels,
        link_strategy=settings.link_strategy,
        max_link_distance_um=settings.max_link_distance_um,
        median_largest_component_voxels=profile.median_largest_component_voxels,
        median_foreground_fraction=profile.median_foreground_fraction,
        reason=settings.reason,
    )
    return graph, record


def run_adaptive_submission(
    input_dir: str | Path,
    output_csv: str | Path,
    report_json: str | Path,
    *,
    max_samples: int | None = None,
    max_timepoints: int | None = None,
) -> list[SampleRunRecord]:
    sample_paths = discover_zarr_samples(input_dir)
    if max_samples is not None:
        sample_paths = sample_paths[:max_samples]
    if not sample_paths:
        raise FileNotFoundError(f"No .zarr samples found in {input_dir}")

    graphs: list[LineageGraph] = []
    records: list[SampleRunRecord] = []
    for sample_path in sample_paths:
        graph, record = build_graph_for_sample(sample_path, max_timepoints=max_timepoints)
        graphs.append(graph)
        records.append(record)
        print(json.dumps(asdict(record)), flush=True)

    output_path = write_submission(graphs, output_csv)
    report_path = Path(report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps([asdict(record) for record in records], indent=2), encoding="utf-8")
    print(json.dumps({"submission_csv": str(output_path), "report_json": str(report_path)}), flush=True)
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run adaptive Atabey baseline and write Kaggle submission CSV.")
    parser.add_argument("--input-dir", default="test", help="Directory containing .zarr samples.")
    parser.add_argument("--output-csv", default="submission.csv", help="Output Kaggle submission CSV path.")
    parser.add_argument("--report-json", default="submissions/adaptive_runtime_report.json", help="Runtime/settings report path.")
    parser.add_argument("--max-samples", type=int, default=None, help="Optional sample limit for smoke tests.")
    parser.add_argument("--max-timepoints", type=int, default=None, help="Optional timepoint limit for smoke tests.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_adaptive_submission(
        args.input_dir,
        args.output_csv,
        args.report_json,
        max_samples=args.max_samples,
        max_timepoints=args.max_timepoints,
    )


if __name__ == "__main__":
    main()
