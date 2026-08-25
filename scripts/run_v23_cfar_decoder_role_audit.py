"""Audit decoder evidence by parent and daughter role on fixed CFAR actions.

This is read-only. It reuses the completed action shadow table, labels only
registered geometric-TP action participants, and never changes candidates or
graphs. The labels are a 7 um registered proxy, not official metric labels.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


FEATURES = [
    "decoder_logit",
    "confidence",
    "embedding_norm",
    "embedding_mean",
    "embedding_std",
]
ROLES = ["parent", "daughter_1", "daughter_2"]


def _auc(values_positive: np.ndarray, values_negative: np.ndarray) -> float | None:
    positive = values_positive[np.isfinite(values_positive)]
    negative = values_negative[np.isfinite(values_negative)]
    if not len(positive) or not len(negative):
        return None
    joined = np.concatenate([positive, negative])
    ranks = pd.Series(joined).rank(method="average").to_numpy()
    return float((ranks[: len(positive)].sum() - len(positive) * (len(positive) + 1) / 2) / (len(positive) * len(negative)))


def _stats(positive: np.ndarray, negative: np.ndarray) -> dict:
    pos = positive[np.isfinite(positive)]
    neg = negative[np.isfinite(negative)]
    return {
        "positive_n": int(len(pos)),
        "negative_n": int(len(neg)),
        "positive_median": float(np.median(pos)) if len(pos) else None,
        "negative_median": float(np.median(neg)) if len(neg) else None,
        "auc_positive_higher": _auc(pos, neg),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actions", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    actions = pd.read_csv(args.actions)
    evidence = pd.read_csv(args.evidence).set_index("node_id")
    roles = {
        "parent": "parent_peak_id",
        "daughter_1": "child_1_peak_id",
        "daughter_2": "child_2_peak_id",
    }
    rows = []
    coverage = []
    for event_id, event in actions.groupby("event_id", sort=True):
        positive = event[event.geometry_tp]
        positive_ids = {role: set(positive[column].dropna()) for role, column in roles.items()}
        event_ids = set().union(*(set(event[column].dropna()) for column in roles.values()))
        for role, column in roles.items():
            role_ids = set(event[column].dropna())
            for node_id in sorted(role_ids):
                if node_id not in evidence.index:
                    raise RuntimeError(f"Missing decoder evidence for {node_id}")
                label = "positive_role" if node_id in positive_ids[role] else "event_control"
                item = evidence.loc[node_id]
                rows.append({
                    "event_id": event_id,
                    "sample_id": event_id.split(":", 1)[0],
                    "role": role,
                    "node_id": node_id,
                    "label": label,
                    **{feature: float(item[feature]) for feature in FEATURES},
                })
            coverage.append({
                "event_id": event_id,
                "role": role,
                "positive_role_nodes": int(len(positive_ids[role])),
                "event_nodes": int(len(role_ids)),
                "positive_role_coverage": float(len(positive_ids[role]) / len(role_ids)) if role_ids else None,
            })

    frame = pd.DataFrame(rows)
    result = {}
    for role in ROLES:
        role_frame = frame[frame.role.eq(role)]
        role_result = {}
        for feature in FEATURES:
            role_result[feature] = _stats(
                role_frame.loc[role_frame.label.eq("positive_role"), feature].to_numpy(float),
                role_frame.loc[role_frame.label.eq("event_control"), feature].to_numpy(float),
            )
        result[role] = role_result

    event_results = {}
    for event_id, event in frame.groupby("event_id", sort=True):
        event_results[event_id] = {}
        for role in ROLES:
            role_frame = event[event.role.eq(role)]
            event_results[event_id][role] = {
                feature: _stats(
                    role_frame.loc[role_frame.label.eq("positive_role"), feature].to_numpy(float),
                    role_frame.loc[role_frame.label.eq("event_control"), feature].to_numpy(float),
                )
                for feature in FEATURES
            }

    summary = {
        "status": "read_only_cfar_decoder_role_audit",
        "official_metric_used": False,
        "geometry_tp_is_registered_7um_proxy": True,
        "candidate_set_changed": False,
        "graph_mutation": False,
        "population": {
            "events": int(actions.event_id.nunique()),
            "action_rows": int(len(actions)),
            "geometry_tp_actions": int(actions.geometry_tp.sum()),
            "unique_evidence_nodes": int(frame.node_id.nunique()),
        },
        "role_feature_comparison": result,
        "event_role_coverage": coverage,
        "event_role_feature_comparison": event_results,
    }
    frame.to_csv(args.output, index=False, compression="gzip")
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# V23 CFAR Decoder Role-Level Evidence Audit",
        "",
        "Decision: **READ-ONLY DIAGNOSTIC; NO RANKING OR INTEGRATION**.",
        "",
        f"Population: `{len(actions):,}` fixed CFAR actions, `{actions.event_id.nunique()}` events, `{int(actions.geometry_tp.sum())}` registered 7 um geometric TP-proxy actions.",
        "",
        "Positive-role nodes are participants in a registered geometric TP-proxy action. Controls are other nodes appearing in actions from the same event and role. This is not an official-metric evaluation and does not treat unsupported actions as negatives.",
        "",
        "## Pooled Role Comparison",
        "",
        "| Role | Feature | Positive median | Control median | AUC (positive higher) | n+ | n- |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for role in ROLES:
        for feature in FEATURES:
            item = result[role][feature]
            fmt = lambda value: "NA" if value is None else f"{value:.4f}"
            lines.append(f"| {role} | {feature} | {fmt(item['positive_median'])} | {fmt(item['negative_median'])} | {fmt(item['auc_positive_higher'])} | {item['positive_n']} | {item['negative_n']} |")
    lines += [
        "",
        "## Interpretation Guardrail",
        "",
        "Pooled separation is descriptive only and may be dominated by a small number of events. A useful decoder signal would require consistent role-level separation across events, with no graph mutation. Failure at this stage closes the decoder as a ranking source rather than motivating threshold tuning.",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
