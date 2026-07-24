from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from atabey.tracking.unet_action_availability import (
    UnetShadowPeak,
    action_matches_registered_division,
    enumerate_anchored_division_actions,
    evaluate_action_as_official_fork,
)
from atabey.types import LineageGraph
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route


def _graph_signature(graph: LineageGraph) -> tuple[tuple[object, ...], tuple[object, ...]]:
    detections = tuple(
        (
            node.node_id,
            node.sample_id,
            node.t,
            node.z_um,
            node.y_um,
            node.x_um,
            node.detection_confidence,
        )
        for node in graph.detections
    )
    edges = tuple(
        (edge.source_id, edge.target_id, edge.confidence, edge.relation)
        for edge in graph.edges
    )
    return detections, edges


def _read_peaks(path: Path) -> dict[str, list[UnetShadowPeak]]:
    by_sample: dict[str, list[UnetShadowPeak]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            confidence = row.get("confidence", "")
            peak = UnetShadowPeak(
                peak_id=row["peak_id"],
                sample_id=row["sample_id"],
                t=int(row["t"]),
                z_um=float(row["z_um"]),
                y_um=float(row["y_um"]),
                x_um=float(row["x_um"]),
                confidence=float(confidence) if confidence not in {"", None} else None,
            )
            by_sample[peak.sample_id].append(peak)
    for peaks in by_sample.values():
        peaks.sort(key=lambda peak: (peak.t, peak.peak_id))
    return dict(by_sample)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _summarize(
    rows: list[dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, Any]:
    positives = [row for row in rows if bool(row["official_positive_available"])]
    controls = [row for row in rows if row["cohort"] == "positive_control"]
    preserved = [row for row in controls if bool(row["official_positive_available"])]
    families = sorted({row["sample_id"].split("_", 1)[0] for row in positives})
    zero_perturbation = all(bool(row["source_zero_perturbation"]) for row in rows)
    decision_contract = contract["decision_contract"]
    gates = {
        "complete": len(rows) == int(contract["expected_cases"]),
        "official_positive_count": len(positives)
        >= int(decision_contract["minimum_official_positive_divisions"]),
        "positive_controls": len(preserved)
        >= int(decision_contract["minimum_positive_controls_preserved"]),
        "families": families
        == sorted(decision_contract["required_official_positive_families"]),
        "zero_perturbation": zero_perturbation,
        "shadow_only": (
            not bool(contract["semantic_scoring_enabled"])
            and not bool(contract["assignment_enabled"])
            and not bool(contract["graph_mutation_enabled"])
        ),
    }
    return {
        "decision": "GO_FOR_SEMANTIC_SCORE_DEVELOPMENT" if all(gates.values()) else "NO_GO",
        "cases": len(rows),
        "samples": len({row["sample_id"] for row in rows}),
        "official_positive_divisions": len(positives),
        "official_positive_families": families,
        "positive_controls_preserved": len(preserved),
        "positive_controls": len(controls),
        "baseline_unavailable_official_positive": sum(
            bool(row["official_positive_available"])
            for row in rows
            if row["cohort"] == "baseline_unavailable"
        ),
        "baseline_nonofficial_official_positive": sum(
            bool(row["official_positive_available"])
            for row in rows
            if row["cohort"] == "baseline_nonofficial_action"
        ),
        "source_zero_perturbation": zero_perturbation,
        "semantic_scoring_enabled": False,
        "assignment_enabled": False,
        "graph_mutation": False,
        "gates": gates,
    }


def _write_report(path: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    lines = [
        "# V22 U-Net Official-Action Availability Results",
        "",
        f"Decision: **{summary['decision']}**",
        "",
        "## Primary Results",
        "",
        f"- Official-positive divisions: **{summary['official_positive_divisions']}/{summary['cases']}**.",
        f"- Positive controls preserved: **{summary['positive_controls_preserved']}/{summary['positive_controls']}**.",
        f"- Newly available from the unavailable stratum: **{summary['baseline_unavailable_official_positive']}/25**.",
        f"- Official-positive families: **{', '.join(summary['official_positive_families']) or 'none'}**.",
        f"- Source zero perturbation: **{summary['source_zero_perturbation']}**.",
        "",
        "## Gate Outcomes",
        "",
    ]
    for name, passed in summary["gates"].items():
        lines.append(f"- `{name}`: **{'PASS' if passed else 'FAIL'}**")
    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| Case | Route | Anchored parents | Division actions | GT-matched actions | Official TP actions | Available |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(
            f"| `{row['case_id']}` | `{row['source_detector']}/{row['source_link_strategy']}` | "
            f"{row['anchored_parent_count']} | {row['division_action_count']} | "
            f"{row['registered_geometric_action_count']} | {row['official_tp_action_count']} | "
            f"{row['official_positive_available']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            "This audit measures whether an officially recognizable fork exists in the formed action set.",
            "It does not select an action, estimate precision, fit confidence, solve ownership, or mutate",
            "a tracking graph. Raw action counts are not official false positives.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit official fork availability from frozen V22 U-Net peaks."
    )
    parser.add_argument("--peaks", type=Path, required=True)
    parser.add_argument("--train-dir", type=Path, default=project_root / "train")
    parser.add_argument(
        "--contract",
        type=Path,
        default=project_root
        / "tests/fixtures/v22_unet_official_action_development_46.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "v22_unet_official_action_development_46.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=project_root
        / "v22_unet_official_action_development_46_summary.json",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=project_root / "V22_UNET_OFFICIAL_ACTION_AVAILABILITY_RESULTS.md",
    )
    args = parser.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8-sig"))
    source_fixture_path = project_root / contract["source_fixture"]
    source_bytes = source_fixture_path.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    if source_hash != contract["source_fixture_sha256"]:
        raise RuntimeError(
            f"Source fixture SHA-256 mismatch: {source_hash} != "
            f"{contract['source_fixture_sha256']}"
        )
    fixture = json.loads(source_bytes.decode("utf-8-sig"))
    peaks_by_sample = _read_peaks(args.peaks)

    cases_by_sample: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in fixture["cases"]:
        cases_by_sample[case["sample_id"]].append(case)

    rows: list[dict[str, Any]] = []
    for sample_index, sample_id in enumerate(sorted(cases_by_sample), start=1):
        sample_cases = cases_by_sample[sample_id]
        max_timepoints = max(int(case["t"]) for case in sample_cases) + 2
        print(
            f"[{sample_index}/{len(cases_by_sample)}] {sample_id} "
            f"through {max_timepoints} timepoints",
            flush=True,
        )
        graph, detector, link_strategy = _build_v19_prefirewall_with_route(
            args.train_dir / f"{sample_id}.zarr",
            max_timepoints=max_timepoints,
        )
        ground_truth = read_geff_graph(args.train_dir / f"{sample_id}.geff")
        gt_nodes = {int(node.node_id): node for node in ground_truth.nodes}
        before = _graph_signature(graph)
        sample_peaks = peaks_by_sample.get(sample_id, [])

        enumerations: dict[int, Any] = {}
        for case in sample_cases:
            parent_t = int(case["t"])
            if parent_t not in enumerations:
                enumerations[parent_t] = enumerate_anchored_division_actions(
                    graph,
                    sample_peaks,
                    parent_t=parent_t,
                    anchor_radius_um=float(contract["parent_anchor_radius_um"]),
                    formation_radius_um=float(
                        contract["daughter_formation_radius_um"]
                    ),
                )
            enumeration = enumerations[parent_t]
            parent = gt_nodes[int(case["gt_parent_id"])]
            child_1 = gt_nodes[int(case["gt_child_ids"][0])]
            child_2 = gt_nodes[int(case["gt_child_ids"][1])]
            registered = [
                action
                for action in enumeration.actions
                if action_matches_registered_division(
                    action,
                    parent_position_um=parent.position_um,
                    daughter_positions_um=(
                        child_1.position_um,
                        child_2.position_um,
                    ),
                    match_radius_um=float(contract["official_match_radius_um"]),
                )
            ]
            official_tp_count = sum(
                evaluate_action_as_official_fork(
                    action,
                    ground_truth,
                    gt_parent_id=int(case["gt_parent_id"]),
                )
                for action in registered
            )
            zero_perturbation = before == _graph_signature(graph)
            rows.append(
                {
                    "case_id": case["case_id"],
                    "sample_id": sample_id,
                    "t": parent_t,
                    "cohort": case["cohort"],
                    "baseline_status": case["baseline_status"],
                    "source_detector": detector,
                    "source_link_strategy": link_strategy,
                    "anchor_count": enumeration.anchor_count,
                    "parent_peak_count": enumeration.parent_peak_count,
                    "anchored_parent_count": enumeration.anchored_parent_count,
                    "division_action_count": enumeration.division_action_count,
                    "registered_geometric_action_count": len(registered),
                    "official_tp_action_count": official_tp_count,
                    "official_positive_available": official_tp_count > 0,
                    "source_zero_perturbation": zero_perturbation,
                    "semantic_scoring_enabled": False,
                    "assignment_enabled": False,
                    "graph_mutated": False,
                }
            )
            print(
                f"  {case['case_id']}: actions={enumeration.division_action_count} "
                f"registered={len(registered)} official_tp={official_tp_count} "
                f"zero_perturb={zero_perturbation}",
                flush=True,
            )
        if before != _graph_signature(graph):
            raise RuntimeError(f"{sample_id}: official-action shadow mutated source graph")

    rows.sort(key=lambda row: row["case_id"])
    _write_csv(args.output, rows)
    summary = _summarize(rows, contract)
    args.summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_report(args.report, rows, summary)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    print(f"Wrote {args.output}, {args.summary}, and {args.report}", flush=True)


if __name__ == "__main__":
    main()
