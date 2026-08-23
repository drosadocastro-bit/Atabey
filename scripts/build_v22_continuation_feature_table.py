from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.tracking.continuation_features import (
    CONTINUATION_FEATURE_NAMES,
    iter_continuation_candidate_rows,
)
from atabey.tracking.continuation_reference import (
    ContinuationReference,
    extract_continuation_references,
)
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route
from run_v22_unet_official_action_availability import _graph_signature


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


def _load_contracts(
    contract_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    reference_contract_path = project_root / contract["source_reference_contract"]
    reference_summary_path = project_root / contract["source_reference_summary"]
    _verify_hash(
        reference_contract_path,
        contract["source_reference_contract_sha256"],
        "Reference contract",
    )
    _verify_hash(
        reference_summary_path,
        contract["source_reference_summary_sha256"],
        "Reference summary",
    )
    reference_contract = json.loads(
        reference_contract_path.read_text(encoding="utf-8-sig")
    )
    reference_summary = json.loads(
        reference_summary_path.read_text(encoding="utf-8-sig")
    )
    if reference_summary["decision"] != "GO_TO_CONTINUATION_TABLE_BUILD":
        raise RuntimeError("Reference availability audit did not authorize table build")
    semantic_path = project_root / reference_contract["source_semantic_contract"]
    division_path = project_root / reference_contract["source_division_fixture"]
    _verify_hash(
        semantic_path,
        reference_contract["source_semantic_contract_sha256"],
        "Semantic contract",
    )
    _verify_hash(
        division_path,
        reference_contract["source_division_fixture_sha256"],
        "Division fixture",
    )
    semantic_contract = json.loads(semantic_path.read_text(encoding="utf-8-sig"))
    division_fixture = json.loads(division_path.read_text(encoding="utf-8-sig"))
    return contract, reference_contract, semantic_contract, division_fixture


def _fold_map(semantic_contract: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for fold in semantic_contract["folds"]:
        for sample_id in fold["samples"]:
            if sample_id in result:
                raise RuntimeError(f"Sample appears in multiple folds: {sample_id}")
            result[sample_id] = int(fold["fold"])
    return result


def _read_source_references(
    *,
    sample_id: str,
    source_dir: Path,
    expected_contract_sha256: str,
) -> tuple[list[ContinuationReference], dict[str, Any], str]:
    shard_path = source_dir / f"{sample_id}.csv.gz"
    summary_path = source_dir / f"{sample_id}.summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary["contract_sha256"] != expected_contract_sha256:
        raise RuntimeError(f"{sample_id}: stale source reference contract")
    if summary["shard_sha256"] != _sha256(shard_path):
        raise RuntimeError(f"{sample_id}: source reference shard hash mismatch")

    references: list[ContinuationReference] = []
    with gzip.open(shard_path, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            references.append(
                ContinuationReference(
                    reference_id=row["reference_id"],
                    sample_id=row["sample_id"],
                    anchor_id=row["anchor_id"],
                    parent_id=row["parent_id"],
                    child_id=row["child_id"],
                    anchor_t=int(row["anchor_t"]),
                    parent_t=int(row["parent_t"]),
                    child_t=int(row["child_t"]),
                    anchor_parent_distance_um=float(
                        row["anchor_parent_distance_um"]
                    ),
                    parent_child_distance_um=float(
                        row["parent_child_distance_um"]
                    ),
                    prediction_error_um=float(row["prediction_error_um"]),
                    forward_margin_um=_optional_float(row["forward_margin_um"]),
                    reverse_margin_um=_optional_float(row["reverse_margin_um"]),
                    local_target_count_14um=int(row["local_target_count_14um"]),
                    alternative_target_count_14um=int(
                        row["alternative_target_count_14um"]
                    ),
                    local_competing_source_count_14um=int(
                        row["local_competing_source_count_14um"]
                    ),
                )
            )
    return references, summary, _sha256(shard_path)


def _optional_float(value: str) -> float | None:
    return None if value == "" else float(value)


def _reference_map(
    references: list[ContinuationReference],
) -> dict[str, ContinuationReference]:
    result = {reference.reference_id: reference for reference in references}
    if len(result) != len(references):
        raise RuntimeError("Source reference IDs are not unique")
    return result


def _assert_rebuilt_reference_parity(
    source: list[ContinuationReference],
    rebuilt: tuple[ContinuationReference, ...],
    *,
    tolerance: float = 1e-9,
) -> float:
    source_map = _reference_map(source)
    rebuilt_map = _reference_map(list(rebuilt))
    if set(source_map) != set(rebuilt_map):
        missing = sorted(set(source_map) - set(rebuilt_map))[:5]
        extra = sorted(set(rebuilt_map) - set(source_map))[:5]
        raise RuntimeError(
            f"Rebuilt reference IDs differ: missing={missing}, extra={extra}"
        )
    maximum_delta = 0.0
    for reference_id, expected in source_map.items():
        actual = rebuilt_map[reference_id]
        for field in (
            "anchor_parent_distance_um",
            "parent_child_distance_um",
            "prediction_error_um",
            "forward_margin_um",
            "reverse_margin_um",
        ):
            first = getattr(expected, field)
            second = getattr(actual, field)
            if first is None or second is None:
                if first is not second:
                    raise RuntimeError(
                        f"{reference_id}: {field} availability mismatch"
                    )
                continue
            delta = abs(float(first) - float(second))
            maximum_delta = max(maximum_delta, delta)
            if delta > tolerance:
                raise RuntimeError(
                    f"{reference_id}: {field} delta {delta} exceeds {tolerance}"
                )
        for field in (
            "local_target_count_14um",
            "alternative_target_count_14um",
            "local_competing_source_count_14um",
        ):
            if getattr(expected, field) != getattr(actual, field):
                raise RuntimeError(f"{reference_id}: {field} mismatch")
    return maximum_delta


def _build_sample(
    *,
    sample_id: str,
    fold: int,
    division_times: set[int],
    train_dir: Path,
    source_dir: Path,
    output_dir: Path,
    contract: dict[str, Any],
    reference_contract: dict[str, Any],
    contract_sha256: str,
) -> dict[str, Any]:
    source_references, source_summary, source_shard_sha256 = (
        _read_source_references(
            sample_id=sample_id,
            source_dir=source_dir,
            expected_contract_sha256=contract[
                "source_reference_contract_sha256"
            ],
        )
    )
    graph, detector, link_strategy = _build_v19_prefirewall_with_route(
        train_dir / f"{sample_id}.zarr",
        max_timepoints=int(contract["max_timepoints"]),
    )
    before = _graph_signature(graph)
    definition = reference_contract["reference_definition"]
    rebuilt_audit = extract_continuation_references(
        graph,
        registered_division_times=division_times,
        exclusion_radius_frames=int(
            definition["exclude_within_frames_of_registered_division"]
        ),
        local_radius_um=float(definition["local_action_radius_um"]),
        tie_tolerance_um=float(definition["strict_tie_tolerance_um"]),
    )
    source_metric_max_delta = _assert_rebuilt_reference_parity(
        source_references, rebuilt_audit.references
    )
    if before != _graph_signature(graph):
        raise RuntimeError(f"{sample_id}: reference rebuild mutated source graph")

    candidate_definition = contract["candidate_definition"]
    shard_path = output_dir / f"{sample_id}.csv.gz"
    shard_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = shard_path.with_name(shard_path.name + ".tmp")
    candidate_ids: set[str] = set()
    reference_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    missing_counts: Counter[str] = Counter()
    rows = 0
    weight_sum = 0.0
    max_reference_feature_delta = 0.0
    fieldnames: list[str] | None = None
    source_by_id = _reference_map(source_references)

    with gzip.open(temporary, "wt", newline="", encoding="utf-8") as handle:
        writer: csv.DictWriter | None = None
        for row in iter_continuation_candidate_rows(
            graph,
            rebuilt_audit.references,
            fold=fold,
            detector=detector,
            link_strategy=link_strategy,
            local_radius_um=float(candidate_definition["local_action_radius_um"]),
            density_radius_um=float(candidate_definition["density_radius_um"]),
        ):
            if writer is None:
                fieldnames = list(row)
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
            candidate_id = str(row["candidate_id"])
            if candidate_id in candidate_ids:
                raise RuntimeError(f"{sample_id}: duplicate candidate ID")
            candidate_ids.add(candidate_id)
            reference_id = str(row["reference_id"])
            reference_counts[reference_id] += 1
            role_counts[str(row["candidate_role"])] += 1
            weight_sum += float(row["sample_hierarchical_weight"])
            if int(row["weak_preference_target"]) == 1:
                expected = source_by_id[reference_id]
                for field in (
                    "anchor_parent_distance_um",
                    "parent_child_distance_um",
                    "prediction_error_um",
                    "forward_competitor_margin_um",
                    "reverse_competitor_margin_um",
                ):
                    source_field = {
                        "forward_competitor_margin_um": "forward_margin_um",
                        "reverse_competitor_margin_um": "reverse_margin_um",
                    }.get(field, field)
                    expected_value = getattr(expected, source_field)
                    actual_value = row[field]
                    if expected_value is None or actual_value is None:
                        if expected_value is not actual_value:
                            raise RuntimeError(
                                f"{reference_id}: {field} availability mismatch"
                            )
                    else:
                        max_reference_feature_delta = max(
                            max_reference_feature_delta,
                            abs(float(expected_value) - float(actual_value)),
                        )
            for feature, reason in json.loads(row["missing_features"]).items():
                missing_counts[f"{feature}:{reason}"] += 1
            for feature in CONTINUATION_FEATURE_NAMES:
                value = row[feature]
                if value is not None and not math.isfinite(float(value)):
                    raise RuntimeError(
                        f"{sample_id}: non-finite available feature {feature}"
                    )
            writer.writerow(row)
            rows += 1
    if fieldnames is None:
        raise RuntimeError(f"{sample_id}: no continuation candidates produced")
    os.replace(temporary, shard_path)

    expected_reference_ids = set(source_by_id)
    if set(reference_counts) != expected_reference_ids:
        raise RuntimeError(f"{sample_id}: candidate groups differ from references")
    if role_counts["weak_reference_preferred"] != len(source_references):
        raise RuntimeError(f"{sample_id}: not exactly one reference row per group")
    expected_rows = sum(
        1 + reference.alternative_target_count_14um
        for reference in source_references
    )
    if rows != expected_rows:
        raise RuntimeError(
            f"{sample_id}: candidate rows {rows} != expected {expected_rows}"
        )
    if abs(weight_sum - 1.0) > float(
        contract["decision_contract"]["sample_weight_sum_tolerance"]
    ):
        raise RuntimeError(f"{sample_id}: hierarchical weight sum is {weight_sum}")
    if max_reference_feature_delta > 1e-9:
        raise RuntimeError(
            f"{sample_id}: reference feature delta {max_reference_feature_delta}"
        )
    if before != _graph_signature(graph):
        raise RuntimeError(f"{sample_id}: feature build mutated source graph")

    summary = {
        "sample_id": sample_id,
        "fold": int(fold),
        "family": sample_id.split("_", 1)[0],
        "route": f"{detector}/{link_strategy}",
        "references": len(source_references),
        "alternatives": expected_rows - len(source_references),
        "candidate_rows": rows,
        "candidate_ids_unique": len(candidate_ids) == rows,
        "reference_groups": len(reference_counts),
        "weak_reference_rows": role_counts["weak_reference_preferred"],
        "weak_alternative_rows": role_counts["weak_alternative_unknown"],
        "sample_hierarchical_weight_sum": weight_sum,
        "source_reference_metric_max_delta": source_metric_max_delta,
        "reference_feature_max_delta": max_reference_feature_delta,
        "missing_feature_reasons": dict(sorted(missing_counts.items())),
        "source_reference_shard_sha256": source_shard_sha256,
        "source_reference_summary_route": source_summary["route"],
        "source_zero_perturbation": True,
        "all_features_finite_when_available": True,
        "semantic_scores_present": 0,
        "assignment_selections": 0,
        "graph_mutated": False,
        "shard": str(shard_path),
        "shard_sha256": _sha256(shard_path),
        "contract_sha256": contract_sha256,
    }
    _atomic_write_json(output_dir / f"{sample_id}.summary.json", summary)
    return summary


def _aggregate(
    summaries: list[dict[str, Any]],
    *,
    contract: dict[str, Any],
    contract_sha256: str,
    expected_samples: int,
) -> dict[str, Any]:
    def grouped(key: str) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for summary in summaries:
            counts[str(summary[key])] += int(summary["candidate_rows"])
        return dict(sorted(counts.items()))

    population = contract["expected_population"]
    by_fold = grouped("fold")
    by_family = grouped("family")
    by_route = grouped("route")
    rows = sum(int(summary["candidate_rows"]) for summary in summaries)
    references = sum(int(summary["references"]) for summary in summaries)
    alternatives = sum(int(summary["alternatives"]) for summary in summaries)
    sample_counts = sorted(
        (
            (str(summary["sample_id"]), int(summary["candidate_rows"]))
            for summary in summaries
        ),
        key=lambda item: (-item[1], item[0]),
    )
    squared_sample_rows = sum(count * count for _sample, count in sample_counts)
    missing_feature_reasons: Counter[str] = Counter()
    for summary in summaries:
        missing_feature_reasons.update(summary["missing_feature_reasons"])
    complete = len(summaries) == expected_samples
    gates = {
        "samples": len(summaries) == int(population["samples"]),
        "references": references == int(population["references"]),
        "alternatives": alternatives == int(population["alternatives"]),
        "candidate_rows": rows == int(population["candidate_rows"]),
        "candidate_rows_by_fold": by_fold
        == population["candidate_rows_by_fold"],
        "candidate_rows_by_family": by_family
        == population["candidate_rows_by_family"],
        "candidate_rows_by_route": by_route
        == population["candidate_rows_by_route"],
        "candidate_ids_unique": all(
            bool(summary["candidate_ids_unique"]) for summary in summaries
        ),
        "one_reference_candidate_per_reference": all(
            int(summary["weak_reference_rows"]) == int(summary["references"])
            for summary in summaries
        ),
        "reference_ids_match_source": all(
            int(summary["reference_groups"]) == int(summary["references"])
            for summary in summaries
        ),
        "reference_metrics_match_source": all(
            float(summary["source_reference_metric_max_delta"]) <= 1e-9
            and float(summary["reference_feature_max_delta"]) <= 1e-9
            for summary in summaries
        ),
        "sample_weights": all(
            abs(float(summary["sample_hierarchical_weight_sum"]) - 1.0)
            <= float(
                contract["decision_contract"]["sample_weight_sum_tolerance"]
            )
            for summary in summaries
        ),
        "source_zero_perturbation": all(
            bool(summary["source_zero_perturbation"]) for summary in summaries
        ),
        "all_features_finite_when_available": all(
            bool(summary["all_features_finite_when_available"])
            for summary in summaries
        ),
        "closed_scopes": all(
            int(summary["semantic_scores_present"]) == 0
            and int(summary["assignment_selections"]) == 0
            and not bool(summary["graph_mutated"])
            for summary in summaries
        ),
    }
    return {
        "contract": contract["name"],
        "contract_sha256": contract_sha256,
        "completed_samples": len(summaries),
        "expected_samples": expected_samples,
        "complete": complete,
        "decision": (
            "GO_TO_OUT_OF_FOLD_CONTINUATION_HEAD"
            if complete and all(gates.values())
            else "NO_GO" if complete else "INCOMPLETE"
        ),
        "gates": gates,
        "references": references,
        "alternatives": alternatives,
        "candidate_rows": rows,
        "candidate_rows_by_fold": by_fold,
        "candidate_rows_by_family": by_family,
        "candidate_rows_by_route": by_route,
        "raw_row_concentration": {
            "effective_sample_size": (
                rows * rows / squared_sample_rows if squared_sample_rows else 0.0
            ),
            "top_sample_share": (
                sample_counts[0][1] / rows if rows and sample_counts else None
            ),
            "top_three_sample_share": (
                sum(count for _sample, count in sample_counts[:3]) / rows
                if rows
                else None
            ),
            "largest_samples": [
                {"sample_id": sample_id, "candidate_rows": count}
                for sample_id, count in sample_counts[:10]
            ],
        },
        "maximum_sample_weight_deviation": max(
            (
                abs(float(summary["sample_hierarchical_weight_sum"]) - 1.0)
                for summary in summaries
            ),
            default=0.0,
        ),
        "maximum_source_reference_metric_delta": max(
            (
                float(summary["source_reference_metric_max_delta"])
                for summary in summaries
            ),
            default=0.0,
        ),
        "maximum_reference_feature_delta": max(
            (
                float(summary["reference_feature_max_delta"])
                for summary in summaries
            ),
            default=0.0,
        ),
        "missing_feature_reasons": dict(sorted(missing_feature_reasons.items())),
        "local_maxima_reporting": {
            "candidate_rows": by_route.get("local_maxima/motion_mutual", 0),
            "development_samples": int(
                contract["reporting"]["local_maxima_development_samples"]
            ),
            "development_fold": int(
                contract["reporting"]["local_maxima_development_fold"]
            ),
            "generalization_status": "unproven",
            "required_metric_caveat": contract["reporting"][
                "local_maxima_required_metric_caveat"
            ],
        },
        "semantic_scoring_enabled": False,
        "model_fitting_enabled": False,
        "assignment_enabled": False,
        "graph_mutated": False,
        "full_199_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build the fold-safe V22 weak continuation feature table without "
            "model fitting, assignment, or graph mutation."
        )
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=project_root
        / "tests/fixtures/v22_continuation_feature_table.json",
    )
    parser.add_argument("--train-dir", type=Path, default=project_root / "train")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "v22_continuation_feature_shards",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=project_root / "v22_continuation_feature_table_summary.json",
    )
    parser.add_argument("--sample-ids", nargs="*", default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    contract, reference_contract, semantic_contract, division_fixture = (
        _load_contracts(args.contract)
    )
    if any(
        bool(contract[key])
        for key in (
            "semantic_scoring_enabled",
            "model_fitting_enabled",
            "assignment_enabled",
            "production_graph_mutation_enabled",
            "locked_validation_opened",
            "full_199_authorized",
        )
    ):
        raise RuntimeError("Continuation table builder requires all closed scopes")
    if tuple(contract["feature_contract"]["model_feature_allowlist"]) != (
        CONTINUATION_FEATURE_NAMES
    ):
        raise RuntimeError("Feature implementation and contract allowlist differ")

    contract_sha256 = _sha256(args.contract)
    folds = _fold_map(semantic_contract)
    division_times: dict[str, set[int]] = defaultdict(set)
    for case in division_fixture["cases"]:
        division_times[case["sample_id"]].add(int(case["t"]))
    selected_samples = (
        sorted(set(args.sample_ids)) if args.sample_ids else sorted(folds)
    )
    unknown = sorted(set(selected_samples) - set(folds))
    if unknown:
        raise ValueError(f"Unknown development samples: {unknown}")

    source_dir = project_root / contract["source_reference_shards"]
    for index, sample_id in enumerate(selected_samples, start=1):
        shard_path = args.output_dir / f"{sample_id}.csv.gz"
        summary_path = args.output_dir / f"{sample_id}.summary.json"
        if args.resume and shard_path.exists() and summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            if summary["contract_sha256"] != contract_sha256:
                raise RuntimeError(f"{sample_id}: checkpoint contract mismatch")
            if summary["shard_sha256"] != _sha256(shard_path):
                raise RuntimeError(f"{sample_id}: checkpoint shard mismatch")
            print(
                f"[{index}/{len(selected_samples)}] {sample_id} checkpoint complete",
                flush=True,
            )
            continue
        print(
            f"[{index}/{len(selected_samples)}] {sample_id} fold={folds[sample_id]}",
            flush=True,
        )
        summary = _build_sample(
            sample_id=sample_id,
            fold=folds[sample_id],
            division_times=division_times.get(sample_id, set()),
            train_dir=args.train_dir,
            source_dir=source_dir,
            output_dir=args.output_dir,
            contract=contract,
            reference_contract=reference_contract,
            contract_sha256=contract_sha256,
        )
        print(
            f"  route={summary['route']} refs={summary['references']} "
            f"candidates={summary['candidate_rows']} "
            f"weight={summary['sample_hierarchical_weight_sum']:.12f}",
            flush=True,
        )

        current = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(args.output_dir.glob("*.summary.json"))
            if path.name.removesuffix(".summary.json") in folds
            and json.loads(path.read_text(encoding="utf-8")).get(
                "contract_sha256"
            )
            == contract_sha256
        ]
        _atomic_write_json(
            args.summary,
            _aggregate(
                current,
                contract=contract,
                contract_sha256=contract_sha256,
                expected_samples=len(folds),
            ),
        )

    summaries: list[dict[str, Any]] = []
    for path in sorted(args.output_dir.glob("*.summary.json")):
        sample_id = path.name.removesuffix(".summary.json")
        if sample_id not in folds:
            continue
        summary = json.loads(path.read_text(encoding="utf-8"))
        shard_path = args.output_dir / f"{sample_id}.csv.gz"
        if summary["contract_sha256"] != contract_sha256:
            raise RuntimeError(f"{sample_id}: stale output contract")
        if summary["shard_sha256"] != _sha256(shard_path):
            raise RuntimeError(f"{sample_id}: output shard hash mismatch")
        summaries.append(summary)
    aggregate = _aggregate(
        summaries,
        contract=contract,
        contract_sha256=contract_sha256,
        expected_samples=len(folds),
    )
    _atomic_write_json(args.summary, aggregate)
    print(json.dumps(aggregate, indent=2, sort_keys=True), flush=True)
    print(f"Wrote {args.summary}", flush=True)


if __name__ == "__main__":
    main()
