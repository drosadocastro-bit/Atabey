"""Audit CFAR-route candidate formation losses from the frozen 46-case table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def classify(row: pd.Series) -> str:
    if int(row.unet_parent_candidates) == 0:
        return "parent_detection_loss"
    if int(row.unet_daughter_1_candidates) == 0 or int(row.unet_daughter_2_candidates) == 0:
        return "daughter_detection_loss"
    if not bool(row.distinct_daughter_pair):
        return "pair_formation_loss"
    if not bool(row.complete_triplet):
        return "triplet_formation_loss"
    if int(row.official_tp_action_count) == 0:
        return "formed_but_official_match_loss"
    return "official_tp_available"


def distribution(frame: pd.DataFrame, column: str) -> dict:
    values = pd.to_numeric(frame[column], errors="coerce").dropna().to_numpy(float)
    if not len(values):
        return {"n": 0, "min": None, "median": None, "p90": None, "max": None}
    return {
        "n": int(len(values)),
        "min": float(np.min(values)),
        "median": float(np.median(values)),
        "p90": float(np.percentile(values, 90)),
        "max": float(np.max(values)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--availability", type=Path, required=True)
    parser.add_argument("--detector", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    availability = pd.read_csv(args.availability)
    detector = pd.read_csv(args.detector)
    cases = pd.DataFrame(fixture["cases"])
    frame = cases.merge(availability, on=["case_id", "sample_id", "t"], how="left", validate="one_to_one")
    frame = frame.merge(detector, on=["case_id", "sample_id", "t"], how="left", validate="one_to_one", suffixes=("", "_detector"))
    if frame.source_detector.isna().any():
        raise RuntimeError("Availability join failed for one or more registered cases")
    frame["formation_class"] = frame.apply(classify, axis=1)
    frame["family"] = frame.sample_id.str.split("_", n=1).str[0]
    frame["mean_frame_density"] = frame[["parent_frame_peak_count", "daughter_frame_peak_count"]].mean(axis=1)
    frame["density_ratio"] = frame["mean_frame_density"] / frame["division_action_count"].replace(0, np.nan)

    strata = {}
    for keys, group in frame.groupby(["source_detector", "family"], dropna=False, sort=True):
        route, family = keys
        strata[f"{route}/{family}"] = {
            "cases": int(len(group)),
            "formation_class_counts": group.formation_class.value_counts().to_dict(),
            "parent_distance_um": distribution(group, "parent_distance_um"),
            "daughter_1_distance_um": distribution(group, "daughter_1_distance_um"),
            "daughter_2_distance_um": distribution(group, "daughter_2_distance_um"),
            "mean_frame_density": distribution(group, "mean_frame_density"),
            "division_action_count": distribution(group, "division_action_count"),
        }
    summary = {
        "status": "read_only_cfar_candidate_formation_audit",
        "candidate_set_changed": False,
        "graph_mutation": False,
        "official_metric_used": False,
        "population": {
            "cases": int(len(frame)),
            "families": sorted(frame.family.unique().tolist()),
            "routes": frame.source_detector.value_counts().to_dict(),
        },
        "formation_class_counts": frame.formation_class.value_counts().to_dict(),
        "strata": strata,
    }
    frame.to_csv(args.output, index=False)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    counts = frame.formation_class.value_counts()
    lines = [
        "# V23 CFAR Candidate-Formation Audit",
        "",
        "Decision: **READ-ONLY DIAGNOSTIC; NO CFAR GATE CHANGE**.",
        "",
        f"Population: `{len(frame)}` registered development cases. Candidate formation was evaluated from the frozen availability/detector artifacts; no detector rerun or graph mutation occurred.",
        "",
        "## Loss Classification",
        "",
        "| Formation outcome | Cases | Percent |",
        "|---|---:|---:|",
    ]
    for label, count in counts.items():
        lines.append(f"| {label} | {int(count)} | {100.0 * count / len(frame):.1f}% |")
    lines += [
        "",
        "## Route and Family",
        "",
        "| Route / family | Cases | Formation outcomes | Median action count | Median mean frame density |",
        "|---|---:|---|---:|---:|",
    ]
    for key, item in strata.items():
        outcomes = ", ".join(f"{name}={value}" for name, value in item["formation_class_counts"].items())
        lines.append(f"| {key} | {item['cases']} | {outcomes} | {item['division_action_count']['median'] or 0:.0f} | {item['mean_frame_density']['median'] or 0:.1f} |")
    lines += [
        "",
        "## Interpretation Guardrail",
        "",
        "This audit separates missing role detections from pair/triplet formation and later official matching. Distances and density are descriptive covariates, not threshold-tuning evidence. Any follow-up gate change must be a bounded shadow experiment with CFAR retained as the control.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
