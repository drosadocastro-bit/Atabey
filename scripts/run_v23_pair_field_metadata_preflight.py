"""Metadata-only preflight for the V23 CFAR pair-field extractor."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from atabey.io.geff_reader import read_geff_graph
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.tracking.pair_field import estimate_storage, synthetic_integrity_check
from audit_v23_cfar_pair_field_positive_availability import (
    FORMATION_RADIUS_UM,
    MATCH_RADIUS_UM,
    _detect,
    _distance,
    _official_tp,
)


@dataclass(frozen=True)
class PositiveEvent:
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


def _load_events(path: Path) -> list[PositiveEvent]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["status"] == "official_positive"
        ]
    return [
        PositiveEvent(
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
        [
            (detection, _distance(detection.position_um, position))
            for detection in detections
            if _distance(detection.position_um, position) <= radius_um
        ],
        key=lambda item: (item[1], item[0].node_id),
    )


def _sample_preflight(train_dir: str, raw_events: list[dict]) -> list[dict]:
    events = [PositiveEvent(**item) for item in raw_events]
    sample_id = events[0].sample_id
    train = Path(train_dir)
    ground_truth = read_geff_graph(train / f"{sample_id}.geff")
    gt_nodes = {int(node.node_id): node for node in ground_truth.nodes}
    array = open_competition_array(train / f"{sample_id}.zarr")
    required_frames = sorted({event.t + offset for event in events for offset in (0, 1)})
    detected = {
        t: _detect(sample_id, t, read_timepoint(array, t))
        for t in required_frames
    }

    output = []
    for event in events:
        parent_gt = gt_nodes[event.gt_parent_id]
        child_1_gt = gt_nodes[event.gt_child_1_id]
        child_2_gt = gt_nodes[event.gt_child_2_id]
        parents = _near(detected[event.t], parent_gt.position_um, MATCH_RADIUS_UM)
        child_1_roles = _near(
            detected[event.t + 1],
            child_1_gt.position_um,
            MATCH_RADIUS_UM,
        )
        child_2_roles = _near(
            detected[event.t + 1],
            child_2_gt.position_um,
            MATCH_RADIUS_UM,
        )

        full_action_count = 0
        max_daughters_per_parent = 0
        cache_keys = []
        for parent, _distance_to_gt in parents:
            daughters = [
                child
                for child in detected[event.t + 1]
                if _distance(parent.position_um, child.position_um)
                <= FORMATION_RADIUS_UM
            ]
            max_daughters_per_parent = max(max_daughters_per_parent, len(daughters))
            full_action_count += len(daughters) * (len(daughters) - 1) // 2
            cache_keys.append(
                f"{sample_id}|{event.t}|{parent.node_id}|v23_pair_field_norm_v1"
            )

        role_specs = {}
        for parent, parent_distance in parents:
            for (child_1, distance_1), (child_2, distance_2) in (
                (left, right)
                for left in child_1_roles
                for right in child_2_roles
            ):
                if child_1.node_id == child_2.node_id:
                    continue
                if _distance(parent.position_um, child_1.position_um) > FORMATION_RADIUS_UM:
                    continue
                if _distance(parent.position_um, child_2.position_um) > FORMATION_RADIUS_UM:
                    continue
                ordered = sorted((child_1, child_2), key=lambda item: item.node_id)
                key = (parent.node_id, ordered[0].node_id, ordered[1].node_id)
                role_distance = parent_distance + distance_1 + distance_2
                if key not in role_specs or role_distance < role_specs[key][0]:
                    role_specs[key] = (
                        role_distance,
                        parent,
                        ordered[0],
                        ordered[1],
                    )

        observed_tp_actions = sum(
            _official_tp(
                parent,
                child_1,
                child_2,
                ground_truth,
                event.gt_parent_id,
            )
            for _role_distance, parent, child_1, child_2 in role_specs.values()
        )
        output.append(
            {
                "event_id": event.event_id,
                "sample_id": sample_id,
                "family": event.family,
                "fold": event.fold,
                "t": event.t,
                "parent_fields": len(parents),
                "full_candidate_actions": full_action_count,
                "max_daughters_per_parent": max_daughters_per_parent,
                "expected_tp_actions": event.expected_tp_actions,
                "observed_tp_actions": observed_tp_actions,
                "official_label_parity": observed_tp_actions
                == event.expected_tp_actions,
                "cache_keys": cache_keys,
                "tensor_written": False,
                "graph_mutated": False,
            }
        )
    return output


def _summarize(rows: list[dict], contract: dict) -> dict:
    cache_keys = {
        key
        for row in rows
        for key in row["cache_keys"]
    }
    actions = sum(row["full_candidate_actions"] for row in rows)
    storage = estimate_storage(len(cache_keys), actions)
    limits = contract["storage"]["preflight_limits"]
    families_by_fold = {
        str(fold): sorted(
            {
                row["family"]
                for row in rows
                if row["fold"] == fold
            }
        )
        for fold in (1, 2, 3)
    }
    integrity = {
        "expected_positive_events": len(rows)
        == contract["extraction_integrity"]["expected_positive_events"],
        "expected_positive_action_variants": sum(
            row["observed_tp_actions"] for row in rows
        )
        == contract["extraction_integrity"]["expected_positive_action_variants"],
        "official_metric_relabel_parity": all(
            row["official_label_parity"] for row in rows
        ),
        "sample_blocked_folds": all(
            len({row["fold"] for row in rows if row["sample_id"] == sample_id})
            == 1
            for sample_id in {row["sample_id"] for row in rows}
        ),
        "both_families_each_fold": all(
            families == ["44b6", "6bba"]
            for families in families_by_fold.values()
        ),
        "synthetic_tensor_harness": all(synthetic_integrity_check().values()),
        "zero_tensor_writes": all(not row["tensor_written"] for row in rows),
        "zero_graph_mutation": all(not row["graph_mutated"] for row in rows),
    }
    resource = {
        "estimated_uncompressed_gib": storage.cached_gib
        <= float(limits["estimated_uncompressed_gib_max"]),
        "actions_per_event": max(row["full_candidate_actions"] for row in rows)
        <= int(limits["actions_per_event_max"]),
        "parent_fields": len(cache_keys) <= int(limits["parent_fields_max"]),
    }
    if not all(integrity.values()):
        decision = "NO_GO_EXTRACTION"
    elif not all(resource.values()):
        decision = "HOLD_EXTRACTION_RESOURCE_OR_STRATUM_CONCERN"
    else:
        decision = "GO_TO_BOUNDED_PAIR_FIELD_MODEL_PREREGISTRATION"

    clean_rows = [
        {key: value for key, value in row.items() if key != "cache_keys"}
        for row in rows
    ]
    return {
        "status": "v23_pair_field_metadata_only_preflight",
        "decision": decision,
        "population": {
            "events": len(rows),
            "samples": len({row["sample_id"] for row in rows}),
            "parent_fields": len(cache_keys),
            "full_candidate_actions": actions,
            "official_tp_action_variants": sum(
                row["observed_tp_actions"] for row in rows
            ),
            "max_actions_per_event": max(
                row["full_candidate_actions"] for row in rows
            ),
        },
        "storage": {
            "cached_uncompressed_gib": storage.cached_gib,
            "naive_assembled_uncompressed_gib": storage.naive_assembled_gib,
            "cache_reduction_fraction": (
                1.0 - storage.cached_bytes / storage.naive_assembled_bytes
                if storage.naive_assembled_bytes
                else 0.0
            ),
            "action_metadata_bytes_assumption": 256,
        },
        "fold_family_events": {
            str(fold): {
                family: sum(
                    row["fold"] == fold and row["family"] == family
                    for row in rows
                )
                for family in ("44b6", "6bba")
            }
            for fold in (1, 2, 3)
        },
        "integrity_gates": integrity,
        "resource_gates": resource,
        "synthetic_tensor_checks": synthetic_integrity_check(),
        "events": clean_rows,
        "tensor_writes_enabled": False,
        "tensors_written": 0,
        "model_fitted": False,
        "assignment_enabled": False,
        "graph_mutation": False,
        "full_199_authorized": False,
    }


def _report(summary: dict) -> str:
    population = summary["population"]
    storage = summary["storage"]
    lines = [
        "# V23 Pair-Field Metadata Preflight Results",
        "",
        f"Decision: **{summary['decision']}**.",
        "",
        "This pass enumerated metadata and exercised the tensor contract only on synthetic arrays. It wrote no real image tensor, fit no model, and mutated no graph.",
        "",
        "## Population",
        "",
        f"- {population['events']} positive events across {population['samples']} samples",
        f"- {population['parent_fields']} unique cached parent fields",
        f"- {population['full_candidate_actions']} full local candidate actions",
        f"- {population['official_tp_action_variants']} patched-official TP action variants reproduced",
        f"- maximum {population['max_actions_per_event']} actions in one event",
        "",
        "## Storage",
        "",
        f"- cached estimate: {storage['cached_uncompressed_gib']:.3f} GiB",
        f"- naive assembled estimate: {storage['naive_assembled_uncompressed_gib']:.3f} GiB",
        f"- estimated reduction from parent caching: {storage['cache_reduction_fraction']:.1%}",
        "",
        "## Gates",
        "",
    ]
    for group in ("integrity_gates", "resource_gates"):
        for name, passed in summary[group].items():
            lines.append(f"- {'PASS' if passed else 'FAIL'}: `{name}`")
    lines += [
        "",
        "A GO authorizes only a separate bounded model preregistration. Real tensor extraction remains disabled until that artifact is reviewed.",
        "",
        "Guardrail: unsupported candidates remain unknown and no full-199 run is authorized.",
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
        "--contract",
        type=Path,
        default=ROOT
        / "tests/fixtures/v23_cfar_pair_field_extraction_validation.json",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / "v23_pair_field_metadata_preflight_summary.json",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "V23_PAIR_FIELD_METADATA_PREFLIGHT_RESULTS.md",
    )
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    events = _load_events(args.availability)
    grouped = {}
    for event in events:
        grouped.setdefault(event.sample_id, []).append(event.__dict__)

    rows = []
    print(
        f"Preflight population: {len(events)} events across {len(grouped)} samples",
        flush=True,
    )
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(_sample_preflight, str(args.train_dir), sample_events): sample_id
            for sample_id, sample_events in grouped.items()
        }
        for index, future in enumerate(as_completed(futures), start=1):
            sample_id = futures[future]
            sample_rows = future.result()
            rows.extend(sample_rows)
            print(
                f"[{index}/{len(futures)}] {sample_id}: "
                f"{sum(row['full_candidate_actions'] for row in sample_rows)} actions",
                flush=True,
            )

    rows.sort(key=lambda row: (row["sample_id"], row["t"], row["event_id"]))
    summary = _summarize(rows, contract)
    args.summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.report.write_text(_report(summary), encoding="utf-8")
    print(
        json.dumps(
            {
                "decision": summary["decision"],
                "population": summary["population"],
                "storage": summary["storage"],
                "integrity_gates": summary["integrity_gates"],
                "resource_gates": summary["resource_gates"],
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
