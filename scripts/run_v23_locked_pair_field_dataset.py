"""Build the locked V23 pair-field cache and officially labeled action manifest."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from atabey.evaluation.official_division_metric import evaluate_official_divisions
from atabey.evaluation.semantic_positive_availability import gt_division_window
from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.tracking.pair_field import (
    HALF_EXTENT_UM,
    SPACING_UM,
    extract_parent_field,
    synthetic_integrity_check,
    tensor_sha256,
)
from atabey.types import LineageEdge, LineageGraph
from audit_v23_cfar_pair_field_positive_availability import (
    FORMATION_RADIUS_UM,
    MATCH_RADIUS_UM,
    _detect,
    _distance,
)


NORMALIZATION_VERSION = "v23_pair_field_norm_v1"
FP_HASH_SEED = "v23-pair-field-fp-v1"
FP_CAP_PER_EVENT = 64


@dataclass(frozen=True)
class EventSpec:
    sample_id: str
    gt_parent_id: int
    gt_child_1_id: int
    gt_child_2_id: int
    family: str
    fold: int
    t: int
    expected_tp_actions: int

    @property
    def event_id(self) -> str:
        return f"{self.sample_id}:t{self.t}:gt{self.gt_parent_id}"


def _load_events(path: Path) -> list[EventSpec]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["status"] == "official_positive"
        ]
    return [
        EventSpec(
            sample_id=row["sample_id"],
            gt_parent_id=int(row["gt_parent_id"]),
            gt_child_1_id=int(row["gt_child_1_id"]),
            gt_child_2_id=int(row["gt_child_2_id"]),
            family=row["family"],
            fold=int(row["fold"]),
            t=int(row["t"]),
            expected_tp_actions=int(row["official_tp_action_count"]),
        )
        for row in rows
    ]


def _near(detections, position, radius_um):
    return sorted(
        (
            (item, _distance(item.position_um, position))
            for item in detections
            if _distance(item.position_um, position) <= radius_um
        ),
        key=lambda item: (item[1], item[0].node_id),
    )


def _cache_key(sample_id: str, t: int, parent_id: str) -> str:
    return f"{sample_id}|{t}|{parent_id}|{NORMALIZATION_VERSION}"


def _action_id(event_id: str, parent_id: str, child_1_id: str, child_2_id: str) -> str:
    payload = "|".join((event_id, parent_id, child_1_id, child_2_id))
    return hashlib.sha256(payload.encode()).hexdigest()


def _label_action(parent, child_1, child_2, ground_truth, gt_parent_id: int) -> str:
    graph = LineageGraph(
        sample_id=parent.sample_id,
        detections=[parent, child_1, child_2],
        edges=[
            LineageEdge(parent.node_id, child_1.node_id, relation="division"),
            LineageEdge(parent.node_id, child_2.node_id, relation="division"),
        ],
    )
    result = evaluate_official_divisions(
        graph,
        gt_division_window(ground_truth, gt_parent_id),
    )
    if parent.node_id in result.tp_fork_ids:
        return "official_tp"
    if parent.node_id in result.fp_fork_ids:
        return "official_fp"
    return "official_unsupported"


def _sparse_splat(relative_position_um) -> list[dict]:
    relative = np.asarray(relative_position_um, dtype=np.float64)
    index = relative / SPACING_UM + HALF_EXTENT_UM / SPACING_UM
    if relative.shape != (3,) or np.any(index < 0.0) or np.any(index > 32.0):
        raise ValueError("Sparse splat position falls outside the frozen field")
    low = np.floor(index).astype(int)
    fraction = index - low
    high = np.minimum(low + 1, 32)
    entries = {}
    for z_choice in (0, 1):
        for y_choice in (0, 1):
            for x_choice in (0, 1):
                choices = np.asarray((z_choice, y_choice, x_choice), dtype=int)
                target = np.where(choices == 0, low, high)
                weights = np.where(choices == 0, 1.0 - fraction, fraction)
                weight = float(np.prod(weights))
                key = tuple(int(value) for value in target)
                if weight:
                    entries[key] = entries.get(key, 0.0) + weight
    return [
        {"index_zyx": list(index_zyx), "weight": weight}
        for index_zyx, weight in sorted(entries.items())
    ]


def _pair_sparse_splat(parent, child_1, child_2) -> list[dict]:
    combined = {}
    parent_position = np.asarray(parent.position_um, dtype=np.float64)
    for child in (child_1, child_2):
        relative = np.asarray(child.position_um, dtype=np.float64) - parent_position
        for entry in _sparse_splat(relative):
            key = tuple(entry["index_zyx"])
            combined[key] = combined.get(key, 0.0) + float(entry["weight"])
    return [
        {"index_zyx": list(index_zyx), "weight": weight}
        for index_zyx, weight in sorted(combined.items())
    ]


def _sample_actions(train_dir: str, raw_events: list[dict]) -> dict:
    events = [EventSpec(**item) for item in raw_events]
    sample_id = events[0].sample_id
    train = Path(train_dir)
    ground_truth = read_geff_graph(train / f"{sample_id}.geff")
    gt_nodes = {int(node.node_id): node for node in ground_truth.nodes}
    array = open_competition_array(train / f"{sample_id}.zarr")
    required_frames = sorted({event.t + offset for event in events for offset in (0, 1)})
    detections = {
        t: _detect(sample_id, t, read_timepoint(array, t))
        for t in required_frames
    }

    actions = []
    parents = {}
    event_rows = []
    for event in events:
        gt_parent = gt_nodes[event.gt_parent_id]
        parent_candidates = _near(
            detections[event.t],
            gt_parent.position_um,
            MATCH_RADIUS_UM,
        )
        event_actions = []
        for parent, parent_gt_distance in parent_candidates:
            key = _cache_key(sample_id, event.t, parent.node_id)
            parents[key] = {
                "cache_key": key,
                "sample_id": sample_id,
                "t": event.t,
                "parent_peak_id": parent.node_id,
                "parent_position_um": list(parent.position_um),
            }
            daughters = sorted(
                (
                    item
                    for item in detections[event.t + 1]
                    if _distance(parent.position_um, item.position_um)
                    <= FORMATION_RADIUS_UM
                ),
                key=lambda item: item.node_id,
            )
            for child_1, child_2 in combinations(daughters, 2):
                action_id = _action_id(
                    event.event_id,
                    parent.node_id,
                    child_1.node_id,
                    child_2.node_id,
                )
                label = _label_action(
                    parent,
                    child_1,
                    child_2,
                    ground_truth,
                    event.gt_parent_id,
                )
                row = {
                    "action_id": action_id,
                    "event_id": event.event_id,
                    "sample_id": sample_id,
                    "family": event.family,
                    "fold": event.fold,
                    "t": event.t,
                    "gt_parent_id": event.gt_parent_id,
                    "parent_cache_key": key,
                    "parent_peak_id": parent.node_id,
                    "child_1_peak_id": child_1.node_id,
                    "child_2_peak_id": child_2.node_id,
                    "parent_position_um": list(parent.position_um),
                    "child_1_position_um": list(child_1.position_um),
                    "child_2_position_um": list(child_2.position_um),
                    "child_1_relative_um": (
                        np.asarray(child_1.position_um)
                        - np.asarray(parent.position_um)
                    ).tolist(),
                    "child_2_relative_um": (
                        np.asarray(child_2.position_um)
                        - np.asarray(parent.position_um)
                    ).tolist(),
                    "daughter_pair_sparse_splat": _pair_sparse_splat(
                        parent,
                        child_1,
                        child_2,
                    ),
                    "parent_gt_distance_um": parent_gt_distance,
                    "parent_child_distance_sum_um": _distance(
                        parent.position_um,
                        child_1.position_um,
                    )
                    + _distance(parent.position_um, child_2.position_um),
                    "official_label": label,
                    "selected_for_training": False,
                    "tensor_written": False,
                    "graph_mutated": False,
                }
                actions.append(row)
                event_actions.append(row)

        label_counts = {
            label: sum(row["official_label"] == label for row in event_actions)
            for label in ("official_tp", "official_fp", "official_unsupported")
        }
        event_rows.append(
            {
                "event_id": event.event_id,
                "sample_id": sample_id,
                "family": event.family,
                "fold": event.fold,
                "actions": len(event_actions),
                "expected_tp_actions": event.expected_tp_actions,
                **label_counts,
            }
        )

    return {
        "sample_id": sample_id,
        "actions": actions,
        "parents": list(parents.values()),
        "events": event_rows,
    }


def _select_training_actions(actions: list[dict]) -> None:
    by_event = {}
    for row in actions:
        by_event.setdefault(row["event_id"], []).append(row)
    for event_rows in by_event.values():
        for row in event_rows:
            if row["official_label"] == "official_tp":
                row["selected_for_training"] = True
        fps = [row for row in event_rows if row["official_label"] == "official_fp"]
        fps.sort(
            key=lambda row: hashlib.sha256(
                f"{FP_HASH_SEED}|{row['action_id']}".encode()
            ).hexdigest()
        )
        for row in fps[:FP_CAP_PER_EVENT]:
            row["selected_for_training"] = True


def _readiness(events: list[dict], contract: dict) -> dict:
    ready = [
        event
        for event in events
        if event["official_tp"] > 0 and event["official_fp"] > 0
    ]
    requirements = contract["dataset_readiness"]
    by_family = {
        family: sum(event["family"] == family for event in ready)
        for family in ("44b6", "6bba")
    }
    by_training_complement = {
        str(heldout): sum(event["fold"] != heldout for event in ready)
        for heldout in (1, 2, 3)
    }
    gates = {
        "exact_tp_events": sum(event["official_tp"] > 0 for event in events)
        == requirements["exact_tp_event_count_required"],
        "exact_tp_action_variants": sum(event["official_tp"] for event in events)
        == requirements["exact_tp_action_variant_count_required"],
        "events_with_tp_and_fp_overall": len(ready)
        >= requirements["minimum_events_with_tp_and_fp_overall"],
        "events_with_tp_and_fp_per_family": all(
            count >= requirements["minimum_events_with_tp_and_fp_per_family"]
            for count in by_family.values()
        ),
        "events_with_tp_and_fp_per_training_complement": all(
            count
            >= requirements["minimum_events_with_tp_and_fp_per_outer_training_complement"]
            for count in by_training_complement.values()
        ),
    }
    return {
        "events_with_tp_and_fp": len(ready),
        "by_family": by_family,
        "by_outer_training_complement": by_training_complement,
        "gates": gates,
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_jsonl_gzip(path: Path, rows: list[dict]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            for row in rows:
                payload = (
                    json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                ).encode()
                zipped.write(payload)


def _write_dataset(
    *,
    train_dir: Path,
    output_root: Path,
    parents: list[dict],
    actions: list[dict],
    events: list[dict],
) -> dict:
    staging = output_root.with_name(output_root.name + ".staging")
    if output_root.exists() or staging.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing extraction output: {output_root} or {staging}"
        )
    parent_dir = staging / "parents"
    parent_dir.mkdir(parents=True)

    tensor_rows = []
    arrays = {}
    try:
        for index, parent in enumerate(sorted(parents, key=lambda row: row["cache_key"]), start=1):
            sample_id = parent["sample_id"]
            t = int(parent["t"])
            if sample_id not in arrays:
                arrays[sample_id] = open_competition_array(
                    train_dir / f"{sample_id}.zarr"
                )
            array = arrays[sample_id]
            volume_t = read_timepoint(array, t)
            volume_t1 = read_timepoint(array, t + 1)
            position = parent["parent_position_um"]
            first = extract_parent_field(volume_t, volume_t1, position)
            second = extract_parent_field(volume_t, volume_t1, position)
            first_hash = tensor_sha256(first)
            second_hash = tensor_sha256(second)
            if first_hash != second_hash:
                raise RuntimeError(f"Non-deterministic parent tensor: {parent['cache_key']}")
            filename = hashlib.sha256(parent["cache_key"].encode()).hexdigest()[:24] + ".npy"
            path = parent_dir / filename
            np.save(path, first, allow_pickle=False)
            tensor_rows.append(
                {
                    **parent,
                    "relative_path": f"parents/{filename}",
                    "shape": list(first.shape),
                    "dtype": str(first.dtype),
                    "tensor_sha256": first_hash,
                    "file_sha256": _file_sha256(path),
                    "finite": bool(np.isfinite(first).all()),
                    "image_range_valid": bool(
                        np.all((first[:2] >= 0.0) & (first[:2] <= 1.0))
                    ),
                    "coverage_binary": bool(
                        set(np.unique(first[3]).tolist()).issubset({0.0, 1.0})
                    ),
                    "parent_mask_mass": float(first[2].sum()),
                }
            )
            print(f"  tensor [{index}/{len(parents)}] {parent['cache_key']}", flush=True)

        _write_jsonl_gzip(staging / "actions.jsonl.gz", actions)
        _write_jsonl_gzip(staging / "events.jsonl.gz", events)
        (staging / "parents.json").write_text(
            json.dumps(tensor_rows, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest = {
            "status": "v23_locked_pair_field_dataset",
            "normalization_version": NORMALIZATION_VERSION,
            "parent_fields": len(tensor_rows),
            "actions": len(actions),
            "events": len(events),
            "parent_manifest": "parents.json",
            "action_manifest": "actions.jsonl.gz",
            "event_manifest": "events.jsonl.gz",
            "all_parent_tensors_valid": all(
                row["finite"]
                and row["image_range_valid"]
                and row["coverage_binary"]
                and abs(row["parent_mask_mass"] - 1.0) <= 1e-5
                for row in tensor_rows
            ),
            "actions_sha256": _file_sha256(staging / "actions.jsonl.gz"),
            "events_sha256": _file_sha256(staging / "events.jsonl.gz"),
            "parents_sha256": _file_sha256(staging / "parents.json"),
            "model_fitted": False,
            "graph_mutation": False,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.replace(output_root)
        return manifest
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def _report(summary: dict) -> str:
    counts = summary["labels"]
    readiness = summary["dataset_readiness"]
    lines = [
        "# V23 Locked Pair-Field Dataset Results",
        "",
        f"Decision: **{summary['decision']}**.",
        "",
        "The locked extractor labeled the complete bounded action universe through the patched official scorer and wrote parent fields only after readiness passed. No model was fit and no graph was mutated.",
        "",
        "## Dataset",
        "",
        f"- parent fields: {summary['parent_fields']}",
        f"- events: {summary['events']}",
        f"- actions: {summary['actions']}",
        f"- official TP: {counts['official_tp']}",
        f"- official FP: {counts['official_fp']}",
        f"- unknown: {counts['official_unsupported']}",
        f"- selected training actions: {summary['selected_training_actions']}",
        "",
        "## Readiness",
        "",
        f"- events containing TP and FP: {readiness['events_with_tp_and_fp']}",
        f"- family support: {readiness['by_family']}",
        f"- outer-training complements: {readiness['by_outer_training_complement']}",
        "",
    ]
    for name, passed in readiness["gates"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'}: `{name}`")
    lines += [
        "",
        f"Tensor manifest valid: {summary['tensor_manifest']['all_parent_tensors_valid']}.",
        "",
        "This result authorizes implementation and fitting of the already preregistered bounded ranker only. Assignment and production graph mutation remain disabled.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument(
        "--availability",
        type=Path,
        default=ROOT / "v23_cfar_pair_field_positive_availability.csv",
    )
    parser.add_argument(
        "--model-contract",
        type=Path,
        default=ROOT / "tests/fixtures/v23_bounded_pair_field_ranker.json",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "outputs/v23_cfar_pair_field_v1",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / "v23_locked_pair_field_dataset_summary.json",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "V23_LOCKED_PAIR_FIELD_DATASET_RESULTS.md",
    )
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--write-tensors", action="store_true")
    args = parser.parse_args()

    contract = json.loads(args.model_contract.read_text(encoding="utf-8"))
    events = _load_events(args.availability)
    grouped = {}
    for event in events:
        grouped.setdefault(event.sample_id, []).append(event.__dict__)

    results = []
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(_sample_actions, str(args.train_dir), sample_events): sample_id
            for sample_id, sample_events in grouped.items()
        }
        for index, future in enumerate(as_completed(futures), start=1):
            sample_id = futures[future]
            result = future.result()
            results.append(result)
            print(
                f"[{index}/{len(futures)}] {sample_id}: "
                f"{len(result['actions'])} labeled actions",
                flush=True,
            )

    actions = sorted(
        [row for result in results for row in result["actions"]],
        key=lambda row: row["action_id"],
    )
    parents_by_key = {
        row["cache_key"]: row
        for result in results
        for row in result["parents"]
    }
    parents = list(parents_by_key.values())
    event_rows = sorted(
        [row for result in results for row in result["events"]],
        key=lambda row: row["event_id"],
    )
    _select_training_actions(actions)
    readiness = _readiness(event_rows, contract)
    prewrite_gates = {
        "action_count_parity": len(actions) == contract["scope"]["full_candidate_actions"],
        "parent_field_count_parity": len(parents)
        == contract["scope"]["parent_fields"],
        "synthetic_tensor_harness": all(synthetic_integrity_check().values()),
        **readiness["gates"],
    }
    if not all(prewrite_gates.values()):
        summary = {
            "decision": "HOLD_DATASET_LABEL_SUPPORT",
            "prewrite_gates": prewrite_gates,
            "dataset_readiness": readiness,
            "tensor_writes_enabled": False,
            "tensors_written": 0,
            "model_fitted": False,
            "graph_mutation": False,
        }
        args.summary.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, indent=2), flush=True)
        return

    if not args.write_tensors:
        raise RuntimeError(
            "All prewrite gates passed. Re-run with --write-tensors to publish the locked dataset."
        )

    tensor_manifest = _write_dataset(
        train_dir=args.train_dir,
        output_root=args.output_root,
        parents=parents,
        actions=actions,
        events=event_rows,
    )
    labels = {
        label: sum(row["official_label"] == label for row in actions)
        for label in ("official_tp", "official_fp", "official_unsupported")
    }
    decision = (
        "GO_TO_BOUNDED_PAIR_FIELD_MODEL_IMPLEMENTATION"
        if tensor_manifest["all_parent_tensors_valid"]
        else "NO_GO_EXTRACTION"
    )
    summary = {
        "status": "v23_locked_pair_field_dataset_result",
        "decision": decision,
        "parent_fields": len(parents),
        "events": len(event_rows),
        "actions": len(actions),
        "labels": labels,
        "selected_training_actions": sum(
            row["selected_for_training"] for row in actions
        ),
        "dataset_readiness": readiness,
        "prewrite_gates": prewrite_gates,
        "tensor_manifest": tensor_manifest,
        "output_root": str(args.output_root),
        "model_fitted": False,
        "assignment_enabled": False,
        "graph_mutation": False,
        "full_199_authorized": False,
    }
    args.summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.report.write_text(_report(summary), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
