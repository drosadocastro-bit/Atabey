from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import numpy as np

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.types import Detection, LineageGraph
from run_v21_division_recovery_shadow import _build_v19_prefirewall


@dataclass(frozen=True)
class PairingCase:
    case_id: str
    sample_id: str
    parent_id: str
    correct_child_1_id: str
    correct_child_2_id: str
    known_wrong_child_1_id: str | None
    known_wrong_child_2_id: str | None
    t: int
    context: str


KNOWN_CASES = {
    case.case_id: case
    for case in (
        PairingCase(
            case_id="V21-FN-EBDF-PAIRING",
            sample_id="6bba_ebdf3b34",
            parent_id="6bba_ebdf3b34:t13:cf520",
            correct_child_1_id="6bba_ebdf3b34:t14:cf601",
            correct_child_2_id="6bba_ebdf3b34:t14:cf555",
            known_wrong_child_1_id="6bba_ebdf3b34:t14:cf31",
            known_wrong_child_2_id="6bba_ebdf3b34:t14:cf601",
            t=13,
            context="The 9 um graph forms cf31+cf601 and leaves the matched GT daughter cf555 unlinked.",
        ),
        PairingCase(
            case_id="LINK-GATE-14-REGRESSION-05DB",
            sample_id="6bba_05db0fb1",
            parent_id="6bba_05db0fb1:t24:cf76",
            correct_child_1_id="6bba_05db0fb1:t25:cf17",
            correct_child_2_id="6bba_05db0fb1:t25:cf3",
            known_wrong_child_1_id="6bba_05db0fb1:t25:cf17",
            known_wrong_child_2_id="6bba_05db0fb1:t25:cf206",
            t=24,
            context="The 9 um graph forms cf17+cf3; a global 14 um gate replaced cf3 with cf206.",
        ),
        PairingCase(
            case_id="V19-TP-B329",
            sample_id="6bba_b329af44",
            parent_id="6bba_b329af44:t82:cf38",
            correct_child_1_id="6bba_b329af44:t83:cf298",
            correct_child_2_id="6bba_b329af44:t83:cf309",
            known_wrong_child_1_id=None,
            known_wrong_child_2_id=None,
            t=82,
            context="V19 formed the sparse-GT-matched pair; V20 later lost the branch upstream.",
        ),
        PairingCase(
            case_id="V19-TP-EBDF",
            sample_id="6bba_ebdf3b34",
            parent_id="6bba_ebdf3b34:t84:cf39",
            correct_child_1_id="6bba_ebdf3b34:t85:cf80",
            correct_child_2_id="6bba_ebdf3b34:t85:cf282",
            known_wrong_child_1_id=None,
            known_wrong_child_2_id=None,
            t=84,
            context="V19 formed the sparse-GT-matched pair; the strict V20 fallback ratio rejected it.",
        ),
    )
}


def _distance(left: Detection, right: Detection) -> float:
    return float(np.linalg.norm(np.array(left.position_um, dtype=float) - np.array(right.position_um, dtype=float)))


def _angle_between(left: np.ndarray, right: np.ndarray) -> float | None:
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm < 1e-9 or right_norm < 1e-9:
        return None
    cosine = float(np.dot(left, right) / (left_norm * right_norm))
    return float(math.degrees(math.acos(float(np.clip(cosine, -1.0, 1.0)))))


def _outgoing(graph: LineageGraph) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for edge in graph.edges:
        result.setdefault(edge.source_id, []).append(edge.target_id)
    for targets in result.values():
        targets.sort()
    return result


def _trace_existing_continuation(
    parent: Detection,
    child: Detection,
    *,
    nodes: dict[str, Detection],
    outgoing: dict[str, list[str]],
    horizon: int,
) -> list[Detection]:
    """Follow existing edges, choosing the most motion-consistent branch without mutating the graph."""
    path = [child]
    previous = parent
    current = child
    while len(path) < horizon:
        candidates = [
            nodes[target_id]
            for target_id in outgoing.get(current.node_id, [])
            if target_id in nodes and int(nodes[target_id].t) == int(current.t) + 1
        ]
        if not candidates:
            break
        previous_position = np.array(previous.position_um, dtype=float)
        current_position = np.array(current.position_um, dtype=float)
        prediction = current_position + (current_position - previous_position)
        current, previous = min(
            candidates,
            key=lambda candidate: (
                float(np.linalg.norm(np.array(candidate.position_um, dtype=float) - prediction)),
                _distance(current, candidate),
                candidate.node_id,
            ),
        ), current
        path.append(current)
    return path


def _prediction_errors(parent: Detection, path: list[Detection]) -> list[float]:
    errors: list[float] = []
    previous = parent
    for current, nxt in zip(path, path[1:]):
        previous_position = np.array(previous.position_um, dtype=float)
        current_position = np.array(current.position_um, dtype=float)
        prediction = current_position + (current_position - previous_position)
        errors.append(float(np.linalg.norm(np.array(nxt.position_um, dtype=float) - prediction)))
        previous = current
    return errors


def _pair_metrics(
    parent: Detection,
    child_1: Detection,
    child_2: Detection,
    *,
    nodes: dict[str, Detection],
    outgoing: dict[str, list[str]],
    horizon: int,
) -> dict[str, float | int | None]:
    path_1 = _trace_existing_continuation(parent, child_1, nodes=nodes, outgoing=outgoing, horizon=horizon)
    path_2 = _trace_existing_continuation(parent, child_2, nodes=nodes, outgoing=outgoing, horizon=horizon)
    prediction_errors = _prediction_errors(parent, path_1) + _prediction_errors(parent, path_2)

    axes: list[np.ndarray] = []
    separations: list[float] = []
    for left, right in zip(path_1, path_2):
        axis = np.array(left.position_um, dtype=float) - np.array(right.position_um, dtype=float)
        axes.append(axis)
        separations.append(float(np.linalg.norm(axis)))

    drifts: list[float] = []
    for previous_axis, current_axis in zip(axes, axes[1:]):
        angle = _angle_between(previous_axis, current_axis)
        if angle is not None:
            drifts.append(min(angle, 180.0 - angle))

    parent_position = np.array(parent.position_um, dtype=float)
    vector_1 = np.array(child_1.position_um, dtype=float) - parent_position
    vector_2 = np.array(child_2.position_um, dtype=float) - parent_position
    distance_1 = float(np.linalg.norm(vector_1))
    distance_2 = float(np.linalg.norm(vector_2))
    immediate_angle = _angle_between(vector_1, vector_2)
    distance_ratio = max(distance_1, distance_2) / max(min(distance_1, distance_2), 1e-9)
    coverage = (len(path_1) + len(path_2)) / float(2 * horizon)
    mean_error = float(np.mean(prediction_errors)) if prediction_errors else None
    max_error = float(max(prediction_errors)) if prediction_errors else None
    max_drift = float(max(drifts)) if drifts else None
    separation_growth = separations[-1] - separations[0] if len(separations) >= 2 else None
    min_separation = min(separations) if separations else 0.0

    return {
        "child_1_distance_um": distance_1,
        "child_2_distance_um": distance_2,
        "immediate_angle_deg": immediate_angle,
        "distance_ratio": distance_ratio,
        "initial_separation_um": separations[0],
        "final_separation_um": separations[-1],
        "separation_growth_um": separation_growth,
        "minimum_separation_um": min_separation,
        "branch_1_frames": len(path_1),
        "branch_2_frames": len(path_2),
        "coverage_ratio": coverage,
        "mean_prediction_error_um": mean_error,
        "max_prediction_error_um": max_error,
        "max_axis_drift_deg": max_drift,
    }


def _evidence_components(row: dict[str, object]) -> tuple[float, float, float, float]:
    coverage = float(row["coverage_ratio"])
    mean_error = row["mean_prediction_error_um"]
    max_drift = row["max_axis_drift_deg"]
    minimum_separation = float(row["minimum_separation_um"])
    smoothness = 1.0 / (1.0 + float(mean_error)) if mean_error is not None else 0.0
    axis_stability = 1.0 / (1.0 + float(max_drift) / 15.0) if max_drift is not None else 0.0
    noncollapse = minimum_separation / (minimum_separation + 2.0)
    return coverage, smoothness, axis_stability, noncollapse


def _add_scores_and_ranks(rows: list[dict[str, object]]) -> None:
    profiles = {
        "coverage_heavy": (0.60, 0.25, 0.10, 0.05),
        "balanced": (0.40, 0.30, 0.20, 0.10),
        "stability_heavy": (0.25, 0.20, 0.45, 0.10),
    }
    components = [_evidence_components(row) for row in rows]
    for row, values in zip(rows, components):
        row["coverage_component"] = values[0]
        row["smoothness_component"] = values[1]
        row["axis_stability_component"] = values[2]
        row["noncollapse_component"] = values[3]
        for name, weights in profiles.items():
            row[f"{name}_score"] = sum(weight * value for weight, value in zip(weights, values))

    for name in profiles:
        ordered = sorted(
            range(len(rows)),
            key=lambda index: (
                -float(rows[index][f"{name}_score"]),
                str(rows[index]["child_1_id"]),
                str(rows[index]["child_2_id"]),
            ),
        )
        for rank, index in enumerate(ordered, start=1):
            rows[index][f"{name}_rank"] = rank

    for index, values in enumerate(components):
        dominated_by = 0
        dominates = 0
        for other_index, other in enumerate(components):
            if index == other_index:
                continue
            if all(left >= right for left, right in zip(other, values)) and any(
                left > right for left, right in zip(other, values)
            ):
                dominated_by += 1
            if all(left >= right for left, right in zip(values, other)) and any(
                left > right for left, right in zip(values, other)
            ):
                dominates += 1
        rows[index]["pareto_dominated_by"] = dominated_by
        rows[index]["pareto_dominates"] = dominates
        rows[index]["pareto_front"] = dominated_by == 0


def _pair_key(left_id: str, right_id: str) -> tuple[str, str]:
    return tuple(sorted((left_id, right_id)))


def _edge_signature(graph: LineageGraph) -> tuple[tuple[str, str, float | None, str], ...]:
    return tuple((edge.source_id, edge.target_id, edge.confidence, edge.relation) for edge in graph.edges)


def audit_case(
    graph: LineageGraph,
    case: PairingCase,
    *,
    observation_radius_um: float,
    horizon: int,
) -> list[dict[str, object]]:
    nodes = {node.node_id: node for node in graph.detections}
    parent = nodes.get(case.parent_id)
    if parent is None:
        raise RuntimeError(f"{case.case_id}: parent {case.parent_id} is absent from the bounded graph")
    correct_ids = _pair_key(case.correct_child_1_id, case.correct_child_2_id)
    wrong_ids = (
        _pair_key(case.known_wrong_child_1_id, case.known_wrong_child_2_id)
        if case.known_wrong_child_1_id is not None and case.known_wrong_child_2_id is not None
        else None
    )
    for child_id in correct_ids + (wrong_ids or ()):
        if child_id not in nodes:
            raise RuntimeError(f"{case.case_id}: required child {child_id} is absent from the bounded graph")

    local_targets = [
        node
        for node in graph.detections
        if int(node.t) == int(parent.t) + 1 and _distance(parent, node) <= observation_radius_um
    ]
    local_by_id = {node.node_id: node for node in local_targets}
    for child_id in correct_ids:
        local_by_id[child_id] = nodes[child_id]

    # Matched controls hold one sparse-GT-matched daughter fixed and substitute one local alternative.
    pair_ids = {correct_ids}
    if wrong_ids is not None:
        pair_ids.add(wrong_ids)
    for fixed_id in correct_ids:
        for alternative_id in local_by_id:
            if alternative_id != fixed_id:
                pair_ids.add(_pair_key(fixed_id, alternative_id))

    outgoing = _outgoing(graph)
    formed_children = [
        target_id
        for target_id in outgoing.get(parent.node_id, [])
        if target_id in nodes and int(nodes[target_id].t) == int(parent.t) + 1
    ]
    formed_pairs = {_pair_key(*pair) for pair in combinations(formed_children, 2)}

    rows: list[dict[str, object]] = []
    for child_1_id, child_2_id in sorted(pair_ids):
        if child_1_id not in nodes or child_2_id not in nodes:
            continue
        metrics = _pair_metrics(
            parent,
            nodes[child_1_id],
            nodes[child_2_id],
            nodes=nodes,
            outgoing=outgoing,
            horizon=horizon,
        )
        rows.append(
            {
                "case_id": case.case_id,
                "sample_id": case.sample_id,
                "t": case.t,
                "parent_id": case.parent_id,
                "child_1_id": child_1_id,
                "child_2_id": child_2_id,
                "is_correct_pair": (child_1_id, child_2_id) == correct_ids,
                "is_known_wrong_pair": wrong_ids is not None and (child_1_id, child_2_id) == wrong_ids,
                "is_currently_formed_pair": (child_1_id, child_2_id) in formed_pairs,
                "inside_production_9um": max(
                    _distance(parent, nodes[child_1_id]), _distance(parent, nodes[child_2_id])
                ) <= 9.0,
                "observation_radius_um": observation_radius_um,
                "horizon_frames": horizon,
                **metrics,
            }
        )
    _add_scores_and_ranks(rows)
    return rows


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fmt(value: object, digits: int = 3) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _write_report(path: Path, cases: list[PairingCase], rows: list[dict[str, object]], zero_perturbation: dict[str, bool]) -> None:
    lines = [
        "# V21 Counterfactual Pairing Audit",
        "",
        "Date: 2026-07-21",
        "Branch: `mitosis_hough_audit`",
        "Status: shadow-only diagnostic; no graph, gate, Track A, or Track B change",
        "",
        "## Method",
        "",
        "For each known pairing failure, the audit holds one matched daughter fixed and substitutes nearby",
        "detections from `t+1` inside a diagnostic 14 um radius. It follows existing outgoing graph edges for",
        "four child frames and measures continuation coverage, constant-velocity prediction error, branch-axis",
        "stability, and non-collapse. The 14 um radius only observes alternatives; the production 9 um gate is",
        "unchanged.",
        "",
        "Three deliberately different score profiles are reported as sensitivity analysis. They are not",
        "probabilities or calibrated confidence. Pareto-front membership is also reported to avoid relying on",
        "one arbitrary weighting.",
        "",
        "## Results",
        "",
        "| Case | Pair | Correct | Current | Coverage | Mean error | Max drift | Growth | Balanced rank | Pareto front |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for case in cases:
        case_rows = [row for row in rows if row["case_id"] == case.case_id]
        selected = [row for row in case_rows if row["is_correct_pair"] or row["is_known_wrong_pair"]]
        for row in sorted(selected, key=lambda item: (not bool(item["is_correct_pair"]), str(item["child_1_id"]))):
            pair = f"`{str(row['child_1_id']).split(':')[-1]}+{str(row['child_2_id']).split(':')[-1]}`"
            lines.append(
                f"| `{case.case_id}` | {pair} | {row['is_correct_pair']} | {row['is_currently_formed_pair']} | "
                f"{_fmt(row['coverage_ratio'])} | {_fmt(row['mean_prediction_error_um'])} | "
                f"{_fmt(row['max_axis_drift_deg'])} | {_fmt(row['separation_growth_um'])} | "
                f"{row['balanced_rank']}/{len(case_rows)} | {row['pareto_front']} |"
            )

    lines.extend(["", "## Per-Case Interpretation", ""])
    for case in cases:
        case_rows = [row for row in rows if row["case_id"] == case.case_id]
        correct = next(row for row in case_rows if row["is_correct_pair"])
        wrong = next((row for row in case_rows if row["is_known_wrong_pair"]), None)
        details = [
            f"### {case.case_id}",
            "",
            case.context,
            "",
            f"- Alternatives evaluated: `{len(case_rows)}` matched substitution pairs.",
        ]
        if wrong is not None:
            robust_wins = sum(
                int(correct[f"{name}_rank"] < wrong[f"{name}_rank"])
                for name in ("coverage_heavy", "balanced", "stability_heavy")
            )
            details.extend(
                [
                    f"- Correct pair beats the known wrong pair in `{robust_wins}/3` score profiles.",
                    f"- Wrong ranks: coverage `{wrong['coverage_heavy_rank']}`, balanced `{wrong['balanced_rank']}`, stability `{wrong['stability_heavy_rank']}`.",
                    f"- Wrong Pareto front: `{wrong['pareto_front']}`.",
                ]
            )
        details.extend(
            [
                f"- Correct ranks: coverage `{correct['coverage_heavy_rank']}`, balanced `{correct['balanced_rank']}`, stability `{correct['stability_heavy_rank']}`.",
                f"- Correct Pareto front: `{correct['pareto_front']}`.",
                f"- Graph zero perturbation: `{zero_perturbation[case.sample_id]}`.",
                "",
            ]
        )
        lines.extend(details)

    correct_rows = [row for row in rows if row["is_correct_pair"]]
    known_wrong_cases = [
        case for case in cases if any(row["case_id"] == case.case_id and row["is_known_wrong_pair"] for row in rows)
    ]
    pairwise_profile_wins = 0
    for case in known_wrong_cases:
        case_rows = [row for row in rows if row["case_id"] == case.case_id]
        correct = next(row for row in case_rows if row["is_correct_pair"])
        wrong = next(row for row in case_rows if row["is_known_wrong_pair"])
        if all(
            int(correct[f"{name}_rank"]) < int(wrong[f"{name}_rank"])
            for name in ("coverage_heavy", "balanced", "stability_heavy")
        ):
            pairwise_profile_wins += 1
    top_5 = sum(int(row["balanced_rank"]) <= 5 for row in correct_rows)
    top_10 = sum(int(row["balanced_rank"]) <= 10 for row in correct_rows)
    pareto = sum(bool(row["pareto_front"]) for row in correct_rows)
    rank_summary = ", ".join(
        f"{row['balanced_rank']}/{sum(other['case_id'] == row['case_id'] for other in rows)}"
        for row in correct_rows
    )
    lines.extend(
        [
            "## Aggregate Finding",
            "",
            f"- Correct-pair balanced ranks: `{rank_summary}`.",
            f"- Correct pairs in the top 5: `{top_5}/{len(correct_rows)}`; top 10: `{top_10}/{len(correct_rows)}`.",
            f"- Correct pairs on the Pareto front: `{pareto}/{len(correct_rows)}`.",
            f"- Correct pair beat the specifically known wrong pair under all three profiles in `{pairwise_profile_wins}/{len(known_wrong_cases)}` applicable cases.",
            f"- Zero perturbation held for `{sum(zero_perturbation.values())}/{len(zero_perturbation)}` rebuilt samples.",
            "",
            "## GO/NO-GO Assessment",
            "",
            "**NO-GO as an active daughter-pair selector. Partial positive evidence as a diagnostic signal.**",
            "",
            "The future-continuation evidence consistently demoted the two known wrong pairings, but it did not",
            "surface any correct pair in the top five and placed only half of the correct pairs on the Pareto front.",
            "Nearby detections belonging to other smooth tracks often produced better continuation evidence. This",
            "shows that individual daughter persistence and smoothness do not establish shared parentage.",
            "",
            "A further pairing study would need an independent parent-centered signal, not another weighting of the",
            "same daughter-continuation features. Possible evidence includes predecessor-conditioned split symmetry,",
            "explicit local assignment competition, or validated appearance conservation. None is authorized here.",
            "",
        ]
    )

    lines.extend(
        [
            "## Decision Rule",
            "",
            "A future pairing mechanism is a GO candidate only if the correct pair consistently outranks the known",
            "wrong pair across the scoring profiles, remains competitive against matched local controls, and the",
            "same evidence does not elevate collision controls. Otherwise the short-horizon idea is insufficient",
            "or requires a different evidence source.",
            "",
            "This audit does not authorize graph mutation or parameter tuning.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the V21 shadow-only counterfactual daughter-pair audit.")
    parser.add_argument("--case-ids", nargs="+", choices=sorted(KNOWN_CASES), default=list(KNOWN_CASES))
    parser.add_argument("--horizon", type=int, default=4)
    parser.add_argument("--observation-radius-um", type=float, default=14.0)
    parser.add_argument("--output", type=Path, default=Path("v21_counterfactual_pairing_audit.csv"))
    parser.add_argument("--report", type=Path, default=Path("V21_COUNTERFACTUAL_PAIRING_AUDIT.md"))
    args = parser.parse_args()
    if args.horizon < 2:
        parser.error("--horizon must be at least 2")

    cases = [KNOWN_CASES[case_id] for case_id in args.case_ids]
    rows: list[dict[str, object]] = []
    zero_perturbation: dict[str, bool] = {}
    for sample_id in sorted({case.sample_id for case in cases}):
        sample_cases = [case for case in cases if case.sample_id == sample_id]
        max_timepoints = max(case.t + args.horizon + 1 for case in sample_cases)
        print(f"Building {sample_id} through {max_timepoints} timepoints...", flush=True)
        graph = _build_v19_prefirewall(project_root / "train" / f"{sample_id}.zarr", max_timepoints)
        before = _edge_signature(graph)
        for case in sample_cases:
            case_rows = audit_case(
                graph,
                case,
                observation_radius_um=float(args.observation_radius_um),
                horizon=int(args.horizon),
            )
            rows.extend(case_rows)
            correct = next(row for row in case_rows if row["is_correct_pair"])
            wrong = next((row for row in case_rows if row["is_known_wrong_pair"]), None)
            wrong_text = f" wrong_rank={wrong['balanced_rank']}" if wrong is not None else ""
            print(
                f"  {case.case_id}: pairs={len(case_rows)} "
                f"correct_rank={correct['balanced_rank']}{wrong_text}",
                flush=True,
            )
        zero_perturbation[sample_id] = before == _edge_signature(graph)
        if not zero_perturbation[sample_id]:
            raise RuntimeError(f"{sample_id}: audit mutated graph edges")

    _write_csv(args.output, rows)
    _write_report(args.report, cases, rows, zero_perturbation)
    print(f"Wrote {args.output} and {args.report}", flush=True)


if __name__ == "__main__":
    main()
