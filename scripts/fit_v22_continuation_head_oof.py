from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from atabey.tracking.continuation_head import (
    evaluate_generalization,
    fit_pairwise_logistic,
    strict_group_metrics,
)


ROOT = Path(__file__).resolve().parents[1]
DECISION_ROUTES = ("cfar_sidelobe/bipartite", "components/greedy")
LOCAL_MAXIMA_ROUTE = "local_maxima/motion_mutual"


@dataclass(frozen=True)
class Group:
    reference_id: str
    parent_t: int
    start: int
    stop: int
    reference_index: int


@dataclass
class SampleData:
    sample_id: str
    fold: int
    family: str
    route: str
    values: np.ndarray
    row_weights: np.ndarray
    groups: list[Group]
    reference_count: int


@dataclass(frozen=True)
class Preprocessor:
    medians: np.ndarray
    means: np.ndarray
    scales: np.ndarray

    def transform(self, values: np.ndarray) -> np.ndarray:
        raw = np.asarray(values, dtype=np.float64)
        missing = ~np.isfinite(raw)
        imputed = np.where(missing, self.medians, raw)
        standardized = (imputed - self.means) / self.scales
        return np.concatenate([standardized, missing.astype(np.float64)], axis=1)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values, kind="stable")
    values = values[order]
    weights = weights[order]
    cutoff = 0.5 * float(weights.sum())
    index = int(np.searchsorted(np.cumsum(weights), cutoff, side="left"))
    return float(values[min(index, values.size - 1)])


def _fit_preprocessor(samples: list[SampleData], feature_indices: np.ndarray) -> Preprocessor:
    raw = np.concatenate([sample.values[:, feature_indices] for sample in samples])
    weights = np.concatenate([sample.row_weights for sample in samples])
    if any(abs(float(sample.row_weights.sum()) - 1.0) > 1e-8 for sample in samples):
        raise RuntimeError("Input sample weights do not preserve equal sample mass")
    medians = np.empty(raw.shape[1], dtype=np.float64)
    for column in range(raw.shape[1]):
        available = np.isfinite(raw[:, column])
        medians[column] = (
            _weighted_median(raw[available, column], weights[available])
            if np.any(available)
            else 0.0
        )
    imputed = np.where(np.isfinite(raw), raw, medians)
    normalized = weights / float(weights.sum())
    means = normalized @ imputed
    centered = imputed - means
    scales = np.sqrt(np.maximum(normalized @ (centered * centered), 0.0))
    scales = np.where(scales > 1e-12, scales, 1.0)
    return Preprocessor(medians=medians, means=means, scales=scales)


def _load_samples(shard_dir: Path, feature_names: list[str]) -> list[SampleData]:
    metadata = [
        "reference_id", "sample_id", "fold", "family", "route", "parent_t",
        "weak_preference_target", "sample_hierarchical_weight",
    ]
    samples: list[SampleData] = []
    for path in sorted(shard_dir.glob("*.csv.gz")):
        frame = pd.read_csv(path, usecols=metadata + feature_names)
        if frame.empty:
            raise RuntimeError(f"Empty continuation shard: {path}")
        sample_ids = frame["sample_id"].astype(str).unique()
        folds = frame["fold"].unique()
        families = frame["family"].astype(str).unique()
        routes = frame["route"].astype(str).unique()
        if not (len(sample_ids) == len(folds) == len(families) == len(routes) == 1):
            raise RuntimeError(f"Mixed sample metadata in {path}")

        reference_ids = frame["reference_id"].astype(str).to_numpy()
        targets = frame["weak_preference_target"].to_numpy(dtype=np.int8)
        parent_times = frame["parent_t"].to_numpy(dtype=np.int32)
        boundaries = np.r_[0, np.flatnonzero(reference_ids[1:] != reference_ids[:-1]) + 1, len(frame)]
        groups: list[Group] = []
        seen: set[str] = set()
        for start, stop in zip(boundaries[:-1], boundaries[1:]):
            reference_id = str(reference_ids[start])
            if reference_id in seen:
                raise RuntimeError(f"Non-contiguous duplicate reference {reference_id} in {path}")
            seen.add(reference_id)
            reference_rows = np.flatnonzero(targets[start:stop] == 1)
            if reference_rows.size != 1:
                raise RuntimeError(f"Reference {reference_id} does not have exactly one preferred row")
            groups.append(Group(reference_id, int(parent_times[start]), int(start), int(stop), int(start + reference_rows[0])))

        samples.append(SampleData(
            sample_id=str(sample_ids[0]),
            fold=int(folds[0]),
            family=str(families[0]),
            route=str(routes[0]),
            values=frame[feature_names].to_numpy(dtype=np.float64),
            row_weights=frame["sample_hierarchical_weight"].to_numpy(dtype=np.float64),
            groups=groups,
            reference_count=len(groups),
        ))
        print(f"Loaded {sample_ids[0]}: fold={folds[0]} route={routes[0]} rows={len(frame)} groups={len(groups)}", flush=True)
    return samples


def _nontrivial_groups(sample: SampleData) -> list[Group]:
    return [group for group in sample.groups if group.stop - group.start > 1]


def _group_weights(sample: SampleData) -> dict[str, float]:
    groups = _nontrivial_groups(sample)
    by_frame: dict[int, list[Group]] = {}
    for group in groups:
        by_frame.setdefault(group.parent_t, []).append(group)
    if not by_frame:
        return {}
    return {
        group.reference_id: 1.0 / len(by_frame) / len(frame_groups)
        for frame_groups in by_frame.values()
        for group in frame_groups
    }


def _make_pairs(samples: list[SampleData], preprocessor: Preprocessor, feature_indices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    pair_count = sum(group.stop - group.start - 1 for sample in samples for group in _nontrivial_groups(sample))
    width = 2 * len(feature_indices)
    differences = np.empty((pair_count, width), dtype=np.float64)
    weights = np.empty(pair_count, dtype=np.float64)
    cursor = 0
    for sample in samples:
        transformed = preprocessor.transform(sample.values[:, feature_indices])
        group_weights = _group_weights(sample)
        for group in _nontrivial_groups(sample):
            alternatives = np.r_[np.arange(group.start, group.reference_index), np.arange(group.reference_index + 1, group.stop)]
            count = alternatives.size
            differences[cursor:cursor + count] = transformed[group.reference_index] - transformed[alternatives]
            weights[cursor:cursor + count] = group_weights[group.reference_id] / count
            cursor += count
    if cursor != pair_count:
        raise RuntimeError("Pair construction count mismatch")
    return differences, weights


def _score_samples(samples: list[SampleData], preprocessor: Preprocessor, feature_indices: np.ndarray, coefficients: np.ndarray, tie_tolerance: float) -> tuple[list[dict], list[dict]]:
    sample_rows: list[dict] = []
    group_rows: list[dict] = []
    for sample in samples:
        scores = preprocessor.transform(sample.values[:, feature_indices]) @ coefficients
        group_weights = _group_weights(sample)
        totals = {"reference_top1": 0.0, "pairwise_accuracy": 0.0, "mrr": 0.0}
        for group in _nontrivial_groups(sample):
            alternatives = np.r_[np.arange(group.start, group.reference_index), np.arange(group.reference_index + 1, group.stop)]
            metrics = strict_group_metrics(scores[group.reference_index], scores[alternatives], tie_tolerance=tie_tolerance)
            weight = group_weights[group.reference_id]
            totals["reference_top1"] += weight * float(metrics["top1"])
            totals["pairwise_accuracy"] += weight * float(metrics["pairwise_accuracy"])
            totals["mrr"] += weight * float(metrics["mrr"])
            group_rows.append({
                "sample_id": sample.sample_id, "fold": sample.fold, "family": sample.family,
                "route": sample.route, "parent_t": group.parent_t, "reference_id": group.reference_id,
                "candidate_count": group.stop - group.start, "top1": bool(metrics["top1"]),
                "pairwise_accuracy": float(metrics["pairwise_accuracy"]), "rank": int(metrics["rank"]),
                "mrr": float(metrics["mrr"]), "hierarchical_group_weight": weight,
            })
        sample_rows.append({
            "sample_id": sample.sample_id, "fold": sample.fold, "family": sample.family, "route": sample.route,
            "nontrivial_groups": len(group_weights), "singleton_groups": sample.reference_count - len(group_weights),
            **totals,
        })
    return sample_rows, group_rows


def _aggregate(rows: list[dict]) -> dict:
    if not rows:
        raise RuntimeError("Required reporting stratum has no samples")
    return {
        "sample_count": len(rows),
        "nontrivial_groups": int(sum(row["nontrivial_groups"] for row in rows)),
        "reference_top1": float(np.mean([row["reference_top1"] for row in rows])),
        "pairwise_accuracy": float(np.mean([row["pairwise_accuracy"] for row in rows])),
        "mrr": float(np.mean([row["mrr"] for row in rows])),
    }


def _report_strata(sample_rows: list[dict], folds: list[int]) -> dict:
    decision = [row for row in sample_rows if row["route"] in DECISION_ROUTES]
    by_fold = {str(fold): _aggregate([row for row in decision if row["fold"] == fold]) for fold in folds}
    by_route = {route: _aggregate([row for row in decision if row["route"] == route]) for route in DECISION_ROUTES}
    by_fold_route = {
        f"{fold}|{route}": _aggregate([row for row in decision if row["fold"] == fold and row["route"] == route])
        for fold in folds for route in DECISION_ROUTES
    }
    families = sorted({row["family"] for row in decision})
    by_family = {family: _aggregate([row for row in decision if row["family"] == family]) for family in families}
    local = [row for row in sample_rows if row["route"] == LOCAL_MAXIMA_ROUTE]
    return {
        "pooled": _aggregate(decision), "by_fold": by_fold, "by_route": by_route,
        "by_fold_route": by_fold_route, "by_family": by_family,
        "local_maxima_zero_shot_unproven_generalization": _aggregate(local) if local else None,
    }


def _fit_oof(samples: list[SampleData], feature_names: list[str], selected_names: list[str], contract: dict, model_label: str) -> dict:
    feature_indices = np.array([feature_names.index(name) for name in selected_names], dtype=np.int64)
    folds = [int(value) for value in contract["outer_validation"]["folds"]]
    c_grid = [float(value) for value in contract["model"]["regularization_grid_c"]]
    tie_tolerance = float(contract["evaluation"]["strict_score_tie_tolerance"])
    all_sample_rows: list[dict] = []
    all_group_rows: list[dict] = []
    outer_details: list[dict] = []

    for outer_fold in folds:
        train_folds = [fold for fold in folds if fold != outer_fold]
        inner_scores: dict[str, list[float]] = {str(c): [] for c in c_grid}
        inner_details: list[dict] = []
        for validation_fold in train_folds:
            inner_train = [sample for sample in samples if sample.fold in train_folds and sample.fold != validation_fold]
            inner_valid = [sample for sample in samples if sample.fold == validation_fold]
            preprocessor = _fit_preprocessor(inner_train, feature_indices)
            differences, weights = _make_pairs(inner_train, preprocessor, feature_indices)
            for c in c_grid:
                fit = fit_pairwise_logistic(differences, weights, c=c, max_iterations=150)
                if not fit.converged:
                    raise RuntimeError(f"{model_label} inner fit failed to converge: outer={outer_fold} validation={validation_fold} C={c}")
                valid_rows, _ = _score_samples(inner_valid, preprocessor, feature_indices, fit.coefficients, tie_tolerance)
                decision_rows = [row for row in valid_rows if row["route"] in DECISION_ROUTES]
                top1 = _aggregate(decision_rows)["reference_top1"]
                inner_scores[str(c)].append(top1)
                inner_details.append({"validation_fold": validation_fold, "c": c, "reference_top1": top1, "iterations": fit.iterations})
            del differences, weights

        means = {c: float(np.mean(inner_scores[str(c)])) for c in c_grid}
        best_value = max(means.values())
        selected_c = min(c for c in c_grid if abs(means[c] - best_value) <= 1e-12)
        outer_train = [sample for sample in samples if sample.fold != outer_fold]
        outer_valid = [sample for sample in samples if sample.fold == outer_fold]
        preprocessor = _fit_preprocessor(outer_train, feature_indices)
        differences, weights = _make_pairs(outer_train, preprocessor, feature_indices)
        fit = fit_pairwise_logistic(differences, weights, c=selected_c, max_iterations=150)
        if not fit.converged:
            raise RuntimeError(f"{model_label} outer fit failed to converge: fold={outer_fold} C={selected_c}")
        sample_rows, group_rows = _score_samples(outer_valid, preprocessor, feature_indices, fit.coefficients, tie_tolerance)
        all_sample_rows.extend(sample_rows)
        all_group_rows.extend(group_rows)
        outer_details.append({
            "heldout_fold": outer_fold, "selected_c": selected_c, "inner_mean_top1_by_c": {str(c): means[c] for c in c_grid},
            "inner_directions": inner_details, "fit_converged": fit.converged, "fit_iterations": fit.iterations,
            "fit_objective": fit.objective, "feature_names": selected_names,
            "coefficient_names": selected_names + [f"missing:{name}" for name in selected_names],
            "coefficients": fit.coefficients.tolist(),
        })
        print(f"{model_label}: held-out fold {outer_fold} selected C={selected_c:g} complete", flush=True)
        del differences, weights

    strata = _report_strata(all_sample_rows, folds)
    return {
        "model": model_label, "feature_names": selected_names, "outer_fits": outer_details,
        "metrics": strata, "per_sample": sorted(all_sample_rows, key=lambda row: row["sample_id"]),
        "group_rows": all_group_rows,
    }


def _write_results_markdown(path: Path, summary: dict) -> None:
    full = summary["full_model"]
    ablation = summary["teacher_feature_ablation"]
    decision = summary["generalization_decision"]
    lines = [
        "# V22 Out-of-Fold Continuation Head Results", "", f"Decision: **{decision['decision']}**", "",
        "This is weak-reference imitation evidence, not biological continuation validation. No assignment was run and no graph was mutated.", "",
        "## Full Model", "", "| Stratum | Samples | Top-1 | Pairwise | MRR |", "| --- | ---: | ---: | ---: | ---: |",
    ]
    def add_table(metrics: dict) -> None:
        for name, values in metrics.items():
            lines.append(f"| {name} | {values['sample_count']} | {values['reference_top1']:.9f} | {values['pairwise_accuracy']:.9f} | {values['mrr']:.9f} |")
    add_table({"pooled decision routes": full["metrics"]["pooled"]})
    add_table({f"fold {key}": value for key, value in full["metrics"]["by_fold"].items()})
    add_table(full["metrics"]["by_route"])
    add_table(full["metrics"]["by_fold_route"])
    local = full["metrics"]["local_maxima_zero_shot_unproven_generalization"]
    if local:
        add_table({"local_maxima/motion_mutual (zero-shot; unproven generalization; excluded from GO)": local})
    lines += ["", "## Teacher-Feature Ablation", "", "| Stratum | Samples | Top-1 | Pairwise | MRR |", "| --- | ---: | ---: | ---: | ---: |"]
    add_table({"pooled decision routes": ablation["metrics"]["pooled"]})
    add_table({f"fold {key}": value for key, value in ablation["metrics"]["by_fold"].items()})
    add_table(ablation["metrics"]["by_route"])
    lines += ["", "## Frozen Decision Gates", ""]
    for name, passed in decision["hard_gates"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'}: `{name}`")
    lines += ["", "## Flagged Concerns", ""]
    for name, fired in decision["flagged_concerns"].items():
        lines.append(f"- {'FIRED' if fired else 'clear'}: `{name}`")
    lines += ["", "## Boundaries", "", "- Local-maxima is zero-shot-only in held-out fold 3 and cannot carry the pooled decision.", "- The ablation is mandatory diagnostic evidence; the frozen GO/HOLD/NO_GO call is made on the preregistered full model.", "- `assignment_enabled=false`, `graph_mutated=false`, and `full_199_authorized=false`."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit the preregistered V22 continuation head out of fold")
    parser.add_argument("--contract", type=Path, default=ROOT / "tests/fixtures/v22_continuation_head_preregistration.json")
    parser.add_argument("--feature-contract", type=Path, default=ROOT / "tests/fixtures/v22_continuation_feature_table.json")
    parser.add_argument("--shards", type=Path, default=ROOT / "v22_continuation_feature_shards")
    parser.add_argument("--output", type=Path, default=ROOT / "v22_continuation_head_oof_summary.json")
    parser.add_argument("--sample-output", type=Path, default=ROOT / "v22_continuation_head_oof_samples.csv")
    parser.add_argument("--group-output", type=Path, default=ROOT / "v22_continuation_head_oof_groups.csv.gz")
    parser.add_argument("--report", type=Path, default=ROOT / "V22_CONTINUATION_HEAD_RESULTS.md")
    args = parser.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8-sig"))
    feature_contract = json.loads(args.feature_contract.read_text(encoding="utf-8-sig"))
    if _sha256(args.feature_contract) != contract["source_feature_contract_sha256"]:
        raise RuntimeError("Feature contract hash does not match preregistration")
    source_summary = ROOT / contract["source_feature_summary"]
    if _sha256(source_summary) != contract["source_feature_summary_sha256"]:
        raise RuntimeError("Feature summary hash does not match preregistration")
    feature_names = list(feature_contract["feature_contract"]["model_feature_allowlist"])
    teacher_features = set(contract["diagnostics"]["teacher_derived_features"])
    ablated_names = [name for name in feature_names if name not in teacher_features]

    samples = _load_samples(args.shards, feature_names)
    if len(samples) != 27 or {sample.fold for sample in samples} != {1, 2, 3}:
        raise RuntimeError("Development population does not match the locked 27-sample, 3-fold contract")

    full = _fit_oof(samples, feature_names, feature_names, contract, "full")
    ablation = _fit_oof(samples, feature_names, ablated_names, contract, "teacher_feature_ablation")
    generalization = evaluate_generalization(
        pooled=full["metrics"]["pooled"], by_fold=full["metrics"]["by_fold"],
        by_route=full["metrics"]["by_route"], by_fold_route=full["metrics"]["by_fold_route"], contract=contract,
    )

    full_groups = pd.DataFrame(full.pop("group_rows")).rename(columns={
        "top1": "full_top1", "pairwise_accuracy": "full_pairwise_accuracy", "rank": "full_rank", "mrr": "full_mrr"
    })
    ablation_groups = pd.DataFrame(ablation.pop("group_rows"))[["reference_id", "top1", "pairwise_accuracy", "rank", "mrr"]].rename(columns={
        "top1": "ablation_top1", "pairwise_accuracy": "ablation_pairwise_accuracy", "rank": "ablation_rank", "mrr": "ablation_mrr"
    })
    group_output = full_groups.merge(ablation_groups, on="reference_id", how="inner", validate="one_to_one")
    if len(group_output) != len(full_groups):
        raise RuntimeError("Full/ablation group output mismatch")
    group_output.to_csv(args.group_output, index=False, compression="gzip")

    full_samples = pd.DataFrame(full["per_sample"]).add_prefix("full_").rename(columns={"full_sample_id": "sample_id"})
    ablation_samples = pd.DataFrame(ablation["per_sample"]).add_prefix("ablation_").rename(columns={"ablation_sample_id": "sample_id"})
    full_samples.merge(ablation_samples, on="sample_id", validate="one_to_one").to_csv(args.sample_output, index=False)

    summary = {
        "contract": contract["name"], "contract_sha256": _sha256(args.contract),
        "source_feature_contract_sha256": _sha256(args.feature_contract), "samples": len(samples),
        "decision_routes": list(DECISION_ROUTES),
        "local_maxima": {"decision_eligible": False, "status": "zero-shot-only; unproven generalization"},
        "full_model": full, "teacher_feature_ablation": ablation,
        "generalization_decision": generalization,
        "semantic_scoring_enabled": True, "assignment_enabled": False,
        "graph_mutated": False, "full_199_authorized": False,
        "interpretation_boundary": "weak-reference imitation consistency is not biological continuation validation",
    }
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_results_markdown(args.report, summary)
    print(json.dumps({
        "decision": generalization["decision"], "pooled": full["metrics"]["pooled"],
        "by_fold": full["metrics"]["by_fold"], "by_route": full["metrics"]["by_route"],
        "local_maxima": full["metrics"]["local_maxima_zero_shot_unproven_generalization"],
        "ablation_pooled": ablation["metrics"]["pooled"], "graph_mutated": False,
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
