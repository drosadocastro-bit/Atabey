from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


RATIO_CEILING = 1.25
REFERENCE = "v19_frozen_reference"
CHALLENGER = "e016_atabey_relink"


def _float(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    if not value:
        raise ValueError(f"Missing numeric value for {key}")
    return float(value)


def _pearson(pairs: Iterable[tuple[float, float]]) -> float | None:
    values = list(pairs)
    if len(values) < 2:
        return None
    xs = [pair[0] for pair in values]
    ys = [pair[1] for pair in values]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in values)
    denominator_x = sum((x - mean_x) ** 2 for x in xs)
    denominator_y = sum((y - mean_y) ** 2 for y in ys)
    if denominator_x == 0 or denominator_y == 0:
        return None
    return numerator / (denominator_x * denominator_y) ** 0.5


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ratios = sorted(row["node_ratio"] for row in rows)
    deltas = [row["score_delta"] for row in rows]
    midpoint = len(ratios) // 2
    if len(ratios) % 2:
        median_ratio = ratios[midpoint]
    else:
        median_ratio = (ratios[midpoint - 1] + ratios[midpoint]) / 2
    return {
        "sample_count": len(rows),
        "median_node_ratio": median_ratio,
        "mean_node_ratio": sum(ratios) / len(ratios),
        "min_node_ratio": ratios[0],
        "max_node_ratio": ratios[-1],
        "mean_adjusted_edge_delta": sum(deltas) / len(deltas),
        "improved_samples": sum(delta > 1e-6 for delta in deltas),
        "regressed_samples": sum(delta < -1e-6 for delta in deltas),
        "inflated_samples": sum(ratio > RATIO_CEILING for ratio in ratios),
    }


def analyze_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for row in rows:
        reference_nodes = max(_float(row, f"{REFERENCE}_predicted_nodes"), 1.0)
        challenger_nodes = _float(row, f"{CHALLENGER}_predicted_nodes")
        reference_score = _float(row, f"{REFERENCE}_adjusted_edge_jaccard")
        challenger_score = _float(row, f"{CHALLENGER}_adjusted_edge_jaccard")
        records.append(
            {
                "sample_id": row["sample_id"],
                "family": row["family"],
                "route": row["v19_reference_detector"],
                "node_ratio": challenger_nodes / reference_nodes,
                "score_delta": challenger_score - reference_score,
            }
        )

    groups: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(dict)
    for key in ("family", "route"):
        for record in records:
            groups[key].setdefault(record[key], []).append(record)
    inflation_groups = {
        "within_ceiling": [
            record for record in records if record["node_ratio"] <= RATIO_CEILING
        ],
        "above_ceiling": [
            record for record in records if record["node_ratio"] > RATIO_CEILING
        ],
    }
    return {
        "status": "v24_1_node_inflation_diagnostic",
        "sample_count": len(records),
        "ratio_ceiling": RATIO_CEILING,
        "overall": _summary(records),
        "by_family": {
            key: _summary(value) for key, value in sorted(groups["family"].items())
        },
        "by_route": {
            key: _summary(value) for key, value in sorted(groups["route"].items())
        },
        "by_inflation_status": {
            key: _summary(value) for key, value in inflation_groups.items() if value
        },
        "ratio_score_delta_pearson": _pearson(
            (record["node_ratio"], record["score_delta"]) for record in records
        ),
        "samples": sorted(records, key=lambda record: record["sample_id"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit frozen V24 node inflation.")
    parser.add_argument("per_sample_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.per_sample_csv.open(encoding="utf-8", newline="") as handle:
        report = analyze_rows(list(csv.DictReader(handle)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()