"""Separate CFAR candidate-coordinate quality from upstream identity claims."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def quality(distance):
    if distance is None:
        return "no_candidate"
    if distance <= 7.0:
        return "official_radius"
    if distance <= 14.0:
        return "formation_radius_only"
    return "outside_formation_radius"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.audit.read_text(encoding="utf-8"))
    rows = []
    for case in source:
        roles = {
            "parent": case["parent_candidates_within_14um"],
            "daughter_1": case["daughter_1_candidates_within_14um"],
            "daughter_2": case["daughter_2_candidates_within_14um"],
        }
        nearest = {role: values[0] if values else None for role, values in roles.items()}
        nearest_ids = [item["id"] for item in nearest.values() if item is not None]
        reused = len(nearest_ids) != len(set(nearest_ids))
        for role, item in nearest.items():
            distance = item["distance_to_gt_um"] if item else None
            claims = case["candidate_graph_claims"].get(item["id"], {}) if item else {}
            rows.append({
                "sample_id": case["sample_id"],
                "t": case["t"],
                "role": role,
                "candidate_id": item["id"] if item else None,
                "distance_to_gt_um": distance,
                "coordinate_quality": quality(distance),
                "nearest_candidate_reused_across_roles": reused,
                "incoming_parent_ids": claims.get("incoming", []),
                "outgoing_child_ids": claims.get("outgoing", []),
                "claimed_by_other_parent": bool(claims.get("incoming")),
            })

    quality_counts = {}
    for row in rows:
        quality_counts[row["role"]] = quality_counts.get(row["role"], {})
        label = row["coordinate_quality"]
        quality_counts[row["role"]][label] = quality_counts[row["role"]].get(label, 0) + 1
    summary = {
        "status": "read_only_v23_candidate_coordinate_identity_audit",
        "official_metric_used": False,
        "candidate_set_changed": False,
        "graph_mutation": False,
        "population": {
            "cases": len(source),
            "role_rows": len(rows),
            "nearest_role_collisions": sum(row["nearest_candidate_reused_across_roles"] for row in rows if row["role"] == "parent"),
        },
        "coordinate_quality_by_role": quality_counts,
    }
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 Candidate Coordinate and Identity Audit",
        "",
        "Read-only audit separating coordinate quality from graph ownership. No candidate, edge, or graph was changed.",
        "",
        "| Sample | Role | Nearest candidate | Distance | Coordinate quality | Incoming claims | Outgoing claims |",
        "|---|---|---|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| {row['sample_id']} t{row['t']} | {row['role']} | {row['candidate_id'] or 'none'} | {'NA' if row['distance_to_gt_um'] is None else f'{row["distance_to_gt_um"]:.3f}'} | {row['coordinate_quality']} | {', '.join(row['incoming_parent_ids']) or '-'} | {', '.join(row['outgoing_child_ids']) or '-'} |")
    lines += [
        "",
        "Coordinate quality is measured against the registered GT position only for diagnosis. Incoming/outgoing claims describe the existing upstream graph and are not treated as truth labels.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
