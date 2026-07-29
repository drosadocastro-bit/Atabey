"""Evaluate detector-native evidence as a non-mutating complement to CFAR."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

FEATURES = [
    "mean_detection_confidence",
    "mean_daughter_contrast",
    "mean_daughter_anisotropy",
    "daughter_mass_balance",
]


def auc(labels: np.ndarray, scores: np.ndarray) -> float | None:
    labels = np.asarray(labels, dtype=bool)
    scores = np.asarray(scores, dtype=float)
    keep = np.isfinite(scores)
    labels, scores = labels[keep], scores[keep]
    n_pos = int(labels.sum())
    n_neg = int((~labels).sum())
    if not n_pos or not n_neg:
        return None
    ranks = rankdata(scores, method="average")
    return float((ranks[labels].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def event_auc(rows: pd.DataFrame, feature: str) -> dict:
    values = []
    for _, event in rows.groupby("event_id", sort=True):
        labeled = event[event.official_label.isin(["official_tp", "official_fp"])]
        if labeled.official_label.nunique() < 2:
            continue
        score = labeled[feature].to_numpy(float)
        labels = labeled.official_label.eq("official_tp").to_numpy()
        value = auc(labels, score)
        if value is not None:
            values.append(value)
    return {"events": len(values), "event_balanced_auc": float(np.mean(values)) if values else None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = pd.read_csv(args.input)
    cfar = source[source.route.eq("cfar_sidelobe/bipartite")].copy()
    results = {}
    for feature in FEATURES:
        results[feature] = {
            "pooled": event_auc(cfar, feature),
            "by_family": {
                family: event_auc(group, feature)
                for family, group in cfar.groupby("family", sort=True)
            },
        }
    summary = {
        "status": "read_only_cfar_complement_shadow",
        "input": str(args.input),
        "population": {
            "cfar_actions": int(len(cfar)),
            "cfar_events": int(cfar.event_id.nunique()),
            "official_tp": int(cfar.official_label.eq("official_tp").sum()),
            "official_fp": int(cfar.official_label.eq("official_fp").sum()),
            "unknown_excluded_from_auc": True,
        },
        "features": results,
        "graph_mutation": False,
        "candidate_set_changed": False,
        "decoder_logits_attached": False,
        "decision": "DESCRIPTIVE_ONLY_DECODER_ATTACHMENT_PENDING",
    }
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# V23 CFAR Complement Evidence Shadow",
        "",
        "Decision: **DESCRIPTIVE ONLY; decoder-logit attachment pending**.",
        "",
        "CFAR generated the fixed candidate set. Raw detector-native evidence was evaluated only as an annotation/ranking signal. No candidates were removed, no new candidates were added, and no graph was mutated.",
        "",
        f"Population: `{len(cfar):,}` CFAR actions, `{cfar.event_id.nunique()}` events, `{int(cfar.official_label.eq('official_tp').sum())}` official TP actions, `{int(cfar.official_label.eq('official_fp').sum())}` official FP actions.",
        "",
        "## Event-balanced AUC",
        "",
        "| Feature | Pooled | 44b6 | 6bba |",
        "|---|---:|---:|---:|",
    ]
    for feature, result in results.items():
        pooled = result["pooled"]["event_balanced_auc"]
        family = result["by_family"]
        a = family.get("44b6", {}).get("event_balanced_auc")
        b = family.get("6bba", {}).get("event_balanced_auc")
        lines.append(f"| `{feature}` | {pooled:.4f} | {a:.4f} | {b:.4f} |")
    lines += [
        "",
        "## Boundary",
        "",
        "This is a complement test over the existing CFAR action set, not a U-Net detector replacement test. The current local artifacts do not contain decoder logits for the CFAR peak IDs, so the next implementation must export those logits at the unchanged CFAR coordinates before claiming encoder-decoder complement evidence.",
        "",
        "CFAR remains active and quarantined as the detector control.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
