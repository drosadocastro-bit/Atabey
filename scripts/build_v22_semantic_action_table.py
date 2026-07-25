from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from atabey.tracking.unet_action_availability import (
    action_matches_registered_division,
    enumerate_anchored_division_actions,
    label_action_as_official_fork,
)
from atabey.tracking.unet_semantic_dataset import (
    select_actions_for_official_labeling,
)
from atabey.tracking.unet_semantic_features import (
    build_event_feature_context,
    division_action_feature_row,
    semantic_action_id,
)
from run_v21_division_recovery_shadow import _build_v19_prefirewall_with_route
from run_v22_unet_official_action_availability import _graph_signature, _read_peaks


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_hash(path: Path, expected: str, label: str) -> None:
    actual = _sha256(path)
    if actual != expected:
        raise RuntimeError(f"{label} SHA-256 mismatch: {actual} != {expected}")


def _atomic_write_csv_gz(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("Cannot write an empty action shard")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with gzip.open(temporary, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _fold_map(contract: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for fold in contract["folds"]:
        fold_id = int(fold["fold"])
        for sample_id in fold["samples"]:
            if sample_id in result:
                raise RuntimeError(f"Sample appears in multiple folds: {sample_id}")
            result[sample_id] = fold_id
    return result


def _event_id(sample_id: str, t: int) -> str:
    return f"{sample_id}:t{int(t)}"


def _read_event_expectations(path: Path) -> dict[str, dict[str, int]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            grouped[_event_id(row["sample_id"], int(row["t"]))].append(row)

    expectations: dict[str, dict[str, int]] = {}
    for event_id, rows in grouped.items():
        action_counts = {int(row["division_action_count"]) for row in rows}
        if len(action_counts) != 1:
            raise RuntimeError(f"{event_id}: inconsistent pinned action counts")
        expectations[event_id] = {
            "actions": action_counts.pop(),
            "official_tp_actions": sum(
                int(row["official_tp_action_count"]) for row in rows
            ),
        }
    return expectations


def _load_inputs(
    contract_path: Path,
    project_root_path: Path,
    peak_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    source_action_path = project_root_path / contract["source_action_availability_csv"]

    source_contract_path = project_root_path / contract["source_contract"]
    _verify_hash(
        source_action_path,
        contract["source_action_availability_sha256"],
        "Action-availability CSV",
    )
    _verify_hash(peak_path, contract["source_peak_sha256"], "Peak CSV")
    _verify_hash(
        source_contract_path,
        contract["source_contract_sha256"],
        "Official-action contract",
    )

    source_contract = json.loads(
        source_contract_path.read_text(encoding="utf-8-sig")
    )
    source_fixture_path = project_root_path / source_contract["source_fixture"]
    _verify_hash(
        source_fixture_path,
        source_contract["source_fixture_sha256"],
        "Development-case fixture",
    )
    fixture = json.loads(source_fixture_path.read_text(encoding="utf-8-sig"))
    return contract, source_contract, fixture


def _sample_summary_from_shard(path: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    events: set[str] = set()
    rows = 0
    selected = 0
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            events.add(row["event_id"])
            label = row["official_label"]
            counts[label] += 1
            selected += int(label != "not_evaluated")
    return {
        "sample_id": path.name.removesuffix(".csv.gz"),
        "events": len(events),
        "actions": rows,
        "selected_for_official_scoring": selected,
        "official_labels": dict(sorted(counts.items())),
        "shard": str(path),
        "shard_sha256": _sha256(path),
    }


def _build_sample(
    *,
    sample_id: str,
    cases: list[dict[str, Any]],
    fold: int,
    peaks: list[Any],
    train_dir: Path,
    output_dir: Path,
    source_contract: dict[str, Any],
    label_contract: dict[str, Any],
    event_expectations: dict[str, dict[str, int]],
    contract_sha256: str,
    peak_sha256: str,
) -> dict[str, Any]:
    max_timepoints = max(int(case["t"]) for case in cases) + 2
    graph, detector, link_strategy = _build_v19_prefirewall_with_route(
        train_dir / f"{sample_id}.zarr",
        max_timepoints=max_timepoints,
    )
    ground_truth = read_geff_graph(train_dir / f"{sample_id}.geff")
    gt_nodes = {int(node.node_id): node for node in ground_truth.nodes}
    before = _graph_signature(graph)
    rows: list[dict[str, Any]] = []
    case_ids_by_t: dict[int, list[str]] = defaultdict(list)
    for case in cases:
        case_ids_by_t[int(case["t"])].append(case["case_id"])

    for parent_t in sorted(case_ids_by_t):
        event_cases = [case for case in cases if int(case["t"]) == parent_t]
        enumeration = enumerate_anchored_division_actions(
            graph,
            peaks,
            parent_t=parent_t,
            anchor_radius_um=float(source_contract["parent_anchor_radius_um"]),
            formation_radius_um=float(
                source_contract["daughter_formation_radius_um"]
            ),
        )
        event_id = _event_id(sample_id, parent_t)
        expected = event_expectations[event_id]
        if enumeration.division_action_count != expected["actions"]:
            raise RuntimeError(
                f"{event_id}: regenerated {enumeration.division_action_count} "
                f"actions, expected {expected['actions']}"
            )
        context = build_event_feature_context(graph, peaks, enumeration)
        registered = []
        for action in enumeration.actions:
            if any(
                action_matches_registered_division(
                    action,
                    parent_position_um=gt_nodes[int(case["gt_parent_id"])].position_um,
                    daughter_positions_um=(
                        gt_nodes[int(case["gt_child_ids"][0])].position_um,
                        gt_nodes[int(case["gt_child_ids"][1])].position_um,
                    ),
                    match_radius_um=float(source_contract["official_match_radius_um"]),
                )
                for case in event_cases
            ):
                registered.append(action)

        official_positive_actions = [
            action
            for action in registered
            if label_action_as_official_fork(action, ground_truth) == "official_tp"
        ]
        if len(official_positive_actions) != expected["official_tp_actions"]:
            raise RuntimeError(
                f"{event_id}: regenerated {len(official_positive_actions)} "
                f"official TP actions, expected {expected['official_tp_actions']}"
            )
        selection = select_actions_for_official_labeling(
            enumeration.actions,
            official_positive_actions,
            conflict_cap_per_positive=int(
                label_contract["conflict_negative_cap_per_positive"]
            ),
            background_cap_per_event=int(
                label_contract["background_negative_hash_sample_per_event"]
            ),
            namespace=f"v22-semantic-label-v1|{sample_id}|{parent_t}",
        )
        action_by_id = {
            semantic_action_id(action): action for action in enumeration.actions
        }
        labels = {
            action_id: label_action_as_official_fork(
                action_by_id[action_id], ground_truth
            )
            for action_id in selection
        }
        registered_ids = {
            semantic_action_id(action) for action in official_positive_actions
        }
        for action in enumeration.actions:
            action_id = semantic_action_id(action)
            row = division_action_feature_row(action, context)
            row.update(
                {
                    "fold": fold,
                    "event_id": event_id,
                    "case_ids": json.dumps(
                        sorted(case_ids_by_t[parent_t]), separators=(",", ":")
                    ),
                    "source_detector": detector,
                    "source_link_strategy": link_strategy,
                    "registered_official_positive": action_id in registered_ids,
                    "label_selection_reasons": json.dumps(
                        selection.get(action_id, ()), separators=(",", ":")
                    ),
                    "official_label": labels.get(action_id, "not_evaluated"),
                    "eligible_supervised_positive": (
                        labels.get(action_id) == "official_tp"
                    ),
                    "eligible_supervised_negative": (
                        labels.get(action_id) == "official_fp"
                    ),
                    "semantic_score": "",
                    "assignment_selected": False,
                    "graph_mutated": False,
                }
            )
            rows.append(row)

        event_counts = Counter(labels.values())
        print(
            f"  t={parent_t}: actions={len(enumeration.actions)} "
            f"selected={len(selection)} labels={dict(sorted(event_counts.items()))}",
            flush=True,
        )

    if before != _graph_signature(graph):
        raise RuntimeError(f"{sample_id}: semantic evidence build mutated source graph")
    rows.sort(key=lambda row: (int(row["t"]), row["action_id"]))
    shard_path = output_dir / f"{sample_id}.csv.gz"
    _atomic_write_csv_gz(shard_path, rows)
    summary = _sample_summary_from_shard(shard_path)
    summary.update(
        {
            "fold": fold,
            "source_detector": detector,
            "source_link_strategy": link_strategy,
            "source_zero_perturbation": True,
            "contract_sha256": contract_sha256,
            "peak_sha256": peak_sha256,
        }
    )
    _atomic_write_json(output_dir / f"{sample_id}.summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build fold-safe V22 division-action features and patched-official "
            "labels without fitting a model or mutating a graph."
        )
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=project_root
        / "tests/fixtures/v22_joint_semantic_assignment_development.json",
    )
    parser.add_argument(
        "--peaks",
        type=Path,
        default=project_root / "v22_unet_detection_development_46_peaks.csv",
    )
    parser.add_argument("--train-dir", type=Path, default=project_root / "train")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "v22_semantic_action_shards",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=project_root / "v22_semantic_action_table_summary.json",
    )
    parser.add_argument("--sample-ids", nargs="*", default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    contract, source_contract, fixture = _load_inputs(
        args.contract,
        project_root,
        args.peaks,
    )
    contract_sha256 = _sha256(args.contract)
    peak_sha256 = _sha256(args.peaks)
    event_expectations = _read_event_expectations(
        project_root / contract["source_action_availability_csv"]
    )
    logging.getLogger("tracksdata.utils._logging").setLevel(logging.ERROR)
    if contract["semantic_scoring_enabled"] or contract["assignment_enabled"]:
        raise RuntimeError("Evidence builder requires scoring and assignment disabled")
    if contract["production_graph_mutation_enabled"]:
        raise RuntimeError("Evidence builder requires production mutation disabled")

    folds = _fold_map(contract)
    peaks_by_sample = _read_peaks(args.peaks)
    cases_by_sample: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in fixture["cases"]:
        cases_by_sample[case["sample_id"]].append(case)
    if set(cases_by_sample) != set(folds):
        raise RuntimeError("Fixture samples do not exactly match frozen fold samples")

    selected_samples = (
        sorted(set(args.sample_ids))
        if args.sample_ids
        else sorted(cases_by_sample)
    )
    unknown = sorted(set(selected_samples) - set(cases_by_sample))
    if unknown:
        raise ValueError(f"Unknown development samples: {unknown}")

    summaries: list[dict[str, Any]] = []
    for index, sample_id in enumerate(selected_samples, start=1):
        shard_path = args.output_dir / f"{sample_id}.csv.gz"
        summary_path = args.output_dir / f"{sample_id}.summary.json"
        if args.resume and shard_path.exists() and summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            if summary.get("shard_sha256") != _sha256(shard_path):
                raise RuntimeError(f"{sample_id}: checkpoint shard hash mismatch")
            if summary.get("contract_sha256") != contract_sha256:
                raise RuntimeError(f"{sample_id}: checkpoint contract hash mismatch")
            if summary.get("peak_sha256") != peak_sha256:
                raise RuntimeError(f"{sample_id}: checkpoint peak hash mismatch")
            print(
                f"[{index}/{len(selected_samples)}] {sample_id} checkpoint complete",
                flush=True,
            )
        else:
            print(
                f"[{index}/{len(selected_samples)}] {sample_id} fold={folds[sample_id]}",
                flush=True,
            )
            summary = _build_sample(
                sample_id=sample_id,
                cases=cases_by_sample[sample_id],
                fold=folds[sample_id],
                peaks=peaks_by_sample.get(sample_id, []),
                train_dir=args.train_dir,
                output_dir=args.output_dir,
                source_contract=source_contract,
                label_contract=contract["labels"],
                event_expectations=event_expectations,
                contract_sha256=contract_sha256,
                peak_sha256=peak_sha256,
            )
        summaries.append(summary)

    complete_summaries = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(args.output_dir.glob("*.summary.json"))
        if path.stem.removesuffix(".summary") in folds
    ]
    for summary in complete_summaries:
        if summary.get("contract_sha256") != contract_sha256:
            raise RuntimeError(
                f"{summary['sample_id']}: output directory has a stale contract"
            )
        if summary.get("peak_sha256") != peak_sha256:
            raise RuntimeError(
                f"{summary['sample_id']}: output directory has stale peaks"
            )
    label_counts: Counter[str] = Counter()
    for summary in complete_summaries:
        label_counts.update(summary["official_labels"])
    aggregate = {
        "contract": contract["name"],
        "contract_sha256": contract_sha256,
        "peak_sha256": peak_sha256,
        "completed_samples": len(complete_summaries),
        "expected_samples": len(folds),
        "completed_folds": sorted(
            {int(summary["fold"]) for summary in complete_summaries}
        ),
        "actions": sum(int(summary["actions"]) for summary in complete_summaries),
        "expected_development_actions": sum(
            expected["actions"] for expected in event_expectations.values()
        ),
        "expected_official_tp_actions": sum(
            expected["official_tp_actions"]
            for expected in event_expectations.values()
        ),
        "selected_for_official_scoring": sum(
            int(summary["selected_for_official_scoring"])
            for summary in complete_summaries
        ),
        "official_labels": dict(sorted(label_counts.items())),
        "source_zero_perturbation": all(
            bool(summary["source_zero_perturbation"])
            for summary in complete_summaries
        ),
        "semantic_scoring_enabled": False,
        "assignment_enabled": False,
        "graph_mutated": False,
        "full_development_complete": len(complete_summaries) == len(folds),
    }
    _atomic_write_json(args.summary, aggregate)
    print(json.dumps(aggregate, indent=2, sort_keys=True), flush=True)
    print(f"Wrote {args.summary}", flush=True)


if __name__ == "__main__":
    main()
