from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _is_true(value: object) -> bool:
    return value is True or str(value).lower() == "true"


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    index = (len(ordered) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    weight = index - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Join and decide the V22 46-division U-Net shadow."
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("v22_unet_detection_development_46.csv"),
    )
    parser.add_argument(
        "--reference",
        type=Path,
        default=Path("v22_v19_event_frame_reference.csv"),
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("tests/fixtures/v22_unet_detection_development_46.json"),
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("v22_unet_detection_development_46_with_reference.csv"),
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=Path("v22_unet_detection_development_46_final_summary.json"),
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=Path("V22_UNET_DEVELOPMENT_46_RESULTS.md"),
    )
    args = parser.parse_args()

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    results = _read_csv(args.results)
    references = _read_csv(args.reference)
    expected_ids = {case["case_id"] for case in fixture["cases"]}
    result_ids = {row["case_id"] for row in results}
    reference_by_id = {row["case_id"]: row for row in references}
    if result_ids != expected_ids:
        raise RuntimeError(
            f"GPU result case mismatch: missing={sorted(expected_ids - result_ids)}, "
            f"extra={sorted(result_ids - expected_ids)}"
        )
    if set(reference_by_id) != expected_ids:
        raise RuntimeError("V19 frame-reference case set does not match the fixture")

    joined: list[dict[str, Any]] = []
    unique_frames: dict[tuple[str, int], tuple[int, int]] = {}
    for row in results:
        reference = reference_by_id[row["case_id"]]
        parent_unet = int(row["parent_frame_peak_count"])
        daughter_unet = int(row["daughter_frame_peak_count"])
        parent_v19 = int(reference["v19_parent_frame_count"])
        daughter_v19 = int(reference["v19_daughter_frame_count"])
        parent_ratio = parent_unet / parent_v19 if parent_v19 else float("inf")
        daughter_ratio = (
            daughter_unet / daughter_v19 if daughter_v19 else float("inf")
        )
        joined.append(
            {
                **row,
                "source_detector": reference["source_detector"],
                "source_link_strategy": reference["source_link_strategy"],
                "v19_parent_frame_count": parent_v19,
                "v19_daughter_frame_count": daughter_v19,
                "parent_frame_peak_ratio": parent_ratio,
                "daughter_frame_peak_ratio": daughter_ratio,
            }
        )
        sample_id = row["sample_id"]
        parent_t = int(row["t"])
        unique_frames[(sample_id, parent_t)] = (parent_unet, parent_v19)
        unique_frames[(sample_id, parent_t + 1)] = (daughter_unet, daughter_v19)

    ratios = [
        unet_count / v19_count if v19_count else float("inf")
        for unet_count, v19_count in unique_frames.values()
    ]
    unavailable = [
        row for row in joined if row["cohort"] == "baseline_unavailable"
    ]
    nonofficial = [
        row
        for row in joined
        if row["cohort"] == "baseline_nonofficial_action"
    ]
    controls = [
        row for row in joined if row["cohort"] == "positive_control"
    ]
    recovered = [
        row for row in unavailable if _is_true(row["complete_triplet"])
    ]
    preserved = [
        row for row in controls if _is_true(row["complete_triplet"])
    ]
    recovered_families = sorted(
        {row["sample_id"].split("_", 1)[0] for row in recovered}
    )

    contract = fixture["decision_contract"]
    ratio_median = median(ratios)
    ratio_p90 = _percentile(ratios, 0.9)
    gates = {
        "availability": len(recovered)
        >= int(contract["baseline_unavailable_min_complete"]),
        "controls": len(preserved)
        >= int(contract["positive_control_min_preserved"]),
        "families": recovered_families
        == sorted(contract["required_recovered_families"]),
        "frame_ratio_median": ratio_median
        <= float(contract["frame_peak_ratio_median_max"]),
        "frame_ratio_p90": ratio_p90
        <= float(contract["frame_peak_ratio_p90_max"]),
        "zero_perturbation": all(
            not _is_true(row["graph_mutated"])
            and not _is_true(row["edges_inferred"])
            for row in joined
        ),
    }
    decision = "GO" if all(gates.values()) else "NO_GO"
    status_counts = Counter(
        (row["baseline_status"], _is_true(row["complete_triplet"]))
        for row in joined
    )
    family_counts = Counter(
        (
            row["sample_id"].split("_", 1)[0],
            _is_true(row["complete_triplet"]),
        )
        for row in joined
    )
    summary = {
        "decision": decision,
        "gates": gates,
        "cases": len(joined),
        "samples": len({row["sample_id"] for row in joined}),
        "baseline_unavailable_complete_triplets": len(recovered),
        "baseline_unavailable_cases": len(unavailable),
        "baseline_nonofficial_complete_triplets": sum(
            _is_true(row["complete_triplet"]) for row in nonofficial
        ),
        "baseline_nonofficial_cases": len(nonofficial),
        "positive_controls_preserved": len(preserved),
        "positive_controls": len(controls),
        "recovered_families": recovered_families,
        "unique_event_frames": len(unique_frames),
        "frame_peak_ratio_median": ratio_median,
        "frame_peak_ratio_p90": ratio_p90,
        "graph_mutation": False,
        "edge_inference_used": False,
    }

    report_lines = [
        "# V22 Temporal U-Net Full Development Shadow Results",
        "",
        f"Decision: **{decision}**",
        "",
        "## Primary Gates",
        "",
        f"- Previously unavailable complete triplets: **{len(recovered)}/{len(unavailable)}**.",
        f"- Official-positive controls preserved: **{len(preserved)}/{len(controls)}**.",
        f"- Recovered families: **{', '.join(recovered_families) or 'none'}**.",
        f"- Unique event-frame U-Net/V19 peak ratio: median **{ratio_median:.3f}**, p90 **{ratio_p90:.3f}**.",
        "- Graph mutation: **False**.",
        "- Edge inference: **False**.",
        "",
        "## Gate Outcomes",
        "",
    ]
    report_lines.extend(
        f"- `{name}`: **{'PASS' if passed else 'FAIL'}**"
        for name, passed in gates.items()
    )
    report_lines.extend(
        [
            "",
            "## Complete Triplets By Baseline Status",
            "",
            "| status | complete | incomplete |",
            "|---|---:|---:|",
        ]
    )
    for status in sorted({row["baseline_status"] for row in joined}):
        report_lines.append(
            f"| `{status}` | {status_counts[(status, True)]} | "
            f"{status_counts[(status, False)]} |"
        )
    report_lines.extend(
        [
            "",
            "## Complete Triplets By Family",
            "",
            "| family | complete | incomplete |",
            "|---|---:|---:|",
        ]
    )
    for family in ("44b6", "6bba"):
        report_lines.append(
            f"| `{family}` | {family_counts[(family, True)]} | "
            f"{family_counts[(family, False)]} |"
        )
    report_lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            "A complete triplet is detector availability, not an official division TP. "
            "This shadow does not evaluate learned edges, semantic division scoring, "
            "or production graph integration.",
            "",
        ]
    )

    _write_csv(args.output_csv, joined)
    args.output_summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output_report.write_text(
        "\n".join(report_lines),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
