from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.evaluation.semantic_positive_availability import (
    DivisionPositiveAvailability,
    audit_gt_division_positive_availability,
    gt_division_parent_ids,
)
from atabey.io.geff_reader import read_geff_graph
from atabey.tracking.joint_semantic_shadow import evidence_as_row
from atabey.types import LineageGraph
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route


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


def _load_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _availability_row(
    split: str,
    family: str,
    detector: str,
    link_strategy: str,
    result: DivisionPositiveAvailability,
    zero_perturbation: bool,
) -> dict[str, object]:
    row = {
        "split": split,
        "family": family,
        "source_detector": detector,
        "source_link_strategy": link_strategy,
        **{
            key: value
            for key, value in asdict(result).items()
            if key != "canonical_evidence"
        },
        "gt_child_ids": ";".join(str(value) for value in result.gt_child_ids),
        "source_zero_perturbation": zero_perturbation,
    }
    if result.canonical_evidence is not None:
        row.update(
            {
                f"evidence_{key}": value
                for key, value in evidence_as_row(result.canonical_evidence).items()
            }
        )
    return row


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


def _write_report(
    path: Path,
    rows: list[dict[str, object]],
    manifest: dict[str, object],
    selected_splits: list[str],
) -> None:
    go_rules = manifest["go_rules"]
    lines = [
        "# V21 Semantic Positive Availability Audit",
        "",
        "Status: read-only prerequisite audit; no model fit, threshold tuning, assignment solve, or graph mutation",
        "",
        "## Contract",
        "",
        "Each row represents one distinct known GT division. A division counts as available only",
        "when at least one parent-centered action projects as a true positive through the patched",
        "official scorer. Candidate multiplicity never increases the positive count. Sparse absence",
        "is not treated as a negative label.",
        "",
        "## Split Results",
        "",
        "| Split | Samples | GT divisions | Official positives | 44b6 positives | 6bba positives | Zero perturbation | Minimum met |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    split_results: dict[str, bool] = {}
    for split in selected_splits:
        split_rows = [row for row in rows if row["split"] == split]
        samples = {str(row["sample_id"]) for row in split_rows}
        positives = [row for row in split_rows if row["status"] == "official_positive"]
        family_counts = Counter(str(row["family"]) for row in positives)
        zero = all(_truthy(row["source_zero_perturbation"]) for row in split_rows)
        minimum = int(
            go_rules[f"minimum_official_positive_divisions_{split}"]
        )
        passed = (
            len(positives) >= minimum
            and all(
                family_counts[family] >= int(
                    go_rules["minimum_official_positive_divisions_per_family_per_split"]
                )
                for family in ("44b6", "6bba")
            )
            and zero
        )
        split_results[split] = passed
        lines.append(
            f"| `{split}` | {len(samples)} | {len(split_rows)} | {len(positives)} | "
            f"{family_counts['44b6']} | {family_counts['6bba']} | {zero} | {passed} |"
        )

    lines.extend(
        [
            "",
            "## Failure Modes",
            "",
            "| Split | Status | Count |",
            "|---|---|---:|",
        ]
    )
    for split in selected_splits:
        counts = Counter(
            str(row["status"]) for row in rows if row["split"] == split
        )
        for status, count in sorted(counts.items()):
            lines.append(f"| `{split}` | `{status}` | {count} |")

    complete = set(selected_splits) == {"development", "calibration"}
    overall_go = complete and all(split_results.values())
    lines.extend(
        [
            "",
            "## Decision",
            "",
            (
                "**GO to scorer development:** both preregistered pools satisfy the positive-count, "
                "family-coverage, and zero-perturbation gates."
                if overall_go
                else (
                    "**NO-GO for calibrated semantic scoring:** the complete preregistered gate "
                    "has not been satisfied."
                    if complete
                    else "**Partial audit only:** no overall GO/NO-GO is issued until both splits run."
                )
            ),
            "",
            "The locked 20-sample validation cohort was not opened or used. This audit does not",
            "authorize production graph mutation; it only determines whether enough official-positive",
            "actions exist to begin development under the preregistered contract.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit official-positive semantic action availability without fitting a model."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=project_root / "tests" / "fixtures" / "v21_semantic_dataset_split.json",
    )
    parser.add_argument(
        "--splits",
        nargs="+",
        choices=("development", "calibration"),
        default=["development", "calibration"],
    )
    parser.add_argument("--sample-ids", nargs="*", default=None)
    parser.add_argument("--formation-radius-um", type=float, default=14.0)
    parser.add_argument("--match-radius-um", type=float, default=7.0)
    parser.add_argument("--continuity-horizon", type=int, default=2)
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "v21_semantic_positive_availability.csv",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=project_root / "V21_SEMANTIC_POSITIVE_AVAILABILITY_AUDIT.md",
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    manifest = _load_manifest(args.manifest)
    selected_ids = set(args.sample_ids or ())
    entries = [
        (split, entry)
        for split in args.splits
        for entry in manifest["splits"][split]
        if not selected_ids or entry["sample_id"] in selected_ids
    ]
    if selected_ids:
        known = {entry["sample_id"] for _split, entry in entries}
        unknown = sorted(selected_ids - known)
        if unknown:
            raise ValueError(f"Sample IDs not present in selected preregistered splits: {unknown}")

    rows = _read_csv(args.output) if args.resume else []
    completed = {
        (str(row["split"]), str(row["sample_id"]))
        for row in rows
    }
    pending = [
        (split, entry)
        for split, entry in entries
        if (split, entry["sample_id"]) not in completed
    ]
    print(
        f"Preregistered audit: completed={len(completed)} pending={len(pending)} "
        f"selected={len(entries)}",
        flush=True,
    )

    for index, (split, entry) in enumerate(pending, start=1):
        sample_id = str(entry["sample_id"])
        ground_truth = read_geff_graph(project_root / "train" / f"{sample_id}.geff")
        division_ids = gt_division_parent_ids(ground_truth)
        expected = int(entry["gt_divisions"])
        if len(division_ids) != expected:
            raise RuntimeError(
                f"{sample_id}: manifest has {expected} GT divisions, found {len(division_ids)}"
            )
        nodes = {int(node.node_id): node for node in ground_truth.nodes}
        max_timepoints = max(
            int(nodes[parent_id].t) + args.continuity_horizon + 3
            for parent_id in division_ids
        )
        print(
            f"[{index}/{len(pending)}] {split} {sample_id}: "
            f"{len(division_ids)} GT divisions through {max_timepoints} timepoints",
            flush=True,
        )
        graph, detector, link_strategy = _build_v19_prefirewall_with_route(
            project_root / "train" / f"{sample_id}.zarr",
            max_timepoints=max_timepoints,
        )
        before = _graph_signature(graph)
        sample_results = [
            audit_gt_division_positive_availability(
                graph,
                ground_truth,
                parent_id,
                match_radius_um=args.match_radius_um,
                formation_radius_um=args.formation_radius_um,
                continuity_horizon=args.continuity_horizon,
            )
            for parent_id in division_ids
        ]
        zero_perturbation = before == _graph_signature(graph)
        if not zero_perturbation:
            raise RuntimeError(f"{sample_id}: availability audit mutated the source graph")
        rows.extend(
            _availability_row(
                split,
                str(entry["family"]),
                detector,
                link_strategy,
                result,
                zero_perturbation,
            )
            for result in sample_results
        )
        _write_csv(args.output, rows)
        positives = sum(result.official_positive for result in sample_results)
        print(
            f"  route={detector}/{link_strategy} official_positive="
            f"{positives}/{len(sample_results)} zero_perturb=True",
            flush=True,
        )

    _write_csv(args.output, rows)
    _write_report(args.report, rows, manifest, list(args.splits))
    print(f"Wrote {args.output} and {args.report}", flush=True)


if __name__ == "__main__":
    main()
