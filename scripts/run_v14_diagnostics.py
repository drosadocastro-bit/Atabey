"""V14 diagnostic investigation: runtime cost attribution and collapse forensics.

This script is instrumentation and analysis ONLY. It does not change any
production default behavior. It re-uses the exact production detection
primitives from ``atabey.detection.baseline`` but wraps them with per-stage
timers so we can attribute where hybrid runtime cost concentrates and diagnose
the zero-node collapse observed on a specific sample under pfa/axial.

Parts implemented (mirrors the TODO):
  Part 1 - stage-level timing for the hybrid CFAR+sidelobe route vs baseline.
  Part 2 - controlled ablation isolating sigma vs isotropic-floor effects.
  Part 3 - forensic sample characterization + pfa sensitivity sweep for the
           collapse sample against non-collapsing peers.

The output is a machine-readable JSON bundle plus a human-readable summary
printed to stdout. No graph mutation, no autonomous action.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median

import numpy as np

from atabey.baseline import build_baseline_graph
from atabey.detection.adaptive import choose_settings_for_sample
from atabey.detection.baseline import (
    _cfar_alpha_from_pfa,
    _cfar_background_stats_box,
    _cfar_margin_confidence,
    _sidelobe_suppress_detections,
    robust_normalize,
)
from atabey.evaluation.sparse_ground_truth import evaluate_sparse_ground_truth
from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.constants import DEFAULT_VOXEL_SCALE_UM
from atabey.types import Detection


# Frozen calibration for the diagnostic runs. These mirror the values already
# exercised in the recorded V14 experiments so the forensics stays comparable.
DIAG_MIN_DISTANCE_VOXELS = (1, 5, 5)
DIAG_CFAR_TRAINING_RADIUS = (1, 6, 6)
DIAG_CFAR_GUARD_RADIUS = (0, 1, 1)
DIAG_SIDELOBE_RADIUS = (1, 12, 12)
DIAG_SIDELOBE_AXIAL_Z_RADIUS = 2
DIAG_SIDELOBE_AXIAL_XY_TOLERANCE = (1, 1)
DIAG_MAX_DETECTIONS = 900

BASELINE_SIDELOBE_FLOOR = 0.85  # production default
BASELINE_CFAR_K_SIGMA = 1.1  # production default


@dataclass(frozen=True)
class StageTimings:
    normalize_ms: float
    peak_ms: float
    cfar_stats_ms: float
    cfar_threshold_ms: float
    sidelobe_ms: float
    detection_build_ms: float

    def total_ms(self) -> float:
        return (
            self.normalize_ms
            + self.peak_ms
            + self.cfar_stats_ms
            + self.cfar_threshold_ms
            + self.sidelobe_ms
            + self.detection_build_ms
        )


@dataclass
class StageAccumulator:
    normalize_ms: float = 0.0
    peak_ms: float = 0.0
    cfar_stats_ms: float = 0.0
    cfar_threshold_ms: float = 0.0
    sidelobe_ms: float = 0.0
    detection_build_ms: float = 0.0
    kept_detection_count: int = 0
    pre_sidelobe_detection_count: int = 0
    timepoints: int = 0

    def as_stage_timings(self) -> StageTimings:
        return StageTimings(
            normalize_ms=round(self.normalize_ms, 3),
            peak_ms=round(self.peak_ms, 3),
            cfar_stats_ms=round(self.cfar_stats_ms, 3),
            cfar_threshold_ms=round(self.cfar_threshold_ms, 3),
            sidelobe_ms=round(self.sidelobe_ms, 3),
            detection_build_ms=round(self.detection_build_ms, 3),
        )


def _log(message: str) -> None:
    print(f"[v14-diag] {message}", file=sys.stderr, flush=True)


def _ndimage():
    from scipy import ndimage

    return ndimage


def _timed_cfar_sidelobe_timepoint(
    sample_id: str,
    t: int,
    volume: np.ndarray,
    *,
    threshold: float,
    cfar_threshold_mode: str,
    cfar_k_sigma: float,
    cfar_pfa: float,
    sidelobe_mode: str,
    sidelobe_floor_ratio: float,
    accumulator: StageAccumulator,
) -> list[Detection]:
    """Run one CFAR+sidelobe timepoint with per-stage timing.

    Mirrors ``threshold_local_maxima_cfar_sidelobe`` exactly but instruments the
    internal stages so we can attribute runtime. Uses the same production
    helpers, so detection results match the production path.
    """

    ndimage = _ndimage()

    t0 = time.perf_counter()
    normalized = robust_normalize(volume, upper=99.9)
    peak_source = volume.astype(np.float32)
    t1 = time.perf_counter()
    accumulator.normalize_ms += (t1 - t0) * 1000.0

    peak_size = tuple(2 * max(0, int(radius)) + 1 for radius in DIAG_MIN_DISTANCE_VOXELS)
    local_max = ndimage.maximum_filter(peak_source, size=peak_size, mode="nearest")
    peak_mask = peak_source == local_max
    t2 = time.perf_counter()
    accumulator.peak_ms += (t2 - t1) * 1000.0

    background_mean, background_std, ring_count = _cfar_background_stats_box(
        normalized,
        cfar_training_radius_voxels=DIAG_CFAR_TRAINING_RADIUS,
        cfar_guard_radius_voxels=DIAG_CFAR_GUARD_RADIUS,
    )
    t3 = time.perf_counter()
    accumulator.cfar_stats_ms += (t3 - t2) * 1000.0

    if cfar_threshold_mode == "sigma":
        adaptive_threshold = background_mean + float(cfar_k_sigma) * background_std
    elif cfar_threshold_mode == "pfa":
        alpha = _cfar_alpha_from_pfa(float(cfar_pfa), float(ring_count))
        adaptive_threshold = background_mean * alpha
    else:
        raise ValueError(f"Unknown CFAR threshold mode: {cfar_threshold_mode}")

    keep_mask = peak_mask & (normalized >= float(threshold)) & (normalized >= adaptive_threshold)
    coords = np.argwhere(keep_mask)
    if coords.size == 0:
        t4 = time.perf_counter()
        accumulator.cfar_threshold_ms += (t4 - t3) * 1000.0
        accumulator.timepoints += 1
        return []

    confidences = normalized[keep_mask]
    adaptive_at_peaks = adaptive_threshold[keep_mask]
    margin_confidences = np.maximum(
        0.0,
        (confidences - adaptive_at_peaks) / np.maximum(adaptive_at_peaks, 1e-6),
    )
    raw_values = volume[keep_mask]
    order = np.argsort(margin_confidences)[::-1]
    if DIAG_MAX_DETECTIONS is not None:
        order = order[: int(DIAG_MAX_DETECTIONS)]
    t4 = time.perf_counter()
    accumulator.cfar_threshold_ms += (t4 - t3) * 1000.0

    detections: list[Detection] = []
    for output_idx, coord_idx in enumerate(order, start=1):
        z, y, x = coords[int(coord_idx)]
        zf, yf, xf = float(z), float(y), float(x)
        z_um, y_um, x_um = DEFAULT_VOXEL_SCALE_UM.voxel_to_um(zf, yf, xf)
        raw_value = float(raw_values[int(coord_idx)])
        confidence = _cfar_margin_confidence(
            float(confidences[int(coord_idx)]),
            float(adaptive_at_peaks[int(coord_idx)]),
        )
        detections.append(
            Detection(
                node_id=f"{sample_id}:t{t}:cf{output_idx}",
                sample_id=sample_id,
                t=t,
                z=zf,
                y=yf,
                x=xf,
                z_um=z_um,
                y_um=y_um,
                x_um=x_um,
                intensity_mean=raw_value,
                intensity_max=raw_value,
                component_volume=1,
                detection_confidence=confidence,
            )
        )
    t5 = time.perf_counter()
    accumulator.detection_build_ms += (t5 - t4) * 1000.0
    accumulator.pre_sidelobe_detection_count += len(detections)

    kept = _sidelobe_suppress_detections(
        detections,
        sidelobe_mode=sidelobe_mode,
        sidelobe_radius_voxels=DIAG_SIDELOBE_RADIUS,
        sidelobe_axial_z_radius_voxels=DIAG_SIDELOBE_AXIAL_Z_RADIUS,
        sidelobe_axial_xy_tolerance_voxels=DIAG_SIDELOBE_AXIAL_XY_TOLERANCE,
        sidelobe_floor_ratio=sidelobe_floor_ratio,
    )
    t6 = time.perf_counter()
    accumulator.sidelobe_ms += (t6 - t5) * 1000.0
    accumulator.kept_detection_count += len(kept)
    accumulator.timepoints += 1
    return kept


def time_hybrid_stages(
    sample_path: Path,
    *,
    max_timepoints: int | None,
    cfar_threshold: float,
    cfar_threshold_mode: str,
    cfar_k_sigma: float,
    cfar_pfa: float,
    sidelobe_mode: str,
    sidelobe_floor_ratio: float,
) -> StageAccumulator:
    array = open_competition_array(sample_path)
    total_timepoints = int(array.shape[0])
    if max_timepoints is not None:
        total_timepoints = min(total_timepoints, int(max_timepoints))
    sample_id = sample_path.name.removesuffix(".zarr")

    accumulator = StageAccumulator()
    for t in range(total_timepoints):
        volume = read_timepoint(array, t)
        _timed_cfar_sidelobe_timepoint(
            sample_id,
            t,
            volume,
            threshold=cfar_threshold,
            cfar_threshold_mode=cfar_threshold_mode,
            cfar_k_sigma=cfar_k_sigma,
            cfar_pfa=cfar_pfa,
            sidelobe_mode=sidelobe_mode,
            sidelobe_floor_ratio=sidelobe_floor_ratio,
            accumulator=accumulator,
        )
    return accumulator


def time_baseline_graph(sample_path: Path, *, max_timepoints: int | None) -> float:
    _profile, settings = choose_settings_for_sample(sample_path)
    link_strategy = "motion_mutual" if settings.detector == "local_maxima" else settings.link_strategy
    start = time.perf_counter()
    build_baseline_graph(
        sample_path,
        max_timepoints=max_timepoints,
        threshold=settings.threshold,
        min_volume=settings.min_volume,
        max_link_distance_um=settings.max_link_distance_um,
        link_strategy=link_strategy,
        detector=settings.detector,
        peak_min_distance_voxels=settings.peak_min_distance_voxels,
    )
    return (time.perf_counter() - start) * 1000.0


def _stage_breakdown(timings: StageTimings) -> list[dict[str, float | str]]:
    total = max(timings.total_ms(), 1e-9)
    rows: list[dict[str, float | str]] = []
    for name, value in [
        ("normalize", timings.normalize_ms),
        ("peak_local_max", timings.peak_ms),
        ("cfar_background_stats", timings.cfar_stats_ms),
        ("cfar_threshold_select", timings.cfar_threshold_ms),
        ("sidelobe_suppression", timings.sidelobe_ms),
        ("detection_build", timings.detection_build_ms),
    ]:
        rows.append(
            {
                "stage": name,
                "total_ms": round(float(value), 3),
                "percent_of_hybrid": round(100.0 * float(value) / total, 2),
            }
        )
    return rows


def run_part1_and_part2(
    *,
    train_dir: Path,
    sample_ids: list[str],
    max_timepoints: int | None,
) -> dict:
    """Stage timing + controlled sigma/isotropic ablation across samples."""

    ablation_configs = {
        "baseline_adaptive": None,  # non-CFAR baseline path
        "runA_sigma06_only": {
            "cfar_threshold_mode": "sigma",
            "cfar_k_sigma": 0.6,
            "sidelobe_floor_ratio": BASELINE_SIDELOBE_FLOOR,
        },
        "runB_iso07_only": {
            "cfar_threshold_mode": "sigma",
            "cfar_k_sigma": BASELINE_CFAR_K_SIGMA,
            "sidelobe_floor_ratio": 0.7,
        },
        "runC_sigma06_iso07": {
            "cfar_threshold_mode": "sigma",
            "cfar_k_sigma": 0.6,
            "sidelobe_floor_ratio": 0.7,
        },
    }

    per_sample: list[dict] = []
    for sample_id in sample_ids:
        _log(f"part1/2 sample={sample_id} baseline timing...")
        sample_path = train_dir / f"{sample_id}.zarr"
        geff_path = train_dir / f"{sample_id}.geff"
        ground_truth = read_geff_graph(geff_path)

        baseline_ms = time_baseline_graph(sample_path, max_timepoints=max_timepoints)
        baseline_graph = build_baseline_graph(
            sample_path,
            max_timepoints=max_timepoints,
            **_baseline_kwargs(sample_path),
        )
        baseline_report = evaluate_sparse_ground_truth(baseline_graph, ground_truth, match_radius_um=7.0)

        sample_record: dict = {
            "sample_id": sample_id,
            "baseline_total_ms": round(baseline_ms, 3),
            "baseline_predicted_nodes": baseline_report.predicted_nodes,
            "baseline_sparse_recall": baseline_report.sparse_recall,
            "runs": [],
        }

        for run_name, cfg in ablation_configs.items():
            if cfg is None:
                continue
            _log(f"part1/2 sample={sample_id} run={run_name}...")
            accumulator = time_hybrid_stages(
                sample_path,
                max_timepoints=max_timepoints,
                cfar_threshold=0.50,
                cfar_threshold_mode=cfg["cfar_threshold_mode"],
                cfar_k_sigma=cfg["cfar_k_sigma"],
                cfar_pfa=1e-4,
                sidelobe_mode="isotropic",
                sidelobe_floor_ratio=cfg["sidelobe_floor_ratio"],
            )
            timings = accumulator.as_stage_timings()
            hybrid_total_ms = timings.total_ms()
            sample_record["runs"].append(
                {
                    "run": run_name,
                    "cfar_k_sigma": cfg["cfar_k_sigma"],
                    "sidelobe_floor_ratio": cfg["sidelobe_floor_ratio"],
                    "hybrid_detection_total_ms": round(hybrid_total_ms, 3),
                    "kept_detection_count": accumulator.kept_detection_count,
                    "pre_sidelobe_detection_count": accumulator.pre_sidelobe_detection_count,
                    "timepoints": accumulator.timepoints,
                    "stage_breakdown": _stage_breakdown(timings),
                    "hybrid_vs_baseline_ms_delta": round(hybrid_total_ms - baseline_ms, 3),
                }
            )
        per_sample.append(sample_record)

    aggregate = _aggregate_part1_part2(per_sample)
    return {"per_sample": per_sample, "aggregate": aggregate}


def _baseline_kwargs(sample_path: Path) -> dict:
    _profile, settings = choose_settings_for_sample(sample_path)
    link_strategy = "motion_mutual" if settings.detector == "local_maxima" else settings.link_strategy
    return {
        "threshold": settings.threshold,
        "min_volume": settings.min_volume,
        "max_link_distance_um": settings.max_link_distance_um,
        "link_strategy": link_strategy,
        "detector": settings.detector,
        "peak_min_distance_voxels": settings.peak_min_distance_voxels,
    }


def _aggregate_part1_part2(per_sample: list[dict]) -> dict:
    run_names = ["runA_sigma06_only", "runB_iso07_only", "runC_sigma06_iso07"]
    baseline_ms_values = [rec["baseline_total_ms"] for rec in per_sample]
    aggregate: dict = {
        "mean_baseline_total_ms": round(mean(baseline_ms_values), 3) if baseline_ms_values else None,
        "runs": {},
    }
    stage_names = [
        "normalize",
        "peak_local_max",
        "cfar_background_stats",
        "cfar_threshold_select",
        "sidelobe_suppression",
        "detection_build",
    ]
    for run_name in run_names:
        totals: list[float] = []
        stage_totals: dict[str, list[float]] = {name: [] for name in stage_names}
        deltas: list[float] = []
        for rec in per_sample:
            run = next((r for r in rec["runs"] if r["run"] == run_name), None)
            if run is None:
                continue
            totals.append(run["hybrid_detection_total_ms"])
            deltas.append(run["hybrid_vs_baseline_ms_delta"])
            for stage in run["stage_breakdown"]:
                stage_totals[stage["stage"]].append(stage["total_ms"])
        if not totals:
            continue
        aggregate["runs"][run_name] = {
            "mean_hybrid_detection_total_ms": round(mean(totals), 3),
            "mean_hybrid_vs_baseline_ms_delta": round(mean(deltas), 3),
            "mean_stage_ms": {name: round(mean(values), 3) for name, values in stage_totals.items() if values},
        }
    return aggregate


def run_part3_forensics(
    *,
    train_dir: Path,
    collapse_sample_id: str,
    peer_sample_ids: list[str],
    max_timepoints: int | None,
    pfa_sweep: list[float],
) -> dict:
    """Characterize the collapse sample and bound pfa sensitivity."""

    all_ids = [collapse_sample_id, *[s for s in peer_sample_ids if s != collapse_sample_id]]
    characterization: list[dict] = []
    for sample_id in all_ids:
        _log(f"part3 characterize sample={sample_id}...")
        sample_path = train_dir / f"{sample_id}.zarr"
        characterization.append(
            _characterize_sample(sample_path, sample_id, max_timepoints=max_timepoints)
        )

    sweep_results: list[dict] = []
    collapse_path = train_dir / f"{collapse_sample_id}.zarr"
    for pfa in pfa_sweep:
        _log(f"part3 pfa-axial sweep pfa={pfa}...")
        accumulator = time_hybrid_stages(
            collapse_path,
            max_timepoints=max_timepoints,
            cfar_threshold=0.50,
            cfar_threshold_mode="pfa",
            cfar_pfa=pfa,
            cfar_k_sigma=BASELINE_CFAR_K_SIGMA,
            sidelobe_mode="axial",
            sidelobe_floor_ratio=BASELINE_SIDELOBE_FLOOR,
        )
        sweep_results.append(
            {
                "pfa": pfa,
                "kept_detection_count": accumulator.kept_detection_count,
                "pre_sidelobe_detection_count": accumulator.pre_sidelobe_detection_count,
                "collapsed": accumulator.kept_detection_count == 0,
                "timepoints": accumulator.timepoints,
            }
        )

    first_non_collapse = next((r["pfa"] for r in sweep_results if not r["collapsed"]), None)
    return {
        "collapse_sample_id": collapse_sample_id,
        "characterization": characterization,
        "pfa_axial_sweep": sweep_results,
        "first_non_collapsing_pfa": first_non_collapse,
    }


def _characterize_sample(sample_path: Path, sample_id: str, *, max_timepoints: int | None) -> dict:
    """Compute image-level SNR + density characteristics from a few timepoints."""

    ndimage = _ndimage()
    array = open_competition_array(sample_path)
    total_timepoints = int(array.shape[0])
    if max_timepoints is not None:
        total_timepoints = min(total_timepoints, int(max_timepoints))

    if total_timepoints <= 1:
        sampled = [0]
    else:
        sampled = sorted(
            set(
                [
                    0,
                    total_timepoints // 4,
                    total_timepoints // 2,
                    (3 * total_timepoints) // 4,
                    total_timepoints - 1,
                ]
            )
        )

    foreground_fractions: list[float] = []
    largest_components: list[int] = []
    component_counts: list[int] = []
    baseline_peak_counts: list[int] = []
    snr_estimates: list[float] = []
    background_means: list[float] = []
    background_stds: list[float] = []

    peak_size = tuple(2 * max(0, int(r)) + 1 for r in DIAG_MIN_DISTANCE_VOXELS)
    for t in sampled:
        volume = read_timepoint(array, min(max(0, int(t)), int(array.shape[0]) - 1))
        normalized = robust_normalize(volume)
        mask = normalized >= 0.65
        labels, component_count = ndimage.label(mask)
        counts = np.bincount(labels.ravel())[1:]
        largest_components.append(int(counts.max()) if counts.size else 0)
        foreground_fractions.append(float(mask.mean()))
        component_counts.append(int(component_count))

        # Baseline local-maxima peak count (pre-CFAR), same normalization as detector.
        norm_peaks = robust_normalize(volume, upper=99.9)
        peak_source = volume.astype(np.float32)
        local_max = ndimage.maximum_filter(peak_source, size=peak_size, mode="nearest")
        peak_mask = (norm_peaks >= 0.65) & (peak_source == local_max)
        baseline_peak_counts.append(int(peak_mask.sum()))

        # SNR proxy: foreground signal vs background clutter on normalized scale.
        fg_values = norm_peaks[mask]
        bg_values = norm_peaks[~mask]
        bg_mean = float(bg_values.mean()) if bg_values.size else 0.0
        bg_std = float(bg_values.std()) if bg_values.size else 0.0
        fg_mean = float(fg_values.mean()) if fg_values.size else 0.0
        background_means.append(bg_mean)
        background_stds.append(bg_std)
        snr = (fg_mean - bg_mean) / bg_std if bg_std > 1e-9 else float("inf")
        snr_estimates.append(float(snr))

    finite_snr = [s for s in snr_estimates if np.isfinite(s)]
    return {
        "sample_id": sample_id,
        "sampled_timepoints": sampled,
        "frame_count_total": int(array.shape[0]),
        "median_foreground_fraction": float(median(foreground_fractions)),
        "median_largest_component_voxels": float(median(largest_components)),
        "median_component_count": float(median(component_counts)),
        "median_baseline_peak_count": float(median(baseline_peak_counts)),
        "median_background_mean_norm": float(median(background_means)),
        "median_background_std_norm": float(median(background_stds)),
        "median_snr_proxy": float(median(finite_snr)) if finite_snr else None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V14 diagnostic investigation (instrumentation and analysis only).")
    parser.add_argument("--train-dir", default="train", help="Directory with .zarr/.geff train pairs.")
    parser.add_argument(
        "--sample-ids",
        nargs="+",
        default=["44b6_0113de3b", "44b6_0b24845f", "44b6_0c582fdc"],
        help="Sample IDs for the 3-sample comparison and forensics peers.",
    )
    parser.add_argument(
        "--collapse-sample-id",
        default="44b6_0c582fdc",
        help="Sample that collapsed to zero nodes under pfa/axial.",
    )
    parser.add_argument("--max-timepoints", type=int, default=20, help="Bounded timepoint cap for diagnostics.")
    parser.add_argument(
        "--pfa-sweep",
        nargs="+",
        type=float,
        default=[1e-3, 1e-2, 1e-1, 3e-1],
        help="pfa values to test for collapse sensitivity under axial mode.",
    )
    parser.add_argument(
        "--output-json",
        default="submissions/v14_diagnostics.json",
        help="Path to write the full diagnostic JSON bundle.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    train_dir = Path(args.train_dir)
    sample_ids = list(args.sample_ids)

    part12 = run_part1_and_part2(
        train_dir=train_dir,
        sample_ids=sample_ids,
        max_timepoints=args.max_timepoints,
    )
    part3 = run_part3_forensics(
        train_dir=train_dir,
        collapse_sample_id=str(args.collapse_sample_id),
        peer_sample_ids=sample_ids,
        max_timepoints=args.max_timepoints,
        pfa_sweep=list(args.pfa_sweep),
    )

    bundle = {
        "max_timepoints": args.max_timepoints,
        "sample_ids": sample_ids,
        "part1_part2_runtime_and_ablation": part12,
        "part3_collapse_forensics": part3,
    }

    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    print(json.dumps({"output_json": str(output_json)}), flush=True)
    print(json.dumps({"aggregate_runtime": part12["aggregate"]}, indent=2), flush=True)
    print(
        json.dumps(
            {
                "collapse_forensics": {
                    "first_non_collapsing_pfa": part3["first_non_collapsing_pfa"],
                    "pfa_axial_sweep": part3["pfa_axial_sweep"],
                }
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
