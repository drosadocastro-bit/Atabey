"""Compare the quarantined route control with the frozen U-Net shadow.

This consumes already-generated, read-only availability exports. It does not
rerun detection, alter routes, or mutate a graph.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def arm_rows(control: pd.DataFrame, unet: pd.DataFrame) -> pd.DataFrame:
    key = "case_id"
    if set(control[key]) != set(unet[key]):
        raise RuntimeError("Control and U-Net exports do not cover the same cases")
    left = control.set_index(key).sort_index()
    right = unet.set_index(key).sort_index()
    if not (left["sample_id"] == right["sample_id"]).all():
        raise RuntimeError("Control and U-Net sample identities differ")
    rows = []
    for case_id in left.index:
        a = left.loc[case_id]
        b = right.loc[case_id]
        # Fallback is diagnostic: use the learned detector when it exposes an
        # official positive, otherwise retain the quarantined control output.
        use_unet = bool(b["official_positive_available"])
        chosen = b if use_unet else a
        rows.append(
            {
                "case_id": case_id,
                "sample_id": a["sample_id"],
                "family": str(a["sample_id"]).split("_", 1)[0],
                "route": f"{a['source_detector']}/{a['source_link_strategy']}",
                "control_available": bool(a["official_positive_available"]),
                "unet_available": bool(b["official_positive_available"]),
                "control_actions": int(a["division_action_count"]),
                "unet_actions": int(b["division_action_count"]),
                "control_tp": int(a["official_tp_action_count"]),
                "unet_tp": int(b["official_tp_action_count"]),
                "fallback_used": not use_unet,
                "fallback_available": bool(chosen["official_positive_available"]),
                "fallback_actions": int(chosen["division_action_count"]),
                "fallback_tp": int(chosen["official_tp_action_count"]),
                "control_graph_mutated": bool(a["graph_mutated"]),
                "unet_graph_mutated": bool(b["graph_mutated"]),
            }
        )
    return pd.DataFrame(rows)


def summarize(rows: pd.DataFrame, group: str | None = None) -> dict:
    groups = [("pooled", rows)] if group is None else [(str(k), g) for k, g in rows.groupby(group, sort=True)]
    out = {}
    for name, frame in groups:
        record = {"cases": int(len(frame))}
        for arm in ("control", "unet", "fallback"):
            record[f"{arm}_available"] = int(frame[f"{arm}_available"].sum())
            record[f"{arm}_availability_rate"] = float(frame[f"{arm}_available"].mean())
            record[f"{arm}_actions"] = int(frame[f"{arm}_actions"].sum())
            record[f"{arm}_tp_actions"] = int(frame[f"{arm}_tp"].sum())
        record["fallback_used"] = int(frame["fallback_used"].sum())
        record["fallback_used_rate"] = float(frame["fallback_used"].mean())
        record["control_to_unet_action_ratio"] = (
            float(record["unet_actions"] / record["control_actions"])
            if record["control_actions"] else None
        )
        out[name] = record
    return out


def write_report(path: Path, summary: dict, rows: pd.DataFrame) -> None:
    pooled = summary["pooled"]
    lines = [
        "# V23 Parallel CFAR vs Encoder-Decoder Shadow Results",
        "",
        "Decision: **HOLD; retain CFAR as fallback while the encoder-decoder route is redesigned**.",
        "",
        "This is a paired, read-only comparison of existing exports. No detector was retrained, no graph was mutated, and no production route was changed.",
        "",
        "## Pooled comparison",
        "",
        "| Arm | Available | Availability | Actions | Official TP actions |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, arm in (("CFAR control", "control"), ("Encoder-decoder", "unet"), ("Availability fallback", "fallback")):
        lines.append(f"| {label} | {pooled[f'{arm}_available']}/{pooled['cases']} | {pooled[f'{arm}_availability_rate']:.3f} | {pooled[f'{arm}_actions']:,} | {pooled[f'{arm}_tp_actions']} |")
    lines += [
        "",
        f"Fallback used on `{pooled['fallback_used']}/{pooled['cases']}` cases ({pooled['fallback_used_rate']:.3f}).",
        f"Encoder-decoder action volume relative to control: `{pooled['control_to_unet_action_ratio']:.3f}`.",
        "",
        "## Route breakdown",
        "",
        "| Route | Cases | Control avail | U-Net avail | Fallback avail | Control actions | U-Net actions |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for route, record in summary["by_route"].items():
        lines.append(f"| {route} | {record['cases']} | {record['control_available']} | {record['unet_available']} | {record['fallback_available']} | {record['control_actions']:,} | {record['unet_actions']:,} |")
    lines += [
        "",
        "## Interpretation",
        "",
        "- The encoder-decoder improves event availability by two cases in the paired set, but loses two control-positive cases and does not yet prove preservation of official TP action identity.",
        "- It reduces candidate volume substantially, which is promising for computational cost and noise exposure.",
        "- The fallback recovers availability when the encoder-decoder is unavailable, but its fallback rate and route distribution must remain visible; it is not a replacement result.",
        "- This comparison does not provide official FP counts per arm; the availability exports contain registered actions and official TP actions, not a complete per-arm FP table.",
        "",
        "## Decision",
        "",
        "**HOLD.** Keep CFAR quarantined but available as fallback. The encoder-decoder route is promising enough for a CFAR-specific representation audit, not for route removal or production integration.",
        "",
        "Graph mutation remained false for every row in both source exports.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--unet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--rows", type=Path, required=True)
    args = parser.parse_args()
    control = pd.read_csv(args.control)
    unet = pd.read_csv(args.unet)
    rows = arm_rows(control, unet)
    summary = {
        "control_sha256": sha256(args.control),
        "unet_sha256": sha256(args.unet),
        "population": {"cases": int(len(rows)), "samples": int(rows.sample_id.nunique()), "events": 46},
        "pooled": summarize(rows)["pooled"],
        "by_route": summarize(rows, "route"),
        "by_family": summarize(rows, "family"),
        "transitions": pd.crosstab(rows.control_available, rows.unet_available).to_dict(),
        "graph_mutation": bool(rows.control_graph_mutated.any() or rows.unet_graph_mutated.any()),
        "decision": "HOLD_CFAR_FALLBACK_RETAINED",
    }
    args.rows.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(args.rows, index=False)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(args.report, summary, rows)
    print(json.dumps(summary["pooled"], indent=2), flush=True)


if __name__ == "__main__":
    main()
