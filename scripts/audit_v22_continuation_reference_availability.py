from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.tracking.continuation_reference import (
    extract_continuation_references,
    reference_as_row,
)
from atabey.types import LineageGraph
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route
from run_v22_unet_official_action_availability import _graph_signature


REFERENCE_FIELDS = [
    "reference_id",
    "sample_id",
    "anchor_id",
    "parent_id",
    "child_id",
    "anchor_t",
    "parent_t",
    "child_t",
    "anchor_parent_distance_um",
    "parent_child_distance_um",
    "prediction_error_um",
    "forward_margin_um",
    "reverse_margin_um",
    "local_target_count_14um",
    "alternative_target_count_14um",
    "local_competing_source_count_14um",
    "reference_is_ground_truth",
    "graph_mutated",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_hash(path: Path, expected: str, label: str) -> None:
    actual = _sha256(path)
    if actual != expected:
        raise RuntimeError(f"{label} SHA-256 mismatch: {actual} != {expected}")


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _atomic_write_csv_gz(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with gzip.open(temporary, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REFERENCE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def _fold_map(semantic_contract: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for fold in semantic_contract["folds"]:
        fold_id = int(fold["fold"])
        for sample_id in fold["samples"]:
            if sample_id in result:
                raise RuntimeError(f"Sample appears in multiple folds: {sample_id}")
            result[sample_id] = fold_id
    return result


def _load_contracts(
    contract_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    semantic_path = project_root / contract["source_semantic_contract"]
    division_path = project_root / contract["source_division_fixture"]
    _verify_hash(
        semantic_path,
        contract["source_semantic_contract_sha256"],
        "Semantic experiment contract",
    )
    _verify_hash(
        division_path,
        contract["source_division_fixture_sha256"],
        "Registered division fixture",
    )
    semantic_contract = json.loads(
        semantic_path.read_text(encoding="utf-8-sig")
    )
    division_fixture = json.loads(
        division_path.read_text(encoding="utf-8-sig")
    )
    return contract, semantic_contract, division_fixture


def _percentiles(values: list[int | float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "median": None, "p90": None, "max": None}
    array = np.asarray(values, dtype=float)
    return {
        "min": float(array.min()),
        "median": float(np.median(array)),
        "p90": float(np.percentile(array, 90)),
        "max": float(array.max()),
    }


def _summarize_sample(
    *,
    sample_id: str,
    fold: int,
    detector: str,
    link_strategy: str,
    graph: LineageGraph,
    audit: Any,
    contract_sha256: str,
    max_timepoints: int,
    shard_path: Path,
) -> dict[str, Any]:
    alternatives = [
        int(reference.alternative_target_count_14um)
        for reference in audit.references
    ]
    competing_sources = [
        int(reference.local_competing_source_count_14um)
        for reference in audit.references
    ]
    by_parent_t = Counter(
        int(reference.parent_t) for reference in audit.references
    )
    return {
        "sample_id": sample_id,
        "fold": int(fold),
        "family": sample_id.split("_", 1)[0],
        "detector": detector,
        "link_strategy": link_strategy,
        "route": f"{detector}/{link_strategy}",
        "max_timepoints": int(max_timepoints),
        "graph_nodes": len(graph.detections),
        "graph_edges": len(graph.edges),
        "references": len(audit.references),
        "references_with_alternatives": sum(value > 0 for value in alternatives),
        "references_with_competing_sources": sum(
            value > 0 for value in competing_sources
        ),
        "alternative_target_distribution": _percentiles(alternatives),
        "competing_source_distribution": _percentiles(competing_sources),
        "references_by_parent_t": {
            str(key): value for key, value in sorted(by_parent_t.items())
        },
        "funnel": audit.funnel,
        "rejection_reasons": audit.rejection_reasons,
        "source_zero_perturbation": True,
        "local_maxima_reporting": {
            "development_samples": int(
                by_route.get("local_maxima/motion_mutual", {}).get("samples", 0)
            ),
            "development_fold": 3,
            "rounds_without_heldout_route_evidence": 2,
            "heldout_round_training_route_status": "absent_zero_shot",
            "generalization_status": "unproven",
            "required_metric_caveat": contract["reporting"][
                "local_maxima_required_metric_caveat"
            ],
            "pooled_metrics_require_route_breakdown": bool(
                contract["reporting"]["pooled_metrics_require_route_breakdown"]
            ),
        },        "reference_is_ground_truth": False,
        "semantic_scoring_enabled": False,
        "assignment_enabled": False,
        "graph_mutated": False,
        "contract_sha256": contract_sha256,
        "shard": str(shard_path),
        "shard_sha256": _sha256(shard_path),
    }


def _summarize_group_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    reference_counts = [int(row["references"]) for row in rows]
    references = sum(reference_counts)
    with_alternatives = sum(
        int(row["references_with_alternatives"]) for row in rows
    )
    with_competing_sources = sum(
        int(row["references_with_competing_sources"]) for row in rows
    )
    return {
        "samples": len(rows),
        "samples_with_references": sum(count > 0 for count in reference_counts),
        "references": references,
        "references_with_alternatives": with_alternatives,
        "alternative_reference_rate": (
            with_alternatives / references if references else None
        ),
        "references_with_competing_sources": with_competing_sources,
        "competing_source_reference_rate": (
            with_competing_sources / references if references else None
        ),
        "per_sample_reference_distribution": _percentiles(reference_counts),
    }


def _group_summary(
    summaries: list[dict[str, Any]],
    key: str,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for summary in summaries:
        grouped[str(summary[key])].append(summary)
    return {
        value: _summarize_group_rows(rows)
        for value, rows in sorted(grouped.items())
    }


def _cross_group_summary(
    summaries: list[dict[str, Any]],
    first_key: str,
    second_key: str,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for summary in summaries:
        value = f"{summary[first_key]}|{summary[second_key]}"
        grouped[value].append(summary)
    return {
        value: _summarize_group_rows(rows)
        for value, rows in sorted(grouped.items())
    }


def _aggregate_summary(
    summaries: list[dict[str, Any]],
    *,
    expected_samples: int,
    contract: dict[str, Any],
    contract_sha256: str,
) -> dict[str, Any]:
    by_fold = _group_summary(summaries, "fold")
    by_family = _group_summary(summaries, "family")
    by_route = _group_summary(summaries, "route")
    by_fold_family = _cross_group_summary(summaries, "fold", "family")
    by_fold_route = _cross_group_summary(summaries, "fold", "route")
    total_references = sum(int(row["references"]) for row in summaries)
    total_with_alternatives = sum(
        int(row["references_with_alternatives"]) for row in summaries
    )
    total_with_competing_sources = sum(
        int(row["references_with_competing_sources"]) for row in summaries
    )
    if total_references:
        for grouping in (
            by_fold,
            by_family,
            by_route,
            by_fold_family,
            by_fold_route,
        ):
            for row in grouping.values():
                row["reference_share"] = row["references"] / total_references
    sample_counts = sorted(
        (
            (row["sample_id"], int(row["references"]))
            for row in summaries
        ),
        key=lambda item: (-item[1], item[0]),
    )
    top_sample_share = (
        sample_counts[0][1] / total_references
        if total_references and sample_counts
        else None
    )
    top_three_share = (
        sum(count for _sample, count in sample_counts[:3]) / total_references
        if total_references
        else None
    )
    squared_sum = sum(count * count for _sample, count in sample_counts)
    effective_sample_size = (
        total_references * total_references / squared_sum
        if squared_sum
        else 0.0
    )

    frame_counts: Counter[str] = Counter()
    for summary in summaries:
        for parent_t, count in summary["references_by_parent_t"].items():
            frame_counts[f"{summary['sample_id']}:t{parent_t}"] += int(count)
    ordered_frames = sorted(
        frame_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )
    top_frame_share = (
        ordered_frames[0][1] / total_references
        if total_references and ordered_frames
        else None
    )
    top_three_frame_share = (
        sum(count for _frame, count in ordered_frames[:3]) / total_references
        if total_references
        else None
    )

    complete = len(summaries) == expected_samples
    gates: dict[str, bool] = {}
    if complete:
        decision = contract["decision_contract"]
        gates = {
            "minimum_total_references": total_references
            >= int(decision["minimum_total_references"]),
            "minimum_references_per_fold": all(
                int(row["references"])
                >= int(decision["minimum_references_per_fold"])
                for row in by_fold.values()
            ),
            "minimum_references_with_alternatives_per_fold": all(
                int(row["references_with_alternatives"])
                >= int(decision["minimum_references_with_alternatives_per_fold"])
                for row in by_fold.values()
            ),
            "minimum_samples_with_references_per_fold": all(
                int(row["samples_with_references"])
                >= int(decision["minimum_samples_with_references_per_fold"])
                for row in by_fold.values()
            ),
            "minimum_references_per_family": all(
                int(row["references"])
                >= int(decision["minimum_references_per_family"])
                for row in by_family.values()
            ),
            "minimum_references_per_observed_route": all(
                int(row["references"])
                >= int(decision["minimum_references_per_observed_route"])
                for row in by_route.values()
            ),
            "maximum_top_sample_share": (
                top_sample_share is not None
                and top_sample_share <= float(decision["maximum_top_sample_share"])
            ),
            "maximum_top_three_sample_share": (
                top_three_share is not None
                and top_three_share
                <= float(decision["maximum_top_three_sample_share"])
            ),
            "both_families_required": set(by_family) == {"44b6", "6bba"},
            "all_source_graphs_zero_perturbation": all(
                bool(row["source_zero_perturbation"]) for row in summaries
            ),
        }

    return {
        "contract": contract["name"],
        "contract_sha256": contract_sha256,
        "completed_samples": len(summaries),
        "expected_samples": expected_samples,
        "complete": complete,
        "decision": (
            "GO_TO_CONTINUATION_TABLE_BUILD"
            if complete and gates and all(gates.values())
            else "NO_GO" if complete else "INCOMPLETE"
        ),
        "gates": gates,
        "references": total_references,
        "references_with_alternatives": total_with_alternatives,
        "alternative_reference_rate": (
            total_with_alternatives / total_references
            if total_references
            else None
        ),
        "references_with_competing_sources": total_with_competing_sources,
        "competing_source_reference_rate": (
            total_with_competing_sources / total_references
            if total_references
            else None
        ),
        "by_fold": by_fold,
        "by_family": by_family,
        "by_route": by_route,
        "by_fold_family": by_fold_family,
        "by_fold_route": by_fold_route,
        "funnel": {
            key: sum(int(row["funnel"].get(key, 0)) for row in summaries)
            for key in sorted(
                {key for row in summaries for key in row["funnel"]}
            )
        },
        "rejection_reasons": {
            key: sum(
                int(row["rejection_reasons"].get(key, 0))
                for row in summaries
            )
            for key in sorted(
                {
                    key
                    for row in summaries
                    for key in row["rejection_reasons"]
                }
            )
        },
        "sample_concentration": {
            "top_sample_share": top_sample_share,
            "top_three_sample_share": top_three_share,
            "effective_sample_size": effective_sample_size,
            "largest_samples": [
                {"sample_id": sample_id, "references": count}
                for sample_id, count in sample_counts[:10]
            ],
        },
        "frame_concentration": {
            "top_frame_share": top_frame_share,
            "top_three_frame_share": top_three_frame_share,
            "largest_frames": [
                {"frame": frame, "references": count}
                for frame, count in ordered_frames[:10]
            ],
        },
        "local_maxima_reporting": {
            "development_samples": int(
                by_route.get("local_maxima/motion_mutual", {}).get("samples", 0)
            ),
            "development_fold": 3,
            "rounds_without_heldout_route_evidence": 2,
            "heldout_round_training_route_status": "absent_zero_shot",
            "generalization_status": "unproven",
            "required_metric_caveat": contract["reporting"][
                "local_maxima_required_metric_caveat"
            ],
            "pooled_metrics_require_route_breakdown": bool(
                contract["reporting"]["pooled_metrics_require_route_breakdown"]
            ),
        },        "reference_is_ground_truth": False,
        "semantic_scoring_enabled": False,
        "assignment_enabled": False,
        "graph_mutated": False,
        "full_199_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Audit fold-stratified V19 continuation-reference availability "
            "without fitting a model or mutating a graph."
        )
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=project_root
        / "tests/fixtures/v22_continuation_reference_audit.json",
    )
    parser.add_argument("--train-dir", type=Path, default=project_root / "train")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "v22_continuation_reference_audit",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=project_root / "v22_continuation_reference_audit_summary.json",
    )
    parser.add_argument("--sample-ids", nargs="*", default=None)
    parser.add_argument("--max-timepoints", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    contract, semantic_contract, division_fixture = _load_contracts(args.contract)
    if (
        contract["semantic_scoring_enabled"]
        or contract["assignment_enabled"]
        or contract["production_graph_mutation_enabled"]
    ):
        raise RuntimeError("Continuation availability audit must remain shadow-only")
    contract_sha256 = _sha256(args.contract)
    max_timepoints = int(args.max_timepoints or contract["max_timepoints"])
    folds = _fold_map(semantic_contract)
    division_times: dict[str, set[int]] = defaultdict(set)
    for case in division_fixture["cases"]:
        division_times[case["sample_id"]].add(int(case["t"]))

    selected_samples = (
        sorted(set(args.sample_ids))
        if args.sample_ids
        else sorted(folds)
    )
    unknown = sorted(set(selected_samples) - set(folds))
    if unknown:
        raise ValueError(f"Unknown development samples: {unknown}")

    for index, sample_id in enumerate(selected_samples, start=1):
        shard_path = args.output_dir / f"{sample_id}.csv.gz"
        sample_summary_path = args.output_dir / f"{sample_id}.summary.json"
        if args.resume and shard_path.exists() and sample_summary_path.exists():
            existing = json.loads(
                sample_summary_path.read_text(encoding="utf-8")
            )
            if existing.get("contract_sha256") != contract_sha256:
                raise RuntimeError(f"{sample_id}: checkpoint contract mismatch")
            if int(existing.get("max_timepoints", -1)) != max_timepoints:
                raise RuntimeError(f"{sample_id}: checkpoint timepoint mismatch")
            if existing.get("shard_sha256") != _sha256(shard_path):
                raise RuntimeError(f"{sample_id}: checkpoint shard mismatch")
            print(
                f"[{index}/{len(selected_samples)}] {sample_id} checkpoint complete",
                flush=True,
            )
            continue

        print(
            f"[{index}/{len(selected_samples)}] {sample_id} "
            f"fold={folds[sample_id]} max_timepoints={max_timepoints}",
            flush=True,
        )
        graph, detector, link_strategy = _build_v19_prefirewall_with_route(
            args.train_dir / f"{sample_id}.zarr",
            max_timepoints=max_timepoints,
        )
        before = _graph_signature(graph)
        definition = contract["reference_definition"]
        audit = extract_continuation_references(
            graph,
            registered_division_times=division_times.get(sample_id, set()),
            exclusion_radius_frames=int(
                definition["exclude_within_frames_of_registered_division"]
            ),
            local_radius_um=float(definition["local_action_radius_um"]),
            tie_tolerance_um=float(definition["strict_tie_tolerance_um"]),
        )
        if before != _graph_signature(graph):
            raise RuntimeError(f"{sample_id}: audit mutated source graph")
        rows = [reference_as_row(reference) for reference in audit.references]
        _atomic_write_csv_gz(shard_path, rows)
        summary = _summarize_sample(
            sample_id=sample_id,
            fold=folds[sample_id],
            detector=detector,
            link_strategy=link_strategy,
            graph=graph,
            audit=audit,
            contract_sha256=contract_sha256,
            max_timepoints=max_timepoints,
            shard_path=shard_path,
        )
        _atomic_write_json(sample_summary_path, summary)
        print(
            f"  route={summary['route']} refs={summary['references']} "
            f"with_alternatives={summary['references_with_alternatives']} "
            f"near_division_rejected="
            f"{summary['rejection_reasons'].get('near_registered_division', 0)}",
            flush=True,
        )

        all_summaries = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(args.output_dir.glob("*.summary.json"))
            if path.name.removesuffix(".summary.json") in folds
            and json.loads(path.read_text(encoding="utf-8")).get(
                "contract_sha256"
            )
            == contract_sha256
            and int(
                json.loads(path.read_text(encoding="utf-8")).get(
                    "max_timepoints", -1
                )
            )
            == max_timepoints
        ]
        aggregate = _aggregate_summary(
            all_summaries,
            expected_samples=len(folds),
            contract=contract,
            contract_sha256=contract_sha256,
        )
        _atomic_write_json(args.summary, aggregate)

    all_summaries = []
    for path in sorted(args.output_dir.glob("*.summary.json")):
        sample_id = path.name.removesuffix(".summary.json")
        if sample_id not in folds:
            continue
        summary = json.loads(path.read_text(encoding="utf-8"))
        if summary.get("contract_sha256") != contract_sha256:
            raise RuntimeError(f"{sample_id}: stale contract in output directory")
        if int(summary.get("max_timepoints", -1)) != max_timepoints:
            raise RuntimeError(f"{sample_id}: stale timepoint scope")
        shard_path = args.output_dir / f"{sample_id}.csv.gz"
        if summary.get("shard_sha256") != _sha256(shard_path):
            raise RuntimeError(f"{sample_id}: shard hash mismatch")
        all_summaries.append(summary)
    aggregate = _aggregate_summary(
        all_summaries,
        expected_samples=len(folds),
        contract=contract,
        contract_sha256=contract_sha256,
    )
    _atomic_write_json(args.summary, aggregate)
    print(json.dumps(aggregate, indent=2, sort_keys=True), flush=True)
    print(f"Wrote {args.summary}", flush=True)


if __name__ == "__main__":
    main()
