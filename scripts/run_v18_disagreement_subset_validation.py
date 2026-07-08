from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from atabey.evaluation.sparse_ground_truth import match_sparse_centroids
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
class DisagreementShadowRecord:
    sample_id: str
    source_id: str
    frame_t: int
    source_present_in_graph: bool
    expected_gt_source_id: int | None
    expected_gt_target_id: int | None
    expected_target_from: str | None
    singleton_has_direct_candidate: bool
    full_context_has_direct_candidate: bool
    source_neighbors_within_radius: int
    greedy_target_id: str | None
    global_target_id: str | None
    changed_decision: bool
    used_second_step: bool
    shadow_elapsed_ms: float
    source_gt_id: int | None
    greedy_target_gt_id: int | None
    global_target_gt_id: int | None
    greedy_correct: bool | None
    global_correct: bool | None
    shadow_outcome: str


@dataclass(frozen=True)
class DecisionSummary:
    cohort: str
    disagreement_records: int
    source_missing: int
    evaluable_records: int
    changed_decisions: int
    used_second_step: int
    global_better: int
    greedy_better: int
    both_correct: int
    both_wrong: int
    unmapped_or_unevaluable: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V18 disagreement-first shadow accuracy validation under strict 3-frame bounded window.")
    parser.add_argument("--train-dir", default="train", help="Directory containing train .zarr/.geff sample pairs.")
    parser.add_argument("--scan-json", default="submissions/cfar_bounded_scan_fulltrain.json", help="CFAR cohort split artifact.")
    parser.add_argument("--v17-gate-trace-json", default="submissions/v17_gate_trace_audit.json", help="V17 gate disagreement artifact.")
    parser.add_argument("--v17-validate-json", default="submissions/v17_hard_exclusion_validate.json", help="V17 validation artifact with detector/link settings.")
    parser.add_argument("--cohort", choices=["routed", "at_risk", "outside"], default="at_risk")
    parser.add_argument("--sample-limit", type=int, default=0, help="Optional max samples from the selected cohort (0 means all).")
    parser.add_argument("--output-json", default="submissions/v18_disagreement_subset_validate.json")
    parser.add_argument("--output-jsonl", default="submissions/v18_disagreement_subset_records.jsonl")
    parser.add_argument("--first-step-prediction-weight", type=float, default=1.0)
    parser.add_argument("--first-step-distance-weight", type=float, default=0.4)
    parser.add_argument("--second-step-prediction-weight", type=float, default=1.0)
    parser.add_argument("--second-step-distance-weight", type=float, default=0.3)
    parser.add_argument("--terminal-without-second-step-penalty", type=float, default=1.2)
    return parser.parse_args()


def _cohort_sample_ids(*, cohort: str, cohorts: Any) -> list[str]:
    if cohort == "routed":
        return list(cohorts.routed_cfar_66)
    if cohort == "at_risk":
        return list(cohorts.at_risk_pfa_1e_03_51)
    return list(cohorts.outside_at_risk_15)


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


def _build_gt_outgoing_index(train_dir: Path, sample_ids: list[str]) -> dict[str, dict[int, list[tuple[int, int]]]]:
    index: dict[str, dict[int, list[tuple[int, int]]]] = {}
    for sample_id in sample_ids:
        gt_graph = read_geff_graph(train_dir / f"{sample_id}.geff")
        t_by_node = {int(node.node_id): int(node.t) for node in gt_graph.nodes}
        outgoing: dict[int, list[tuple[int, int]]] = {}
        for source_id_raw, target_id_raw in gt_graph.edges:
            source_id = int(source_id_raw)
            target_id = int(target_id_raw)
            outgoing.setdefault(source_id, []).append((t_by_node.get(target_id, -1), target_id))
        index[sample_id] = outgoing
    return index


def _match_maps(graph, gt_graph) -> tuple[dict[int, str], dict[str, int]]:
    rows = [
        row
        for row in match_sparse_centroids(graph, gt_graph, radius_um=7.0)
        if row.matched and row.prediction_node_id is not None
    ]
    gt_to_pred = {int(row.ground_truth_node_id): str(row.prediction_node_id) for row in rows}
    pred_to_gt = {str(row.prediction_node_id): int(row.ground_truth_node_id) for row in rows}
    return gt_to_pred, pred_to_gt


def _resolve_expected_gt_target(
    *,
    record: dict[str, Any],
    source_gt_id: int | None,
    gt_outgoing: dict[int, list[tuple[int, int]]],
) -> tuple[int | None, int | None, str | None]:
    if record.get("gt_source_id") is not None and record.get("gt_target_id") is not None:
        return int(record["gt_source_id"]), int(record["gt_target_id"]), "gate_trace"

    if source_gt_id is None:
        return None, None, None

    outgoing = gt_outgoing.get(int(source_gt_id), [])
    if not outgoing:
        return int(source_gt_id), None, None

    frame_t = int(record["frame_t"])
    adjacent = [edge for edge in outgoing if int(edge[0]) == frame_t + 1]
    if adjacent:
        return int(source_gt_id), int(adjacent[0][1]), "pred_to_gt_adjacent"
    return int(source_gt_id), int(outgoing[0][1]), "pred_to_gt_first_outgoing"


def _shadow_outcome(*, greedy_correct: bool | None, global_correct: bool | None) -> str:
    if global_correct is True and greedy_correct is not True:
        return "global_better"
    if greedy_correct is True and global_correct is not True:
        return "greedy_better"
    if greedy_correct is True and global_correct is True:
        return "both_correct"
    if greedy_correct is False and global_correct is False:
        return "both_wrong"
    return "unmapped_or_unevaluable"


def _summarize(*, cohort: str, records: list[DisagreementShadowRecord]) -> DecisionSummary:
    return DecisionSummary(
        cohort=cohort,
        disagreement_records=len(records),
        source_missing=sum(1 for item in records if not item.source_present_in_graph),
        evaluable_records=sum(1 for item in records if item.expected_gt_target_id is not None),
        changed_decisions=sum(1 for item in records if item.changed_decision),
        used_second_step=sum(1 for item in records if item.used_second_step),
        global_better=sum(1 for item in records if item.shadow_outcome == "global_better"),
        greedy_better=sum(1 for item in records if item.shadow_outcome == "greedy_better"),
        both_correct=sum(1 for item in records if item.shadow_outcome == "both_correct"),
        both_wrong=sum(1 for item in records if item.shadow_outcome == "both_wrong"),
        unmapped_or_unevaluable=sum(1 for item in records if item.shadow_outcome == "unmapped_or_unevaluable"),
    )


def main() -> None:
    args = _parse_args()
    train_dir = Path(args.train_dir)
    scan_json = Path(args.scan_json)
    v17_gate_trace_json = Path(args.v17_gate_trace_json)
    v17_validate_json = Path(args.v17_validate_json)
    output_json = Path(args.output_json)
    output_jsonl = Path(args.output_jsonl)

    cohorts = load_cfar_validation_cohorts(scan_json)
    validate_expected_cohort_sizes(cohorts)

    selected_samples = _cohort_sample_ids(cohort=args.cohort, cohorts=cohorts)
    if int(args.sample_limit) > 0:
        selected_samples = selected_samples[: int(args.sample_limit)]
    selected_sample_set = set(selected_samples)

    gate_trace_payload = json.loads(v17_gate_trace_json.read_text(encoding="utf-8"))
    v17_payload = json.loads(v17_validate_json.read_text(encoding="utf-8"))

    all_disagreements = [
        row
        for row in gate_trace_payload.get("disagreement_outcomes", [])
        if str(row["sample_id"]) in selected_sample_set
    ]
    disagreements_by_sample: dict[str, list[dict[str, Any]]] = {}
    for row in all_disagreements:
        disagreements_by_sample.setdefault(str(row["sample_id"]), []).append(dict(row))

    v17_metadata = dict(v17_payload["metadata"])
    kinematic_settings = KinematicRecoverySettings(**v17_metadata["kinematic_recovery_settings"])
    window_settings = GlobalWindowSettings(
        first_step_prediction_weight=float(args.first_step_prediction_weight),
        first_step_distance_weight=float(args.first_step_distance_weight),
        second_step_prediction_weight=float(args.second_step_prediction_weight),
        second_step_distance_weight=float(args.second_step_distance_weight),
        terminal_without_second_step_penalty=float(args.terminal_without_second_step_penalty),
    )

    gt_outgoing_index = _build_gt_outgoing_index(train_dir, sorted(disagreements_by_sample.keys()))

    records: list[DisagreementShadowRecord] = []
    graph_build_times: list[float] = []
    shadow_times_ms: list[float] = []

    sample_sequence = [sample_id for sample_id in selected_samples if sample_id in disagreements_by_sample]
    for idx, sample_id in enumerate(sample_sequence, start=1):
        print(f"[v18-disagree {idx}/{len(sample_sequence)}] sample={sample_id}", flush=True)
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
        graph_build_times.append(float(time.perf_counter() - build_start))

        detection_by_id = {detection.node_id: detection for detection in graph.detections}
        detections_by_t: dict[int, list[Any]] = {}
        for detection in graph.detections:
            detections_by_t.setdefault(int(detection.t), []).append(detection)
        predecessor_by_id = _build_predecessor_map(graph)
        _gt_to_pred, pred_to_gt = _match_maps(graph, gt_graph)
        gt_outgoing = gt_outgoing_index.get(sample_id, {})

        for row in disagreements_by_sample[sample_id]:
            source_id = str(row["source_id"])
            source = detection_by_id.get(source_id)
            if source is None:
                records.append(
                    DisagreementShadowRecord(
                        sample_id=sample_id,
                        source_id=source_id,
                        frame_t=int(row["frame_t"]),
                        source_present_in_graph=False,
                        expected_gt_source_id=(int(row["gt_source_id"]) if row.get("gt_source_id") is not None else None),
                        expected_gt_target_id=(int(row["gt_target_id"]) if row.get("gt_target_id") is not None else None),
                        expected_target_from=("gate_trace" if row.get("gt_target_id") is not None else None),
                        singleton_has_direct_candidate=bool(row.get("singleton_has_direct_candidate", False)),
                        full_context_has_direct_candidate=bool(row.get("full_context_has_direct_candidate", False)),
                        source_neighbors_within_radius=int(row.get("source_neighbors_within_radius", 0)),
                        greedy_target_id=None,
                        global_target_id=None,
                        changed_decision=False,
                        used_second_step=False,
                        shadow_elapsed_ms=0.0,
                        source_gt_id=None,
                        greedy_target_gt_id=None,
                        global_target_gt_id=None,
                        greedy_correct=None,
                        global_correct=None,
                        shadow_outcome="unmapped_or_unevaluable",
                    )
                )
                continue

            source_gt_id = pred_to_gt.get(source_id)
            expected_gt_source_id, expected_gt_target_id, expected_target_from = _resolve_expected_gt_target(
                record=row,
                source_gt_id=source_gt_id,
                gt_outgoing=gt_outgoing,
            )

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
            shadow_times_ms.append(float(shadow_elapsed_ms))

            greedy_target_gt_id = pred_to_gt.get(decision.greedy_target_id) if decision.greedy_target_id is not None else None
            global_target_gt_id = pred_to_gt.get(decision.global_target_id) if decision.global_target_id is not None else None
            greedy_correct = (
                bool(greedy_target_gt_id == expected_gt_target_id) if expected_gt_target_id is not None and greedy_target_gt_id is not None else None
            )
            global_correct = (
                bool(global_target_gt_id == expected_gt_target_id) if expected_gt_target_id is not None and global_target_gt_id is not None else None
            )

            records.append(
                DisagreementShadowRecord(
                    sample_id=sample_id,
                    source_id=source_id,
                    frame_t=int(row["frame_t"]),
                    source_present_in_graph=True,
                    expected_gt_source_id=expected_gt_source_id,
                    expected_gt_target_id=expected_gt_target_id,
                    expected_target_from=expected_target_from,
                    singleton_has_direct_candidate=bool(row.get("singleton_has_direct_candidate", False)),
                    full_context_has_direct_candidate=bool(row.get("full_context_has_direct_candidate", False)),
                    source_neighbors_within_radius=int(row.get("source_neighbors_within_radius", 0)),
                    greedy_target_id=decision.greedy_target_id,
                    global_target_id=decision.global_target_id,
                    changed_decision=decision.greedy_target_id != decision.global_target_id,
                    used_second_step=bool(decision.used_second_step),
                    shadow_elapsed_ms=float(shadow_elapsed_ms),
                    source_gt_id=source_gt_id,
                    greedy_target_gt_id=greedy_target_gt_id,
                    global_target_gt_id=global_target_gt_id,
                    greedy_correct=greedy_correct,
                    global_correct=global_correct,
                    shadow_outcome=_shadow_outcome(greedy_correct=greedy_correct, global_correct=global_correct),
                )
            )

    summary = _summarize(cohort=args.cohort, records=records)

    output_payload = {
        "metadata": {
            "experiment": "v18_disagreement_first_shadow_validation",
            "objective": "disagreement-first bounded global optimization shadow check (3-frame) with graph reuse per sample",
            "cohort": args.cohort,
            "selected_samples": selected_samples,
            "disagreement_samples": sample_sequence,
            "disagreement_records_input": len(all_disagreements),
            "window": "3-frame strict bounded window (t,t+1,t+2)",
            "method_guardrail": "shadow only, no graph injection, no run.py or V13 default changes",
            "scan_json": str(scan_json),
            "v17_gate_trace_json": str(v17_gate_trace_json),
            "v17_validate_json": str(v17_validate_json),
            "cohort_sizes": {
                COHORT_ROUTED_66: len(cohorts.routed_cfar_66),
                COHORT_AT_RISK_51: len(cohorts.at_risk_pfa_1e_03_51),
                COHORT_OUTSIDE_15: len(cohorts.outside_at_risk_15),
            },
            "window_settings": asdict(window_settings),
        },
        "decision_summary": asdict(summary),
        "runtime": {
            "graph_build_total_seconds": float(sum(graph_build_times)),
            "graph_build_mean_seconds": float(mean(graph_build_times)) if graph_build_times else 0.0,
            "shadow_eval_total_ms": float(sum(shadow_times_ms)),
            "shadow_eval_mean_ms": float(mean(shadow_times_ms)) if shadow_times_ms else 0.0,
            "shadow_eval_max_ms": float(max(shadow_times_ms)) if shadow_times_ms else 0.0,
        },
        "examples": [
            asdict(item)
            for item in sorted(
                records,
                key=lambda row: (
                    row.shadow_outcome != "global_better",
                    not row.changed_decision,
                    row.sample_id,
                    row.frame_t,
                ),
            )[:30]
        ],
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with output_jsonl.open("w", encoding="utf-8") as handle:
        for row in records:
            handle.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "output_json": str(output_json),
                "output_jsonl": str(output_jsonl),
                "records": len(records),
                "changed_decisions": sum(1 for row in records if row.changed_decision),
                "global_better": sum(1 for row in records if row.shadow_outcome == "global_better"),
                "greedy_better": sum(1 for row in records if row.shadow_outcome == "greedy_better"),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
