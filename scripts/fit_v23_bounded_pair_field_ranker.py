"""Fit the frozen V23 pair-field ranker and its preregistered controls."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from atabey.tracking.pair_field_ranker import (
    aggregate_event_metrics,
    assemble_action_field,
    build_pair_field_ranker,
    event_ranking_rows,
    geometry_features,
    fit_pairwise_logistic,
    load_locked_pair_field_data,
    model_parameter_count,
    selected_preference_pairs,
    stratified_metrics,
    xy_d4,
)


def _seed_everything(seed: int) -> None:
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True


def _batch_fields(data, indices, *, image_mode, image_map=None, transforms=None):
    fields = []
    for offset, index in enumerate(indices):
        image_parent_index = None if image_map is None else image_map.get(
            data.actions[int(index)]["parent_cache_key"]
        )
        field = assemble_action_field(
            data,
            data.actions[int(index)],
            image_mode=image_mode,
            image_parent_index=image_parent_index,
        )
        if transforms is not None:
            field = xy_d4(field, int(transforms[offset]))
        fields.append(field)
    return np.stack(fields)


def _scores(model, data, indices, *, device, batch_size, image_mode="main", image_map=None):
    import torch

    model.eval()
    result = np.full(len(data.actions), np.nan, dtype=np.float64)
    with torch.inference_mode():
        for start in range(0, len(indices), batch_size):
            batch_indices = np.asarray(indices[start : start + batch_size], dtype=np.int64)
            fields = _batch_fields(
                data,
                batch_indices,
                image_mode=image_mode,
                image_map=image_map,
            )
            tensor = torch.from_numpy(fields).to(device)
            values = model(tensor).detach().cpu().numpy()
            result[batch_indices] = values
    return result


def _pairwise_loss_from_scores(scores, pairs, weights):
    margins = scores[pairs[:, 0]] - scores[pairs[:, 1]]
    return float(np.dot(weights, np.logaddexp(0.0, -margins)))


def _validation_loss(model, data, folds, *, device, batch_size, image_mode):
    indices = [i for i, row in enumerate(data.actions) if int(row["fold"]) in set(folds)]
    scores = _scores(
        model, data, indices, device=device, batch_size=batch_size, image_mode=image_mode
    )
    pairs, weights = selected_preference_pairs(data.actions, folds)
    return _pairwise_loss_from_scores(scores, pairs, weights)


def _fit_cnn(
    data,
    *,
    train_folds,
    seed,
    device,
    image_mode,
    batch_size,
    maximum_epochs,
    validation_folds=None,
    patience=8,
    minimum_delta=1e-4,
):
    import torch
    import torch.nn.functional as functional

    _seed_everything(seed)
    model = build_pair_field_ranker().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-3)
    pairs, weights = selected_preference_pairs(data.actions, train_folds)
    rng = np.random.default_rng(seed)
    best_loss = math.inf
    best_epoch = 0
    best_state = None
    stale = 0
    history = []

    for epoch in range(1, maximum_epochs + 1):
        order = rng.permutation(len(pairs))
        model.train()
        train_numerator = 0.0
        train_denominator = 0.0
        for start in range(0, len(order), batch_size):
            selected = order[start : start + batch_size]
            pair_batch = pairs[selected]
            pair_weights = weights[selected]
            transforms = rng.integers(0, 8, size=len(selected))
            positive = _batch_fields(
                data,
                pair_batch[:, 0],
                image_mode=image_mode,
                transforms=transforms,
            )
            negative = _batch_fields(
                data,
                pair_batch[:, 1],
                image_mode=image_mode,
                transforms=transforms,
            )
            positive_tensor = torch.from_numpy(positive).to(device)
            negative_tensor = torch.from_numpy(negative).to(device)
            weight_tensor = torch.from_numpy(pair_weights.astype(np.float32)).to(device)
            optimizer.zero_grad(set_to_none=True)
            margin = model(positive_tensor) - model(negative_tensor)
            losses = functional.softplus(-margin)
            loss = (losses * weight_tensor).sum() / weight_tensor.sum()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_numerator += float((losses.detach() * weight_tensor).sum().cpu())
            train_denominator += float(weight_tensor.sum().cpu())

        validation_loss = None
        if validation_folds is not None:
            validation_loss = _validation_loss(
                model,
                data,
                validation_folds,
                device=device,
                batch_size=batch_size,
                image_mode=image_mode,
            )
            if validation_loss < best_loss - minimum_delta:
                best_loss = validation_loss
                best_epoch = epoch
                best_state = {
                    key: value.detach().cpu().clone()
                    for key, value in model.state_dict().items()
                }
                stale = 0
            else:
                stale += 1
        history.append(
            {
                "epoch": epoch,
                "train_loss": train_numerator / train_denominator,
                "validation_loss": validation_loss,
            }
        )
        if validation_folds is not None and stale >= patience:
            break

    if validation_folds is not None:
        if best_state is None:
            raise RuntimeError("Early stopping never recorded a checkpoint")
        model.load_state_dict(best_state)
    else:
        best_epoch = maximum_epochs
        best_loss = history[-1]["train_loss"]
    return model, {
        "best_epoch": int(best_epoch),
        "best_loss": float(best_loss),
        "epochs_run": len(history),
        "history": history,
    }


def _fit_outer_cnn(data, *, outer_fold, seed, device, image_mode, batch_size, maximum_epochs):
    training_folds = [fold for fold in (1, 2, 3) if fold != outer_fold]
    swap_results = []
    for train_fold, validation_fold in (
        (training_folds[0], training_folds[1]),
        (training_folds[1], training_folds[0]),
    ):
        _, selection = _fit_cnn(
            data,
            train_folds=(train_fold,),
            validation_folds=(validation_fold,),
            seed=seed,
            device=device,
            image_mode=image_mode,
            batch_size=batch_size,
            maximum_epochs=maximum_epochs,
        )
        swap_results.append(
            {
                "train_fold": train_fold,
                "validation_fold": validation_fold,
                **selection,
            }
        )
    final_epochs = max(1, int(math.floor(np.median([row["best_epoch"] for row in swap_results]))))
    model, final_fit = _fit_cnn(
        data,
        train_folds=training_folds,
        validation_folds=None,
        seed=seed,
        device=device,
        image_mode=image_mode,
        batch_size=batch_size,
        maximum_epochs=final_epochs,
    )
    return model, {
        "outer_fold": outer_fold,
        "inner_swaps": swap_results,
        "final_refit_epochs": final_epochs,
        "final_train_loss": final_fit["best_loss"],
    }


def _geometry_scores(data, outer_fold):
    features = np.stack([geometry_features(row) for row in data.actions])
    training_folds = [fold for fold in (1, 2, 3) if fold != outer_fold]
    candidates = (0.01, 0.1, 1.0, 10.0)
    losses = {}
    for c in candidates:
        swap_losses = []
        for train_fold, validation_fold in (
            (training_folds[0], training_folds[1]),
            (training_folds[1], training_folds[0]),
        ):
            train_indices = np.asarray(
                [i for i, row in enumerate(data.actions) if row["fold"] == train_fold]
            )
            mean = features[train_indices].mean(axis=0)
            scale = features[train_indices].std(axis=0)
            scale[scale < 1e-8] = 1.0
            normalized = (features - mean) / scale
            pairs, weights = selected_preference_pairs(data.actions, (train_fold,))
            fit = fit_pairwise_logistic(
                normalized[pairs[:, 0]] - normalized[pairs[:, 1]], weights, c=c
            )
            validation_pairs, validation_weights = selected_preference_pairs(
                data.actions, (validation_fold,)
            )
            scores = normalized @ fit.coefficients
            swap_losses.append(_pairwise_loss_from_scores(scores, validation_pairs, validation_weights))
        losses[c] = float(np.mean(swap_losses))
    selected_c = min(candidates, key=lambda value: (losses[value], value))
    train_indices = np.asarray(
        [i for i, row in enumerate(data.actions) if row["fold"] in training_folds]
    )
    mean = features[train_indices].mean(axis=0)
    scale = features[train_indices].std(axis=0)
    scale[scale < 1e-8] = 1.0
    normalized = (features - mean) / scale
    pairs, weights = selected_preference_pairs(data.actions, training_folds)
    fit = fit_pairwise_logistic(
        normalized[pairs[:, 0]] - normalized[pairs[:, 1]], weights, c=selected_c
    )
    return normalized @ fit.coefficients, {
        "selected_c": selected_c,
        "inner_validation_losses": {str(key): value for key, value in losses.items()},
        "converged": fit.converged,
    }


def _nearest_scores(data):
    return -np.asarray(
        [row["parent_child_distance_sum_um"] for row in data.actions], dtype=np.float64
    )


def _shuffle_image_map(data, outer_fold, seed):
    parent_rows = []
    for cache_key, parent_index in data.parent_index.items():
        related = [
            row
            for row in data.actions
            if row["parent_cache_key"] == cache_key and int(row["fold"]) == outer_fold
        ]
        if not related:
            continue
        parent_rows.append(
            {
                "cache_key": cache_key,
                "parent_index": parent_index,
                "family": related[0]["family"],
                "coverage": float(data.parent_tensors[parent_index, 3].mean()),
            }
        )
    strata = {}
    for family in sorted({row["family"] for row in parent_rows}):
        family_rows = sorted(
            [row for row in parent_rows if row["family"] == family],
            key=lambda row: (row["coverage"], row["cache_key"]),
        )
        for rank, row in enumerate(family_rows):
            quartile = min(3, (4 * rank) // len(family_rows))
            strata.setdefault((family, quartile), []).append(row)

    mapping = {}
    singleton_strata = []
    for stratum, rows in sorted(strata.items()):
        ordered = sorted(
            rows,
            key=lambda row: hashlib_key(f"{seed}|{row['cache_key']}"),
        )
        if len(ordered) == 1:
            mapping[ordered[0]["cache_key"]] = ordered[0]["parent_index"]
            singleton_strata.append({"family": stratum[0], "quartile": stratum[1]})
            continue
        for index, row in enumerate(ordered):
            mapping[row["cache_key"]] = ordered[(index + 1) % len(ordered)]["parent_index"]

    heldout_events = {
        row["event_id"] for row in data.actions if int(row["fold"]) == outer_fold
    }
    moved_events = set()
    moved_actions = 0
    heldout_actions = 0
    for row in data.actions:
        if int(row["fold"]) != outer_fold:
            continue
        heldout_actions += 1
        source = data.parent_index[row["parent_cache_key"]]
        if mapping[row["parent_cache_key"]] != source:
            moved_actions += 1
            moved_events.add(row["event_id"])
    return mapping, {
        "events": len(heldout_events),
        "moved_events": len(moved_events),
        "moved_event_fraction": len(moved_events) / len(heldout_events),
        "moved_action_fraction": moved_actions / heldout_actions,
        "singleton_strata": singleton_strata,
    }


def hashlib_key(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def _heldout_indices(data, fold):
    return [i for i, row in enumerate(data.actions) if int(row["fold"]) == fold]


def _atomic_json(path, payload):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _evaluate_seed(
    data, *, seed, device, batch_size, maximum_epochs, checkpoint_dir,
    outer_folds=(1, 2, 3), resume=False,
):
    import torch

    names = ("main", "mask_only", "image_shuffled", "static_image", "geometry_only")
    score_sets = {
        name: np.full(len(data.actions), np.nan, dtype=np.float64)
        for name in names
    }
    fit_records = []
    shuffle_records = []
    evaluated_indices = []
    shard_dir = checkpoint_dir.parent / "shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    for outer_fold in outer_folds:
        heldout = _heldout_indices(data, outer_fold)
        evaluated_indices.extend(heldout)
        score_path = shard_dir / f"seed_{seed}_fold_{outer_fold}_scores.npz"
        record_path = shard_dir / f"seed_{seed}_fold_{outer_fold}_record.json"
        if resume and score_path.exists() and record_path.exists():
            archive = np.load(score_path, allow_pickle=False)
            if not np.array_equal(archive["indices"], np.asarray(heldout)):
                raise ValueError(f"Resume shard index mismatch: {score_path}")
            for name in names:
                score_sets[name][heldout] = archive[name]
            record = json.loads(record_path.read_text(encoding="utf-8"))
            fit_records.append(record["fit"])
            shuffle_records.append(record["shuffle"])
            print(f"seed={seed} outer_fold={outer_fold} resumed", flush=True)
            continue
        main_model, main_fit = _fit_outer_cnn(
            data,
            outer_fold=outer_fold,
            seed=seed,
            device=device,
            image_mode="main",
            batch_size=batch_size,
            maximum_epochs=maximum_epochs,
        )
        mask_model, mask_fit = _fit_outer_cnn(
            data,
            outer_fold=outer_fold,
            seed=seed,
            device=device,
            image_mode="mask_only",
            batch_size=batch_size,
            maximum_epochs=maximum_epochs,
        )
        score_sets["main"][heldout] = _scores(
            main_model, data, heldout, device=device, batch_size=batch_size
        )[heldout]
        score_sets["mask_only"][heldout] = _scores(
            mask_model, data, heldout, device=device, batch_size=batch_size, image_mode="mask_only"
        )[heldout]
        score_sets["static_image"][heldout] = _scores(
            main_model, data, heldout, device=device, batch_size=batch_size, image_mode="static_image"
        )[heldout]
        image_map, shuffle = _shuffle_image_map(data, outer_fold, seed)
        score_sets["image_shuffled"][heldout] = _scores(
            main_model,
            data,
            heldout,
            device=device,
            batch_size=batch_size,
            image_mode="main",
            image_map=image_map,
        )[heldout]
        geometry, geometry_fit = _geometry_scores(data, outer_fold)
        score_sets["geometry_only"][heldout] = geometry[heldout]
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        torch.save(
            main_model.state_dict(), checkpoint_dir / f"seed_{seed}_fold_{outer_fold}_main.pt"
        )
        torch.save(
            mask_model.state_dict(), checkpoint_dir / f"seed_{seed}_fold_{outer_fold}_mask.pt"
        )
        fit_records.append(
            {
                "outer_fold": outer_fold,
                "main": main_fit,
                "mask_only": mask_fit,
                "geometry_only": geometry_fit,
            }
        )
        shuffle_records.append({"outer_fold": outer_fold, **shuffle})
        temporary_scores = score_path.with_suffix(".npz.tmp")
        with temporary_scores.open("wb") as handle:
            np.savez_compressed(
                handle,
                indices=np.asarray(heldout, dtype=np.int64),
                **{name: score_sets[name][heldout] for name in names},
            )
        temporary_scores.replace(score_path)
        _atomic_json(
            record_path,
            {"seed": seed, "outer_fold": outer_fold,
             "fit": fit_records[-1], "shuffle": shuffle_records[-1]},
        )
        print(f"seed={seed} outer_fold={outer_fold} complete", flush=True)

    nearest = _nearest_scores(data)
    metrics = {}
    event_rows = {}
    for name, scores in {**score_sets, "nearest_distance": nearest}.items():
        subset_actions = [data.actions[index] for index in evaluated_indices]
        subset_scores = [scores[index] for index in evaluated_indices]
        rows = event_ranking_rows(subset_actions, subset_scores)
        event_rows[name] = rows
        metrics[name] = stratified_metrics(rows)
    return {
        "seed": seed,
        "metrics": metrics,
        "fit_records": fit_records,
        "shuffle": shuffle_records,
        "event_rows": event_rows,
    }


def _seed_gates(seed_result, contract):
    gates = contract["hard_gates"]
    metrics = seed_result["metrics"]
    main = metrics["main"]
    fold_values = [row["recall_at_10"] for row in main["by_fold"].values()]
    family_values = [row["recall_at_10"] for row in main["by_family"].values()]
    nonimage_names = ("nearest_distance", "geometry_only", "mask_only")
    best_nonimage = max(metrics[name]["pooled"]["recall_at_10"] for name in nonimage_names)
    regression = []
    for fold in main["by_fold"]:
        main_hits = round(main["by_fold"][fold]["recall_at_10"] * main["by_fold"][fold]["events"])
        control_hits = max(
            round(metrics[name]["by_fold"][fold]["recall_at_10"] * metrics[name]["by_fold"][fold]["events"])
            for name in nonimage_names
        )
        regression.append(control_hits - main_hits)
    checks = {
        "pooled_recall_at_10": main["pooled"]["recall_at_10"] >= gates["pooled_recall_at_10_min"],
        "each_fold_recall_at_10": min(fold_values) >= gates["each_fold_recall_at_10_min"],
        "each_family_recall_at_10": min(family_values) >= gates["each_family_recall_at_10_min"],
        "fold_spread": max(fold_values) - min(fold_values) <= gates["recall_at_10_max_fold_spread"],
        "pooled_mrr": main["pooled"]["mrr"] >= gates["pooled_mrr_min"],
        "pairwise_accuracy": main["pooled"]["pairwise_accuracy"] >= gates["pooled_tp_vs_official_fp_pairwise_accuracy_min"],
        "margin_over_best_nonimage": main["pooled"]["recall_at_10"] - best_nonimage >= gates["recall_at_10_margin_over_best_nonimage_control_min"],
        "margin_over_image_shuffled": main["pooled"]["recall_at_10"] - metrics["image_shuffled"]["pooled"]["recall_at_10"] >= gates["recall_at_10_margin_over_image_shuffled_min"],
        "margin_over_static_image": main["pooled"]["recall_at_10"] - metrics["static_image"]["pooled"]["recall_at_10"] >= gates["recall_at_10_margin_over_static_image_min"],
        "maximum_fold_event_regression": max(regression) <= gates["maximum_fold_event_regression_vs_best_nonimage_control"],
        "shuffle_coverage": min(row["moved_event_fraction"] for row in seed_result["shuffle"]) >= 0.8,
        "not_catastrophic": main["pooled"]["recall_at_10"] >= gates["catastrophic_seed_pooled_recall_at_10_below"],
    }
    return {
        "checks": checks,
        "passed_all": all(checks.values()),
        "best_nonimage_recall_at_10": best_nonimage,
        "fold_event_regressions": regression,
    }


def _decision(seed_results, contract):
    for result in seed_results:
        result["gates"] = _seed_gates(result, contract)
    passing = sum(result["gates"]["passed_all"] for result in seed_results)
    catastrophic = any(not result["gates"]["checks"]["not_catastrophic"] for result in seed_results)
    ordered = sorted(
        seed_results,
        key=lambda row: (
            row["metrics"]["main"]["pooled"]["recall_at_10"],
            row["metrics"]["main"]["pooled"]["mrr"],
            row["seed"],
        ),
    )
    median = ordered[len(ordered) // 2]
    absolute_names = (
        "pooled_recall_at_10",
        "each_fold_recall_at_10",
        "each_family_recall_at_10",
        "fold_spread",
        "pooled_mrr",
        "pairwise_accuracy",
    )
    absolute_pass = all(median["gates"]["checks"][name] for name in absolute_names)
    if passing >= contract["hard_gates"]["minimum_seeds_passing_all_hard_gates"] and not catastrophic:
        decision = "GO_TO_READ_ONLY_LOCAL_ASSIGNMENT_SHADOW_PREREGISTRATION"
    elif absolute_pass:
        decision = "HOLD_PAIR_FIELD_SIGNAL_INCONCLUSIVE"
    else:
        decision = "NO_GO_PAIR_FIELD_RANKER"
    return {
        "decision": decision,
        "passing_seeds": passing,
        "catastrophic_seed_present": catastrophic,
        "median_seed": median["seed"],
    }


def _report(summary):
    lines = [
        "# V23 Bounded Pair-Field Ranker Results",
        "",
        f"Decision: **{summary['decision']}**.",
        "",
        "This is a development-only, sample-blocked retrieval experiment. Scores are not calibrated division probabilities. Assignment, graph mutation, full-cohort evaluation, and submission remain disabled.",
        "",
        "## Seed Results",
        "",
        "| Seed | Recall@10 | MRR | Pairwise | Pass |",
        "|---:|---:|---:|---:|---|",
    ]
    for result in summary["seed_results"]:
        pooled = result["metrics"]["main"]["pooled"]
        lines.append(
            f"| {result['seed']} | {pooled['recall_at_10']:.6f} | {pooled['mrr']:.6f} | {pooled['pairwise_accuracy']:.6f} | {result['gates']['passed_all']} |"
        )
    lines.extend(("", "## Boundaries", "", "- model fit: true", "- assignment enabled: false", "- graph mutation: false", "- full 199 authorized: false"))
    return "\n".join(lines) + "\n"


def main():
    import torch

    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "outputs/v23_cfar_pair_field_v1")
    parser.add_argument("--contract", type=Path, default=ROOT / "tests/fixtures/v23_bounded_pair_field_ranker.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/v23_pair_field_ranker_v1")
    parser.add_argument("--summary", type=Path, default=ROOT / "v23_bounded_pair_field_ranker_summary.json")
    parser.add_argument("--report", type=Path, default=ROOT / "V23_BOUNDED_PAIR_FIELD_RANKER_RESULTS.md")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--maximum-epochs", type=int, default=60)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    data = load_locked_pair_field_data(args.dataset)
    seeds = contract["reproducibility"]["seeds"]
    maximum_epochs = args.maximum_epochs
    if args.smoke:
        seeds = seeds[:1]
        maximum_epochs = 1
    if args.output_dir.exists() and not args.resume:
        raise FileExistsError(f"Refusing to overwrite model output: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=args.resume)

    seed_results = []
    for seed in seeds:
        seed_results.append(
            _evaluate_seed(
                data,
                seed=seed,
                device=torch.device(args.device),
                batch_size=args.batch_size,
                maximum_epochs=maximum_epochs,
                checkpoint_dir=args.output_dir / "checkpoints",
                outer_folds=(1,) if args.smoke else (1, 2, 3),
                resume=args.resume,
            )
        )
    decision = (
        {"decision": "SMOKE_ONLY_NO_DECISION", "passing_seeds": 0, "catastrophic_seed_present": None, "median_seed": seeds[0]}
        if args.smoke
        else _decision(seed_results, contract)
    )
    if args.smoke:
        for result in seed_results:
            result["gates"] = _seed_gates(result, contract)
    summary = {
        "status": "v23_bounded_pair_field_ranker_result",
        **decision,
        "smoke": args.smoke,
        "device": args.device,
        "model_parameters": model_parameter_count(build_pair_field_ranker()),
        "dataset": {"events": len(data.events), "actions": len(data.actions), "parent_fields": len(data.parents)},
        "seed_results": seed_results,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "numpy": np.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "cpu_count": os.cpu_count(),
        },
        "model_fitted": True,
        "assignment_enabled": False,
        "graph_mutation": False,
        "full_199_authorized": False,
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.report.write_text(_report(summary), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("decision", "smoke", "device", "model_parameters")}, indent=2))


if __name__ == "__main__":
    main()
