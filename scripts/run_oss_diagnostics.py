"""Overall System Sensitivity (OSS) budget diagnostic.

READ-ONLY MEASUREMENT PASS. This script introduces no new detection or linking
logic and touches no production defaults. It re-uses the exact production
primitives (``atabey.detection.baseline`` CFAR + sidelobe, the production linker,
and the shadow-only reinforcement summaries) to measure where end-to-end
detection/tracking sensitivity is lost across the pipeline for the CFAR-routed
cohort, and to classify collapse-prone samples as recoverable (Type A) vs. true
blind spots (Type B).

Pipeline stages measured, in order:

    input signal -> CFAR threshold -> sidelobe suppression -> linking -> shadow

Each stage is expressed as a pass/attenuation factor so the chain can be reduced
to one end-to-end effective sensitivity number per sample. The reinforcement
shadow stage is read as a *gain/recovery availability* signal (does stable track
memory exist that could bridge a collapsed frame), not a discard stage.

Inputs re-used (no regeneration of the collapse scan):
  - ``submissions/cfar_bounded_scan_fulltrain.json`` for the routed cohort and the
    per-sample pfa collapse-risk flags.

The production CFAR route runs in ``sigma`` mode (which does not collapse); the
pfa collapse is the experimental failure mode. The OSS pass therefore measures
the real sigma-mode pipeline budget AND uses that same run's track-memory output
to decide whether the hypothetical pfa collapses are recoverable.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter

import numpy as np

from atabey.constants import DEFAULT_VOXEL_SCALE_UM
from atabey.detection.baseline import (
    _cfar_background_stats_box,
    _cfar_margin_confidence,
    _sidelobe_suppress_detections,
    robust_normalize,
)
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS as HFD
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.tracking.event_shadow import compute_lineage_event_shadow
from atabey.tracking.nearest_neighbor import link_adjacent_timepoints
from atabey.tracking.track_quality_shadow import compute_track_quality_shadow
from atabey.types import Detection, LineageGraph


OSS_MIN_DISTANCE_VOXELS = (1, 5, 5)
SCAN_JSON_DEFAULT = Path("submissions/cfar_bounded_scan_fulltrain.json")

# A sample is treated as having usable track memory (Type A) when the production
# run yields at least one stable, high-quality beacon track OR the latent-recovery
# shadow found a gap it could bridge. Both are existing shadow signals.
TYPE_A_BEACON_MIN = 1
_EPS = 1e-6


def _log(message: str) -> None:
    print(f"[oss] {message}", file=sys.stderr, flush=True)


@dataclass
class SampleStageBudget:
    sample_id: str
    routes_to_cfar: bool
    collapse_risk_by_pfa: dict[str, bool]
    timepoints: int
    background_mean_norm: float
    # Stage counts (summed over timepoints).
    peak_candidates: int
    cfar_survivors: int
    sidelobe_survivors: int
    linked_nodes: int
    total_nodes: int
    total_edges: int
    # Signal strength.
    mean_survivor_norm: float
    snr_proxy: float
    # Per-stage pass factors.
    cfar_pass: float
    sidelobe_pass: float
    link_pass: float
    end_to_end_sensitivity: float
    # Shadow / reinforcement memory.
    beacon_count: int
    beacon_fraction: float
    mean_track_quality: float
    mean_persistence: float
    roots: int
    latent_candidate_count: int
    mitosis_candidate_count: int
    # Classification (only meaningful when at collapse risk).
    at_risk_pfa_1e_03: bool
    failure_type: str  # "A", "B", or "n/a"


def _instrumented_timepoint(
    sample_id: str,
    t: int,
    volume: np.ndarray,
) -> tuple[list[Detection], int, int, float]:
    """One production sigma-mode CFAR+sidelobe timepoint, instrumented.

    Returns ``(kept_detections, peak_candidate_count, cfar_survivor_count,
    survivor_norm_sum)``. Uses only production helpers, so results match the
    production hybrid CFAR route.
    """

    from scipy import ndimage

    normalized = robust_normalize(volume, upper=99.9)
    peak_source = volume.astype(np.float32)
    peak_size = tuple(2 * max(0, int(r)) + 1 for r in OSS_MIN_DISTANCE_VOXELS)
    local_max = ndimage.maximum_filter(peak_source, size=peak_size, mode="nearest")

    floor_mask = peak_source == local_max
    candidate_mask = floor_mask & (normalized >= float(HFD.cfar_threshold))
    peak_candidate_count = int(np.count_nonzero(candidate_mask))
    if peak_candidate_count == 0:
        return [], 0, 0, 0.0

    background_mean, background_std, _ring_count = _cfar_background_stats_box(
        normalized,
        cfar_training_radius_voxels=HFD.cfar_training_radius_voxels,
        cfar_guard_radius_voxels=HFD.cfar_guard_radius_voxels,
    )
    adaptive_threshold = background_mean + float(HFD.cfar_k_sigma) * background_std
    keep_mask = candidate_mask & (normalized >= adaptive_threshold)
    coords = np.argwhere(keep_mask)
    cfar_survivor_count = int(coords.shape[0])
    if cfar_survivor_count == 0:
        return [], peak_candidate_count, 0, 0.0

    confidences = normalized[keep_mask]
    adaptive_at_peaks = adaptive_threshold[keep_mask]
    margin = np.maximum(0.0, (confidences - adaptive_at_peaks) / np.maximum(adaptive_at_peaks, _EPS))
    raw_values = volume[keep_mask]
    order = np.argsort(margin)[::-1]
    if HFD.max_detections_per_timepoint is not None:
        order = order[: int(HFD.max_detections_per_timepoint)]

    survivor_norm_sum = 0.0
    detections: list[Detection] = []
    for output_idx, coord_idx in enumerate(order, start=1):
        z, y, x = coords[int(coord_idx)]
        zf, yf, xf = float(z), float(y), float(x)
        z_um, y_um, x_um = DEFAULT_VOXEL_SCALE_UM.voxel_to_um(zf, yf, xf)
        survivor_norm_sum += float(confidences[int(coord_idx)])
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
                intensity_mean=float(raw_values[int(coord_idx)]),
                intensity_max=float(raw_values[int(coord_idx)]),
                component_volume=1,
                detection_confidence=_cfar_margin_confidence(
                    float(confidences[int(coord_idx)]),
                    float(adaptive_at_peaks[int(coord_idx)]),
                ),
            )
        )

    kept = _sidelobe_suppress_detections(
        detections,
        sidelobe_mode=HFD.sidelobe_mode,
        sidelobe_radius_voxels=HFD.sidelobe_radius_voxels,
        sidelobe_axial_z_radius_voxels=HFD.sidelobe_axial_z_radius_voxels,
        sidelobe_axial_xy_tolerance_voxels=HFD.sidelobe_axial_xy_tolerance_voxels,
        sidelobe_floor_ratio=HFD.sidelobe_floor_ratio,
    )
    return kept, peak_candidate_count, cfar_survivor_count, survivor_norm_sum


def _background_mean_norm(volume: np.ndarray) -> float:
    normalized = robust_normalize(volume, upper=99.9)
    background_mean, _std, ring_count = _cfar_background_stats_box(
        normalized,
        cfar_training_radius_voxels=HFD.cfar_training_radius_voxels,
        cfar_guard_radius_voxels=HFD.cfar_guard_radius_voxels,
    )
    valid = ring_count > 0
    return float(np.median(background_mean[valid])) if np.any(valid) else float("nan")


def _measure_sample(
    sample_path: Path,
    *,
    sample_id: str,
    routes_to_cfar: bool,
    collapse_risk_by_pfa: dict[str, bool],
    max_timepoints: int,
) -> SampleStageBudget:
    array = open_competition_array(sample_path)
    total = min(int(array.shape[0]), int(max_timepoints))

    graph = LineageGraph(sample_id=sample_id)
    previous: list[Detection] = []
    detections_by_node_id: dict[str, Detection] = {}
    predecessor_by_node_id: dict[str, Detection] = {}

    peak_candidates = 0
    cfar_survivors = 0
    sidelobe_survivors = 0
    survivor_norm_sum = 0.0
    background_mean_norm = float("nan")

    for t in range(total):
        volume = read_timepoint(array, t)
        if t == total // 2:
            background_mean_norm = _background_mean_norm(volume)
        kept, candidate_count, survivor_count, norm_sum = _instrumented_timepoint(
            sample_id, t, volume
        )
        peak_candidates += candidate_count
        cfar_survivors += survivor_count
        sidelobe_survivors += len(kept)
        survivor_norm_sum += norm_sum

        for detection in kept:
            graph.add_detection(detection)
            detections_by_node_id[detection.node_id] = detection
        edges = link_adjacent_timepoints(
            previous,
            kept,
            HFD.cfar_max_link_distance_um,
            strategy=HFD.cfar_link_strategy,
            predecessor_by_node_id=predecessor_by_node_id,
        )
        for edge in edges:
            graph.add_edge(edge)
            predecessor_by_node_id[edge.target_id] = detections_by_node_id[edge.source_id]
        previous = kept

    linked_node_ids = {edge.source_id for edge in graph.edges} | {edge.target_id for edge in graph.edges}
    linked_nodes = len(linked_node_ids & set(detections_by_node_id))

    track_quality = compute_track_quality_shadow(graph)
    event_shadow = compute_lineage_event_shadow(
        graph,
        latent_window_frames=HFD.latent_shadow_window_frames,
        latent_max_link_distance_um=HFD.latent_shadow_max_link_distance_um,
        mitosis_distance_um=HFD.mitosis_shadow_distance_um,
        mitosis_intensity_tolerance=HFD.mitosis_shadow_intensity_tolerance,
    )

    cfar_pass = cfar_survivors / peak_candidates if peak_candidates else 0.0
    sidelobe_pass = sidelobe_survivors / cfar_survivors if cfar_survivors else 0.0
    link_pass = linked_nodes / sidelobe_survivors if sidelobe_survivors else 0.0
    end_to_end = cfar_pass * sidelobe_pass * link_pass
    mean_survivor_norm = survivor_norm_sum / sidelobe_survivors if sidelobe_survivors else 0.0
    snr_proxy = (
        mean_survivor_norm / background_mean_norm
        if background_mean_norm and not np.isnan(background_mean_norm) and background_mean_norm > _EPS
        else float("nan")
    )

    at_risk = bool(collapse_risk_by_pfa.get("1e-03", False))
    # Type A (recoverable) when the non-collapsing production run demonstrates
    # usable track memory near the collapse: a stable beacon-grade track, an
    # active latent-recovery bridge, or clearly persistent multi-frame tracks
    # (most detections link AND average track depth spans >=2 frames).
    has_track_memory = (
        track_quality.beacon_count >= TYPE_A_BEACON_MIN
        or event_shadow.latent_candidate_count > 0
        or (link_pass >= 0.5 and float(track_quality.mean_persistence) >= 0.5)
    )
    if not at_risk:
        failure_type = "n/a"
    elif has_track_memory:
        failure_type = "A"
    else:
        failure_type = "B"

    return SampleStageBudget(
        sample_id=sample_id,
        routes_to_cfar=routes_to_cfar,
        collapse_risk_by_pfa=collapse_risk_by_pfa,
        timepoints=total,
        background_mean_norm=background_mean_norm,
        peak_candidates=peak_candidates,
        cfar_survivors=cfar_survivors,
        sidelobe_survivors=sidelobe_survivors,
        linked_nodes=linked_nodes,
        total_nodes=len(graph.detections),
        total_edges=len(graph.edges),
        mean_survivor_norm=round(mean_survivor_norm, 5),
        snr_proxy=round(snr_proxy, 4) if not np.isnan(snr_proxy) else float("nan"),
        cfar_pass=round(cfar_pass, 5),
        sidelobe_pass=round(sidelobe_pass, 5),
        link_pass=round(link_pass, 5),
        end_to_end_sensitivity=round(end_to_end, 5),
        beacon_count=int(track_quality.beacon_count),
        beacon_fraction=round(float(track_quality.beacon_fraction), 5),
        mean_track_quality=round(float(track_quality.mean_track_quality), 5),
        mean_persistence=round(float(track_quality.mean_persistence), 5),
        roots=int(track_quality.roots),
        latent_candidate_count=int(event_shadow.latent_candidate_count),
        mitosis_candidate_count=int(event_shadow.mitosis_candidate_count),
        at_risk_pfa_1e_03=at_risk,
        failure_type=failure_type,
    )


def _load_routed_records(scan_json: Path) -> list[dict]:
    with open(scan_json, encoding="utf-8") as handle:
        payload = json.load(handle)
    records = payload.get("records", [])
    return [r for r in records if r.get("routes_to_cfar")]


def _mean_optional(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None and not (isinstance(v, float) and np.isnan(v))]
    return round(float(mean(clean)), 5) if clean else None


def run_oss(
    train_dir: Path,
    scan_json: Path,
    *,
    max_timepoints: int,
    max_samples: int | None,
) -> dict:
    routed = _load_routed_records(scan_json)
    if max_samples is not None:
        routed = routed[:max_samples]
    _log(f"measuring {len(routed)} routed samples over up to {max_timepoints} timepoints")

    budgets: list[SampleStageBudget] = []
    for index, record in enumerate(routed, start=1):
        sample_id = record["sample_id"]
        sample_path = train_dir / f"{sample_id}.zarr"
        if not sample_path.exists():
            _log(f"  [{index}/{len(routed)}] {sample_id} missing zarr, skipping")
            continue
        try:
            budget = _measure_sample(
                sample_path,
                sample_id=sample_id,
                routes_to_cfar=True,
                collapse_risk_by_pfa=record.get("collapse_risk_by_pfa", {}),
                max_timepoints=max_timepoints,
            )
        except Exception as exc:  # noqa: BLE001 - report and continue.
            _log(f"  [{index}/{len(routed)}] {sample_id} FAILED: {exc}")
            continue
        budgets.append(budget)
        if index % 5 == 0 or index == len(routed):
            _log(
                f"  [{index}/{len(routed)}] {sample_id} e2e={budget.end_to_end_sensitivity} "
                f"type={budget.failure_type} beacons={budget.beacon_count}"
            )

    at_risk = [b for b in budgets if b.at_risk_pfa_1e_03]
    type_a = [b for b in at_risk if b.failure_type == "A"]
    type_b = [b for b in at_risk if b.failure_type == "B"]

    raw_collapse_rate = len(at_risk) / len(budgets) if budgets else 0.0
    type_a_fraction = len(type_a) / len(at_risk) if at_risk else 0.0
    type_b_fraction = len(type_b) / len(at_risk) if at_risk else 0.0
    effective_blind_spot_rate = raw_collapse_rate * type_b_fraction

    stage_summary = {
        "mean_cfar_pass": _mean_optional([b.cfar_pass for b in budgets]),
        "mean_sidelobe_pass": _mean_optional([b.sidelobe_pass for b in budgets]),
        "mean_link_pass": _mean_optional([b.link_pass for b in budgets]),
        "mean_end_to_end_sensitivity": _mean_optional([b.end_to_end_sensitivity for b in budgets]),
        "mean_beacon_fraction": _mean_optional([b.beacon_fraction for b in budgets]),
        "mean_snr_proxy": _mean_optional([b.snr_proxy for b in budgets]),
    }

    return {
        "cohort_size": len(budgets),
        "at_risk_pfa_1e_03": len(at_risk),
        "raw_cfar_only_collapse_rate": round(raw_collapse_rate, 4),
        "type_A_recoverable": len(type_a),
        "type_B_blind_spot": len(type_b),
        "type_A_fraction_of_at_risk": round(type_a_fraction, 4),
        "type_B_fraction_of_at_risk": round(type_b_fraction, 4),
        "effective_system_blind_spot_rate": round(effective_blind_spot_rate, 4),
        "stage_attenuation_summary": stage_summary,
        "type_A_sample_ids": sorted(b.sample_id for b in type_a),
        "type_B_sample_ids": sorted(b.sample_id for b in type_b),
        "budgets": [asdict(b) for b in budgets],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-dir", default="train", help="Directory with .zarr/.geff pairs.")
    parser.add_argument("--scan-json", type=Path, default=SCAN_JSON_DEFAULT, help="Full-train scan JSON.")
    parser.add_argument("--max-timepoints", type=int, default=8, help="Timepoints per sample.")
    parser.add_argument("--max-samples", type=int, default=None, help="Cap routed samples (debug).")
    parser.add_argument("--output-json", type=Path, default=None, help="Optional JSON output path.")
    args = parser.parse_args(argv)

    payload = run_oss(
        Path(args.train_dir),
        args.scan_json,
        max_timepoints=args.max_timepoints,
        max_samples=args.max_samples,
    )
    print(json.dumps({k: v for k, v in payload.items() if k != "budgets"}, indent=2))

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        _log(f"wrote {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
