from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from atabey.tracking.joint_semantic_shadow import (
    evidence_as_row,
    extract_joint_semantic_evidence,
    label_division_action_official,
)
from atabey.types import LineageGraph
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route
from run_v21_local_assignment_shadow import CASES, ValidationCase, _matched_ids


@dataclass(frozen=True)
class CaseSummary:
    case_id: str
    phase: str
    sample_id: str
    parent_id: str
    correct_child_1_id: str
    correct_child_2_id: str
    source_detector: str
    source_link_strategy: str
    action_count: int
    divide_count: int
    correct_pair_representable: bool
    correct_pair_official_label: str
    source_zero_perturbation: bool


def _graph_signature(graph: LineageGraph) -> tuple[tuple[object, ...], tuple[object, ...]]:
    detections = tuple(
        (
            node.node_id,
            node.sample_id,
            node.t,
            node.z,
            node.y,
            node.x,
            node.z_um,
            node.y_um,
            node.x_um,
            node.intensity_mean,
            node.intensity_max,
            node.component_volume,
            node.detection_confidence,
        )
        for node in graph.detections
    )
    edges = tuple(
        (edge.source_id, edge.target_id, edge.confidence, edge.relation)
        for edge in graph.edges
    )
    return detections, edges


def _correct_pair(row, child_1_id: str, child_2_id: str) -> bool:
    return row.action_type == "divide" and {
        row.child_1_id,
        row.child_2_id,
    } == {child_1_id, child_2_id}


def _write_report(path: Path, summaries: list[CaseSummary]) -> None:
    represented = sum(row.correct_pair_representable for row in summaries)
    official_tp = sum(row.correct_pair_official_label == "official_tp" for row in summaries)
    official_fp = sum(row.correct_pair_official_label == "official_fp" for row in summaries)
    zero_perturbation = sum(row.source_zero_perturbation for row in summaries)
    action_count = sum(row.action_count for row in summaries)
    divide_count = sum(row.divide_count for row in summaries)
    original_tp_cases = {"P1-05DB", "P1-B329", "P1-EBDF-EARLY", "P1-EBDF-LATE"}
    original_tp_preserved = sum(
        row.case_id in original_tp_cases and row.correct_pair_official_label == "official_tp"
        for row in summaries
    )
    hungarian_regressions = {"P2-12DF", "P2-2A2E", "P2-4FFD"}
    regression_cases_visible = sum(
        row.case_id in hungarian_regressions and row.correct_pair_representable
        for row in summaries
    )
    lines = [
        "# V21 Joint Semantic Phase 0 Fixed-Battery Audit",
        "",
        "Status: shadow evidence extraction only; no semantic score, assignment solve, or graph mutation",
        "",
        "## Contract",
        "",
        "The extractor enumerates continuation, division, termination, and abstention actions around",
        "the registered focal parents. It records raw parent-centered geometry, daughter continuity,",
        "appearance/mass diagnostics, feature availability, and missingness reasons. Every action",
        "abstains. Only each registered correct pair is projected through the patched official scorer;",
        "all other sparse candidates remain unlabeled rather than being treated as negatives.",
        "",
        "## Results",
        "",
        f"- Raw evidence rows: **{action_count}** total, including **{divide_count}** division actions.",
        f"- Registered correct pairs representable inside 14 um: **{represented}/{len(summaries)}**.",
        f"- Registered correct pairs labeled official TP in current ownership context: **{official_tp}/{len(summaries)}**.",
        f"- Registered correct pairs labeled official FP in current ownership context: **{official_fp}/{len(summaries)}**.",
        f"- Original official V19 TPs preserved: **{original_tp_preserved}/4**.",
        f"- Prior Hungarian regression cases representable and still abstaining: **{regression_cases_visible}/3**.",
        f"- Source zero perturbation: **{zero_perturbation}/{len(summaries)}**.",
        "",
        "| Case | Phase | Route | Actions | Division actions | Correct representable | Official projected label | Zero perturbation |",
        "|---|---|---|---:|---:|---:|---|---:|",
    ]
    for row in summaries:
        lines.append(
            f"| `{row.case_id}` | `{row.phase}` | `{row.source_detector}/{row.source_link_strategy}` | "
            f"{row.action_count} | {row.divide_count} | "
            f"{row.correct_pair_representable} | `{row.correct_pair_official_label}` | "
            f"{row.source_zero_perturbation} |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "A registered sparse pair and an official TP are not interchangeable labels. The projected",
            "official result includes current local ownership and topology, so an `official_fp` here",
            "does not prove that the biological pair is false. It proves that forming that fork alone",
            "does not satisfy the patched competition metric in the current graph context.",
            "",
            "This audit does not fit a model and cannot establish calibrated confidence. An official FP",
            "label is not inferred from absence in sparse GT. Assignment remains disabled until semantic",
            "evidence passes its own registered gate.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _selected_cases(case_ids: list[str] | None) -> list[ValidationCase]:
    if not case_ids:
        return list(CASES)
    by_id = {case.case_id: case for case in CASES}
    unknown = [case_id for case_id in case_ids if case_id not in by_id]
    if unknown:
        raise ValueError(f"Unknown case IDs: {unknown}")
    return [by_id[case_id] for case_id in case_ids]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract unscored V21 joint semantic evidence on the fixed 14-case battery."
    )
    parser.add_argument("--case-ids", nargs="*", default=None)
    parser.add_argument("--formation-radius-um", type=float, default=14.0)
    parser.add_argument("--continuity-horizon", type=int, default=2)
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "v21_joint_semantic_phase0_fixed14.csv",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=project_root / "V21_JOINT_SEMANTIC_PHASE0_AUDIT.md",
    )
    args = parser.parse_args()

    selected = _selected_cases(args.case_ids)
    evidence_rows: list[dict[str, object]] = []
    summaries: list[CaseSummary] = []
    for sample_index, sample_id in enumerate(
        sorted({case.sample_id for case in selected}),
        start=1,
    ):
        sample_cases = [case for case in selected if case.sample_id == sample_id]
        max_timepoints = max(
            case.t + args.continuity_horizon + 3
            for case in sample_cases
        )
        print(
            f"[{sample_index}/{len({case.sample_id for case in selected})}] "
            f"{sample_id} through {max_timepoints} timepoints",
            flush=True,
        )
        graph, source_detector, source_link_strategy = _build_v19_prefirewall_with_route(
            project_root / "train" / f"{sample_id}.zarr",
            max_timepoints=max_timepoints,
        )
        ground_truth = read_geff_graph(project_root / "train" / f"{sample_id}.geff")
        sample_before = _graph_signature(graph)

        for case in sample_cases:
            parent_id, child_1_id, child_2_id = _matched_ids(
                graph,
                sample_id,
                (case.gt_parent_id, case.gt_child_1_id, case.gt_child_2_id),
            )
            case_before = _graph_signature(graph)
            shadow = extract_joint_semantic_evidence(
                graph,
                parent_ids=[parent_id],
                formation_radius_um=args.formation_radius_um,
                continuity_horizon=args.continuity_horizon,
            )
            correct = [
                row
                for row in shadow.evidence
                if _correct_pair(row, child_1_id, child_2_id)
            ]
            if len(correct) > 1:
                raise RuntimeError(f"{case.case_id}: duplicate registered correct action")
            labeled_correct = (
                label_division_action_official(correct[0], graph, ground_truth)
                if correct
                else None
            )

            for evidence in shadow.evidence:
                output_evidence = (
                    labeled_correct
                    if labeled_correct is not None
                    and _correct_pair(evidence, child_1_id, child_2_id)
                    else evidence
                )
                evidence_rows.append(
                    {
                        "case_id": case.case_id,
                        "phase": case.phase,
                        "registered_gt_parent_id": case.gt_parent_id,
                        "registered_gt_child_1_id": case.gt_child_1_id,
                        "registered_gt_child_2_id": case.gt_child_2_id,
                        "registered_correct_action": _correct_pair(
                            evidence,
                            child_1_id,
                            child_2_id,
                        ),
                        "source_detector": source_detector,
                        "source_link_strategy": source_link_strategy,
                        **evidence_as_row(output_evidence),
                    }
                )

            zero_perturbation = case_before == _graph_signature(graph)
            summaries.append(
                CaseSummary(
                    case_id=case.case_id,
                    phase=case.phase,
                    sample_id=sample_id,
                    parent_id=parent_id,
                    correct_child_1_id=child_1_id,
                    correct_child_2_id=child_2_id,
                    source_detector=source_detector,
                    source_link_strategy=source_link_strategy,
                    action_count=shadow.action_count,
                    divide_count=shadow.divide_count,
                    correct_pair_representable=bool(correct),
                    correct_pair_official_label=(
                        labeled_correct.official_label
                        if labeled_correct is not None
                        else "candidate_absent"
                    ),
                    source_zero_perturbation=zero_perturbation,
                )
            )
            print(
                f"  {case.case_id}: route={source_detector}/{source_link_strategy} "
                f"actions={shadow.action_count} "
                f"divide={shadow.divide_count} representable={bool(correct)} "
                f"official={summaries[-1].correct_pair_official_label} "
                f"zero_perturb={zero_perturbation}",
                flush=True,
            )

        if sample_before != _graph_signature(graph):
            raise RuntimeError(f"{sample_id}: semantic shadow mutated the source graph")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(evidence_rows[0]))
        writer.writeheader()
        writer.writerows(evidence_rows)
    _write_report(args.report, summaries)
    print(f"Wrote {args.output} and {args.report}", flush=True)


if __name__ == "__main__":
    main()
