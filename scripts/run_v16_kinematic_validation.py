from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS, DEFAULT_KINEMATIC_RECOVERY_SETTINGS
from atabey.tracking.kinematic_recovery import KinematicRecoverySettings

try:
    from run_hybrid_train_evaluation import _format_int_tuple, _parse_int_tuple, run_train_evaluation
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_v16_kinematic_validation.
    from scripts.run_hybrid_train_evaluation import _format_int_tuple, _parse_int_tuple, run_train_evaluation


ROUTE_HYBRID_CFAR_SIDELOBE = "hybrid_cfar_sidelobe"
COHORT_ROUTED_66 = "routed_cfar_66"
COHORT_AT_RISK_51 = "at_risk_pfa_1e_03_51"
COHORT_OUTSIDE_15 = "outside_at_risk_15"
EXPECTED_COHORT_SIZES = {
    COHORT_ROUTED_66: 66,
    COHORT_AT_RISK_51: 51,
    COHORT_OUTSIDE_15: 15,
}


@dataclass(frozen=True)
class CohortSets:
    routed_cfar_66: list[str]
    at_risk_pfa_1e_03_51: list[str]
    outside_at_risk_15: list[str]


@dataclass(frozen=True)
class DeltaSummary:
    cohort: str
    samples: int
    mean_quality_delta: float
    mean_sparse_recall_delta: float
    mean_sparse_edge_recall_delta: float
    improved: int
    regressed: int
    unchanged: int


def load_cfar_validation_cohorts(scan_json: Path) -> CohortSets:
    payload = json.loads(scan_json.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    routed = sorted(
        str(record["sample_id"])
        for record in records
        if bool(record.get("routes_to_cfar"))
    )
    at_risk = sorted(
        str(record["sample_id"])
        for record in records
        if bool(record.get("routes_to_cfar")) and bool(record.get("collapse_risk_by_pfa", {}).get("1e-03"))
    )
    at_risk_set = set(at_risk)
    outside = sorted(sample_id for sample_id in routed if sample_id not in at_risk_set)
    return CohortSets(
        routed_cfar_66=routed,
        at_risk_pfa_1e_03_51=at_risk,
        outside_at_risk_15=outside,
    )


def validate_expected_cohort_sizes(cohorts: CohortSets) -> None:
    actual_sizes = {
        COHORT_ROUTED_66: len(cohorts.routed_cfar_66),
        COHORT_AT_RISK_51: len(cohorts.at_risk_pfa_1e_03_51),
        COHORT_OUTSIDE_15: len(cohorts.outside_at_risk_15),
    }
    for cohort_name, expected_size in EXPECTED_COHORT_SIZES.items():
        actual_size = actual_sizes[cohort_name]
        if actual_size != expected_size:
            raise ValueError(
                f"Unexpected cohort size for {cohort_name}: expected {expected_size}, got {actual_size}."
            )


def build_hybrid_route_index(records: list[Any]) -> dict[str, Any]:
    return {
        str(record.sample_id): record
        for record in records
        if str(record.route) == ROUTE_HYBRID_CFAR_SIDELOBE
    }


def build_paired_hybrid_deltas(*, off_records: list[Any], on_records: list[Any]) -> list[dict[str, Any]]:
    off_index = build_hybrid_route_index(off_records)
    on_index = build_hybrid_route_index(on_records)
    sample_ids = sorted(set(off_index) & set(on_index))
    paired: list[dict[str, Any]] = []
    for sample_id in sample_ids:
        off_record = off_index[sample_id]
        on_record = on_index[sample_id]
        off_quality = float(off_record.quality_score)
        on_quality = float(on_record.quality_score)
        off_sparse_recall = 0.0 if off_record.sparse_recall is None else float(off_record.sparse_recall)
        on_sparse_recall = 0.0 if on_record.sparse_recall is None else float(on_record.sparse_recall)
        off_sparse_edge_recall = 0.0 if off_record.sparse_edge_recall is None else float(off_record.sparse_edge_recall)
        on_sparse_edge_recall = 0.0 if on_record.sparse_edge_recall is None else float(on_record.sparse_edge_recall)
        paired.append(
            {
                "sample_id": sample_id,
                "quality_off": off_quality,
                "quality_on": on_quality,
                "quality_delta": on_quality - off_quality,
                "sparse_recall_off": off_sparse_recall,
                "sparse_recall_on": on_sparse_recall,
                "sparse_recall_delta": on_sparse_recall - off_sparse_recall,
                "sparse_edge_recall_off": off_sparse_edge_recall,
                "sparse_edge_recall_on": on_sparse_edge_recall,
                "sparse_edge_recall_delta": on_sparse_edge_recall - off_sparse_edge_recall,
                "recovered_edges_on": on_record.kinematic_recovered_edges,
                "suppressed_by_clean_context_on": on_record.kinematic_suppressed_by_clean_context,
                "suppressed_by_edge_ceiling_on": on_record.kinematic_suppressed_by_edge_ceiling,
                "kinematic_overhead_ms_on": on_record.kinematic_overhead_ms,
            }
        )
    return paired


def summarize_deltas(*, cohort_name: str, paired_deltas: list[dict[str, Any]], sample_ids: set[str]) -> DeltaSummary:
    items = [delta for delta in paired_deltas if delta["sample_id"] in sample_ids]
    if not items:
        raise ValueError(f"No paired hybrid records found for cohort {cohort_name}.")
    improved = sum(1 for delta in items if float(delta["quality_delta"]) > 0.0)
    regressed = sum(1 for delta in items if float(delta["quality_delta"]) < 0.0)
    unchanged = len(items) - improved - regressed
    return DeltaSummary(
        cohort=cohort_name,
        samples=len(items),
        mean_quality_delta=sum(float(delta["quality_delta"]) for delta in items) / len(items),
        mean_sparse_recall_delta=sum(float(delta["sparse_recall_delta"]) for delta in items) / len(items),
        mean_sparse_edge_recall_delta=sum(float(delta["sparse_edge_recall_delta"]) for delta in items) / len(items),
        improved=improved,
        regressed=regressed,
        unchanged=unchanged,
    )


def mean_hybrid_quality(records: list[Any]) -> float:
    items = [float(record.quality_score) for record in records if str(record.route) == ROUTE_HYBRID_CFAR_SIDELOBE]
    if not items:
        raise ValueError("No hybrid_cfar_sidelobe records were produced during validation.")
    return float(sum(items) / len(items))


def _run_evaluation(
    *,
    train_dir: Path,
    sample_ids: list[str],
    max_timepoints: int,
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
    enable_kinematic_recovery: bool,
    kinematic_recovery_settings: KinematicRecoverySettings,
) -> list[Any]:
    with tempfile.TemporaryDirectory(prefix="atabey-v16-validate-") as temp_dir:
        temp_root = Path(temp_dir)
        return run_train_evaluation(
            train_dir=train_dir,
            sample_ids=sample_ids,
            output_json=temp_root / ("on.json" if enable_kinematic_recovery else "off.json"),
            output_summary_json=temp_root / ("on_summary.json" if enable_kinematic_recovery else "off_summary.json"),
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
            enable_kinematic_recovery=enable_kinematic_recovery,
            kinematic_recovery_settings=kinematic_recovery_settings,
        )


def build_validation_report(
    *,
    scan_json: Path,
    train_dir: Path,
    max_timepoints: int,
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
    kinematic_recovery_settings: KinematicRecoverySettings,
) -> dict[str, Any]:
    cohorts = load_cfar_validation_cohorts(scan_json)
    validate_expected_cohort_sizes(cohorts)

    off_records = _run_evaluation(
        train_dir=train_dir,
        sample_ids=cohorts.routed_cfar_66,
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
        enable_kinematic_recovery=False,
        kinematic_recovery_settings=kinematic_recovery_settings,
    )
    on_records = _run_evaluation(
        train_dir=train_dir,
        sample_ids=cohorts.routed_cfar_66,
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
        enable_kinematic_recovery=True,
        kinematic_recovery_settings=kinematic_recovery_settings,
    )

    paired_deltas = build_paired_hybrid_deltas(off_records=off_records, on_records=on_records)
    summaries = [
        summarize_deltas(
            cohort_name=COHORT_ROUTED_66,
            paired_deltas=paired_deltas,
            sample_ids=set(cohorts.routed_cfar_66),
        ),
        summarize_deltas(
            cohort_name=COHORT_AT_RISK_51,
            paired_deltas=paired_deltas,
            sample_ids=set(cohorts.at_risk_pfa_1e_03_51),
        ),
        summarize_deltas(
            cohort_name=COHORT_OUTSIDE_15,
            paired_deltas=paired_deltas,
            sample_ids=set(cohorts.outside_at_risk_15),
        ),
    ]

    outside_regressions = sorted(
        (delta for delta in paired_deltas if delta["sample_id"] in set(cohorts.outside_at_risk_15) and float(delta["quality_delta"]) < 0.0),
        key=lambda item: float(item["quality_delta"]),
    )
    top_improvements = sorted(paired_deltas, key=lambda item: float(item["quality_delta"]), reverse=True)[:10]
    top_regressions = sorted(paired_deltas, key=lambda item: float(item["quality_delta"]))[:10]

    off_hybrid_mean = mean_hybrid_quality(off_records)
    on_hybrid_mean = mean_hybrid_quality(on_records)

    return {
        "metadata": {
            "experiment": "v16_kinematic_soft_linking",
            "metric": "quality_score = 0.5*sparse_recall + 0.5*sparse_edge_recall",
            "train_dir": str(train_dir),
            "scan_json": str(scan_json),
            "max_timepoints": max_timepoints,
            "cfar_threshold": cfar_threshold,
            "cfar_training_radius_voxels": list(cfar_training_radius_voxels),
            "cfar_guard_radius_voxels": list(cfar_guard_radius_voxels),
            "cfar_k_sigma": cfar_k_sigma,
            "sidelobe_radius_voxels": list(sidelobe_radius_voxels),
            "sidelobe_floor_ratio": sidelobe_floor_ratio,
            "max_detections_per_timepoint": max_detections_per_timepoint,
            "cfar_link_strategy": cfar_link_strategy,
            "cfar_max_link_distance_um": cfar_max_link_distance_um,
            "cfar_route_policy": cfar_route_policy,
            "kinematic_recovery_settings": asdict(kinematic_recovery_settings),
            "cohort_sizes": {
                COHORT_ROUTED_66: len(cohorts.routed_cfar_66),
                COHORT_AT_RISK_51: len(cohorts.at_risk_pfa_1e_03_51),
                COHORT_OUTSIDE_15: len(cohorts.outside_at_risk_15),
            },
        },
        "hybrid_route_mean_quality": {
            "off": off_hybrid_mean,
            "on": on_hybrid_mean,
            "delta": on_hybrid_mean - off_hybrid_mean,
        },
        "cohort_summaries": [asdict(summary) for summary in summaries],
        "outside_cohort_regressions": outside_regressions,
        "top_improvements": top_improvements,
        "top_regressions": top_regressions,
        "per_sample_hybrid_deltas": paired_deltas,
        "cohorts": {
            COHORT_AT_RISK_51: cohorts.at_risk_pfa_1e_03_51,
            COHORT_OUTSIDE_15: cohorts.outside_at_risk_15,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the V16 kinematic recovery ON/OFF validation on the routed CFAR cohort.")
    parser.add_argument("--train-dir", default="train", help="Directory containing .zarr/.geff train pairs.")
    parser.add_argument(
        "--scan-json",
        default="submissions/cfar_bounded_scan_fulltrain.json",
        help="Scan JSON containing the routed 66-sample CFAR cohort and the 51/15 at-risk split.",
    )
    parser.add_argument(
        "--output-json",
        default="submissions/v16_kinematic_validate.json",
        help="Consolidated OFF vs ON validation report path.",
    )
    parser.add_argument("--max-timepoints", type=int, default=10, help="Timepoint cap used for the real-metric validation pass.")
    parser.add_argument(
        "--cfar-threshold",
        type=float,
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold,
        help="CFAR global normalized floor threshold.",
    )
    parser.add_argument(
        "--cfar-training-radius",
        default=_format_int_tuple(DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_training_radius_voxels),
        help="CFAR training radius as tz,ty,tx.",
    )
    parser.add_argument(
        "--cfar-guard-radius",
        default=_format_int_tuple(DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_guard_radius_voxels),
        help="CFAR guard radius as gz,gy,gx.",
    )
    parser.add_argument(
        "--cfar-k-sigma",
        type=float,
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_k_sigma,
        help="CFAR k-sigma multiplier.",
    )
    parser.add_argument(
        "--sidelobe-radius",
        default=_format_int_tuple(DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_radius_voxels),
        help="Sidelobe suppression radius as sz,sy,sx.",
    )
    parser.add_argument(
        "--sidelobe-floor",
        type=float,
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_floor_ratio,
        help="Sidelobe floor ratio.",
    )
    parser.add_argument(
        "--max-detections-per-timepoint",
        type=int,
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.max_detections_per_timepoint,
        help="CFAR route detection cap.",
    )
    parser.add_argument(
        "--cfar-route-policy",
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_route_policy,
        choices=["merged_all", "merged_6bba_only"],
        help="Hybrid router policy used during the validation pass.",
    )
    parser.add_argument(
        "--cfar-link-strategy",
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_link_strategy,
        help="CFAR route link strategy.",
    )
    parser.add_argument(
        "--cfar-max-link-distance-um",
        type=float,
        default=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_max_link_distance_um,
        help="CFAR route link distance.",
    )
    parser.add_argument(
        "--kinematic-max-gap-frames",
        type=int,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.max_gap_frames,
        help="Maximum number of missing frames eligible for kinematic recovery.",
    )
    parser.add_argument(
        "--kinematic-min-track-length-edges",
        type=int,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.min_track_length_edges,
        help="Minimum accepted track length before a dying track can enter recovery.",
    )
    parser.add_argument(
        "--kinematic-trigger-background-mean-min",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.trigger_background_mean_min,
        help="Minimum local CFAR background mean required to classify a gap as clutter-risk.",
    )
    parser.add_argument(
        "--kinematic-trigger-adaptive-threshold-min",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.trigger_adaptive_threshold_min,
        help="Minimum local adaptive threshold required for clutter-risk authorization.",
    )
    parser.add_argument(
        "--kinematic-trigger-contrast-max",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.trigger_contrast_max,
        help="Maximum local contrast allowed for a recovery-eligible termination.",
    )
    parser.add_argument(
        "--kinematic-trigger-cfar-margin-max",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.trigger_cfar_margin_max,
        help="Maximum local CFAR margin allowed for recovery authorization.",
    )
    parser.add_argument(
        "--kinematic-base-sigma-um",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.base_sigma_um,
        help="Base positional uncertainty in microns for the kinematic cone.",
    )
    parser.add_argument(
        "--kinematic-velocity-sigma-scale",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.velocity_sigma_scale,
        help="Velocity-dependent cone expansion along the motion axis.",
    )
    parser.add_argument(
        "--kinematic-transverse-sigma-um",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.transverse_sigma_um,
        help="Cross-axis uncertainty in microns for the kinematic cone.",
    )
    parser.add_argument(
        "--kinematic-mahalanobis-threshold",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.mahalanobis_threshold,
        help="Mahalanobis gate threshold for virtual gap edges.",
    )
    parser.add_argument(
        "--kinematic-directional-cosine-min",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.directional_cosine_min,
        help="Minimum cosine agreement between prior motion and recovered displacement.",
    )
    parser.add_argument(
        "--kinematic-temporal-discount",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.temporal_discount,
        help="Discount factor applied to gap-edge confidence as missing frames increase.",
    )
    parser.add_argument(
        "--kinematic-edge-inflation-ceiling-ratio",
        type=float,
        default=DEFAULT_KINEMATIC_RECOVERY_SETTINGS.edge_inflation_ceiling_ratio,
        help="Maximum recovered-edge count as a ratio of adjacent recovered edges in the same frame.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    train_dir = Path(args.train_dir)
    scan_json = Path(args.scan_json)
    output_json = Path(args.output_json)
    kinematic_recovery_settings = KinematicRecoverySettings(
        max_gap_frames=int(args.kinematic_max_gap_frames),
        min_track_length_edges=int(args.kinematic_min_track_length_edges),
        trigger_background_mean_min=float(args.kinematic_trigger_background_mean_min),
        trigger_adaptive_threshold_min=float(args.kinematic_trigger_adaptive_threshold_min),
        trigger_contrast_max=float(args.kinematic_trigger_contrast_max),
        trigger_cfar_margin_max=float(args.kinematic_trigger_cfar_margin_max),
        base_sigma_um=float(args.kinematic_base_sigma_um),
        velocity_sigma_scale=float(args.kinematic_velocity_sigma_scale),
        transverse_sigma_um=float(args.kinematic_transverse_sigma_um),
        mahalanobis_threshold=float(args.kinematic_mahalanobis_threshold),
        directional_cosine_min=float(args.kinematic_directional_cosine_min),
        temporal_discount=float(args.kinematic_temporal_discount),
        edge_inflation_ceiling_ratio=float(args.kinematic_edge_inflation_ceiling_ratio),
    )
    report = build_validation_report(
        scan_json=scan_json,
        train_dir=train_dir,
        max_timepoints=int(args.max_timepoints),
        cfar_threshold=float(args.cfar_threshold),
        cfar_training_radius_voxels=_parse_int_tuple(str(args.cfar_training_radius)),
        cfar_guard_radius_voxels=_parse_int_tuple(str(args.cfar_guard_radius)),
        cfar_k_sigma=float(args.cfar_k_sigma),
        sidelobe_radius_voxels=_parse_int_tuple(str(args.sidelobe_radius)),
        sidelobe_floor_ratio=float(args.sidelobe_floor),
        max_detections_per_timepoint=(None if args.max_detections_per_timepoint is None else int(args.max_detections_per_timepoint)),
        cfar_link_strategy=str(args.cfar_link_strategy),
        cfar_max_link_distance_um=float(args.cfar_max_link_distance_um),
        cfar_route_policy=str(args.cfar_route_policy),
        kinematic_recovery_settings=kinematic_recovery_settings,
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"output_json": str(output_json), "cohort_summaries": report["cohort_summaries"]}), flush=True)


if __name__ == "__main__":
    main()