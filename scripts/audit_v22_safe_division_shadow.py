from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import asdict, fields
from pathlib import Path


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.evaluation.official_division_metric import evaluate_official_divisions
from atabey.evaluation.official_tracking_metric import (
    OfficialTrackingResult,
    evaluate_official_tracking,
    summarize_official_tracking,
)
from atabey.evaluation.semantic_positive_availability import (
    audit_gt_division_positive_availability,
    gt_division_parent_ids,
)
from atabey.io.geff_reader import read_geff_graph
from atabey.tracking.safe_division_shadow import (
    SafeDivisionShadowCandidate,
    SafeDivisionShadowConfig,
    compute_safe_division_shadow,
    project_safe_division_shadow,
)
from atabey.types import LineageGraph
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route


DEVELOPMENT_SPLIT = "development"
EXPECTED_DEVELOPMENT_SAMPLES = 27
EXPECTED_DEVELOPMENT_DIVISIONS = 46
EXPECTED_BASELINE_AVAILABLE_POSITIVES = 13
EXPECTED_BASELINE_PROJECTED_INVALID = 8


def _graph_signature(graph: LineageGraph) -> tuple[tuple[object, ...], tuple[object, ...]]:
    return (
        tuple(
            (
                node.node_id,
                node.sample_id,
                node.t,
                node.z_um,
                node.y_um,
                node.x_um,
                node.intensity_mean,
                node.intensity_max,
                node.component_volume,
                node.detection_confidence,
            )
            for node in graph.detections
        ),
        tuple(
            (edge.source_id, edge.target_id, edge.confidence, edge.relation)
            for edge in graph.edges
        ),
    )


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _optional_float(value: object) -> float | None:
    text = str(value).strip()
    return None if text in {"", "None", "nan"} else float(text)


def _optional_int(value: object) -> int | None:
    text = str(value).strip()
    return None if text in {"", "None", "nan"} else int(float(text))


def _tracking_row(prefix: str, result: OfficialTrackingResult) -> dict[str, object]:
    return {f"{prefix}_{key}": value for key, value in asdict(result).items()}


def _tracking_from_row(prefix: str, row: dict[str, object]) -> OfficialTrackingResult:
    integer_fields = {
        "edge_tp",
        "edge_fp",
        "edge_fn",
        "predicted_nodes",
        "division_tp",
        "division_fp",
        "division_fn",
    }
    optional_integer_fields = {"estimated_total_nodes"}
    values: dict[str, object] = {}
    for field in fields(OfficialTrackingResult):
        value = row[f"{prefix}_{field.name}"]
        if field.name in integer_fields:
            values[field.name] = int(float(str(value)))
        elif field.name in optional_integer_fields:
            values[field.name] = _optional_int(value)
        else:
            values[field.name] = _optional_float(value)
    return OfficialTrackingResult(**values)


def _candidate_row(
    sample_id: str,
    detector: str,
    link_strategy: str,
    candidate: SafeDivisionShadowCandidate,
    baseline_tp_forks: frozenset[str],
    shadow_tp_forks: frozenset[str],
) -> dict[str, object]:
    row = asdict(candidate)
    row.update(
        {
            "sample_id": sample_id,
            "source_detector": detector,
            "source_link_strategy": link_strategy,
            "baseline_parent_official_tp": candidate.parent_id in baseline_tp_forks,
            "shadow_parent_official_tp": candidate.parent_id in shadow_tp_forks,
            "new_official_tp_parent": (
                candidate.parent_id in shadow_tp_forks
                and candidate.parent_id not in baseline_tp_forks
            ),
        }
    )
    return row


def _delta_bucket(after: float | None, before: float | None, tolerance: float = 1e-12) -> str:
    if after is None or before is None:
        return "not_comparable"
    delta = float(after) - float(before)
    if delta > tolerance:
        return "improved"
    if delta < -tolerance:
        return "regressed"
    return "flat"


def _write_report(
    path: Path,
    sample_rows: list[dict[str, object]],
    gt_rows: list[dict[str, object]],
    candidate_rows: list[dict[str, object]],
) -> None:
    completed = len({str(row["sample_id"]) for row in sample_rows})
    gt_count = len(gt_rows)
    selected = [row for row in candidate_rows if _truthy(row["selected"])]
    baseline_results = [_tracking_from_row("baseline", row) for row in sample_rows]
    shadow_results = [_tracking_from_row("shadow", row) for row in sample_rows]
    baseline_summary = summarize_official_tracking(baseline_results) if baseline_results else None
    shadow_summary = summarize_official_tracking(shadow_results) if shadow_results else None

    baseline_available = [
        row for row in gt_rows if row["baseline_availability_status"] == "official_positive"
    ]
    preserved_available = [
        row
        for row in baseline_available
        if row["shadow_availability_status"] == "official_positive"
    ]
    projected_invalid = [
        row
        for row in gt_rows
        if row["baseline_availability_status"] == "projected_actions_not_official_tp"
    ]
    projected_invalid_recovered = [
        row
        for row in projected_invalid
        if row["shadow_availability_status"] == "official_positive"
        or _truthy(row["new_actual_official_tp"])
    ]
    new_actual = [row for row in gt_rows if _truthy(row["new_actual_official_tp"])]
    lost_actual = [row for row in gt_rows if _truthy(row["lost_actual_official_tp"])]
    zero_perturbation = all(_truthy(row["source_zero_perturbation"]) for row in sample_rows)
    edge_buckets = Counter(str(row["adjusted_edge_delta_bucket"]) for row in sample_rows)
    division_buckets = Counter(str(row["division_delta_bucket"]) for row in sample_rows)
    complete = (
        completed == EXPECTED_DEVELOPMENT_SAMPLES
        and gt_count == EXPECTED_DEVELOPMENT_DIVISIONS
    )
    baseline_contract_matches = (
        len(baseline_available) == EXPECTED_BASELINE_AVAILABLE_POSITIVES
        and len(projected_invalid) == EXPECTED_BASELINE_PROJECTED_INVALID
    )
    adjusted_nonregression = (
        baseline_summary is not None
        and shadow_summary is not None
        and baseline_summary.adjusted_edge_jaccard is not None
        and shadow_summary.adjusted_edge_jaccard is not None
        and shadow_summary.adjusted_edge_jaccard
        >= baseline_summary.adjusted_edge_jaccard - 1e-12
    )
    go = (
        complete
        and baseline_contract_matches
        and zero_perturbation
        and len(preserved_available) == len(baseline_available)
        and len(new_actual) >= 1
        and adjusted_nonregression
        and sum(result.division_fp for result in shadow_results)
        <= sum(result.division_fp for result in baseline_results) + len(new_actual)
    )

    def metric(value: float | None) -> str:
        return "None" if value is None else f"{value:.9f}"

    lines = [
        "# V22 Public Safe-Division Shadow Audit",
        "",
        "Status: development-only read-only shadow; no threshold tuning or production mutation",
        "",
        "## Frozen Rule",
        "",
        "The shadow faithfully evaluates the public 0.902 notebook's post-link second-child rule:",
        "one existing child, one unowned next-frame candidate, parent-candidate <= 4.66 um,",
        "existing parent-child <= 7.65 um, sister separation <= 8.5 um, score equal to parent",
        "distance plus 0.15 times sister distance, frame cap 0.0076, and global cap 0.00375.",
        "",
        "## Coverage",
        "",
        f"- Completed samples: **{completed}/{EXPECTED_DEVELOPMENT_SAMPLES}**.",
        f"- Known GT divisions: **{gt_count}/{EXPECTED_DEVELOPMENT_DIVISIONS}**.",
        f"- Raw eligible proposals: **{len(candidate_rows)}**.",
        f"- Budget-selected second-child edges: **{len(selected)}**.",
        f"- Source zero perturbation: **{zero_perturbation}**.",
        "",
        "## Official Graph Impact",
        "",
        "| Metric | Baseline | Shadow |",
        "|---|---:|---:|",
        f"| Adjusted edge Jaccard | {metric(baseline_summary.adjusted_edge_jaccard if baseline_summary else None)} | {metric(shadow_summary.adjusted_edge_jaccard if shadow_summary else None)} |",
        f"| Division Jaccard | {metric(baseline_summary.division_jaccard if baseline_summary else None)} | {metric(shadow_summary.division_jaccard if shadow_summary else None)} |",
        f"| Division TP | {sum(result.division_tp for result in baseline_results)} | {sum(result.division_tp for result in shadow_results)} |",
        f"| Division FP | {sum(result.division_fp for result in baseline_results)} | {sum(result.division_fp for result in shadow_results)} |",
        f"| Division FN | {sum(result.division_fn for result in baseline_results)} | {sum(result.division_fn for result in shadow_results)} |",
        "",
        f"Adjusted-edge per-sample breakdown: improved {edge_buckets['improved']}, flat {edge_buckets['flat']}, regressed {edge_buckets['regressed']}, not comparable {edge_buckets['not_comparable']}.",
        "",
        f"Division per-sample breakdown: improved {division_buckets['improved']}, flat {division_buckets['flat']}, regressed {division_buckets['regressed']}, not comparable {division_buckets['not_comparable']}.",
        "",
        "## Availability Contract",
        "",
        f"- Baseline official-positive availability reproduced: **{len(baseline_available)}/{EXPECTED_BASELINE_AVAILABLE_POSITIVES}**.",
        f"- Baseline projected-invalid category reproduced: **{len(projected_invalid)}/{EXPECTED_BASELINE_PROJECTED_INVALID}**.",
        f"- Previously available positives preserved: **{len(preserved_available)}/{len(baseline_available)}**.",
        f"- Projected-invalid divisions recovered: **{len(projected_invalid_recovered)}/{len(projected_invalid)}**.",
        f"- New actual official TPs: **{len(new_actual)}**.",
        f"- Lost actual official TPs: **{len(lost_actual)}**.",
        "",
        "## Decision",
        "",
    ]
    if not complete:
        lines.append("**PARTIAL:** no GO/NO-GO is issued until all 27 development samples complete.")
    elif go:
        lines.append("**GO for a separate confirmatory shadow:** every preregistered gate passed. This does not authorize production integration.")
    else:
        lines.append("**NO-GO under the frozen rule:** at least one preregistered efficacy or safety gate failed.")
    lines.extend(
        [
            "",
            "The calibration split and locked independent validation cohort were not opened. Raw",
            "proposal counts are geometric eligibility counts, not official FPs or biological labels.",
            "The shadow does not address GT divisions whose parent or daughter detections are absent.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit the public notebook's safe-division rule in read-only V22 shadow mode."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=project_root / "tests" / "fixtures" / "v21_semantic_dataset_split.json",
    )
    parser.add_argument("--sample-ids", nargs="*", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--sample-output",
        type=Path,
        default=project_root / "v22_safe_division_shadow_samples.csv",
    )
    parser.add_argument(
        "--gt-output",
        type=Path,
        default=project_root / "v22_safe_division_shadow_gt.csv",
    )
    parser.add_argument(
        "--candidate-output",
        type=Path,
        default=project_root / "v22_safe_division_shadow_candidates.csv",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=project_root / "V22_SAFE_DIVISION_SHADOW_AUDIT.md",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    entries = list(manifest["splits"][DEVELOPMENT_SPLIT])
    selected_ids = set(args.sample_ids or ())
    if selected_ids:
        entries = [entry for entry in entries if entry["sample_id"] in selected_ids]
        known = {entry["sample_id"] for entry in entries}
        unknown = sorted(selected_ids - known)
        if unknown:
            raise ValueError(f"Samples are not in the frozen development split: {unknown}")

    sample_rows = _read_csv(args.sample_output) if args.resume else []
    gt_rows = _read_csv(args.gt_output) if args.resume else []
    candidate_rows = _read_csv(args.candidate_output) if args.resume else []
    completed = {str(row["sample_id"]) for row in sample_rows}
    pending = [entry for entry in entries if entry["sample_id"] not in completed]
    config = SafeDivisionShadowConfig()
    print(
        f"V22 safe-division shadow: completed={len(completed)} "
        f"pending={len(pending)} selected={len(entries)}",
        flush=True,
    )

    for index, entry in enumerate(pending, start=1):
        sample_id = str(entry["sample_id"])
        ground_truth = read_geff_graph(project_root / "train" / f"{sample_id}.geff")
        division_ids = gt_division_parent_ids(ground_truth)
        if len(division_ids) != int(entry["gt_divisions"]):
            raise RuntimeError(f"{sample_id}: GT division count changed from manifest")
        gt_nodes = {int(node.node_id): node for node in ground_truth.nodes}
        max_timepoints = max(int(gt_nodes[parent_id].t) + 5 for parent_id in division_ids)
        print(
            f"[{index}/{len(pending)}] {sample_id}: {len(division_ids)} GT divisions "
            f"through {max_timepoints} timepoints",
            flush=True,
        )
        graph, detector, link_strategy = _build_v19_prefirewall_with_route(
            project_root / "train" / f"{sample_id}.zarr",
            max_timepoints=max_timepoints,
        )
        before = _graph_signature(graph)
        baseline_availability = {
            parent_id: audit_gt_division_positive_availability(
                graph,
                ground_truth,
                parent_id,
            )
            for parent_id in division_ids
        }
        baseline_tracking = evaluate_official_tracking(graph, ground_truth)
        baseline_divisions = evaluate_official_divisions(graph, ground_truth)

        shadow = compute_safe_division_shadow(graph, config=config)
        projected = project_safe_division_shadow(graph, shadow)
        shadow_tracking = evaluate_official_tracking(projected, ground_truth)
        shadow_divisions = evaluate_official_divisions(projected, ground_truth)
        shadow_availability = {
            parent_id: audit_gt_division_positive_availability(
                projected,
                ground_truth,
                parent_id,
            )
            for parent_id in division_ids
        }
        zero_perturbation = before == _graph_signature(graph)
        if not zero_perturbation:
            raise RuntimeError(f"{sample_id}: safe-division shadow mutated source graph")

        sample_rows.append(
            {
                "sample_id": sample_id,
                "family": entry["family"],
                "source_detector": detector,
                "source_link_strategy": link_strategy,
                "gt_divisions": len(division_ids),
                "source_nodes": len(graph.detections),
                "source_edges": len(graph.edges),
                "proposal_count": shadow.proposal_count,
                "selected_count": shadow.selected_count,
                "global_cap": shadow.global_cap,
                "source_zero_perturbation": zero_perturbation,
                "adjusted_edge_delta": (
                    None
                    if baseline_tracking.adjusted_edge_jaccard is None
                    or shadow_tracking.adjusted_edge_jaccard is None
                    else shadow_tracking.adjusted_edge_jaccard
                    - baseline_tracking.adjusted_edge_jaccard
                ),
                "adjusted_edge_delta_bucket": _delta_bucket(
                    shadow_tracking.adjusted_edge_jaccard,
                    baseline_tracking.adjusted_edge_jaccard,
                ),
                "division_delta_bucket": _delta_bucket(
                    shadow_tracking.division_jaccard,
                    baseline_tracking.division_jaccard,
                ),
                **_tracking_row("baseline", baseline_tracking),
                **_tracking_row("shadow", shadow_tracking),
            }
        )
        for parent_id in division_ids:
            baseline_status = baseline_availability[parent_id]
            shadow_status = shadow_availability[parent_id]
            baseline_actual = bool(baseline_divisions.gt_scores.get(parent_id, 0))
            shadow_actual = bool(shadow_divisions.gt_scores.get(parent_id, 0))
            gt_rows.append(
                {
                    "sample_id": sample_id,
                    "family": entry["family"],
                    "gt_parent_id": parent_id,
                    "source_detector": detector,
                    "source_link_strategy": link_strategy,
                    "baseline_availability_status": baseline_status.status,
                    "shadow_availability_status": shadow_status.status,
                    "availability_preserved": (
                        baseline_status.official_positive
                        and shadow_status.official_positive
                    ),
                    "new_availability_positive": (
                        not baseline_status.official_positive
                        and shadow_status.official_positive
                    ),
                    "baseline_actual_official_tp": baseline_actual,
                    "shadow_actual_official_tp": shadow_actual,
                    "new_actual_official_tp": shadow_actual and not baseline_actual,
                    "lost_actual_official_tp": baseline_actual and not shadow_actual,
                }
            )
        candidate_rows.extend(
            _candidate_row(
                sample_id,
                detector,
                link_strategy,
                candidate,
                baseline_divisions.tp_fork_ids,
                shadow_divisions.tp_fork_ids,
            )
            for candidate in shadow.candidates
        )
        _write_csv(args.sample_output, sample_rows)
        _write_csv(args.gt_output, gt_rows)
        _write_csv(args.candidate_output, candidate_rows)
        _write_report(args.report, sample_rows, gt_rows, candidate_rows)
        print(
            f"  route={detector}/{link_strategy} proposals={shadow.proposal_count} "
            f"selected={shadow.selected_count} DivTP {baseline_tracking.division_tp}->"
            f"{shadow_tracking.division_tp} FP {baseline_tracking.division_fp}->"
            f"{shadow_tracking.division_fp} edge_bucket="
            f"{sample_rows[-1]['adjusted_edge_delta_bucket']} zero_perturb=True",
            flush=True,
        )

    _write_csv(args.sample_output, sample_rows)
    _write_csv(args.gt_output, gt_rows)
    _write_csv(args.candidate_output, candidate_rows)
    _write_report(args.report, sample_rows, gt_rows, candidate_rows)
    print(f"Wrote {args.report}", flush=True)


if __name__ == "__main__":
    main()
