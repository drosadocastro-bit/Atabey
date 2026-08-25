from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


RATIO_CEILING = 1.25
REFERENCE = "v19_frozen_reference"
RELINK = "e016_atabey_relink"
SHADOW = "e016_atabey_relink_v24_2_shadow"


def _number(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    if not value:
        raise ValueError(f"Missing numeric value for {key}")
    return float(value)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ratios = [row["shadow_node_ratio"] for row in rows]
    return {
        "sample_count": len(rows),
        "median_shadow_node_ratio": sorted(ratios)[len(ratios) // 2],
        "mean_shadow_node_ratio": sum(ratios) / len(ratios),
        "inflated_samples": sum(ratio > RATIO_CEILING for ratio in ratios),
        "total_removed_nodes": sum(row["removed_nodes"] for row in rows),
        "samples_with_removals": sum(row["removed_nodes"] > 0 for row in rows),
    }


def analyze_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for row in rows:
        reference_nodes = max(_number(row, f"{REFERENCE}_predicted_nodes"), 1.0)
        relink_nodes = _number(row, f"{RELINK}_predicted_nodes")
        shadow_nodes = _number(row, f"{SHADOW}_predicted_nodes")
        removed_nodes = _number(row, f"{SHADOW}_shadow_removed_nodes")
        edge_preserved = row.get(f"{SHADOW}_shadow_edge_set_preserved", "")
        records.append(
            {
                "sample_id": row["sample_id"],
                "family": row["family"],
                "route": row["v19_reference_detector"],
                "relink_node_ratio": relink_nodes / reference_nodes,
                "shadow_node_ratio": shadow_nodes / reference_nodes,
                "relink_nodes": int(relink_nodes),
                "shadow_nodes": int(shadow_nodes),
                "removed_nodes": int(removed_nodes),
                "remaining_nodes_after_prune": int(shadow_nodes),
                "removed_fraction_of_relink": removed_nodes / max(relink_nodes, 1.0),
                "edge_set_preserved": edge_preserved.lower() == "true",
            }
        )

    groups: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(dict)
    for key in ("family", "route"):
        for record in records:
            groups[key].setdefault(record[key], []).append(record)
    return {
        "status": "v24_2_node_inflation_decomposition",
        "ratio_ceiling": RATIO_CEILING,
        "sample_count": len(records),
        "overall": _summary(records),
        "by_family": {
            key: _summary(value) for key, value in sorted(groups["family"].items())
        },
        "by_route": {
            key: _summary(value) for key, value in sorted(groups["route"].items())
        },
        "edge_sets_preserved_for_all": all(
            record["edge_set_preserved"] for record in records
        ),
        "interpretation": {
            "removed_isolated_nodes": "recorded by the V24.2 transform",
            "remaining_nodes": (
                "not classifiable as weak or legitimate from per-sample CSV alone; "
                "node-level topology telemetry is required"
            ),
        },
        "samples": sorted(records, key=lambda record: record["sample_id"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit V24.2 residual node inflation.")
    parser.add_argument("per_sample_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.per_sample_csv.open(encoding="utf-8", newline="") as handle:
        report = analyze_rows(list(csv.DictReader(handle)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()