from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from atabey.io.zarr_reader import open_competition_array, read_timepoint
from atabey.tracking.semantic_patch_features import (
    peak_patch_features,
    temporal_division_action_features,
)


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def auc(labels, scores):
    positive = np.asarray(labels) == 1
    values = np.asarray(scores, dtype=float)
    valid = np.isfinite(values)
    positive = positive[valid]
    values = values[valid]
    n_positive = int(positive.sum())
    n_negative = int((~positive).sum())
    if not n_positive or not n_negative:
        return None
    ranks = rankdata(values, method="average")
    return float(
        (ranks[positive].sum() - n_positive * (n_positive + 1) / 2)
        / (n_positive * n_negative)
    )


def event_mean_auc(frame: pd.DataFrame, feature: str, sign: float):
    values = []
    for _, event in frame.groupby("event_id", sort=True):
        value = auc(
            (event.official_label == "official_tp").astype(int),
            sign * event[feature].to_numpy(float),
        )
        if value is not None:
            values.append(value)
    return float(np.mean(values)) if values else None


def extract_temporal_peaks(
    peaks: pd.DataFrame, train_dir: Path, contract: dict
) -> pd.DataFrame:
    patch = contract["patch"]
    requests = []
    for row in peaks.itertuples(index=False):
        for offset in (-1, 0, 1):
            observation_t = int(row.t) + offset
            if 0 <= observation_t < 100:
                requests.append(
                    {
                        "peak_id": row.peak_id,
                        "sample_id": row.sample_id,
                        "peak_t": int(row.t),
                        "offset": offset,
                        "observation_t": observation_t,
                        "z_um": float(row.z_um),
                        "y_um": float(row.y_um),
                        "x_um": float(row.x_um),
                    }
                )
    request_frame = pd.DataFrame(requests)
    rows = []
    for sample_id, sample_requests in request_frame.groupby("sample_id", sort=True):
        array = open_competition_array(train_dir / f"{sample_id}.zarr")
        for observation_t, frame_requests in sample_requests.groupby(
            "observation_t", sort=True
        ):
            volume = np.asarray(read_timepoint(array, int(observation_t)))
            for row in frame_requests.itertuples(index=False):
                features = peak_patch_features(
                    volume,
                    (row.z_um, row.y_um, row.x_um),
                    voxel_scale_um=patch["voxel_scale_um"],
                    core_radius_um=patch["core_radius_um"],
                    shell_inner_radius_um=patch["shell_inner_radius_um"],
                    shell_outer_radius_um=patch["shell_outer_radius_um"],
                    threshold_mad=patch["effective_volume_threshold_mad"],
                )
                rows.append(
                    {
                        "peak_id": row.peak_id,
                        "sample_id": sample_id,
                        "peak_t": int(row.peak_t),
                        "offset": int(row.offset),
                        "observation_t": int(observation_t),
                        **features,
                    }
                )
        print(
            f"temporal peaks {sample_id}: {len(sample_requests)} observations",
            flush=True,
        )
    return pd.DataFrame(rows)


def build_temporal_actions(
    shard_dir: Path, peaks: pd.DataFrame, temporal_peaks: pd.DataFrame, contract: dict
) -> pd.DataFrame:
    peak_times = peaks.set_index("peak_id")["t"].astype(int).to_dict()
    feature_map = temporal_peaks.set_index(["peak_id", "offset"]).to_dict("index")
    temporal_features = [
        feature
        for features in contract["temporal_feature_families"].values()
        for feature in features
    ]
    frames = []
    columns = [
        "action_id",
        "sample_id",
        "t",
        "fold",
        "event_id",
        "source_detector",
        "source_link_strategy",
        "parent_peak_id",
        "child_1_peak_id",
        "child_2_peak_id",
        "official_label",
        "registered_official_positive",
        "assignment_selected",
        "graph_mutated",
    ]
    for path in sorted(shard_dir.glob("*.csv.gz")):
        source = pd.read_csv(path, usecols=columns)
        rows = []
        for row in source.itertuples(index=False):
            if peak_times[row.parent_peak_id] != int(row.t):
                raise RuntimeError(f"Parent peak frame mismatch: {row.action_id}")
            if (
                peak_times[row.child_1_peak_id] != int(row.t) + 1
                or peak_times[row.child_2_peak_id] != int(row.t) + 1
            ):
                raise RuntimeError(f"Daughter peak frame mismatch: {row.action_id}")
            keys = [
                (row.parent_peak_id, -1),
                (row.parent_peak_id, 0),
                (row.child_1_peak_id, -1),
                (row.child_1_peak_id, 0),
                (row.child_1_peak_id, 1),
                (row.child_2_peak_id, -1),
                (row.child_2_peak_id, 0),
                (row.child_2_peak_id, 1),
            ]
            if all(key in feature_map for key in keys):
                values = temporal_division_action_features(
                    *(feature_map[key] for key in keys)
                )
                values["mean_daughter_contrast"] = 0.5 * (
                    feature_map[keys[3]]["patch_contrast"]
                    + feature_map[keys[6]]["patch_contrast"]
                )
            else:
                values = {
                    feature: float("nan")
                    for feature in [*temporal_features, "mean_daughter_contrast"]
                }
            rows.append(
                {
                    "action_id": row.action_id,
                    "sample_id": row.sample_id,
                    "family": row.sample_id.split("_", 1)[0],
                    "fold": int(row.fold),
                    "event_id": row.event_id,
                    "route": f"{row.source_detector}/{row.source_link_strategy}",
                    "official_label": row.official_label,
                    "registered_official_positive": bool(
                        row.registered_official_positive
                    ),
                    "assignment_selected": bool(row.assignment_selected),
                    "graph_mutated": bool(row.graph_mutated),
                    **values,
                }
            )
        frame = pd.DataFrame(rows)
        frames.append(frame)
        print(f"temporal actions {path.stem}: {len(frame)}", flush=True)
    result = pd.concat(frames, ignore_index=True)
    missing = set(temporal_features) - set(result.columns)
    if missing:
        raise RuntimeError(f"Frozen temporal features missing: {sorted(missing)}")
    return result


def evaluate(actions: pd.DataFrame, contract: dict) -> tuple[dict, pd.DataFrame]:
    groups = contract["temporal_feature_families"]
    temporal_features = [
        feature for features in groups.values() for feature in features
    ]
    features = [*temporal_features, contract["evaluation"]["static_baseline"]]
    labeled = actions[
        actions.official_label.isin(["official_tp", "official_fp"])
    ].copy()
    event_rows = []
    for heldout in contract["evaluation"]["outer_folds"]:
        train = labeled[labeled.fold != heldout]
        test = labeled[labeled.fold == heldout]
        for feature in features:
            train_auc = event_mean_auc(train, feature, 1.0)
            sign = 1.0 if train_auc is None or train_auc >= 0.5 else -1.0
            for event_id, event in test.groupby("event_id", sort=True):
                value = auc(
                    (event.official_label == "official_tp").astype(int),
                    sign * event[feature].to_numpy(float),
                )
                if value is None:
                    continue
                first = event.iloc[0]
                event_rows.append(
                    {
                        "feature": feature,
                        "heldout_fold": int(heldout),
                        "event_id": event_id,
                        "sample_id": first.sample_id,
                        "family": first.family,
                        "route": first.route,
                        "sign": int(sign),
                        "auc": value,
                    }
                )
    events = pd.DataFrame(event_rows)
    metrics = {}
    for feature, group in events.groupby("feature", sort=True):
        metrics[feature] = {
            "event_count": len(group),
            "oof_equal_event_auc": float(group.auc.mean()),
            "by_fold": {
                str(int(key)): float(value.auc.mean())
                for key, value in group.groupby("heldout_fold")
            },
            "by_family": {
                str(key): float(value.auc.mean())
                for key, value in group.groupby("family")
            },
            "by_route": {
                str(key): float(value.auc.mean())
                for key, value in group.groupby("route")
            },
        }

    decision = contract["decision"]
    decision_groups = {name: values for name, values in groups.items() if name != "quality"}
    group_best = {
        name: max(metrics[feature]["oof_equal_event_auc"] for feature in values)
        for name, values in decision_groups.items()
    }
    groups_passing = sum(
        value >= decision["temporal_feature_families_pooled_auc_min"]
        for value in group_best.values()
    )
    routes = contract["evaluation"]["decision_routes"]
    stable = []
    for feature in temporal_features:
        metric = metrics[feature]
        if (
            metric["oof_equal_event_auc"]
            >= decision["temporal_feature_families_pooled_auc_min"]
            and min(metric["by_fold"].values())
            >= decision["same_feature_min_fold_auc"]
            and min(metric["by_family"].values())
            >= decision["same_feature_min_family_auc"]
            and all(route in metric["by_route"] for route in routes)
            and metric["by_route"][routes[0]]
            >= decision["same_feature_cfar_auc_min"]
            and metric["by_route"][routes[1]]
            >= decision["same_feature_components_auc_min"]
        ):
            stable.append(feature)

    tp = actions.official_label == "official_tp"
    fp = actions.official_label == "official_fp"
    complete = np.isfinite(actions[temporal_features].to_numpy(float)).all(axis=1)
    availability = {
        "official_tp_descriptor_completeness": float(complete[tp].mean()),
        "official_fp_descriptor_completeness": float(complete[fp].mean()),
    }
    best_temporal = max(
        temporal_features, key=lambda feature: metrics[feature]["oof_equal_event_auc"]
    )
    baseline = contract["evaluation"]["static_baseline"]
    advantage = (
        metrics[best_temporal]["oof_equal_event_auc"]
        - metrics[baseline]["oof_equal_event_auc"]
    )
    gates = {
        "official_tp_descriptor_completeness_min": availability[
            "official_tp_descriptor_completeness"
        ]
        >= decision["official_tp_descriptor_completeness_min"],
        "official_fp_descriptor_completeness_min": availability[
            "official_fp_descriptor_completeness"
        ]
        >= decision["official_fp_descriptor_completeness_min"],
        "temporal_feature_families_passing_min": groups_passing
        >= decision["temporal_feature_families_passing_min"],
        "stable_temporal_feature_exists": bool(stable),
        "best_temporal_auc_advantage_over_static_baseline_min": advantage
        >= decision["best_temporal_auc_advantage_over_static_baseline_min"],
        "source_graph_mutations_required": int(actions.graph_mutated.sum())
        == decision["source_graph_mutations_required"],
        "assignment_decisions_required": int(actions.assignment_selected.sum())
        == decision["assignment_decisions_required"],
    }
    availability_ok = (
        gates["official_tp_descriptor_completeness_min"]
        and gates["official_fp_descriptor_completeness_min"]
    )
    if not availability_ok or groups_passing < decision[
        "temporal_feature_families_passing_min"
    ]:
        state = "NO_GO_TEMPORAL_SEMANTIC_EVIDENCE"
    elif all(gates.values()):
        state = "GO_TO_TEMPORAL_PU_RANKER_PREREGISTRATION"
    else:
        state = "HOLD_TEMPORAL_SIGNAL_ROUTE_OR_FAMILY_UNSTABLE"
    return (
        {
            "decision": state,
            "availability": availability,
            "feature_metrics": metrics,
            "feature_group_best_auc": group_best,
            "feature_groups_passing": groups_passing,
            "stable_temporal_features": stable,
            "best_temporal_feature": {
                "feature": best_temporal,
                "auc": metrics[best_temporal]["oof_equal_event_auc"],
            },
            "static_baseline": {
                "feature": baseline,
                "auc": metrics[baseline]["oof_equal_event_auc"],
            },
            "best_temporal_advantage_over_static_baseline": advantage,
            "gates": gates,
        },
        events,
    )


def write_report(path: Path, summary: dict) -> None:
    evaluation = summary["evaluation"]
    best_name = evaluation["best_temporal_feature"]["feature"]
    best = evaluation["feature_metrics"][best_name]
    lines = [
        "# V22 Route-Robust Temporal Semantic Evidence Audit Results",
        "",
        f"Decision: **{evaluation['decision']}**",
        "",
        "This is conditional discrimination among sampled official TP/FP actions, not biological truth or full-candidate precision.",
        "",
        "## Availability",
        "",
        "| Population | Completeness |",
        "| --- | ---: |",
        f"| official TP actions | {evaluation['availability']['official_tp_descriptor_completeness']:.6f} |",
        f"| official FP actions | {evaluation['availability']['official_fp_descriptor_completeness']:.6f} |",
        "",
        "## Best Evidence",
        "",
        f"- Best temporal feature: `{best_name}` AUC `{best['oof_equal_event_auc']:.6f}`.",
        f"- Static baseline: `{evaluation['static_baseline']['feature']}` AUC `{evaluation['static_baseline']['auc']:.6f}`.",
        f"- Temporal advantage: `{evaluation['best_temporal_advantage_over_static_baseline']:+.6f}`.",
        "",
        "## Best Temporal Feature By Stratum",
        "",
        "| Stratum | OOF event-balanced AUC |",
        "| --- | ---: |",
    ]
    for fold, value in best["by_fold"].items():
        lines.append(f"| fold {fold} | {value:.6f} |")
    for family, value in best["by_family"].items():
        lines.append(f"| family {family} | {value:.6f} |")
    for route, value in best["by_route"].items():
        lines.append(f"| {route} | {value:.6f} |")
    lines.extend(
        [
            "",
            f"Stable temporal features: `{', '.join(evaluation['stable_temporal_features'])}`.",
            "",
            "## Feature Families",
            "",
            "| Family | Best OOF event-balanced AUC |",
            "| --- | ---: |",
        ]
    )
    for family, value in evaluation["feature_group_best_auc"].items():
        lines.append(f"| {family} | {value:.6f} |")
    lines.extend(["", "## Frozen Gates", ""])
    for name, passed in evaluation["gates"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'}: `{name}`")
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- Unknown and unsupported actions were not negatives.",
            "- Local-maxima is descriptive zero-shot evidence and cannot carry the decision.",
            "- Fixed-coordinate temporal sampling used no future peak reassociation.",
            "- No assignment, graph mutation, locked validation, or full-199 evaluation was used.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=ROOT
        / "tests/fixtures/v22_route_robust_temporal_semantic_audit.json",
    )
    parser.add_argument("--train-dir", type=Path, default=ROOT / "train")
    parser.add_argument(
        "--peaks",
        type=Path,
        default=ROOT / "v22_unet_detection_development_46_peaks.csv",
    )
    parser.add_argument(
        "--shards", type=Path, default=ROOT / "v22_semantic_action_shards"
    )
    parser.add_argument(
        "--peak-output",
        type=Path,
        default=ROOT / "v22_temporal_peak_patch_features.csv.gz",
    )
    parser.add_argument(
        "--action-output",
        type=Path,
        default=ROOT / "v22_temporal_action_features.csv.gz",
    )
    parser.add_argument(
        "--event-output",
        type=Path,
        default=ROOT / "v22_temporal_semantic_event_auc.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "v22_temporal_semantic_audit_summary.json",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "V22_ROUTE_ROBUST_TEMPORAL_SEMANTIC_AUDIT_RESULTS.md",
    )
    args = parser.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8-sig"))
    for path_key, hash_key in [
        ("source_peaks", "source_peaks_sha256"),
        ("source_action_summary", "source_action_summary_sha256"),
        ("source_failed_ranker_summary", "source_failed_ranker_summary_sha256"),
        ("source_development_contract", "source_development_contract_sha256"),
    ]:
        if sha256(ROOT / contract[path_key]) != contract[hash_key]:
            raise RuntimeError(f"Pinned source changed: {path_key}")

    peaks = pd.read_csv(args.peaks)
    temporal_peaks = extract_temporal_peaks(peaks, args.train_dir, contract)
    temporal_peaks.to_csv(args.peak_output, index=False, compression="gzip")
    actions = build_temporal_actions(
        args.shards, peaks, temporal_peaks, contract
    )
    actions.to_csv(args.action_output, index=False, compression="gzip")
    evaluation, events = evaluate(actions, contract)
    events.to_csv(args.event_output, index=False)
    summary = {
        "contract": contract["name"],
        "contract_sha256": sha256(args.contract),
        "population": {
            "peaks": len(peaks),
            "temporal_peak_observations": len(temporal_peaks),
            "actions": len(actions),
            "official_tp": int((actions.official_label == "official_tp").sum()),
            "official_fp": int((actions.official_label == "official_fp").sum()),
        },
        "evaluation": evaluation,
        "feature_extraction_enabled": True,
        "model_fitting_enabled": False,
        "assignment_enabled": False,
        "graph_mutated": bool(actions.graph_mutated.any()),
        "locked_validation_opened": False,
        "full_199_authorized": False,
    }
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_report(args.report, summary)
    print(
        json.dumps(
            {
                "decision": evaluation["decision"],
                "availability": evaluation["availability"],
                "best_temporal": evaluation["best_temporal_feature"],
                "static_baseline": evaluation["static_baseline"],
                "temporal_advantage": evaluation[
                    "best_temporal_advantage_over_static_baseline"
                ],
                "feature_groups": evaluation["feature_group_best_auc"],
                "stable_temporal_features": evaluation[
                    "stable_temporal_features"
                ],
                "gates": evaluation["gates"],
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
