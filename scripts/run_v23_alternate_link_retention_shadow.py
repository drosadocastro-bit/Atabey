"""Annotate alternate upstream links without mutating the CFAR graph."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    cases = json.loads(args.audit.read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        focal_parent = case["gt_parent_id"]
        for rank, pair in enumerate(case["best_distinct_pairs"], start=1):
            claims = case["candidate_graph_claims"]
            child_claims = []
            for child_id in (pair["child_1_id"], pair["child_2_id"]):
                incoming = claims.get(child_id, {}).get("incoming", [])
                child_claims.append({
                    "child_id": child_id,
                    "incoming_parent_ids": incoming,
                    "claimed_by_other_parent": any(parent_id != pair["parent_id"] for parent_id in incoming),
                })
            rows.append({
                "sample_id": case["sample_id"],
                "t": case["t"],
                "rank_by_geometric_residual": rank,
                "parent_id": pair["parent_id"],
                "child_1_id": pair["child_1_id"],
                "child_2_id": pair["child_2_id"],
                "parent_distance_um": pair["parent_distance_um"],
                "max_daughter_distance_um": pair["max_daughter_distance_um"],
                "sum_role_distance_um": pair["sum_role_distance_um"],
                "child_claims": child_claims,
                "ownership_conflict": any(item["claimed_by_other_parent"] for item in child_claims),
                "official_7um_geometric_match": pair["max_daughter_distance_um"] <= 7.0 and pair["parent_distance_um"] <= 7.0,
                "candidate_set_changed": False,
                "graph_mutated": False,
            })

    conflicts = [row for row in rows if row["ownership_conflict"]]
    official = [row for row in rows if row["official_7um_geometric_match"]]
    summary = {
        "status": "read_only_v23_alternate_link_retention_shadow",
        "official_metric_used": False,
        "candidate_set_changed": False,
        "graph_mutation": False,
        "population": {
            "cases": len(cases),
            "alternate_pairs": len(rows),
            "ownership_conflict_pairs": len(conflicts),
            "official_7um_geometric_matches": len(official),
        },
        "decision": "NO_OFFICIAL_RECOVERY_FROM_ALTERNATE_RETENTION" if not official else "REQUIRES_OFFICIAL_METRIC_CHECK",
    }
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 Alternate-Link Retention Shadow",
        "",
        f"Decision: **{summary['decision']}**.",
        "",
        "Alternate parent/daughter combinations were retained as annotations only. Existing CFAR edges and graph structure were not changed.",
        "",
        "| Sample | Alternate pairs | Ownership-conflict pairs | Official 7 um geometric matches |",
        "|---|---:|---:|---:|",
    ]
    for case in cases:
        sample_rows = [row for row in rows if row["sample_id"] == case["sample_id"] and row["t"] == case["t"]]
        lines.append(f"| {case['sample_id']} t{case['t']} | {len(sample_rows)} | {sum(row['ownership_conflict'] for row in sample_rows)} | {sum(row['official_7um_geometric_match'] for row in sample_rows)} |")
    lines += [
        "",
        f"Across the four cases, `{len(conflicts)}` alternate pairs show ownership contention, but `{len(official)}` reach the official 7 um geometric bound.",
        "This indicates that ownership retention is a real upstream phenomenon but is not sufficient by itself to recover official divisions in this bounded battery.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
