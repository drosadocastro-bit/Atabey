from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit


@dataclass(frozen=True)
class PairwiseFit:
    coefficients: np.ndarray
    converged: bool
    iterations: int
    objective: float


def fit_pairwise_logistic(
    differences: np.ndarray,
    weights: np.ndarray,
    *,
    c: float,
    max_iterations: int = 100,
) -> PairwiseFit:
    """Fit an L2 pairwise logistic utility with all preferences oriented +1."""

    x = np.asarray(differences, dtype=np.float64)
    pair_weights = np.asarray(weights, dtype=np.float64)
    if x.ndim != 2 or pair_weights.shape != (x.shape[0],):
        raise ValueError("Pair differences and weights have incompatible shapes")
    if x.shape[0] == 0:
        raise ValueError("At least one preference pair is required")
    if c <= 0.0:
        raise ValueError("c must be positive")
    if np.any(pair_weights < 0.0) or not np.all(np.isfinite(pair_weights)):
        raise ValueError("Pair weights must be finite and non-negative")
    weight_sum = float(pair_weights.sum())
    if weight_sum <= 0.0:
        raise ValueError("Pair weights must have positive total mass")
    normalized = pair_weights / weight_sum

    def objective(coefficients: np.ndarray) -> tuple[float, np.ndarray]:
        margins = x @ coefficients
        losses = np.logaddexp(0.0, -margins)
        value = float(np.dot(normalized, losses))
        value += 0.5 * float(np.dot(coefficients, coefficients)) / float(c)
        derivative = -expit(-margins) * normalized
        gradient = x.T @ derivative + coefficients / float(c)
        return value, np.asarray(gradient, dtype=np.float64)

    result = minimize(
        objective,
        np.zeros(x.shape[1], dtype=np.float64),
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": int(max_iterations), "ftol": 1e-10, "gtol": 1e-7},
    )
    return PairwiseFit(
        coefficients=np.asarray(result.x, dtype=np.float64),
        converged=bool(result.success),
        iterations=int(result.nit),
        objective=float(result.fun),
    )


def strict_group_metrics(
    reference_score: float,
    alternative_scores: np.ndarray,
    *,
    tie_tolerance: float,
) -> dict[str, float | int | bool]:
    alternatives = np.asarray(alternative_scores, dtype=np.float64)
    if alternatives.ndim != 1 or alternatives.size == 0:
        raise ValueError("Decision metrics require at least one alternative")
    if tie_tolerance < 0.0:
        raise ValueError("tie_tolerance must be non-negative")

    strictly_preferred = float(reference_score) > alternatives + tie_tolerance
    pairwise_accuracy = float(np.mean(strictly_preferred))
    rank = 1 + int(
        np.sum(alternatives >= float(reference_score) - tie_tolerance)
    )
    return {
        "top1": bool(np.all(strictly_preferred)),
        "pairwise_accuracy": pairwise_accuracy,
        "rank": rank,
        "mrr": 1.0 / float(rank),
    }


def evaluate_generalization(
    *,
    pooled: Mapping[str, float],
    by_fold: Mapping[str, Mapping[str, float]],
    by_route: Mapping[str, Mapping[str, float]],
    by_fold_route: Mapping[str, Mapping[str, float]],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply the frozen fold/route GO-HOLD-NO_GO contract exactly."""

    generalization = contract["generalization"]
    fold_hard = generalization["fold_hard_gates"]
    fold_flags = generalization["fold_flagged_concerns"]
    route_hard = generalization["route_hard_gates"]
    route_flags = generalization["route_flagged_concerns"]
    folds = tuple(str(value) for value in contract["outer_validation"]["folds"])
    decision_routes = tuple(route_hard["decision_routes"])

    fold_top1 = [float(by_fold[fold]["reference_top1"]) for fold in folds]
    fold_pairwise = [
        float(by_fold[fold]["pairwise_accuracy"]) for fold in folds
    ]
    fold_mrr = [float(by_fold[fold]["mrr"]) for fold in folds]
    top1_spread = max(fold_top1) - min(fold_top1)
    pairwise_spread = max(fold_pairwise) - min(fold_pairwise)
    fold_drops = {
        fold: max(
            0.0,
            float(np.mean([fold_top1[j] for j in range(3) if j != index]))
            - fold_top1[index],
        )
        for index, fold in enumerate(folds)
    }

    route_top1 = {
        route: float(by_route[route]["reference_top1"])
        for route in decision_routes
    }
    route_pairwise = {
        route: float(by_route[route]["pairwise_accuracy"])
        for route in decision_routes
    }
    top1_route_gap = max(route_top1.values()) - min(route_top1.values())
    pairwise_route_gap = max(route_pairwise.values()) - min(
        route_pairwise.values()
    )
    route_fold_drops: dict[str, float] = {}
    route_fold_top1_values: dict[str, float] = {}
    for fold in folds:
        for route in decision_routes:
            key = f"{fold}|{route}"
            value = float(by_fold_route[key]["reference_top1"])
            route_fold_top1_values[key] = value
            route_fold_drops[key] = max(0.0, route_top1[route] - value)

    hard_gates = {
        "pooled_reference_top1_min": float(pooled["reference_top1"])
        >= float(fold_hard["pooled_reference_top1_min"]),
        "each_fold_reference_top1_min": min(fold_top1)
        >= float(fold_hard["each_fold_reference_top1_min"]),
        "reference_top1_max_fold_spread": top1_spread
        <= float(fold_hard["reference_top1_max_fold_spread"]),
        "pooled_pairwise_accuracy_min": float(pooled["pairwise_accuracy"])
        >= float(fold_hard["pooled_pairwise_accuracy_min"]),
        "each_fold_pairwise_accuracy_min": min(fold_pairwise)
        >= float(fold_hard["each_fold_pairwise_accuracy_min"]),
        "pairwise_accuracy_max_fold_spread": pairwise_spread
        <= float(fold_hard["pairwise_accuracy_max_fold_spread"]),
        "each_fold_mrr_min": min(fold_mrr)
        >= float(fold_hard["each_fold_mrr_min"]),
        "maximum_fold_drop_from_other_two_mean": max(fold_drops.values())
        <= float(fold_hard["maximum_fold_drop_from_other_two_mean"]),
        "each_route_reference_top1_min": min(route_top1.values())
        >= float(route_hard["each_route_reference_top1_min"]),
        "each_route_pairwise_accuracy_min": min(route_pairwise.values())
        >= float(route_hard["each_route_pairwise_accuracy_min"]),
        "reference_top1_max_route_gap": top1_route_gap
        <= float(route_hard["reference_top1_max_route_gap"]),
        "pairwise_accuracy_max_route_gap": pairwise_route_gap
        <= float(route_hard["pairwise_accuracy_max_route_gap"]),
        "each_route_fold_reference_top1_min": min(
            route_fold_top1_values.values()
        )
        >= float(route_hard["each_route_fold_reference_top1_min"]),
        "maximum_route_fold_drop_from_route_oof": max(
            route_fold_drops.values()
        )
        <= float(route_hard["maximum_route_fold_drop_from_route_oof"]),
    }
    flagged_concerns = {
        "reference_top1_fold_spread": top1_spread
        > float(fold_flags["reference_top1_fold_spread_above"]),
        "pairwise_accuracy_fold_spread": pairwise_spread
        > float(fold_flags["pairwise_accuracy_fold_spread_above"]),
        "fold_drop_from_other_two_mean": max(fold_drops.values())
        > float(fold_flags["fold_drop_from_other_two_mean_above"]),
        "reference_top1_route_gap": top1_route_gap
        > float(route_flags["reference_top1_route_gap_above"]),
        "pairwise_accuracy_route_gap": pairwise_route_gap
        > float(route_flags["pairwise_accuracy_route_gap_above"]),
        "route_fold_drop_from_route_oof": max(route_fold_drops.values())
        > float(route_flags["route_fold_drop_from_route_oof_above"]),
    }

    if not all(hard_gates.values()):
        decision = "NO_GO"
    elif any(flagged_concerns.values()):
        decision = "HOLD_GENERALIZATION_CONCERN"
    else:
        decision = "GO_TO_JOINT_SEMANTIC_SHADOW"
    return {
        "decision": decision,
        "hard_gates": hard_gates,
        "flagged_concerns": flagged_concerns,
        "observed": {
            "reference_top1_fold_spread": top1_spread,
            "pairwise_accuracy_fold_spread": pairwise_spread,
            "fold_drop_from_other_two_mean": fold_drops,
            "reference_top1_route_gap": top1_route_gap,
            "pairwise_accuracy_route_gap": pairwise_route_gap,
            "route_fold_drop_from_route_oof": route_fold_drops,
        },
    }
