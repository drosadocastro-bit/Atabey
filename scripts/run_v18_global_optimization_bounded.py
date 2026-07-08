from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from atabey.evaluation.sparse_ground_truth import evaluate_sparse_ground_truth, match_sparse_centroids
from atabey.io.geff_reader import read_geff_graph
from atabey.tracking.global_window_optimizer import (
    GlobalWindowDecision,
    GlobalWindowSettings,
    compare_greedy_vs_window_global,
)
from atabey.tracking.kinematic_recovery import KinematicRecoverySettings

try:
    from run_hybrid_submission import build_graph_cfar_sidelobe
except ModuleNotFoundError:  # pragma: no cover
    from scripts.run_hybrid_submission import build_graph_cfar_sidelobe

try:
    from run_v16_kinematic_validation import (
        COHORT_AT_RISK_51,
        COHORT_OUTSIDE_15,
        COHORT_ROUTED_66,
        load_cfar_validation_cohorts,
        validate_expected_cohort_sizes,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scripts.run_v16_kinematic_validation import (
        COHORT_AT_RISK_51,
        COHORT_OUTSIDE_15,
        COHORT_ROUTED_66,
        load_cfar_validation_cohorts,
        validate_expected_cohort_sizes,
    )


@dataclass(frozen=True)
class SampleQualityRecord:
    sample_id: str
    sparse_recall: float | None
    sparse_edge_recall: float | None
    quality_score: float
    build_elapsed_seconds: float


@dataclass(frozen=True)
class ShadowEdgeRecord:
    sample_id: str
    source_t: int
    source_id: str
    gt_source_id: int
    gt_target_id: int
    nearest_t_plus_1_distance_um_v16: float | None
    source_present_in_graph: bool
    greedy_target_id: str | None
    global_target_id: str | None
    changed_decision: bool
    used_second_step: bool
    global_total_cost: float | None
    greedy_distance_um: float | None
    source_gt_id: int | None
    greedy_target_gt_id: int | None
    global_target_gt_id: int | None
    source_matches_gt_source: bool
    greedy_correct: bool | None
    global_correct: bool | None
    shadow_outcome: str
    shadow_elapsed_ms: float


@dataclass(frozen=True)
class DecisionSummary:
    cohort: str
    considered_edges: int
    source_missing: int
    changed_decisions: int
    used_second_step: int
    global_better: int
    greedy_better: int
    both_correct: int
    both_wrong_or_unmapped: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V18 bounded global-optimization shadow audit on known wrong-edge residuals.")
    parser.add_argument("--train-dir", default="train", help="Directory containing train .zarr/.geff sample pairs.")
    parser.add_argument("--scan-json", default="submissions/cfar_bounded_scan_fulltrain.json", help="CFAR routing scan with 66/51/15 cohort definitions.")
    parser.add_argument("--v16-diagnostic-json", default="submissions/v16_diagnostic_root_cause.json", help="Known Type-1 regressed edge artifact used as the V18 target subset.")
    parser.add_argument("--v17-validate-json", default="submissions/v17_hard_exclusion_validate.json", help="V17 validation artifact used to mirror detector and linker settings.")
    parser.add_argument("--output-json", default="submissions/v18_global_optimization_bounded.json", help="Consolidated V18 shadow audit output.")
    parser.add_argument("--output-jsonl", default="submissions/v18_global_optimization_shadow_edges.jsonl", help="Per-edge shadow decision records output.")
    parser.add_argument("--first-step-prediction-weight", type=float, default=1.0)
    parser.add_argument("--first-step-distance-weight", type=float, default=0.4)
    parser.add_argument("--second-step-prediction-weight", type=float, default=1.0)
    parser.add_argument("--second-step-distance-weight", type=float, default=0.3)
    parser.add_argument("--terminal-without-second-step-penalty", type=float, default=1.2)
    return parser.parse_args()


def _quality_score(sparse_recall: float | None, sparse_edge_recall: float | None) -> float:
    node_component = 0.0 if sparse_recall is None else float(sparse_recall)
    edge_component = 0.0 if sparse_edge_recall is None else float(sparse_edge_recall)
    return 0.5 * node_component + 0.5 * edge_component


def _build_predecessor_map(graph) -> dict[str, Any]:
    detection_by_id = {detection.node_id: detection for detection in graph.detections}
    predecessor_by_id: dict[str, Any] = {}
    for edge in graph.edges:
        source = detection_by_id.get(edge.source_id)
        target = detection_by_id.get(edge.target_id)
        if source is None or target is None:
            continue
        if int(target.t) != int(source.t) + 1:
            continue
        existing = predecessor_by_id.get(target.node_id)
        if existing is None:
            predecessor_by_id[target.node_id] = source
            continue
        if int(source.t) > int(existing.t):
            predecessor_by_id[target.node_id] = source
    return predecessor_by_id


def _rows_by_sample(v16_payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for sample_id, payload in v16_payload.get("per_sample", {}).items():
        sample_rows: list[dict[str, Any]] = []
        for row in payload.get("regressed_edges", []):
            row_type = str(row.get("type"))
            if row_type != "Type1_direct_edge_replaced_by_frame_skip":
                continue
            sample_rows.append(dict(row))
        if sample_rows:
            rows[str(sample_id)] = sample_rows
    return rows


def _match_maps(graph, gt_graph) -> tuple[dict[int, str], dict[str, int]]:
    matches = [
        item
        for item in match_sparse_centroids(graph, gt_graph, radius_um=7.0)
        if item.matched and item.prediction_node_id is not None
    ]
    gt_to_pred = {int(item.ground_truth_node_id): str(item.prediction_node_id) for item in matches}
    pred_to_gt = {str(item.prediction_node_id): int(item.ground_truth_node_id) for item in matches}
    return gt_to_pred, pred_to_gt


def _shadow_outcome(*, greedy_correct: bool | None, global_correct: bool | None) -> str:
    if global_correct is True and greedy_correct is not True:
        return "global_better"
    if greedy_correct is True and global_correct is not True:
        return "greedy_better"
    if greedy_correct is True and global_correct is True:
        return "both_correct"
    return "both_wrong_or_unmapped"


def _summarize_decisions(*, cohort: str, records: list[ShadowEdgeRecord]) -> DecisionSummary:
    return DecisionSummary(
        cohort=cohort,
        considered_edges=len(records),
        source_missing=sum(1 for item in records if not item.source_present_in_graph),
        changed_decisions=sum(1 for item in records if item.changed_decision),
        used_second_step=sum(1 for item in records if item.used_second_step),
        global_better=sum(1 for item in records if item.shadow_outcome == "global_better"),
        greedy_better=sum(1 for item in records if item.shadow_outcome == "greedy_better"),
        both_correct=sum(1 for item in records if item.shadow_outcome == "both_correct"),
        both_wrong_or_unmapped=sum(1 for item in records if item.shadow_outcome == "both_wrong_or_unmapped"),
    )


def _mean_quality(records: list[SampleQualityRecord], sample_ids: set[str]) -> float:
    scoped = [item.quality_score for item in records if item.sample_id in sample_ids]
    if not scoped:
        return 0.0
    return float(sum(scoped) / len(scoped))


def main() -> None:
    args = _parse_args()
    train_dir = Path(args.train_dir)
    scan_json = Path(args.scan_json)
    v16_diagnostic_json = Path(args.v16_diagnostic_json)
    v17_validate_json = Path(args.v17_validate_json)
    output_json = Path(args.output_json)
    output_jsonl = Path(args.output_jsonl)

    cohorts = load_cfar_validation_cohorts(scan_json)
    validate_expected_cohort_sizes(cohorts)

    v16_payload = json.loads(v16_diagnostic_json.read_text(encoding="utf-8"))
    v17_payload = json.loads(v17_validate_json.read_text(encoding="utf-8"))

    v17_metadata = dict(v17_payload["metadata"])
    kinematic_settings = KinematicRecoverySettings(**v17_metadata["kinematic_recovery_settings"])
    window_settings = GlobalWindowSettings(
        first_step_prediction_weight=float(args.first_step_prediction_weight),
        first_step_distance_weight=float(args.first_step_distance_weight),
        second_step_prediction_weight=float(args.second_step_prediction_weight),
        second_step_distance_weight=float(args.second_step_distance_weight),
        terminal_without_second_step_penalty=float(args.terminal_without_second_step_penalty),
    )

    sample_rows = _rows_by_sample(v16_payload)
    target_rows = [row for rows in sample_rows.values() for row in rows]

    quality_records: list[SampleQualityRecord] = []
    shadow_records: list[ShadowEdgeRecord] = []

    for idx, sample_id in enumerate(cohorts.routed_cfar_66, start=1):
        print(f"[v18 {idx}/{len(cohorts.routed_cfar_66)}] sample={sample_id}", flush=True)
        sample_path = train_dir / f"{sample_id}.zarr"
        gt_graph = read_geff_graph(train_dir / f"{sample_id}.geff")

        build_start = time.perf_counter()
        graph, _fallbacks, _telemetry = build_graph_cfar_sidelobe(
            sample_path=sample_path,
            threshold=float(v17_metadata["cfar_threshold"]),
            cfar_training_radius_voxels=tuple(v17_metadata["cfar_training_radius_voxels"]),
            cfar_guard_radius_voxels=tuple(v17_metadata["cfar_guard_radius_voxels"]),
            cfar_k_sigma=float(v17_metadata["cfar_k_sigma"]),
            sidelobe_radius_voxels=tuple(v17_metadata["sidelobe_radius_voxels"]),
            sidelobe_floor_ratio=float(v17_metadata["sidelobe_floor_ratio"]),
            max_detections_per_timepoint=(
                int(v17_metadata["max_detections_per_timepoint"])
                if v17_metadata["max_detections_per_timepoint"] is not None
                else None
            ),
            link_strategy=str(v17_metadata["cfar_link_strategy"]),
            max_link_distance_um=float(v17_metadata["cfar_max_link_distance_um"]),
            max_timepoints=int(v17_metadata["max_timepoints"]),
            kinematic_recovery_enabled=True,
            kinematic_recovery_settings=kinematic_settings,
            return_kinematic_telemetry=True,
        )
        build_elapsed_seconds = time.perf_counter() - build_start

        sparse_report = evaluate_sparse_ground_truth(graph, gt_graph, match_radius_um=7.0)
        quality_records.append(
            SampleQualityRecord(
                sample_id=sample_id,
                sparse_recall=sparse_report.sparse_recall,
                sparse_edge_recall=sparse_report.sparse_edge_recall,
                quality_score=_quality_score(sparse_report.sparse_recall, sparse_report.sparse_edge_recall),
                build_elapsed_seconds=float(build_elapsed_seconds),
            )
        )

        if sample_id not in sample_rows:
            continue

        detection_by_id = {detection.node_id: detection for detection in graph.detections}
        detections_by_t: dict[int, list[Any]] = {}
        for detection in graph.detections:
            detections_by_t.setdefault(int(detection.t), []).append(detection)
        predecessor_by_id = _build_predecessor_map(graph)
        _gt_to_pred, pred_to_gt = _match_maps(graph, gt_graph)

        for row in sample_rows[sample_id]:
            source_id = str(row["pred_source_off"])
            source_t = int(row["source_t"])
            source = detection_by_id.get(source_id)
            if source is None:
                shadow_records.append(
                    ShadowEdgeRecord(
                        sample_id=sample_id,
                        source_t=source_t,
                        source_id=source_id,
                        gt_source_id=int(row["gt_source_id"]),
                        gt_target_id=int(row["gt_target_id"]),
                        nearest_t_plus_1_distance_um_v16=(
                            float(row["nearest_t_plus_1_distance_um"])
                            if row.get("nearest_t_plus_1_distance_um") is not None
                            else None
                        ),
                        source_present_in_graph=False,
                        greedy_target_id=None,
                        global_target_id=None,
                        changed_decision=False,
                        used_second_step=False,
                        global_total_cost=None,
                        greedy_distance_um=None,
                        source_gt_id=None,
                        greedy_target_gt_id=None,
                        global_target_gt_id=None,
                        source_matches_gt_source=False,
                        greedy_correct=None,
                        global_correct=None,
                        shadow_outcome="both_wrong_or_unmapped",
                        shadow_elapsed_ms=0.0,
                    )
                )
                continue

            current_candidates = list(detections_by_t.get(int(source.t) + 1, []))
            future_candidates = list(detections_by_t.get(int(source.t) + 2, []))
            predecessor = predecessor_by_id.get(source.node_id)

            shadow_start = time.perf_counter()
            decision: GlobalWindowDecision = compare_greedy_vs_window_global(
                source=source,
                predecessor=predecessor,
                current_candidates=current_candidates,
                future_candidates=future_candidates,
                max_link_distance_um=float(v17_metadata["cfar_max_link_distance_um"]),
                link_strategy=str(v17_metadata["cfar_link_strategy"]),
                settings=window_settings,
            )
            shadow_elapsed_ms = (time.perf_counter() - shadow_start) * 1000.0

            gt_source_id = int(row["gt_source_id"])
            gt_target_id = int(row["gt_target_id"])
            source_gt_id = pred_to_gt.get(source.node_id)
            greedy_target_gt_id = pred_to_gt.get(decision.greedy_target_id) if decision.greedy_target_id is not None else None
            global_target_gt_id = pred_to_gt.get(decision.global_target_id) if decision.global_target_id is not None else None

            source_matches_gt = source_gt_id == gt_source_id
            greedy_correct = None if greedy_target_gt_id is None else bool(greedy_target_gt_id == gt_target_id)
            global_correct = None if global_target_gt_id is None else bool(global_target_gt_id == gt_target_id)

            shadow_records.append(
                ShadowEdgeRecord(
                    sample_id=sample_id,
                    source_t=source_t,
                    source_id=source_id,
                    gt_source_id=gt_source_id,
                    gt_target_id=gt_target_id,
                    nearest_t_plus_1_distance_um_v16=(
                        float(row["nearest_t_plus_1_distance_um"])
                        if row.get("nearest_t_plus_1_distance_um") is not None
                        else None
                    ),
                    source_present_in_graph=True,
                    greedy_target_id=decision.greedy_target_id,
                    global_target_id=decision.global_target_id,
                    changed_decision=decision.greedy_target_id != decision.global_target_id,
                    used_second_step=decision.used_second_step,
                    global_total_cost=decision.global_total_cost,
                    greedy_distance_um=decision.greedy_distance_um,
                    source_gt_id=source_gt_id,
                    greedy_target_gt_id=greedy_target_gt_id,
                    global_target_gt_id=global_target_gt_id,
                    source_matches_gt_source=bool(source_matches_gt),
                    greedy_correct=greedy_correct,
                    global_correct=global_correct,
                    shadow_outcome=_shadow_outcome(greedy_correct=greedy_correct, global_correct=global_correct),
                    shadow_elapsed_ms=float(shadow_elapsed_ms),
                )
            )

    at_risk_set = set(cohorts.at_risk_pfa_1e_03_51)
    outside_set = set(cohorts.outside_at_risk_15)

    decisions_routed = shadow_records
    decisions_at_risk = [item for item in shadow_records if item.sample_id in at_risk_set]
    decisions_outside = [item for item in shadow_records if item.sample_id in outside_set]

    decision_summaries = [
        _summarize_decisions(cohort=COHORT_ROUTED_66, records=decisions_routed),
        _summarize_decisions(cohort=COHORT_AT_RISK_51, records=decisions_at_risk),
        _summarize_decisions(cohort=COHORT_OUTSIDE_15, records=decisions_outside),
    ]

    build_times = [item.build_elapsed_seconds for item in quality_records]
    shadow_times = [item.shadow_elapsed_ms for item in shadow_records]

    output_payload = {
        "metadata": {
            "experiment": "v18_bounded_global_optimization_shadow",
            "objective": "bounded min-cost-flow-style short-window shadow scorer for known wrong-edge residuals",
            "target_sub_problem": "Type1_direct_edge_replaced_by_frame_skip residual subset from v16_diagnostic_root_cause.json",
            "precedent_basis": [
                "min-cost-flow and network-flow global association used by modern tracking systems including Ultrack-style formulations",
                "multi-hypothesis/global association literature in cell tracking",
                "published ant-colony lineage reconstruction as a mitosis-aware global-search precedent",
            ],
            "method_guardrail": "shadow only, no graph injection, no run.py or V13 default changes",
            "train_dir": str(train_dir),
            "scan_json": str(scan_json),
            "v16_diagnostic_json": str(v16_diagnostic_json),
            "v17_validate_json": str(v17_validate_json),
            "metric": "quality_score = 0.5*sparse_recall + 0.5*sparse_edge_recall",
            "window_settings": asdict(window_settings),
            "cohort_sizes": {
                COHORT_ROUTED_66: len(cohorts.routed_cfar_66),
                COHORT_AT_RISK_51: len(cohorts.at_risk_pfa_1e_03_51),
                COHORT_OUTSIDE_15: len(cohorts.outside_at_risk_15),
            },
            "known_problem_edges": len(target_rows),
        },
        "quality_score_means": {
            COHORT_ROUTED_66: _mean_quality(quality_records, set(cohorts.routed_cfar_66)),
            COHORT_AT_RISK_51: _mean_quality(quality_records, at_risk_set),
            COHORT_OUTSIDE_15: _mean_quality(quality_records, outside_set),
        },
        "decision_summaries": [asdict(item) for item in decision_summaries],
        "runtime": {
            "graph_build_total_seconds": float(sum(build_times)),
            "graph_build_mean_seconds": float(mean(build_times)) if build_times else 0.0,
            "shadow_eval_total_ms": float(sum(shadow_times)),
            "shadow_eval_mean_ms": float(mean(shadow_times)) if shadow_times else 0.0,
            "shadow_eval_max_ms": float(max(shadow_times)) if shadow_times else 0.0,
        },
        "global_vs_greedy_examples": [
            asdict(item)
            for item in sorted(
                [row for row in shadow_records if row.changed_decision],
                key=lambda row: (row.shadow_outcome != "global_better", row.sample_id, row.source_t),
            )[:25]
        ],
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with output_jsonl.open("w", encoding="utf-8") as handle:
        for row in shadow_records:
            handle.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "output_json": str(output_json),
                "output_jsonl": str(output_jsonl),
                "known_problem_edges": len(target_rows),
                "shadow_records": len(shadow_records),
                "changed_decisions": sum(1 for row in shadow_records if row.changed_decision),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
