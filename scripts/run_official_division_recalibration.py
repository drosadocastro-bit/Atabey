from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.evaluation.official_division_metric import evaluate_official_divisions
from atabey.io.geff_reader import SparseGroundTruthGraph, read_geff_graph
from atabey.tracking.division_recovery_shadow import compute_division_recovery_shadow
from run_v21_division_recovery_shadow import _build_track_a_v20, _build_v19_prefirewall
from run_v21_local_assignment_shadow import CASES


KNOWN_TRACK_B_PARENTS = {
    "P1-05DB": "6bba_05db0fb1:t24:cf76",
    "P1-B329": "6bba_b329af44:t82:cf38",
    "P1-EBDF-LATE": "6bba_ebdf3b34:t84:cf39",
}


def _division_subset(
    ground_truth: SparseGroundTruthGraph,
    parent_ids: set[int],
) -> SparseGroundTruthGraph:
    outgoing: dict[int, list[int]] = {}
    incoming: dict[int, list[int]] = {}
    for source_id, target_id in ground_truth.edges:
        outgoing.setdefault(int(source_id), []).append(int(target_id))
        incoming.setdefault(int(target_id), []).append(int(source_id))
    keep: set[int] = set()
    for parent_id in parent_ids:
        children = outgoing.get(parent_id, [])
        keep.add(parent_id)
        keep.update(incoming.get(parent_id, []))
        keep.update(children)
        for child_id in children:
            keep.update(outgoing.get(child_id, []))
    return SparseGroundTruthGraph(
        sample_id=ground_truth.sample_id,
        nodes=[node for node in ground_truth.nodes if int(node.node_id) in keep],
        edges=[
            (int(source_id), int(target_id))
            for source_id, target_id in ground_truth.edges
            if int(source_id) in keep and int(target_id) in keep
        ],
        estimated_number_of_nodes=ground_truth.estimated_number_of_nodes,
    )


def _fork_count(graph) -> int:
    outgoing: dict[str, set[str]] = {}
    for edge in graph.edges:
        outgoing.setdefault(edge.source_id, set()).add(edge.target_id)
    return sum(len(targets) >= 2 for targets in outgoing.values())


def _write_report(path: Path, sample_rows: list[dict[str, object]], case_rows: list[dict[str, object]]) -> None:
    v19_tp = sum(int(row["v19_tp"]) for row in sample_rows)
    v19_fp = sum(int(row["v19_fp"]) for row in sample_rows)
    v19_fn = sum(int(row["v19_fn"]) for row in sample_rows)
    v20_tp = sum(int(row["v20_tp"]) for row in sample_rows)
    v20_fp = sum(int(row["v20_fp"]) for row in sample_rows)
    v20_fn = sum(int(row["v20_fn"]) for row in sample_rows)
    raw_forks = sum(int(row["v19_raw_forks"]) for row in sample_rows)
    accepted = sum(int(row["track_b_accepted"]) for row in sample_rows)
    accepted_tp = sum(int(row["track_b_official_tp_forks"]) for row in sample_rows)
    accepted_fp = sum(int(row["track_b_official_fp_forks"]) for row in sample_rows)
    accepted_ignored = sum(int(row["track_b_official_ignored_forks"]) for row in sample_rows)
    known = [row for row in case_rows if row["known_track_b_parent_id"]]
    known_real = sum(bool(row["known_parent_is_official_tp"]) for row in known)

    def precision(tp: int, fp: int) -> str:
        return f"{tp / (tp + fp):.6f}" if tp + fp else "n/a"

    lines = [
        "# Official Patched Division Recalibration",
        "",
        "This audit calls the host repository's patched `score_divisions` directly after converting",
        "Atabey graphs to `tracksdata.InMemoryGraph`. GT evaluation is restricted to the fixed",
        "Phase 1/2 division windows (grandparent, divider, children, grandchildren). Track A/B",
        "graphs and candidate decisions are not mutated.",
        "",
        "## Aggregate fixed-window counts",
        "",
        f"- V19 official TP/FP/FN: **{v19_tp}/{v19_fp}/{v19_fn}**; precision `{precision(v19_tp, v19_fp)}`.",
        f"- V20 official TP/FP/FN: **{v20_tp}/{v20_fp}/{v20_fn}**; precision `{precision(v20_tp, v20_fp)}`.",
        f"- V19 raw forks in the bounded graphs: **{raw_forks}**; official evaluable FP forks: **{v19_fp}**.",
        f"- Track B accepted forks: **{accepted}** = official TP **{accepted_tp}**, official FP **{accepted_fp}**, sparse-unsupported/ignored **{accepted_ignored}**.",
        "",
        "## Three formerly recovered TPs",
        "",
        f"Official TP confirmation: **{known_real}/3**.",
        "",
        "| Case | GT parent | Track B parent | Accepted | Official GT recovered | Parent is official TP fork |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for row in known:
        lines.append(
            f"| {row['case_id']} | {row['gt_parent_id']} | `{row['known_track_b_parent_id']}` | "
            f"{row['known_parent_track_b_accepted']} | {row['v19_gt_recovered']} | "
            f"{row['known_parent_is_official_tp']} |"
        )
    lines.extend(
        [
            "",
            "## Fixed case breakdown",
            "",
            "| Case | Phase | V19 recovered | V20 recovered |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in case_rows:
        lines.append(
            f"| {row['case_id']} | {row['phase']} | {row['v19_gt_recovered']} | {row['v20_gt_recovered']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation guardrail",
            "",
            "Counts here are corrected official-metric evidence for the pre-registered windows, not a",
            "199-sample population estimate. Joint voting and new division mechanisms remain blocked",
            "until this report is reviewed.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Recalibrate fixed V21 cases with the patched official metric.")
    parser.add_argument("--output-prefix", default="official_division_recalibration")
    args = parser.parse_args()

    sample_rows: list[dict[str, object]] = []
    case_rows: list[dict[str, object]] = []
    for index, sample_id in enumerate(sorted({case.sample_id for case in CASES}), start=1):
        cases = [case for case in CASES if case.sample_id == sample_id]
        max_timepoints = max(case.t + 4 for case in cases)
        print(f"[{index}/13] {sample_id} through {max_timepoints} timepoints", flush=True)
        ground_truth = read_geff_graph(project_root / "train" / f"{sample_id}.geff")
        subset = _division_subset(ground_truth, {int(case.gt_parent_id) for case in cases})
        sample_path = project_root / "train" / f"{sample_id}.zarr"
        v19 = _build_v19_prefirewall(sample_path, max_timepoints)
        v20, _, _ = _build_track_a_v20(sample_path, max_timepoints)
        v19_result = evaluate_official_divisions(v19, subset)
        v20_result = evaluate_official_divisions(v20, subset)
        shadow = compute_division_recovery_shadow(v19)
        accepted_ids = {candidate.parent_id for candidate in shadow.candidates if candidate.accepted}
        accepted_tp = accepted_ids & set(v19_result.tp_fork_ids)
        accepted_fp = accepted_ids & set(v19_result.fp_fork_ids)
        accepted_ignored = accepted_ids - accepted_tp - accepted_fp
        sample_rows.append(
            {
                "sample_id": sample_id,
                "fixed_gt_divisions": len(cases),
                "v19_raw_forks": _fork_count(v19),
                "v19_tp": v19_result.tp,
                "v19_fp": v19_result.fp,
                "v19_fn": v19_result.fn,
                "v20_raw_forks": _fork_count(v20),
                "v20_tp": v20_result.tp,
                "v20_fp": v20_result.fp,
                "v20_fn": v20_result.fn,
                "track_b_accepted": len(accepted_ids),
                "track_b_official_tp_forks": len(accepted_tp),
                "track_b_official_fp_forks": len(accepted_fp),
                "track_b_official_ignored_forks": len(accepted_ignored),
            }
        )
        for case in cases:
            known_parent = KNOWN_TRACK_B_PARENTS.get(case.case_id, "")
            row = {
                "case_id": case.case_id,
                "phase": case.phase,
                "sample_id": sample_id,
                "gt_parent_id": int(case.gt_parent_id),
                "v19_gt_recovered": bool(v19_result.gt_scores.get(int(case.gt_parent_id), 0)),
                "v20_gt_recovered": bool(v20_result.gt_scores.get(int(case.gt_parent_id), 0)),
                "known_track_b_parent_id": known_parent,
                "known_parent_track_b_accepted": bool(known_parent and known_parent in accepted_ids),
                "known_parent_is_official_tp": bool(known_parent and known_parent in v19_result.tp_fork_ids),
                "known_parent_is_official_fp": bool(known_parent and known_parent in v19_result.fp_fork_ids),
            }
            case_rows.append(row)
            print(
                f"  {case.case_id}: V19={row['v19_gt_recovered']} V20={row['v20_gt_recovered']}"
                + (f" known_parent_tp={row['known_parent_is_official_tp']}" if known_parent else ""),
                flush=True,
            )

    prefix = project_root / args.output_prefix
    for suffix, rows in (("_samples.csv", sample_rows), ("_cases.csv", case_rows)):
        with Path(f"{prefix}{suffix}").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    report = project_root / "OFFICIAL_DIVISION_RECALIBRATION.md"
    _write_report(report, sample_rows, case_rows)
    print(f"Wrote {report}", flush=True)


if __name__ == "__main__":
    main()
