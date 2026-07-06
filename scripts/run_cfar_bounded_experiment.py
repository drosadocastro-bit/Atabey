"""Experimental bounded-domain CFAR reformulation experiment (Parts 1 & 3).

ISOLATED EXPERIMENTAL RUNNER. This script never touches production defaults,
``run.py``, or the protected hybrid submission track. It exists purely to
quantify the bounded-signal CFAR collapse and to validate candidate bounded
formulations from ``atabey.detection.cfar_bounded``.

Two modes:

- ``scan`` (Part 1): sweep the full train set. For every sample, estimate the
  normalized background level and flag when ``background_mean * alpha`` exceeds
  the [0,1] ceiling (the collapse condition), broken down by whether the sample
  actually routes to the CFAR path. Tabulates the background-mean distribution.
- ``validate`` (Part 3): for the 3-sample set plus the collapse sample, build
  bounded-CFAR lineage graphs across a pfa sweep and compare collapse behavior,
  sparse recall, and runtime against the production baseline.

The bounded path is gated behind an explicit ``--enable-bounded-cfar`` opt-in so
it can never run by accident.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from time import perf_counter

import numpy as np

from atabey.baseline import build_baseline_graph
from atabey.detection.adaptive import (
    ForegroundProfile,
    choose_settings_for_sample,
    profile_sample_foreground,
)
from atabey.detection.baseline import _cfar_alpha_from_pfa, robust_normalize
from atabey.detection.cfar_bounded import (
    SIGNAL_CEILING,
    background_ring_stats_sat,
    detect_bounded_cfar,
)
from atabey.evaluation.sparse_ground_truth import evaluate_sparse_ground_truth
from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.tracking.nearest_neighbor import link_adjacent_timepoints
from atabey.types import Detection, LineageGraph


# Calibration mirrors the production CFAR route so comparisons stay fair.
BOUNDED_TRAINING_RADIUS = (1, 6, 6)
BOUNDED_GUARD_RADIUS = (0, 1, 1)
BOUNDED_MIN_DISTANCE = (1, 5, 5)
BOUNDED_MAX_DETECTIONS = 900
BOUNDED_THRESHOLD = 0.50
BOUNDED_LINK_STRATEGY = "motion_mutual"
BOUNDED_MAX_LINK_UM = 9.0
# Ring voxel count for training (1,6,6) minus guard (0,1,1): 3*13*13 - 1*3*3.
RING_COUNT_N = 507 - 9

DEFAULT_PFA_VALUES = (1e-3, 1e-2, 2e-2, 5e-2)
DEFAULT_FORMULATIONS = ("alpha_clip", "logit", "beta")


def _log(message: str) -> None:
    print(f"[cfar-bounded] {message}", file=sys.stderr, flush=True)


def _is_profile_6bba_like_for_cfar(profile: ForegroundProfile) -> bool:
    """Same routing gate the production hybrid runner uses for the CFAR path."""

    return (
        profile.median_largest_component_voxels >= 100_000
        and profile.median_largest_component_voxels <= 600_000
        and profile.median_foreground_fraction >= 0.05
        and profile.median_foreground_fraction <= 0.20
    )


# ---------------------------------------------------------------------------
# Part 1: full-train-set collapse scan
# ---------------------------------------------------------------------------


@dataclass
class SampleScanRecord:
    sample_id: str
    routes_to_cfar: bool
    median_largest_component_voxels: float
    median_foreground_fraction: float
    background_mean_norm: float
    collapse_risk_by_pfa: dict[str, bool]

    def any_collapse_risk(self) -> bool:
        return any(self.collapse_risk_by_pfa.values())


def _background_mean_norm(sample_path: Path, *, timepoint: int) -> float:
    array = open_competition_array(sample_path)
    total = int(array.shape[0])
    t = min(max(0, timepoint), total - 1)
    volume = read_timepoint(array, t)
    normalized = robust_normalize(volume, upper=99.9)
    ring_mean, _, ring_count = background_ring_stats_sat(
        normalized,
        training_radius_voxels=BOUNDED_TRAINING_RADIUS,
        guard_radius_voxels=BOUNDED_GUARD_RADIUS,
    )
    valid = ring_count > 0
    return float(np.median(ring_mean[valid])) if np.any(valid) else float("nan")


def _scan_sample(sample_path: Path, pfa_values: tuple[float, ...]) -> SampleScanRecord:
    profile = profile_sample_foreground(sample_path)
    routes = _is_profile_6bba_like_for_cfar(profile)
    array = open_competition_array(sample_path)
    mid = int(array.shape[0]) // 2
    background_mean = _background_mean_norm(sample_path, timepoint=mid)

    collapse_risk: dict[str, bool] = {}
    for pfa in pfa_values:
        alpha = _cfar_alpha_from_pfa(float(pfa), float(RING_COUNT_N))
        collapse_risk[f"{pfa:.0e}"] = bool(background_mean * alpha > SIGNAL_CEILING)

    return SampleScanRecord(
        sample_id=sample_path.stem,
        routes_to_cfar=routes,
        median_largest_component_voxels=profile.median_largest_component_voxels,
        median_foreground_fraction=profile.median_foreground_fraction,
        background_mean_norm=background_mean,
        collapse_risk_by_pfa=collapse_risk,
    )


def _distribution_summary(values: list[float]) -> dict[str, float]:
    clean = [v for v in values if not np.isnan(v)]
    if not clean:
        return {}
    arr = np.asarray(clean, dtype=float)
    return {
        "count": int(arr.size),
        "min": float(arr.min()),
        "p25": float(np.percentile(arr, 25)),
        "median": float(np.median(arr)),
        "p75": float(np.percentile(arr, 75)),
        "p95": float(np.percentile(arr, 95)),
        "max": float(arr.max()),
        "mean": float(arr.mean()),
    }


def run_scan(train_dir: Path, *, max_samples: int | None, pfa_values: tuple[float, ...]) -> dict:
    sample_paths = sorted(train_dir.glob("*.zarr"))
    if max_samples is not None:
        sample_paths = sample_paths[:max_samples]
    _log(f"scanning {len(sample_paths)} train samples across pfa {pfa_values}")

    records: list[SampleScanRecord] = []
    for index, sample_path in enumerate(sample_paths, start=1):
        try:
            record = _scan_sample(sample_path, pfa_values)
        except Exception as exc:  # noqa: BLE001 - report and continue the scan.
            _log(f"  [{index}/{len(sample_paths)}] {sample_path.stem} FAILED: {exc}")
            continue
        records.append(record)
        if index % 10 == 0 or index == len(sample_paths):
            _log(f"  [{index}/{len(sample_paths)}] scanned {sample_path.stem}")

    routed = [r for r in records if r.routes_to_cfar]
    pfa_keys = [f"{pfa:.0e}" for pfa in pfa_values]
    risk_all = {key: sum(r.collapse_risk_by_pfa[key] for r in records) for key in pfa_keys}
    risk_routed = {key: sum(r.collapse_risk_by_pfa[key] for r in routed) for key in pfa_keys}

    summary = {
        "total_samples": len(records),
        "samples_routing_to_cfar": len(routed),
        "background_mean_distribution_all": _distribution_summary(
            [r.background_mean_norm for r in records]
        ),
        "background_mean_distribution_routed": _distribution_summary(
            [r.background_mean_norm for r in routed]
        ),
        "collapse_risk_count_all": risk_all,
        "collapse_risk_count_routed": risk_routed,
        "real_failures_routed_and_at_risk": {
            key: sorted(r.sample_id for r in routed if r.collapse_risk_by_pfa[key])
            for key in pfa_keys
        },
        "records": [asdict(r) for r in records],
    }
    return summary


# ---------------------------------------------------------------------------
# Part 3: bounded-formulation validation
# ---------------------------------------------------------------------------


@dataclass
class BoundedRunRecord:
    sample_id: str
    mode: str
    pfa: float
    predicted_nodes: int
    predicted_edges: int
    collapsed: bool
    sparse_recall: float | None
    sparse_edge_recall: float | None
    detection_ms: float


def _build_bounded_graph(
    sample_path: Path,
    sample_id: str,
    *,
    mode: str,
    pfa: float | None,
    k_sigma: float | None,
    max_timepoints: int | None,
) -> tuple[LineageGraph, float]:
    array = open_competition_array(sample_path)
    total = int(array.shape[0])
    if max_timepoints is not None:
        total = min(total, max_timepoints)

    graph = LineageGraph(sample_id=sample_id)
    previous: list[Detection] = []
    detections_by_node_id: dict[str, Detection] = {}
    predecessor_by_node_id: dict[str, Detection] = {}
    detection_ms = 0.0

    for t in range(total):
        volume = read_timepoint(array, t)
        start = perf_counter()
        current = detect_bounded_cfar(
            sample_id,
            t,
            volume,
            mode=mode,
            threshold=BOUNDED_THRESHOLD,
            min_distance_voxels=BOUNDED_MIN_DISTANCE,
            max_detections=BOUNDED_MAX_DETECTIONS,
            training_radius_voxels=BOUNDED_TRAINING_RADIUS,
            guard_radius_voxels=BOUNDED_GUARD_RADIUS,
            pfa=pfa,
            k_sigma=k_sigma,
        )
        detection_ms += (perf_counter() - start) * 1000.0

        for detection in current:
            graph.add_detection(detection)
            detections_by_node_id[detection.node_id] = detection

        edges = link_adjacent_timepoints(
            previous,
            current,
            BOUNDED_MAX_LINK_UM,
            strategy=BOUNDED_LINK_STRATEGY,
            predecessor_by_node_id=predecessor_by_node_id,
        )
        for edge in edges:
            graph.add_edge(edge)
            predecessor_by_node_id[edge.target_id] = detections_by_node_id[edge.source_id]
        previous = current

    return graph, detection_ms


def _build_baseline_reference(
    sample_path: Path, sample_id: str, *, max_timepoints: int | None
) -> tuple[LineageGraph, float]:
    _, settings = choose_settings_for_sample(sample_path)
    start = perf_counter()
    graph = build_baseline_graph(
        sample_path,
        sample_id=sample_id,
        max_timepoints=max_timepoints,
        threshold=settings.threshold,
        min_volume=settings.min_volume,
        max_link_distance_um=settings.max_link_distance_um,
        link_strategy=settings.link_strategy,
        detector=settings.detector,
        peak_min_distance_voxels=settings.peak_min_distance_voxels,
        max_detections_per_timepoint=BOUNDED_MAX_DETECTIONS,
    )
    elapsed_ms = (perf_counter() - start) * 1000.0
    return graph, elapsed_ms


def run_validate(
    train_dir: Path,
    *,
    sample_ids: list[str],
    collapse_sample_id: str,
    formulations: tuple[str, ...],
    pfa_sweep: tuple[float, ...],
    max_timepoints: int | None,
) -> dict:
    all_ids = list(dict.fromkeys([*sample_ids, collapse_sample_id]))
    per_sample: dict[str, dict] = {}

    for sample_id in all_ids:
        sample_path = train_dir / f"{sample_id}.zarr"
        geff_path = train_dir / f"{sample_id}.geff"
        if not sample_path.exists():
            _log(f"skipping {sample_id}: {sample_path} not found")
            continue
        _log(f"validating {sample_id}")
        ground_truth = read_geff_graph(geff_path) if geff_path.exists() else None

        baseline_graph, baseline_ms = _build_baseline_reference(
            sample_path, sample_id, max_timepoints=max_timepoints
        )
        baseline_report = (
            evaluate_sparse_ground_truth(baseline_graph, ground_truth, match_radius_um=7.0)
            if ground_truth is not None
            else None
        )

        runs: list[BoundedRunRecord] = []
        for mode in formulations:
            for pfa in pfa_sweep:
                graph, detection_ms = _build_bounded_graph(
                    sample_path,
                    sample_id,
                    mode=mode,
                    pfa=float(pfa),
                    k_sigma=None,
                    max_timepoints=max_timepoints,
                )
                report = (
                    evaluate_sparse_ground_truth(graph, ground_truth, match_radius_um=7.0)
                    if ground_truth is not None
                    else None
                )
                runs.append(
                    BoundedRunRecord(
                        sample_id=sample_id,
                        mode=mode,
                        pfa=float(pfa),
                        predicted_nodes=len(graph.detections),
                        predicted_edges=len(graph.edges),
                        collapsed=len(graph.detections) == 0,
                        sparse_recall=None if report is None else report.sparse_recall,
                        sparse_edge_recall=None if report is None else report.sparse_edge_recall,
                        detection_ms=round(detection_ms, 2),
                    )
                )
                _log(
                    f"  {mode} pfa={pfa:.0e}: nodes={len(graph.detections)} "
                    f"recall={None if report is None else round(report.sparse_recall, 4)} "
                    f"detect_ms={round(detection_ms, 1)}"
                )

        per_sample[sample_id] = {
            "baseline": {
                "detector": choose_settings_for_sample(sample_path)[1].detector,
                "predicted_nodes": len(baseline_graph.detections),
                "predicted_edges": len(baseline_graph.edges),
                "sparse_recall": None if baseline_report is None else baseline_report.sparse_recall,
                "sparse_edge_recall": None
                if baseline_report is None
                else baseline_report.sparse_edge_recall,
                "baseline_ms": round(baseline_ms, 2),
            },
            "bounded_runs": [asdict(run) for run in runs],
        }

    collapse_info = per_sample.get(collapse_sample_id, {})
    collapse_runs = collapse_info.get("bounded_runs", [])
    collapse_avoided = bool(collapse_runs) and all(not run["collapsed"] for run in collapse_runs)

    return {
        "collapse_sample_id": collapse_sample_id,
        "collapse_avoided_all_pfa": collapse_avoided,
        "samples": per_sample,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _write_json(payload: dict, output_json: Path | None) -> None:
    if output_json is None:
        return
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    _log(f"wrote {output_json}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["scan", "validate"], help="Experiment mode.")
    parser.add_argument(
        "--enable-bounded-cfar",
        action="store_true",
        help="Required explicit opt-in. The experimental bounded path never runs without it.",
    )
    parser.add_argument("--train-dir", default="train", help="Directory with .zarr/.geff pairs.")
    parser.add_argument("--max-samples", type=int, default=None, help="scan: cap number of samples.")
    parser.add_argument(
        "--pfa-values",
        type=float,
        nargs="+",
        default=list(DEFAULT_PFA_VALUES),
        help="scan: pfa values to test the collapse condition against.",
    )
    parser.add_argument(
        "--sample-ids",
        nargs="+",
        default=["44b6_0113de3b", "44b6_0b24845f"],
        help="validate: peer sample ids.",
    )
    parser.add_argument(
        "--collapse-sample-id",
        default="44b6_0c582fdc",
        help="validate: the known collapse sample.",
    )
    parser.add_argument(
        "--formulations",
        nargs="+",
        default=list(DEFAULT_FORMULATIONS),
        choices=list(DEFAULT_FORMULATIONS),
        help="validate: bounded formulations to test.",
    )
    parser.add_argument(
        "--pfa-sweep",
        type=float,
        nargs="+",
        default=[1e-3, 1e-2, 5e-2],
        help="validate: pfa values to sweep per formulation.",
    )
    parser.add_argument("--max-timepoints", type=int, default=12, help="validate: cap timepoints.")
    parser.add_argument("--output-json", type=Path, default=None, help="Optional JSON output path.")
    args = parser.parse_args(argv)

    if not args.enable_bounded_cfar:
        parser.error(
            "the experimental bounded CFAR path requires the explicit --enable-bounded-cfar opt-in"
        )

    train_dir = Path(args.train_dir)
    if args.mode == "scan":
        payload = run_scan(
            train_dir,
            max_samples=args.max_samples,
            pfa_values=tuple(args.pfa_values),
        )
        summary = {k: v for k, v in payload.items() if k != "records"}
        print(json.dumps(summary, indent=2))
    else:
        payload = run_validate(
            train_dir,
            sample_ids=list(args.sample_ids),
            collapse_sample_id=args.collapse_sample_id,
            formulations=tuple(args.formulations),
            pfa_sweep=tuple(args.pfa_sweep),
            max_timepoints=args.max_timepoints,
        )
        print(json.dumps({k: v for k, v in payload.items() if k != "samples"}, indent=2))

    _write_json(payload, args.output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
