"""Track-continuity correlation layer — shadow ablation runner (Phase 1).

EXPERIMENTAL / GATED. Off by default. Requires ``--enable-correlation-shadow``.
Touches no production defaults, no ``run.py`` path, and never injects synthetic
candidates into any submission graph. It only *logs* what a PSR/SSR-style
correlation layer would recover, so recovery potential can be measured against the
OSS at-risk cohort with zero risk to the protected V13/production path.

Scope: the CFAR-routed cohort from the full-train scan, which is exactly the
``merged_6bba_only`` route-policy cohort (the profile gate is already applied in
``cfar_bounded_scan_fulltrain.json``). This is the same explicit-gate pattern used
by every other experimental CFAR/lineage script.

Pipeline (production-faithful, reused verbatim from the OSS diagnostic):

    input -> sigma-mode CFAR -> sidelobe -> production linker -> built graph
          -> compute_correlation_shadow(graph)   [shadow only]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter

import numpy as np

# Reuse the production-faithful timepoint + cohort loading from the OSS diagnostic.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from run_oss_diagnostics import (  # noqa: E402
    _instrumented_timepoint,
    _load_routed_records,
)

from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS as HFD  # noqa: E402
from atabey.io.zarr_reader import open_competition_array, read_timepoint  # noqa: E402
from atabey.tracking.correlation_shadow import (  # noqa: E402
    compute_correlation_shadow,
    summary_as_dict,
)
from atabey.tracking.nearest_neighbor import link_adjacent_timepoints  # noqa: E402
from atabey.types import Detection, LineageGraph  # noqa: E402

SCAN_JSON_DEFAULT = Path("submissions/cfar_bounded_scan_fulltrain.json")
OSS_JSON_DEFAULT = Path("submissions/oss_diagnostics.json")
CANDIDATE_LOG_SAMPLE = 20  # cap per-sample candidate records written to disk.


def _log(message: str) -> None:
    print(f"[corr] {message}", file=sys.stderr, flush=True)


@dataclass
class SampleCorrelationRow:
    sample_id: str
    at_risk_pfa_1e_03: bool
    timepoints: int
    nodes: int
    edges: int
    low_detection_frames: int
    synthetic_candidate_count: int
    tracks_triggered: int
    frames_with_synthetics: int
    mean_would_be_a_score: float
    node_inflation_pct: float
    suppressed_young_tracks: int
    suppressed_by_consecutive_cap: int
    suppressed_by_node_ceiling: int
    hit_node_ceiling: bool
    build_seconds: float
    shadow_seconds: float
    quality_per_sec: float


def _build_graph(sample_path: Path, *, sample_id: str, max_timepoints: int) -> LineageGraph:
    """Production-faithful sigma-mode CFAR+sidelobe graph, same as the OSS pass."""

    array = open_competition_array(sample_path)
    total = min(int(array.shape[0]), int(max_timepoints))

    graph = LineageGraph(sample_id=sample_id)
    previous: list[Detection] = []
    detections_by_node_id: dict[str, Detection] = {}
    predecessor_by_node_id: dict[str, Detection] = {}

    for t in range(total):
        volume = read_timepoint(array, t)
        kept, _candidates, _survivors, _norm = _instrumented_timepoint(sample_id, t, volume)
        for detection in kept:
            graph.add_detection(detection)
            detections_by_node_id[detection.node_id] = detection
        edges = link_adjacent_timepoints(
            previous,
            kept,
            HFD.cfar_max_link_distance_um,
            strategy=HFD.cfar_link_strategy,
            predecessor_by_node_id=predecessor_by_node_id,
        )
        for edge in edges:
            graph.add_edge(edge)
            predecessor_by_node_id[edge.target_id] = detections_by_node_id[edge.source_id]
        previous = kept

    return graph


def _load_at_risk_ids(oss_json: Path) -> set[str]:
    if not oss_json.exists():
        return set()
    with open(oss_json, encoding="utf-8") as handle:
        payload = json.load(handle)
    return {
        b["sample_id"]
        for b in payload.get("budgets", [])
        if b.get("at_risk_pfa_1e_03")
    }


def run_correlation_shadow(
    train_dir: Path,
    scan_json: Path,
    oss_json: Path,
    *,
    max_timepoints: int,
    max_samples: int | None,
    min_track_age_frames: int,
    max_consecutive_synthetic: int,
    discount: float,
    node_inflation_ratio: float,
    low_detection_floor_ratio: float,
) -> dict:
    routed = _load_routed_records(scan_json)
    if max_samples is not None:
        routed = routed[:max_samples]
    at_risk_ids = _load_at_risk_ids(oss_json)
    _log(
        f"shadow-correlation over {len(routed)} merged_6bba_only routed samples, "
        f"up to {max_timepoints} tp ({len(at_risk_ids)} known at-risk)"
    )

    rows: list[SampleCorrelationRow] = []
    candidate_samples: dict[str, list[dict]] = {}
    for index, record in enumerate(routed, start=1):
        sample_id = record["sample_id"]
        sample_path = train_dir / f"{sample_id}.zarr"
        if not sample_path.exists():
            _log(f"  [{index}/{len(routed)}] {sample_id} missing zarr, skipping")
            continue
        try:
            build_start = perf_counter()
            graph = _build_graph(sample_path, sample_id=sample_id, max_timepoints=max_timepoints)
            build_seconds = perf_counter() - build_start
            shadow_start = perf_counter()
            summary = compute_correlation_shadow(
                graph,
                min_track_age_frames=min_track_age_frames,
                max_consecutive_synthetic=max_consecutive_synthetic,
                discount=discount,
                node_inflation_ratio=node_inflation_ratio,
                low_detection_floor_ratio=low_detection_floor_ratio,
            )
            shadow_seconds = perf_counter() - shadow_start
        except Exception as exc:  # noqa: BLE001 - report and continue.
            _log(f"  [{index}/{len(routed)}] {sample_id} FAILED: {exc}")
            continue

        node_inflation_pct = (
            100.0 * summary.synthetic_candidate_count / summary.nodes if summary.nodes else 0.0
        )
        quality_per_sec = (
            summary.synthetic_candidate_count / shadow_seconds if shadow_seconds > 0 else 0.0
        )
        rows.append(
            SampleCorrelationRow(
                sample_id=sample_id,
                at_risk_pfa_1e_03=sample_id in at_risk_ids,
                timepoints=summary.last_frame + 1,
                nodes=summary.nodes,
                edges=summary.edges,
                low_detection_frames=summary.low_detection_frames,
                synthetic_candidate_count=summary.synthetic_candidate_count,
                tracks_triggered=summary.tracks_triggered,
                frames_with_synthetics=summary.frames_with_synthetics,
                mean_would_be_a_score=summary.mean_would_be_a_score,
                node_inflation_pct=round(node_inflation_pct, 4),
                suppressed_young_tracks=summary.suppressed_young_tracks,
                suppressed_by_consecutive_cap=summary.suppressed_by_consecutive_cap,
                suppressed_by_node_ceiling=summary.suppressed_by_node_ceiling,
                hit_node_ceiling=summary.hit_node_ceiling,
                build_seconds=round(build_seconds, 3),
                shadow_seconds=round(shadow_seconds, 4),
                quality_per_sec=round(quality_per_sec, 3),
            )
        )
        if summary.candidates:
            candidate_samples[sample_id] = [
                asdict(c) for c in summary.candidates[:CANDIDATE_LOG_SAMPLE]
            ]
        if index % 5 == 0 or index == len(routed):
            _log(
                f"  [{index}/{len(routed)}] {sample_id} synth={summary.synthetic_candidate_count} "
                f"inflate={node_inflation_pct:.2f}% build={build_seconds:.2f}s "
                f"shadow={shadow_seconds*1000:.1f}ms"
            )

    at_risk_rows = [r for r in rows if r.at_risk_pfa_1e_03]
    recovered_at_risk = [r for r in at_risk_rows if r.synthetic_candidate_count > 0]

    def _mean(values: list[float]) -> float | None:
        clean = [v for v in values if v is not None]
        return round(float(mean(clean)), 5) if clean else None

    aggregates = {
        "cohort_size": len(rows),
        "total_synthetic_candidates": sum(r.synthetic_candidate_count for r in rows),
        "samples_with_synthetics": sum(1 for r in rows if r.synthetic_candidate_count > 0),
        "mean_node_inflation_pct": _mean([r.node_inflation_pct for r in rows]),
        "max_node_inflation_pct": max((r.node_inflation_pct for r in rows), default=0.0),
        "samples_hit_node_ceiling": sum(1 for r in rows if r.hit_node_ceiling),
        "mean_would_be_a_score": _mean(
            [r.mean_would_be_a_score for r in rows if r.synthetic_candidate_count > 0]
        ),
        "mean_build_seconds_per_sample": _mean([r.build_seconds for r in rows]),
        "mean_shadow_seconds_per_sample": _mean([r.shadow_seconds for r in rows]),
        "max_shadow_seconds": max((r.shadow_seconds for r in rows), default=0.0),
        "at_risk_cohort_size": len(at_risk_rows),
        "at_risk_samples_recovered": len(recovered_at_risk),
        "at_risk_recovery_fraction": (
            round(len(recovered_at_risk) / len(at_risk_rows), 4) if at_risk_rows else 0.0
        ),
        "at_risk_total_synthetic_candidates": sum(
            r.synthetic_candidate_count for r in at_risk_rows
        ),
    }

    return {
        "mode": "shadow_only",
        "scope": "merged_6bba_only",
        "params": {
            "max_timepoints": max_timepoints,
            "min_track_age_frames": min_track_age_frames,
            "max_consecutive_synthetic": max_consecutive_synthetic,
            "discount": discount,
            "node_inflation_ratio": node_inflation_ratio,
            "low_detection_floor_ratio": low_detection_floor_ratio,
        },
        "aggregates": aggregates,
        "rows": [asdict(r) for r in rows],
        "candidate_log_sample": candidate_samples,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--enable-correlation-shadow",
        action="store_true",
        help="Explicit opt-in required. Without it this script is a no-op.",
    )
    parser.add_argument("--train-dir", default="train", help="Directory with .zarr sample folders.")
    parser.add_argument("--scan-json", type=Path, default=SCAN_JSON_DEFAULT)
    parser.add_argument("--oss-json", type=Path, default=OSS_JSON_DEFAULT)
    parser.add_argument("--max-timepoints", type=int, default=10)
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--min-track-age", type=int, default=3)
    parser.add_argument("--max-consecutive", type=int, default=2)
    parser.add_argument("--discount", type=float, default=0.6)
    parser.add_argument("--node-inflation-ratio", type=float, default=1.25)
    parser.add_argument("--low-detection-floor-ratio", type=float, default=0.5)
    parser.add_argument("--output-json", type=Path, default=None)
    args = parser.parse_args(argv)

    if not args.enable_correlation_shadow:
        _log(
            "correlation shadow layer is OFF (default). Pass --enable-correlation-shadow "
            "to run the shadow ablation. No production path is affected."
        )
        return 0

    payload = run_correlation_shadow(
        Path(args.train_dir),
        args.scan_json,
        args.oss_json,
        max_timepoints=args.max_timepoints,
        max_samples=args.max_samples,
        min_track_age_frames=args.min_track_age,
        max_consecutive_synthetic=args.max_consecutive,
        discount=args.discount,
        node_inflation_ratio=args.node_inflation_ratio,
        low_detection_floor_ratio=args.low_detection_floor_ratio,
    )
    print(json.dumps({k: v for k, v in payload.items() if k not in ("rows", "candidate_log_sample")}, indent=2))

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        _log(f"wrote {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
