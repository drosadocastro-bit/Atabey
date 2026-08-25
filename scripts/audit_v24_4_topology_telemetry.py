from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any


ARM = "e016_atabey_relink_v24_2_shadow"
REFERENCE = "v19_frozen_reference"
RATIO_CEILING = 1.25


def _correlation(left: list[float], right: list[float]) -> float:
    left_mean = statistics.mean(left)
    right_mean = statistics.mean(right)
    left_delta = [value - left_mean for value in left]
    right_delta = [value - right_mean for value in right]
    denominator = math.sqrt(
        sum(value * value for value in left_delta)
        * sum(value * value for value in right_delta)
    )
    return sum(a * b for a, b in zip(left_delta, right_delta)) / denominator if denominator else 0.0


def _sample_rows(archive: zipfile.ZipFile) -> list[dict[str, Any]]:
    csv_rows = {
        row["sample_id"]: row
        for row in csv.DictReader(
            archive.read("run/per_sample.csv").decode("utf-8-sig").splitlines()
        )
    }
    rows: list[dict[str, Any]] = []
    for name in sorted(archive.namelist()):
        if not name.startswith("run/samples/") or not name.endswith(".json"):
            continue
        sample = json.loads(archive.read(name))
        telemetry = sample["arms"][ARM]["node_topology_telemetry"]
        csv_row = csv_rows[sample["sample_id"]]
        node_count = telemetry["node_count"]
        ratio = float(csv_row[f"{ARM}_predicted_nodes"]) / max(
            float(csv_row[f"{REFERENCE}_predicted_nodes"]), 1.0
        )
        rows.append(
            {
                "sample_id": sample["sample_id"],
                "family": sample["family"],
                "shadow_node_ratio": ratio,
                "isolated_fraction": telemetry["connectivity"].get("isolated", 0)
                / max(node_count, 1),
                "degree_one_fraction": telemetry["degree_histogram"].get("1", 0)
                / max(node_count, 1),
                "degree_two_fraction": telemetry["degree_histogram"].get("2", 0)
                / max(node_count, 1),
                "continuation_support_zero_fraction": telemetry[
                    "continuation_support_histogram"
                ].get("0", 0)
                / max(node_count, 1),
                "age_one_fraction": telemetry["track_age_histogram"].get("1", 0)
                / max(node_count, 1),
            }
        )
    return rows


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ratio = [row["shadow_node_ratio"] for row in rows]
    correlations = {}
    for key in (
        "isolated_fraction",
        "degree_one_fraction",
        "degree_two_fraction",
        "continuation_support_zero_fraction",
        "age_one_fraction",
    ):
        correlations[key] = _correlation(ratio, [row[key] for row in rows])
    return {
        "sample_count": len(rows),
        "median_shadow_node_ratio": statistics.median(ratio),
        "inflated_samples": sum(value > RATIO_CEILING for value in ratio),
        "correlations_with_shadow_node_ratio": correlations,
        "highest_ratio_samples": sorted(
            rows, key=lambda row: row["shadow_node_ratio"], reverse=True
        )[:8],
    }


def analyze_zip(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        rows = _sample_rows(archive)
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_family[row["family"]].append(row)
    return {
        "status": "v24_4_topology_telemetry_audit",
        "arm": ARM,
        "ratio_definition": f"{ARM}_predicted_nodes / {REFERENCE}_predicted_nodes",
        "ratio_ceiling": RATIO_CEILING,
        "overall": _summarize(rows),
        "by_family": {
            family: _summarize(family_rows)
            for family, family_rows in sorted(by_family.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit V24 topology telemetry.")
    parser.add_argument("artifact_zip", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze_zip(args.artifact_zip)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()