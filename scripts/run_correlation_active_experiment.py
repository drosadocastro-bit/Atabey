"""Correlation layer — active-injection ablation with ground-truth scoring (Phase 2).

EXPERIMENTAL / GATED. Off by default. Requires ``--enable-correlation-active``.
Touches no production defaults, no ``run.py`` path, no V13 submission track. It
actually injects ``beacon_derived`` synthetic candidates into a *copy* of each
built graph and scores baseline vs. active against the sparse GEFF ground truth, so
recovery *potential* (Phase 1) can be confirmed as real quality *gain* — or refuted.

Two views are reported per discount:
  - overall (whole cohort)
  - the isolated at-risk subset (samples with track gaps from the OSS diagnostic)

The graph build (the expensive CFAR pipeline) runs once per sample; each discount
value reuses it via the cheap injection path, so the discount sweep is nearly free.
Ground truth is windowed to the built timepoints for an interpretable in-window recall.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter

# Reuse the production-faithful graph build + cohort/at-risk loading.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from run_correlation_shadow_experiment import _build_graph, _load_at_risk_ids  # noqa: E402
from run_oss_diagnostics import _load_routed_records  # noqa: E402

from atabey.evaluation.sparse_ground_truth import (  # noqa: E402
    evaluate_sparse_ground_truth,
    match_sparse_centroids,
)
from atabey.io.geff_reader import (  # noqa: E402
    SparseGroundTruthGraph,
    read_geff_graph,
)
from atabey.tracking.correlation_active import build_active_graph, is_synthetic_node  # noqa: E402

SCAN_JSON_DEFAULT = Path("submissions/cfar_bounded_scan_fulltrain.json")
OSS_JSON_DEFAULT = Path("submissions/oss_diagnostics.json")
MATCH_RADIUS_UM = 7.0


def _log(message: str) -> None:
    print(f"[active] {message}", file=sys.stderr, flush=True)


@dataclass
class ActiveRunRow:
    sample_id: str
    discount: float
    at_risk_pfa_1e_03: bool
    baseline_nodes: int
    baseline_edges: int
    synthetic_count: int
    node_inflation_pct: float
    edge_inflation_pct: float
    baseline_recall: float | None
    active_recall: float | None
    recall_delta: float | None
    baseline_edge_recall: float | None
    active_edge_recall: float | None
    edge_recall_delta: float | None
    matched_by_synthetic: int
    synthetic_match_precision: float | None
    uniquely_recovered_nodes: int
    displaced_matches: int
    injection_ms: float
    # --- Double-target / merge-gate diagnostics (Phase 3) ---
    synthetic_collision_count: int
    synthetic_gap_count: int
    collision_fraction: float | None
    gated_synthetic_count: int
    suppressed_by_merge_gate: int
    gated_active_recall: float | None
    gated_recall_delta: float | None
    gated_active_edge_recall: float | None
    gated_edge_recall_delta: float | None
    gated_matched_by_synthetic: int


def _window_ground_truth(gt: SparseGroundTruthGraph, max_t: int) -> SparseGroundTruthGraph:
    """Restrict ground truth to the built timepoint window for in-window recall."""

    nodes = [node for node in gt.nodes if node.t < max_t]
    in_window_ids = {node.node_id for node in nodes}
    edges = [(s, t) for s, t in gt.edges if s in in_window_ids and t in in_window_ids]
    return SparseGroundTruthGraph(
        sample_id=gt.sample_id,
        nodes=nodes,
        edges=edges,
        estimated_number_of_nodes=None,
    )


def _match_map(graph, gt, radius_um: float) -> dict[int, tuple[str | None, float | None]]:
    matches = match_sparse_centroids(graph, gt, radius_um=radius_um)
    return {
        m.ground_truth_node_id: (m.prediction_node_id, m.distance_um)
        for m in matches
        if m.matched
    }


def _classify(
    baseline_graph,
    active_graph,
    gt: SparseGroundTruthGraph,
) -> tuple[int, int, int]:
    """Return (matched_by_synthetic, uniquely_recovered, displaced_matches)."""

    baseline = _match_map(baseline_graph, gt, MATCH_RADIUS_UM)
    active = _match_map(active_graph, gt, MATCH_RADIUS_UM)

    matched_by_synthetic = sum(
        1 for pred_id, _dist in active.values() if pred_id and is_synthetic_node(pred_id)
    )
    uniquely_recovered = sum(1 for gt_id in active if gt_id not in baseline)
    displaced = 0
    for gt_id, (_pred, active_dist) in active.items():
        base = baseline.get(gt_id)
        if base is None or active_dist is None or base[1] is None:
            continue
        if active_dist > base[1] + 1e-9:
            displaced += 1
    return matched_by_synthetic, uniquely_recovered, displaced


def run_active(
    train_dir: Path,
    scan_json: Path,
    oss_json: Path,
    *,
    max_timepoints: int,
    max_samples: int | None,
    discounts: list[float],
    min_track_age_frames: int,
    max_consecutive_synthetic: int,
    node_inflation_ratio: float,
    merge_gate_radius_um: float,
    merge_gate_frame_window: int,
) -> dict:
    routed = _load_routed_records(scan_json)
    if max_samples is not None:
        routed = routed[:max_samples]
    at_risk_ids = _load_at_risk_ids(oss_json)
    _log(
        f"active ablation over {len(routed)} merged_6bba_only samples, {max_timepoints} tp, "
        f"discounts={discounts} ({len(at_risk_ids)} at-risk)"
    )

    rows: list[ActiveRunRow] = []
    for index, record in enumerate(routed, start=1):
        sample_id = record["sample_id"]
        sample_path = train_dir / f"{sample_id}.zarr"
        geff_path = train_dir / f"{sample_id}.geff"
        if not sample_path.exists() or not geff_path.exists():
            _log(f"  [{index}/{len(routed)}] {sample_id} missing zarr/geff, skipping")
            continue
        try:
            baseline_graph = _build_graph(
                sample_path, sample_id=sample_id, max_timepoints=max_timepoints
            )
            gt = _window_ground_truth(read_geff_graph(geff_path), max_timepoints)
            baseline_report = evaluate_sparse_ground_truth(
                baseline_graph, gt, match_radius_um=MATCH_RADIUS_UM
            )
            for discount in discounts:
                inject_start = perf_counter()
                # No-gate injection (prior Phase 2 behaviour + collision diagnostics).
                active_graph, summary = build_active_graph(
                    baseline_graph,
                    min_track_age_frames=min_track_age_frames,
                    max_consecutive_synthetic=max_consecutive_synthetic,
                    discount=discount,
                    node_inflation_ratio=node_inflation_ratio,
                    merge_gate_radius_um=merge_gate_radius_um,
                    merge_gate_frame_window=merge_gate_frame_window,
                    apply_merge_gate=False,
                )
                injection_ms = (perf_counter() - inject_start) * 1000.0
                active_report = evaluate_sparse_ground_truth(
                    active_graph, gt, match_radius_um=MATCH_RADIUS_UM
                )
                matched_by_synth, uniquely_recovered, displaced = _classify(
                    baseline_graph, active_graph, gt
                )
                # Gated injection (Phase 3 merge gate: genuine gaps only).
                gated_graph, gated_summary = build_active_graph(
                    baseline_graph,
                    min_track_age_frames=min_track_age_frames,
                    max_consecutive_synthetic=max_consecutive_synthetic,
                    discount=discount,
                    node_inflation_ratio=node_inflation_ratio,
                    merge_gate_radius_um=merge_gate_radius_um,
                    merge_gate_frame_window=merge_gate_frame_window,
                    apply_merge_gate=True,
                )
                gated_report = evaluate_sparse_ground_truth(
                    gated_graph, gt, match_radius_um=MATCH_RADIUS_UM
                )
                gated_matched_by_synth, _gu, _gd = _classify(
                    baseline_graph, gated_graph, gt
                )
                rows.append(
                    _row(
                        sample_id,
                        discount,
                        sample_id in at_risk_ids,
                        baseline_graph,
                        summary,
                        baseline_report,
                        active_report,
                        matched_by_synth,
                        uniquely_recovered,
                        displaced,
                        injection_ms,
                        gated_summary,
                        gated_report,
                        gated_matched_by_synth,
                    )
                )
        except Exception as exc:  # noqa: BLE001 - report and continue.
            _log(f"  [{index}/{len(routed)}] {sample_id} FAILED: {exc}")
            continue
        if index % 5 == 0 or index == len(routed):
            _log(f"  [{index}/{len(routed)}] {sample_id} done")

    return {
        "mode": "active_injection_merge_gate",
        "scope": "merged_6bba_only",
        "params": {
            "max_timepoints": max_timepoints,
            "discounts": discounts,
            "min_track_age_frames": min_track_age_frames,
            "max_consecutive_synthetic": max_consecutive_synthetic,
            "node_inflation_ratio": node_inflation_ratio,
            "merge_gate_radius_um": merge_gate_radius_um,
            "merge_gate_frame_window": merge_gate_frame_window,
            "match_radius_um": MATCH_RADIUS_UM,
        },
        "by_discount": _aggregate_by_discount(rows, discounts),
        "dense_region_check": _dense_region_check(rows, discounts),
        "rows": [asdict(r) for r in rows],
    }


def _row(
    sample_id, discount, at_risk, baseline_graph, summary,
    baseline_report, active_report, matched_by_synth, uniquely_recovered, displaced, injection_ms,
    gated_summary, gated_report, gated_matched_by_synth,
) -> ActiveRunRow:
    nodes = len(baseline_graph.detections)
    edges = len(baseline_graph.edges)

    def _delta(a: float | None, b: float | None) -> float | None:
        return round(a - b, 6) if a is not None and b is not None else None

    evaluated = summary.synthetic_collision_count + summary.synthetic_gap_count
    return ActiveRunRow(
        sample_id=sample_id,
        discount=discount,
        at_risk_pfa_1e_03=at_risk,
        baseline_nodes=nodes,
        baseline_edges=edges,
        synthetic_count=summary.synthetic_candidate_count,
        node_inflation_pct=round(100.0 * summary.synthetic_candidate_count / nodes, 4) if nodes else 0.0,
        edge_inflation_pct=round(100.0 * summary.synthetic_candidate_count / edges, 4) if edges else 0.0,
        baseline_recall=baseline_report.sparse_recall,
        active_recall=active_report.sparse_recall,
        recall_delta=_delta(active_report.sparse_recall, baseline_report.sparse_recall),
        baseline_edge_recall=baseline_report.sparse_edge_recall,
        active_edge_recall=active_report.sparse_edge_recall,
        edge_recall_delta=_delta(active_report.sparse_edge_recall, baseline_report.sparse_edge_recall),
        matched_by_synthetic=matched_by_synth,
        synthetic_match_precision=(
            round(matched_by_synth / summary.synthetic_candidate_count, 5)
            if summary.synthetic_candidate_count
            else None
        ),
        uniquely_recovered_nodes=uniquely_recovered,
        displaced_matches=displaced,
        injection_ms=round(injection_ms, 3),
        synthetic_collision_count=summary.synthetic_collision_count,
        synthetic_gap_count=summary.synthetic_gap_count,
        collision_fraction=(
            round(summary.synthetic_collision_count / evaluated, 5) if evaluated else None
        ),
        gated_synthetic_count=gated_summary.synthetic_candidate_count,
        suppressed_by_merge_gate=gated_summary.suppressed_by_merge_gate,
        gated_active_recall=gated_report.sparse_recall,
        gated_recall_delta=_delta(gated_report.sparse_recall, baseline_report.sparse_recall),
        gated_active_edge_recall=gated_report.sparse_edge_recall,
        gated_edge_recall_delta=_delta(
            gated_report.sparse_edge_recall, baseline_report.sparse_edge_recall
        ),
        gated_matched_by_synthetic=gated_matched_by_synth,
    )


def _mean_opt(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return round(float(mean(clean)), 6) if clean else None


def _aggregate_by_discount(rows: list[ActiveRunRow], discounts: list[float]) -> dict:
    out: dict[str, dict] = {}
    for discount in discounts:
        subset = [r for r in rows if r.discount == discount]
        at_risk = [r for r in subset if r.at_risk_pfa_1e_03]
        out[f"discount_{discount}"] = {
            "overall": _view(subset),
            "at_risk_only": _view(at_risk),
        }
    return out


def _view(rows: list[ActiveRunRow]) -> dict:
    return {
        "samples": len(rows),
        "mean_baseline_recall": _mean_opt([r.baseline_recall for r in rows]),
        "mean_active_recall": _mean_opt([r.active_recall for r in rows]),
        "mean_recall_delta": _mean_opt([r.recall_delta for r in rows]),
        "mean_gated_active_recall": _mean_opt([r.gated_active_recall for r in rows]),
        "mean_gated_recall_delta": _mean_opt([r.gated_recall_delta for r in rows]),
        "mean_baseline_edge_recall": _mean_opt([r.baseline_edge_recall for r in rows]),
        "mean_active_edge_recall": _mean_opt([r.active_edge_recall for r in rows]),
        "mean_edge_recall_delta": _mean_opt([r.edge_recall_delta for r in rows]),
        "mean_gated_active_edge_recall": _mean_opt([r.gated_active_edge_recall for r in rows]),
        "mean_gated_edge_recall_delta": _mean_opt([r.gated_edge_recall_delta for r in rows]),
        "total_synthetic": sum(r.synthetic_count for r in rows),
        "total_gated_synthetic": sum(r.gated_synthetic_count for r in rows),
        "total_synthetic_collision": sum(r.synthetic_collision_count for r in rows),
        "total_synthetic_gap": sum(r.synthetic_gap_count for r in rows),
        "total_suppressed_by_merge_gate": sum(r.suppressed_by_merge_gate for r in rows),
        "mean_collision_fraction": _mean_opt([r.collision_fraction for r in rows]),
        "total_matched_by_synthetic": sum(r.matched_by_synthetic for r in rows),
        "total_gated_matched_by_synthetic": sum(r.gated_matched_by_synthetic for r in rows),
        "total_uniquely_recovered": sum(r.uniquely_recovered_nodes for r in rows),
        "total_displaced_matches": sum(r.displaced_matches for r in rows),
        "mean_synthetic_match_precision": _mean_opt([r.synthetic_match_precision for r in rows]),
        "mean_node_inflation_pct": _mean_opt([r.node_inflation_pct for r in rows]),
        "mean_injection_ms": _mean_opt([r.injection_ms for r in rows]),
        "max_injection_ms": max((r.injection_ms for r in rows), default=0.0),
    }


def _dense_region_check(rows: list[ActiveRunRow], discounts: list[float], top_n: int = 8) -> dict:
    """For the densest at-risk samples, compare no-gate vs gated deltas to confirm
    the merge gate is not over-suppressing in legitimately close-packed regions."""

    out: dict[str, list[dict]] = {}
    for discount in discounts:
        subset = [r for r in rows if r.discount == discount and r.at_risk_pfa_1e_03]
        densest = sorted(subset, key=lambda r: r.baseline_nodes, reverse=True)[:top_n]
        out[f"discount_{discount}"] = [
            {
                "sample_id": r.sample_id,
                "baseline_nodes": r.baseline_nodes,
                "synthetic_count": r.synthetic_count,
                "gated_synthetic_count": r.gated_synthetic_count,
                "suppressed_by_merge_gate": r.suppressed_by_merge_gate,
                "collision_fraction": r.collision_fraction,
                "nogate_node_delta": r.recall_delta,
                "gated_node_delta": r.gated_recall_delta,
                "nogate_edge_delta": r.edge_recall_delta,
                "gated_edge_delta": r.gated_edge_recall_delta,
            }
            for r in densest
        ]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--enable-correlation-active",
        action="store_true",
        help="Explicit opt-in required. Without it this script is a no-op.",
    )
    parser.add_argument("--train-dir", default="train")
    parser.add_argument("--scan-json", type=Path, default=SCAN_JSON_DEFAULT)
    parser.add_argument("--oss-json", type=Path, default=OSS_JSON_DEFAULT)
    parser.add_argument("--max-timepoints", type=int, default=10)
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--discounts", default="0.5,0.6,0.7", help="Comma-separated discount sweep.")
    parser.add_argument("--min-track-age", type=int, default=3)
    parser.add_argument("--max-consecutive", type=int, default=2)
    parser.add_argument("--node-inflation-ratio", type=float, default=1.25)
    parser.add_argument("--merge-gate-radius", type=float, default=3.0)
    parser.add_argument("--merge-gate-frame-window", type=int, default=1)
    parser.add_argument("--output-json", type=Path, default=None)
    args = parser.parse_args(argv)

    if not args.enable_correlation_active:
        _log(
            "active correlation injection is OFF (default). Pass --enable-correlation-active "
            "to run the ablation. No production path is affected."
        )
        return 0

    discounts = [float(x) for x in str(args.discounts).split(",") if x.strip()]
    payload = run_active(
        Path(args.train_dir),
        args.scan_json,
        args.oss_json,
        max_timepoints=args.max_timepoints,
        max_samples=args.max_samples,
        discounts=discounts,
        min_track_age_frames=args.min_track_age,
        max_consecutive_synthetic=args.max_consecutive,
        node_inflation_ratio=args.node_inflation_ratio,
        merge_gate_radius_um=args.merge_gate_radius,
        merge_gate_frame_window=args.merge_gate_frame_window,
    )
    print(json.dumps({k: v for k, v in payload.items() if k != "rows"}, indent=2))

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        _log(f"wrote {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
