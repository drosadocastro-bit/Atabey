"""Attach exported decoder evidence to the frozen CFAR action set."""

from __future__ import annotations

import argparse
import json
from math import inf
from pathlib import Path

import numpy as np
import pandas as pd
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from atabey.tracking.unet_action_availability import (
    UnetShadowPeak,
    action_matches_registered_division,
    enumerate_anchored_division_actions,
)
from atabey.io.geff_reader import read_geff_graph
from run_v21_division_recovery_shadow import (
    _build_v19_prefirewall_with_route,
    _gt_divisions,
)

ROOT = Path(__file__).resolve().parents[1]
FEATURES = [
    "mean_decoder_logit",
    "minimum_daughter_decoder_logit",
    "daughter_decoder_logit_balance",
    "mean_embedding_norm",
    "minimum_daughter_embedding_norm",
    "mean_embedding_mean",
]


def _rank_metrics(rows: pd.DataFrame, feature: str) -> dict:
    positives = rows[rows.geometry_tp]
    if positives.empty:
        return {"positive_count": 0, "events": 0, "event_recall_at_1": None, "event_recall_at_5": None, "event_recall_at_50": None, "mrr": None}
    ranks = []
    for event_id, event in rows.groupby("event_id", sort=True):
        positive = event[event.geometry_tp]
        if positive.empty:
            continue
        scores = event[feature].to_numpy(float)
        for value in positive[feature].to_numpy(float):
            if not np.isfinite(value):
                continue
            rank = 1 + int(np.sum(scores >= value)) - 1
            ranks.append(rank)
    if not ranks:
        return {"positive_count": 0, "events": 0, "event_recall_at_1": None, "event_recall_at_5": None, "event_recall_at_50": None, "mrr": None}
    values = np.asarray(ranks, dtype=float)
    event_min = rows[rows.geometry_tp].groupby("event_id")[feature].max()
    event_ranks = []
    for event_id, event in rows.groupby("event_id", sort=True):
        positive = event[event.geometry_tp]
        if positive.empty:
            continue
        scores = event[feature].to_numpy(float)
        event_ranks.append(min(1 + int(np.sum(scores >= value)) - 1 for value in positive[feature] if np.isfinite(value)))
    event_ranks = np.asarray(event_ranks, dtype=float)
    return {
        "positive_count": int(len(ranks)),
        "events": int(len(event_ranks)),
        "event_recall_at_1": float(np.mean(event_ranks <= 1)),
        "event_recall_at_5": float(np.mean(event_ranks <= 5)),
        "event_recall_at_50": float(np.mean(event_ranks <= 50)),
        "mrr": float(np.mean(1.0 / event_ranks)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, default=ROOT / "train")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--availability", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    evidence = pd.read_csv(args.evidence).set_index("node_id")
    cases = pd.read_csv(args.availability)
    cases = cases[cases.source_detector.eq("cfar_sidelobe")]
    rows = []
    graph_cache = {}

    for sample_id, sample_cases in cases.groupby("sample_id", sort=True):
        graph, detector, link_strategy = _build_v19_prefirewall_with_route(
            args.train_dir / f"{sample_id}.zarr",
            max_timepoints=100,
        )
        if detector != "cfar_sidelobe" or link_strategy != "bipartite":
            raise RuntimeError(f"{sample_id}: route changed to {detector}/{link_strategy}")
        graph_cache[sample_id] = graph
        gt = read_geff_graph(args.train_dir / f"{sample_id}.geff")
        gt_nodes = {node.node_id: node for node in gt.nodes}
        gt_divisions = _gt_divisions(gt)
        peaks = [
            UnetShadowPeak(
                peak_id=node.node_id,
                sample_id=node.sample_id,
                t=int(node.t),
                z_um=float(node.z_um),
                y_um=float(node.y_um),
                x_um=float(node.x_um),
                confidence=node.detection_confidence,
            )
            for node in graph.detections
        ]
        print(f"{sample_id}: detections={len(peaks)} cases={len(sample_cases)}", flush=True)
        for case in sample_cases.itertuples(index=False):
            gt_triplets = [
                (gt_nodes[parent], gt_nodes[child_1], gt_nodes[child_2])
                for parent, child_1, child_2 in gt_divisions
            ]
            enumeration = enumerate_anchored_division_actions(
                graph,
                peaks,
                parent_t=int(case.t),
                anchor_radius_um=14.0,
                formation_radius_um=14.0,
            )
            for action in enumeration.actions:
                ids = [action.parent.peak_id, action.child_1.peak_id, action.child_2.peak_id]
                if not all(node_id in evidence.index for node_id in ids):
                    raise RuntimeError(f"Missing decoder evidence for action node in {sample_id}:{case.t}")
                values = evidence.loc[ids]
                geometry_tp = any(
                    action_matches_registered_division(
                        action,
                        parent_position_um=parent.position_um,
                        daughter_positions_um=(child_1.position_um, child_2.position_um),
                    )
                    for parent, child_1, child_2 in gt_triplets
                )
                daughter_logits = values.iloc[1:]["decoder_logit"].to_numpy(float)
                daughter_norms = values.iloc[1:]["embedding_norm"].to_numpy(float)
                rows.append({
                    "sample_id": sample_id,
                    "family": sample_id.split("_", 1)[0],
                    "event_id": f"{sample_id}:t{int(case.t)}",
                    "route": "cfar_sidelobe/bipartite",
                    "parent_peak_id": action.parent.peak_id,
                    "child_1_peak_id": action.child_1.peak_id,
                    "child_2_peak_id": action.child_2.peak_id,
                    "geometry_tp": bool(geometry_tp),
                    "mean_decoder_logit": float(values.decoder_logit.mean()),
                    "minimum_daughter_decoder_logit": float(daughter_logits.min()),
                    "daughter_decoder_logit_balance": float(abs(daughter_logits[0] - daughter_logits[1])),
                    "mean_embedding_norm": float(values.embedding_norm.mean()),
                    "minimum_daughter_embedding_norm": float(daughter_norms.min()),
                    "mean_embedding_mean": float(values.embedding_mean.mean()),
                    "mean_detection_confidence": float(values.confidence.mean()),
                })

    frame = pd.DataFrame(rows)
    metrics = {feature: _rank_metrics(frame, feature) for feature in FEATURES + ["mean_detection_confidence"]}
    summary = {
        "status": "read_only_cfar_decoder_action_shadow",
        "population": {
            "samples": int(frame.sample_id.nunique()),
            "events": int(frame.event_id.nunique()),
            "actions": int(len(frame)),
            "geometry_tp_actions": int(frame.geometry_tp.sum()),
        },
        "metrics": metrics,
        "candidate_set_changed": False,
        "graph_mutation": False,
        "official_metric_used": False,
        "geometry_tp_is_registered_7um_proxy": True,
        "decision": "DESCRIPTIVE_COMPLEMENT_EVIDENCE_ONLY",
    }
    frame.to_csv(args.output, index=False, compression="gzip")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 CFAR Decoder Complement Action Shadow",
        "",
        "Decision: **DESCRIPTIVE COMPLEMENT EVIDENCE ONLY**.",
        "",
        f"Population: `{len(frame):,}` fixed CFAR actions across `{frame.event_id.nunique()}` events; geometry-matched TP proxy actions: `{int(frame.geometry_tp.sum())}`.",
        "",
        "| Feature | Event R@1 | Event R@5 | Event R@50 | MRR |",
        "|---|---:|---:|---:|---:|",
    ]
    for feature, result in metrics.items():
        lines.append(f"| `{feature}` | {result['event_recall_at_1']:.4f} | {result['event_recall_at_5']:.4f} | {result['event_recall_at_50']:.4f} | {result['mrr']:.4f} |")
    lines += [
        "",
        "Unknown and unsupported actions were not used as negatives. The TP label is a registered 7 um geometric match proxy, not a replacement for the patched official metric.",
        "CFAR generated every candidate; decoder evidence only annotated/ranked the fixed action set. No candidate was removed and no graph was mutated.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
