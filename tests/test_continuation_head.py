import json
from pathlib import Path

import numpy as np
import pytest

from atabey.tracking.continuation_head import (
    evaluate_generalization,
    fit_pairwise_logistic,
    strict_group_metrics,
)

ROOT = Path(__file__).resolve().parents[1]


def _contract():
    return json.loads((ROOT / "tests/fixtures/v22_continuation_head_preregistration.json").read_text(encoding="utf-8-sig"))


def _metric(top1, pairwise, mrr=0.95):
    return {"reference_top1": top1, "pairwise_accuracy": pairwise, "mrr": mrr}


def _inputs(fold_top1=(0.87, 0.88, 0.86), fold_pair=(0.92, 0.93, 0.91), cfar=(0.87, 0.92), components=(0.86, 0.91)):
    by_fold = {str(i): _metric(fold_top1[i - 1], fold_pair[i - 1]) for i in (1, 2, 3)}
    by_route = {
        "cfar_sidelobe/bipartite": _metric(*cfar),
        "components/greedy": _metric(*components),
    }
    by_fold_route = {f"{fold}|{route}": dict(values) for fold in ("1", "2", "3") for route, values in by_route.items()}
    return {"pooled": _metric(0.87, 0.92), "by_fold": by_fold, "by_route": by_route, "by_fold_route": by_fold_route}


def test_pairwise_ranker_learns_reference_preference():
    differences = np.array([[2.0, 0.0], [1.0, 0.2], [1.5, -0.1]])
    fit = fit_pairwise_logistic(differences, np.ones(3), c=1.0)
    assert fit.converged
    assert np.all(differences @ fit.coefficients > 0.0)


def test_strict_ties_fail_top1_and_reduce_rank():
    result = strict_group_metrics(1.0, np.array([1.0, 0.5]), tie_tolerance=1e-12)
    assert result["top1"] is False
    assert result["pairwise_accuracy"] == pytest.approx(0.5)
    assert result["rank"] == 2
    assert result["mrr"] == pytest.approx(0.5)


def test_clean_result_is_go():
    result = evaluate_generalization(**_inputs(), contract=_contract())
    assert result["decision"] == "GO_TO_JOINT_SEMANTIC_SHADOW"
    assert all(result["hard_gates"].values())
    assert not any(result["flagged_concerns"].values())


def test_warning_spread_is_hold():
    result = evaluate_generalization(**_inputs(fold_top1=(0.84, 0.90, 0.88)), contract=_contract())
    assert result["decision"] == "HOLD_GENERALIZATION_CONCERN"
    assert all(result["hard_gates"].values())
    assert result["flagged_concerns"]["reference_top1_fold_spread"]


@pytest.mark.parametrize(("inputs", "gate"), [
    (_inputs(fold_top1=(0.799999999999, 0.88, 0.86)), "each_fold_reference_top1_min"),
    (_inputs(cfar=(0.799999999999, 0.92)), "each_route_reference_top1_min"),
])
def test_failure_is_not_rounded_up(inputs, gate):
    result = evaluate_generalization(**inputs, contract=_contract())
    assert result["decision"] == "NO_GO"
    assert result["hard_gates"][gate] is False
