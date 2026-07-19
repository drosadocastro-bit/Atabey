from __future__ import annotations

import argparse
import csv
import random
import statistics
import sys
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.evaluation.sparse_ground_truth import match_sparse_centroids
from atabey.io.geff_reader import SparseGroundTruthGraph, read_geff_graph
from atabey.tracking.division_recovery_shadow import DivisionRecoveryCandidate, compute_division_recovery_shadow
from atabey.types import LineageGraph
from run_v21_division_recovery_shadow import _build_v19_prefirewall


@dataclass(frozen=True)
class RankedCandidateRow:
    sample_id: str
    rank: int
    parent_id: str
    child_1_id: str
    child_2_id: str
    t: int
    accepted: bool
    is_tp: bool
    matched_gt_parent_id: int | None
    reason: str
    ranking_score: float
    geometry_score: float
    angle_deg: float | None
    distance_ratio: float | None
    max_drift_deg: float | None
    v_sep_1_um_per_frame: float | None
    child_1_distance_um: float
    child_2_distance_um: float
    child_separation_um: float
    local_density_t1_10um: int
    parent_volume: float | None
    child_volume_sum: float | None
    volume_conservation_error: float | None
    parent_intensity: float | None
    child_intensity_sum: float | None
    intensity_conservation_error: float | None


@dataclass(frozen=True)
class MissedGtDivisionRow:
    sample_id: str
    gt_parent_id: int
    gt_child_1_id: int
    gt_child_2_id: int
    pred_parent_id: str | None
    pred_child_1_id: str | None
    pred_child_2_id: str | None
    parent_matched: bool
    child_1_matched: bool
    child_2_matched: bool
    reachable_track_b_candidates: int
    reachable_accepted_candidates: int
    reachable_rejected_candidates: int
    best_rejected_reason: str | None
    best_rejected_ranking_score: float | None
    diagnosis: str


def _outgoing(graph: LineageGraph) -> dict[str, list[str]]:
    outgoing: dict[str, list[str]] = {}
    for edge in graph.edges:
        outgoing.setdefault(edge.source_id, []).append(edge.target_id)
    return outgoing


def _reaches(outgoing: dict[str, list[str]], start_id: str, target_id: str, max_depth: int = 5) -> bool:
    if start_id == target_id:
        return True
    queue: deque[tuple[str, int]] = deque([(start_id, 0)])
    visited = {start_id}
    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for nxt in outgoing.get(current, []):
            if nxt == target_id:
                return True
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, depth + 1))
    return False


def _gt_divisions(ground_truth: SparseGroundTruthGraph) -> list[tuple[int, int, int]]:
    outgoing: dict[int, list[int]] = {}
    for source_id, target_id in ground_truth.edges:
        outgoing.setdefault(int(source_id), []).append(int(target_id))
    return [(source_id, targets[0], targets[1]) for source_id, targets in outgoing.items() if len(targets) >= 2]


def _gt_matches(graph: LineageGraph, ground_truth: SparseGroundTruthGraph) -> dict[int, str]:
    return {
        match.ground_truth_node_id: match.prediction_node_id
        for match in match_sparse_centroids(graph, ground_truth)
        if match.matched and match.prediction_node_id is not None
    }


def _candidate_matches_gt(
    candidate: DivisionRecoveryCandidate,
    gt_parent: int,
    gt_child_1: int,
    gt_child_2: int,
    gt_to_pred: dict[int, str],
    gt_nodes_by_id: dict[int, object],
    pred_nodes_by_id: dict[str, object],
    outgoing: dict[str, list[str]],
) -> bool:
    pred_parent = gt_to_pred.get(gt_parent)
    pred_child_1 = gt_to_pred.get(gt_child_1)
    pred_child_2 = gt_to_pred.get(gt_child_2)
    if not (pred_parent and pred_child_1 and pred_child_2):
        return False
    pred_node = pred_nodes_by_id.get(candidate.parent_id)
    gt_node = gt_nodes_by_id.get(gt_parent)
    if pred_node is None or gt_node is None:
        return False
    if abs(int(pred_node.t) - int(gt_node.t)) > 2:
        return False
    return (
        _reaches(outgoing, pred_parent, candidate.parent_id, max_depth=3)
        and _reaches(outgoing, candidate.parent_id, pred_child_1, max_depth=3)
        and _reaches(outgoing, candidate.parent_id, pred_child_2, max_depth=3)
    )


def _label_candidates(
    graph: LineageGraph,
    ground_truth: SparseGroundTruthGraph,
    candidates: list[DivisionRecoveryCandidate],
) -> tuple[list[RankedCandidateRow], list[MissedGtDivisionRow]]:
    accepted = [candidate for candidate in candidates if candidate.accepted]
    ranked = sorted(accepted, key=lambda candidate: (-candidate.ranking_score, candidate.parent_id))
    outgoing = _outgoing(graph)
    gt_to_pred = _gt_matches(graph, ground_truth)
    gt_nodes_by_id = {int(node.node_id): node for node in ground_truth.nodes}
    pred_nodes_by_id = {node.node_id: node for node in graph.detections}
    gt_divisions = _gt_divisions(ground_truth)

    candidate_to_gt: dict[str, int] = {}
    gt_to_candidate: dict[int, str] = {}
    for gt_parent, gt_child_1, gt_child_2 in gt_divisions:
        for candidate in ranked:
            if candidate.parent_id in candidate_to_gt:
                continue
            if _candidate_matches_gt(
                candidate,
                gt_parent,
                gt_child_1,
                gt_child_2,
                gt_to_pred,
                gt_nodes_by_id,
                pred_nodes_by_id,
                outgoing,
            ):
                candidate_to_gt[candidate.parent_id] = gt_parent
                gt_to_candidate[gt_parent] = candidate.parent_id
                break

    rows = [
        RankedCandidateRow(
            sample_id=candidate.sample_id,
            rank=rank,
            parent_id=candidate.parent_id,
            child_1_id=candidate.child_1_id,
            child_2_id=candidate.child_2_id,
            t=candidate.t,
            accepted=candidate.accepted,
            is_tp=candidate.parent_id in candidate_to_gt,
            matched_gt_parent_id=candidate_to_gt.get(candidate.parent_id),
            reason=candidate.reason,
            ranking_score=candidate.ranking_score,
            geometry_score=candidate.score,
            angle_deg=candidate.angle_deg,
            distance_ratio=candidate.distance_ratio,
            max_drift_deg=candidate.max_drift_deg,
            v_sep_1_um_per_frame=candidate.v_sep_1_um_per_frame,
            child_1_distance_um=candidate.child_1_distance_um,
            child_2_distance_um=candidate.child_2_distance_um,
            child_separation_um=candidate.child_separation_um,
            local_density_t1_10um=candidate.local_density_t1_10um,
            parent_volume=candidate.parent_volume,
            child_volume_sum=candidate.child_volume_sum,
            volume_conservation_error=candidate.volume_conservation_error,
            parent_intensity=candidate.parent_intensity,
            child_intensity_sum=candidate.child_intensity_sum,
            intensity_conservation_error=candidate.intensity_conservation_error,
        )
        for rank, candidate in enumerate(ranked, start=1)
    ]

    missed: list[MissedGtDivisionRow] = []
    all_candidates = list(candidates)
    for gt_parent, gt_child_1, gt_child_2 in gt_divisions:
        if gt_parent in gt_to_candidate:
            continue
        pred_parent = gt_to_pred.get(gt_parent)
        pred_child_1 = gt_to_pred.get(gt_child_1)
        pred_child_2 = gt_to_pred.get(gt_child_2)
        reachable = [
            candidate
            for candidate in all_candidates
            if _candidate_matches_gt(
                candidate,
                gt_parent,
                gt_child_1,
                gt_child_2,
                gt_to_pred,
                gt_nodes_by_id,
                pred_nodes_by_id,
                outgoing,
            )
        ]
        rejected = [candidate for candidate in reachable if not candidate.accepted]
        accepted_reachable = [candidate for candidate in reachable if candidate.accepted]
        best_rejected = max(rejected, key=lambda candidate: candidate.ranking_score) if rejected else None
        if not (pred_parent and pred_child_1 and pred_child_2):
            diagnosis = "sparse_gt_node_unmatched_to_prediction"
        elif accepted_reachable:
            diagnosis = "accepted_candidate_unassigned_after_one_to_one_tp_matching"
        elif rejected:
            diagnosis = "candidate_exists_but_track_b_gate_rejected"
        else:
            diagnosis = "no_track_b_candidate_reaches_gt_division"
        missed.append(
            MissedGtDivisionRow(
                sample_id=graph.sample_id,
                gt_parent_id=gt_parent,
                gt_child_1_id=gt_child_1,
                gt_child_2_id=gt_child_2,
                pred_parent_id=pred_parent,
                pred_child_1_id=pred_child_1,
                pred_child_2_id=pred_child_2,
                parent_matched=pred_parent is not None,
                child_1_matched=pred_child_1 is not None,
                child_2_matched=pred_child_2 is not None,
                reachable_track_b_candidates=len(reachable),
                reachable_accepted_candidates=len(accepted_reachable),
                reachable_rejected_candidates=len(rejected),
                best_rejected_reason=best_rejected.reason if best_rejected else None,
                best_rejected_ranking_score=best_rejected.ranking_score if best_rejected else None,
                diagnosis=diagnosis,
            )
        )
    return rows, missed


def _median(values: list[float]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return float(statistics.median(clean)) if clean else None


def _mean(values: list[float]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return float(statistics.mean(clean)) if clean else None


def _feature_summary(rows: list[RankedCandidateRow], *, fp_sample_size: int, seed: int) -> list[dict[str, object]]:
    rng = random.Random(seed)
    tps = [row for row in rows if row.is_tp]
    fps = [row for row in rows if not row.is_tp]
    fp_sample = rng.sample(fps, min(fp_sample_size, len(fps))) if fps else []
    cohorts = [("tp", tps), ("fp_sample", fp_sample), ("fp_all", fps)]
    features = [
        "ranking_score",
        "geometry_score",
        "angle_deg",
        "distance_ratio",
        "max_drift_deg",
        "v_sep_1_um_per_frame",
        "child_separation_um",
        "local_density_t1_10um",
        "volume_conservation_error",
        "intensity_conservation_error",
    ]
    summary: list[dict[str, object]] = []
    for cohort_name, cohort_rows in cohorts:
        record: dict[str, object] = {"cohort": cohort_name, "n": len(cohort_rows)}
        for feature in features:
            values = [getattr(row, feature) for row in cohort_rows if getattr(row, feature) is not None]
            record[f"{feature}_mean"] = _mean(values)
            record[f"{feature}_median"] = _median(values)
        summary.append(record)
    return summary


def _write_csv(path: Path, rows: list[object], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row) if hasattr(row, "__dataclass_fields__") else row)


def _write_markdown_report(
    path: Path,
    candidate_rows: list[RankedCandidateRow],
    missed_rows: list[MissedGtDivisionRow],
    feature_summary: list[dict[str, object]],
) -> None:
    tp_rows = [row for row in candidate_rows if row.is_tp]
    top_10 = sum(1 for row in tp_rows if row.rank <= 10)
    top_50 = sum(1 for row in tp_rows if row.rank <= 50)
    total_tp = len(tp_rows)
    max_rank = max((row.rank for row in tp_rows), default=None)
    lines = [
        "# V21 Track B Ranking Analysis",
        "",
        "Track B-only ranking analysis. This does not mutate Track A and does not change which Track B candidates are logged.",
        "",
        "## TP Rank Positions",
        "",
        "| Sample | GT parent | Candidate parent | Rank | Ranking score | Reason | Density | Volume error | Intensity error |",
        "| --- | ---: | --- | ---: | ---: | --- | ---: | ---: | ---: |",
    ]
    for row in tp_rows:
        lines.append(
            f"| `{row.sample_id}` | `{row.matched_gt_parent_id}` | `{row.parent_id}` | {row.rank} | {row.ranking_score:.6f} | `{row.reason}` | {row.local_density_t1_10um} | {_fmt(row.volume_conservation_error)} | {_fmt(row.intensity_conservation_error)} |"
        )
    lines.extend([
        "",
        "## Ranking Capture",
        "",
        f"- Known TP candidates ranked: `{total_tp}`.",
        f"- TPs in top 10: `{top_10}/{total_tp}`.",
        f"- TPs in top 50: `{top_50}/{total_tp}`.",
        f"- Worst TP rank: `{max_rank}`.",
        "",
        "## Feature Summary",
        "",
    ])
    for record in feature_summary:
        lines.append(f"### {record['cohort']}")
        lines.append("")
        lines.append(f"- n: `{record['n']}`")
        for key, value in record.items():
            if key in {"cohort", "n"}:
                continue
            if key.endswith("_median"):
                lines.append(f"- {key}: `{_fmt(value)}`")
        lines.append("")
    lines.extend([
        "## Missed GT Divisions",
        "",
        "| Sample | GT parent | Matched nodes | Reachable candidates | Accepted reachable | Rejected reachable | Diagnosis |",
        "| --- | ---: | --- | ---: | ---: | ---: | --- |",
    ])
    for row in missed_rows:
        matched = f"parent={row.parent_matched}, child1={row.child_1_matched}, child2={row.child_2_matched}"
        lines.append(
            f"| `{row.sample_id}` | `{row.gt_parent_id}` | `{matched}` | {row.reachable_track_b_candidates} | {row.reachable_accepted_candidates} | {row.reachable_rejected_candidates} | `{row.diagnosis}` |"
        )
    lines.extend([
        "",
        "## Assessment",
        "",
        "This ranking is diagnostic. It should be judged by TP rank position and top-N capture, not by changing Track A or committing candidates as lineage edges.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt(value: object) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _sample_ids_from_args(sample_ids: list[str]) -> list[str]:
    if sample_ids == ["all"]:
        return sorted(path.stem for path in (project_root / "train").glob("*.zarr"))
    return sample_ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank and diagnose V21 Track B division candidates.")
    parser.add_argument("--sample-ids", nargs="+", default=["6bba_05db0fb1", "6bba_b329af44", "6bba_ebdf3b34"])
    parser.add_argument("--max-timepoints", type=int, default=100)
    parser.add_argument("--candidate-output", type=Path, default=project_root / "v21_track_b_ranked_candidates.csv")
    parser.add_argument("--missed-output", type=Path, default=project_root / "v21_track_b_missed_gt_divisions.csv")
    parser.add_argument("--feature-output", type=Path, default=project_root / "v21_track_b_feature_summary.csv")
    parser.add_argument("--report-output", type=Path, default=project_root / "V21_TRACK_B_RANKING.md")
    parser.add_argument("--fp-sample-size", type=int, default=100)
    parser.add_argument("--random-seed", type=int, default=21)
    args = parser.parse_args()

    candidate_rows: list[RankedCandidateRow] = []
    missed_rows: list[MissedGtDivisionRow] = []
    sample_ids = _sample_ids_from_args(args.sample_ids)
    for index, sample_id in enumerate(sample_ids, start=1):
        print(f"[{index}/{len(sample_ids)}] {sample_id}", flush=True)
        sample_path = project_root / "train" / f"{sample_id}.zarr"
        gt_path = project_root / "train" / f"{sample_id}.geff"
        graph = _build_v19_prefirewall(sample_path, max_timepoints=args.max_timepoints)
        ground_truth = read_geff_graph(gt_path)
        shadow = compute_division_recovery_shadow(graph)
        rows, missed = _label_candidates(graph, ground_truth, shadow.candidates)
        candidate_rows.extend(rows)
        missed_rows.extend(missed)
        tp_ranks = [row.rank for row in rows if row.is_tp]
        print(
            f"  accepted={len(rows)} tp={len(tp_ranks)} missed_gt={len(missed)} "
            f"tp_ranks={tp_ranks}",
            flush=True,
        )

    feature_summary = _feature_summary(candidate_rows, fp_sample_size=args.fp_sample_size, seed=args.random_seed)
    _write_csv(args.candidate_output, candidate_rows, list(RankedCandidateRow.__dataclass_fields__.keys()))
    _write_csv(args.missed_output, missed_rows, list(MissedGtDivisionRow.__dataclass_fields__.keys()))
    _write_csv(args.feature_output, feature_summary, list(feature_summary[0].keys()) if feature_summary else ["cohort", "n"])
    _write_markdown_report(args.report_output, candidate_rows, missed_rows, feature_summary)
    print(f"Wrote {args.candidate_output}")
    print(f"Wrote {args.missed_output}")
    print(f"Wrote {args.feature_output}")
    print(f"Wrote {args.report_output}")


if __name__ == "__main__":
    main()
