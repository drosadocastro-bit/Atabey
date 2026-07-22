from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.evaluation.sparse_ground_truth import match_sparse_centroids
from atabey.io.geff_reader import read_geff_graph
from atabey.tracking.local_assignment_shadow import PairHypothesis, rank_local_pair_hypotheses
from audit_v21_counterfactual_pairing import PairingCase, audit_case
from run_v21_division_recovery_shadow import _build_v19_prefirewall


@dataclass(frozen=True)
class ValidationCase:
    case_id: str
    phase: str
    sample_id: str
    gt_parent_id: int
    gt_child_1_id: int
    gt_child_2_id: int
    t: int


CASES = (
    ValidationCase("P1-05DB", "phase1", "6bba_05db0fb1", 25000381, 26000400, 26000403, 24),
    ValidationCase("P1-B329", "phase1", "6bba_b329af44", 83001755, 84001784, 84001785, 82),
    ValidationCase("P1-EBDF-EARLY", "phase1", "6bba_ebdf3b34", 14000412, 15000432, 15000433, 13),
    ValidationCase("P1-EBDF-LATE", "phase1", "6bba_ebdf3b34", 85001151, 86001164, 86001165, 84),
    ValidationCase("P2-12DF", "phase2", "44b6_12dfb391", 172000000050, 173000000050, 173000000051, 66),
    ValidationCase("P2-207C", "phase2", "6bba_207c6aaf", 42000280, 43000304, 43000305, 41),
    ValidationCase("P2-F8FF", "phase2", "6bba_f8ffd5e7", 64000650, 65000662, 65000663, 63),
    ValidationCase("P2-4FFD", "phase2", "6bba_4ffd3da3", 46000256, 47000265, 47000266, 45),
    ValidationCase("P2-587A", "phase2", "44b6_587a1e22", 21000000052, 22000000053, 22000000052, 19),
    ValidationCase("P2-D754", "phase2", "44b6_d754aa59", 69000000054, 70000000054, 70000000055, 63),
    ValidationCase("P2-32DB", "phase2", "6bba_32db13fc", 6000204, 7000244, 7000281, 5),
    ValidationCase("P2-2A2E", "phase2", "44b6_2a2eff9f", 160000000048, 161000000049, 161000000048, 11),
    ValidationCase("P2-55B7", "phase2", "6bba_55b7eebe", 49000351, 50000359, 50000360, 48),
    ValidationCase("P2-705E", "phase2", "6bba_705ec2c9", 43000460, 44000474, 44000477, 42),
)


def _edge_signature(graph) -> tuple[tuple[str, str, str], ...]:
    return tuple(sorted((edge.source_id, edge.target_id, edge.relation) for edge in graph.edges))


def _matched_ids(graph, sample_id: str, gt_ids: tuple[int, int, int]) -> tuple[str, str, str]:
    ground_truth = read_geff_graph(project_root / "train" / f"{sample_id}.geff")
    mapping = {
        int(match.ground_truth_node_id): match.prediction_node_id
        for match in match_sparse_centroids(graph, ground_truth)
        if match.matched and match.prediction_node_id is not None
    }
    missing = [node_id for node_id in gt_ids if node_id not in mapping]
    if missing:
        raise RuntimeError(f"{sample_id}: validation case unexpectedly lost sparse matches {missing}")
    return tuple(str(mapping[node_id]) for node_id in gt_ids)


def _write_report(path: Path, rows: list[dict[str, object]]) -> None:
    base_ranks = [int(row["base_rank"]) for row in rows]
    local_ranks = [int(row["local_rank"]) for row in rows]
    improved = sum(local < base for base, local in zip(base_ranks, local_ranks))
    flat = sum(local == base for base, local in zip(base_ranks, local_ranks))
    regressed = sum(local > base for base, local in zip(base_ranks, local_ranks))
    top1_before = sum(rank == 1 for rank in base_ranks)
    top1_after = sum(rank == 1 for rank in local_ranks)
    go = median(local_ranks) < median(base_ranks) and regressed == 0 and top1_after >= 10

    lines = [
        "# V21 Local Assignment Shadow Audit",
        "",
        "## Scope",
        "",
        "This is a read-only shadow diagnostic. It does not alter Track A, Track B, graph edges,",
        "candidate formation, or production linking. Each focal daughter-pair hypothesis reserves",
        "only its two proposed cells; Hungarian assignment is then solved only for parents that",
        "already own or mutually claim either reserved cell.",
        "",
        "Ranking is lexicographic: (1) fewer displaced competing parents, (2) lower added",
        "continuation prediction cost, and (3) the existing balanced Track B score. This avoids",
        "mixing physical distance and Track B confidence in an arbitrary weighted scalar.",
        "",
        "## Why 10 of 20 Phase 2 cases were unevaluable",
        "",
        "The sparse centroid matcher uses same-timepoint detections, a 7 um radius, greedy",
        "one-to-one matching, and no lineage edges. Therefore a daughter claimed by another parent",
        "or a parent outside the bounded future window cannot make a detection disappear from this",
        "evaluation. Across 12 missing GT nodes in the 10 cases:",
        "",
        "- 7 were localization gaps between 7 and 14 um.",
        "- 2 were detection/localization gaps beyond 14 um.",
        "- 2 were recovered by a global distance-ordered matcher, proving standard match-order artifacts.",
        "- 1 was one-to-one evaluator contention; that sample also had a parent beyond 14 um.",
        "",
        "At sample level, 8/10 were primarily detection/localization failures and 2/10 were matcher-order",
        "artifacts. This is separate from lineage ownership contention, although both can occur in the",
        "same sample.",
        "",
        "## Pre-registered decision rule",
        "",
        "Proceed beyond this bounded shadow experiment only if the median correct-pair rank improves,",
        "no correct-pair case regresses, and at least 10/14 correct pairs rank first. Passing does not",
        "authorize Track A/B integration.",
        "",
        "## Results",
        "",
        f"- Correct-pair ranks improved/flat/regressed: **{improved}/{flat}/{regressed}**.",
        f"- Top-1 correct pairs: **{top1_before}/14 before, {top1_after}/14 after**.",
        f"- Median correct-pair rank: **{median(base_ranks):g} before, {median(local_ranks):g} after**.",
        f"- Zero perturbation: **{sum(bool(row['zero_perturbation']) for row in rows)}/14**.",
        f"- Decision: **{'GO to a broader shadow experiment' if go else 'NO-GO for broader rollout'}**.",
        "",
        "| Case | Phase | Base rank | Local rank | Pairs | Competitors | Disputed targets | Displaced | Cost increase um |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['case_id']} | {row['phase']} | {row['base_rank']} | {row['local_rank']} | "
            f"{row['pair_count']} | {row['competing_parents']} | {row['disputed_targets']} | "
            f"{row['displaced_parents']} | {float(row['assignment_cost_increase_um']):.3f} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "A GO means only that local ownership contention is informative in this fixed battery.",
            "A NO-GO means Hungarian assignment, in this scoped formulation, does not reliably identify",
            "the true daughter pair and should not be expanded into a frame-wide solver.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate local disputed-cell assignment on 14 fixed cases.")
    parser.add_argument("--horizon", type=int, default=4)
    parser.add_argument("--observation-radius-um", type=float, default=14.0)
    parser.add_argument("--gate-um", type=float, default=9.0)
    parser.add_argument("--output", type=Path, default=Path("v21_local_assignment_shadow_14.csv"))
    parser.add_argument("--report", type=Path, default=Path("V21_LOCAL_ASSIGNMENT_SHADOW_AUDIT.md"))
    args = parser.parse_args()

    rows: list[dict[str, object]] = []
    for sample_id in sorted({case.sample_id for case in CASES}):
        sample_cases = [case for case in CASES if case.sample_id == sample_id]
        max_timepoints = max(case.t + args.horizon + 1 for case in sample_cases)
        print(f"Building {sample_id} through {max_timepoints} timepoints...", flush=True)
        graph = _build_v19_prefirewall(project_root / "train" / f"{sample_id}.zarr", max_timepoints)
        before = _edge_signature(graph)
        for spec in sample_cases:
            parent_id, child_1_id, child_2_id = _matched_ids(
                graph,
                sample_id,
                (spec.gt_parent_id, spec.gt_child_1_id, spec.gt_child_2_id),
            )
            case = PairingCase(
                case_id=spec.case_id,
                sample_id=sample_id,
                parent_id=parent_id,
                correct_child_1_id=child_1_id,
                correct_child_2_id=child_2_id,
                known_wrong_child_1_id=None,
                known_wrong_child_2_id=None,
                t=spec.t,
                context="Fixed Phase 1/2 ownership-contention validation case.",
            )
            pair_rows = audit_case(
                graph,
                case,
                observation_radius_um=args.observation_radius_um,
                horizon=args.horizon,
            )
            ranked = rank_local_pair_hypotheses(
                graph,
                parent_id,
                [
                    PairHypothesis(
                        str(row["child_1_id"]),
                        str(row["child_2_id"]),
                        float(row["balanced_score"]),
                        int(row["balanced_rank"]),
                    )
                    for row in pair_rows
                ],
                gate_um=args.gate_um,
            )
            correct_key = tuple(sorted((child_1_id, child_2_id)))
            correct = next(
                row for row in ranked if (row.child_1_id, row.child_2_id) == correct_key
            )
            row = {
                "case_id": spec.case_id,
                "phase": spec.phase,
                "sample_id": sample_id,
                "t": spec.t,
                "parent_id": parent_id,
                "correct_child_1_id": correct_key[0],
                "correct_child_2_id": correct_key[1],
                "pair_count": len(pair_rows),
                **asdict(correct),
                "zero_perturbation": before == _edge_signature(graph),
            }
            rows.append(row)
            print(
                f"  {spec.case_id}: correct {correct.base_rank}->{correct.local_rank} "
                f"competitors={correct.competing_parents} displaced={correct.displaced_parents}",
                flush=True,
            )
        if before != _edge_signature(graph):
            raise RuntimeError(f"{sample_id}: shadow assignment mutated graph edges")

    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    _write_report(args.report, rows)
    print(f"Wrote {args.output} and {args.report}", flush=True)


if __name__ == "__main__":
    main()
